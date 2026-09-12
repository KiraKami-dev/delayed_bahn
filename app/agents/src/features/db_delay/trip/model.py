"""Trip delay TSLM: OpenTSLM's soft-prompt model answering with a distribution over minutes.

The answer ends in ``Answer: <minutes>`` or ``Answer: cancelled``. After the colon
the model chooses between the space token (a number follows) and ``Ġcancelled``;
after the space it chooses one of the single-token integers 0..999. One forward
pass over the rationale therefore yields P(cancelled) and the full minute
distribution.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from huggingface_hub import hf_hub_download
from opentslm.model.llm.OpenTSLMSP import OpenTSLMSP
from torch.nn.utils.rnn import pad_sequence

BASE_LLM = "unsloth/Llama-3.2-3B"  # same safetensors as meta-llama/Llama-3.2-3B, ungated
START_CHECKPOINT = "OpenTSLM/llama-3.2-3b-m4-sp"
MAX_MINUTES = 999
LOSS_MODES = ("soft_crps", "plain", "plain_crps")  # plain_crps: exact-minute cross-entropy plus the CRPS term


class TripTSLM(OpenTSLMSP):
    """OpenTSLM-SP with right padding, a minute-aware loss and a distribution readout."""

    def __init__(self, llm_id: str = BASE_LLM, device: str = "cuda", loss_mode: str = "soft_crps",
                 crps_weight: float = 0.1, soft_width: tuple[float, float] = (1.0, 0.1)):
        if loss_mode not in LOSS_MODES:
            raise ValueError(f"loss_mode must be one of {LOSS_MODES}")
        super().__init__(llm_id=llm_id, device=device)
        # OpenTSLM loads with eager attention, which stores every attention matrix for the
        # backward pass. SDPA gives the same result without that memory.
        try:
            self.llm.set_attn_implementation("sdpa")
        except (AttributeError, ValueError) as error:
            print(f"keeping eager attention: {error}")
        tok = self.tokenizer
        # pad_and_apply_batch keeps the first N tokens of every text segment, which is only
        # correct with right padding. The mirror's tokenizer ships with left padding.
        tok.padding_side = "right"
        tok.pad_token = tok.eos_token  # as in the OpenTSLM checkpoints, whose tokenizer had no pad token
        self.loss_mode = loss_mode
        self.crps_weight = crps_weight
        self.soft_width = soft_width
        minute_ids = [tok.convert_tokens_to_ids(str(m)) for m in range(MAX_MINUTES + 1)]
        self.space_id = tok.convert_tokens_to_ids("Ġ")
        self.cancel_id = tok.convert_tokens_to_ids("Ġcancelled")
        known = [i for i in minute_ids + [self.space_id, self.cancel_id] if i is not None and i != tok.unk_token_id]
        if len(known) != MAX_MINUTES + 3 or len(set(minute_ids)) != MAX_MINUTES + 1:
            raise ValueError("tokenizer lacks single tokens for 0..999, the space or 'Ġcancelled'")
        self.minute_ids = torch.tensor(minute_ids, device=device)
        self.id_to_minute = {token: minute for minute, token in enumerate(minute_ids)}
        self.minutes = torch.arange(MAX_MINUTES + 1, device=device, dtype=torch.float32)
        self.last_parts: dict[str, float] = {}

    @classmethod
    def from_opentslm_checkpoint(cls, repo: str = START_CHECKPOINT, **kwargs) -> TripTSLM:
        """Build on the base model and load a published OpenTSLM encoder, projector and LoRA adapters.

        Later curriculum stages such as ``ecg-sp`` ship LoRA adapters, and OpenTSLM only loads
        those into a model whose LoRA is already enabled, so enable it first in that case.
        """
        model = cls(**kwargs)
        path = hf_hub_download(repo, "model_checkpoint.pt")
        if torch.load(path, map_location="cpu", weights_only=False).get("lora_enabled"):
            model.enable_lora()
        model.load_from_file(path)
        return model

    def encode(self, text: str) -> list[int]:
        """Token ids of a continuation, without special tokens."""
        return self.tokenizer.encode(text, add_special_tokens=False)

    def _assemble(self, batch: list[dict], continuations: list[list[int]], left_pad: bool = False):
        """Prompt embeddings followed by continuation tokens, padded only at one end."""
        prompt_embeds, prompt_mask = self.pad_and_apply_batch(batch)
        lengths = prompt_mask.sum(dim=1).tolist()
        embed = self.llm.get_input_embeddings()
        seqs, starts = [], []
        for i, ids in enumerate(continuations):
            n = int(lengths[i])
            parts = [prompt_embeds[i, :n]]
            if ids:
                parts.append(embed(torch.tensor(ids, device=self.device)).to(prompt_embeds.dtype))
            seqs.append(torch.cat(parts, dim=0))
            starts.append(n)
        total = max(s.size(0) for s in seqs)
        hidden = prompt_embeds.size(-1)
        embeds = prompt_embeds.new_zeros(len(seqs), total, hidden)
        mask = torch.zeros(len(seqs), total, dtype=torch.long, device=self.device)
        offsets = []
        for i, seq in enumerate(seqs):
            offset = total - seq.size(0) if left_pad else 0
            embeds[i, offset:offset + seq.size(0)] = seq
            mask[i, offset:offset + seq.size(0)] = 1
            offsets.append(offset)
        return embeds, mask, [s + o for s, o in zip(starts, offsets)]

    def _hidden_and_head(self, embeds: torch.Tensor, mask: torch.Tensor):
        """Final hidden states and the output layer, so logits are computed only where needed.

        Full logits cost batch x length x 128k vocabulary entries, which alone nearly fills
        the GPU. LoRA layers live inside the backbone, so skipping the wrapper keeps them.
        """
        base = self.llm.get_base_model() if hasattr(self.llm, "get_base_model") else self.llm
        hidden = base.model(inputs_embeds=embeds, attention_mask=mask, return_dict=True).last_hidden_state
        return hidden, base.lm_head

    def compute_loss(self, batch: list[dict]) -> torch.Tensor:
        """Cross-entropy on the rationale; soft targets plus CRPS at the minute token."""
        eos = self.tokenizer.eos_token_id
        answers = [self.encode(sample["answer"]) + [eos] for sample in batch]
        embeds, mask, starts = self._assemble(batch, answers)
        hidden, head = self._hidden_and_head(embeds, mask)

        rows, cols, targets = [], [], []
        num_rows, num_cols, num_targets = [], [], []
        for i, ids in enumerate(answers):
            cancelled = ids[-2] == self.cancel_id
            if not cancelled and (ids[-3] != self.space_id or ids[-2] not in self.id_to_minute):
                raise ValueError(f"answer does not end in 'Answer: <minutes>': {self.tokenizer.decode(ids[-6:])!r}")
            for j, token in enumerate(ids):
                col = starts[i] + j - 1  # logits at a position predict the next token
                minute_position = not cancelled and j == len(ids) - 2
                if minute_position and self.loss_mode != "plain":
                    num_rows.append(i)
                    num_cols.append(col)
                    num_targets.append(self.id_to_minute[token])
                if not (minute_position and self.loss_mode == "soft_crps"):
                    # soft_crps replaces the token loss at the minute; plain_crps keeps it and adds CRPS
                    rows.append(i)
                    cols.append(col)
                    targets.append(token)
        device = self.device
        token_logits = head(hidden[torch.tensor(rows, device=device), torch.tensor(cols, device=device)]).float()
        token_loss = F.cross_entropy(token_logits, torch.tensor(targets, device=device))
        loss = token_loss
        parts = {"token_ce": token_loss.item()}
        if num_rows:
            selected = head(hidden[torch.tensor(num_rows, device=device), torch.tensor(num_cols, device=device)]).float()
            minute_logits = selected[:, self.minute_ids]
            log_probs = F.log_softmax(selected, dim=-1)[:, self.minute_ids]
            y = torch.tensor(num_targets, device=device, dtype=torch.float32)[:, None]
            cdf = torch.softmax(minute_logits, dim=-1).cumsum(dim=-1)
            crps = ((cdf - (self.minutes[None] >= y).float()) ** 2).sum(dim=-1).mean()
            loss = loss + self.crps_weight * crps
            parts |= {"crps": crps.item()}
            if self.loss_mode == "soft_crps":
                width = self.soft_width[0] + self.soft_width[1] * y
                soft = torch.softmax(-(self.minutes[None] - y).abs() / width, dim=-1)
                soft_ce = -(soft * log_probs).sum(dim=-1).mean()
                loss = loss + soft_ce
                parts |= {"soft_ce": soft_ce.item()}
        self.last_parts = parts
        return loss

    @torch.no_grad()
    def predict_distribution(self, batch: list[dict]) -> dict[str, torch.Tensor]:
        """P(cancelled) and the minute distribution, reading after a teacher-forced rationale."""
        prefixes = [self.encode(sample["prefix"]) + [self.space_id] for sample in batch]
        embeds, mask, starts = self._assemble(batch, prefixes)
        hidden, head = self._hidden_and_head(embeds, mask)
        rows = torch.arange(len(batch), device=self.device)
        space_pos = torch.tensor([starts[i] + len(p) - 1 for i, p in enumerate(prefixes)], device=self.device)
        decide = torch.softmax(head(hidden[rows, space_pos - 1]).float(), dim=-1)
        p_space, p_cancel = decide[:, self.space_id], decide[:, self.cancel_id]
        minute = torch.softmax(head(hidden[rows, space_pos]).float(), dim=-1)[:, self.minute_ids]
        return {
            "probs": minute / minute.sum(dim=-1, keepdim=True),
            "p_cancel": p_cancel / (p_space + p_cancel),
            "leak_decide": 1 - p_space - p_cancel,
            "leak_minute": 1 - minute.sum(dim=-1),
        }

    @torch.no_grad()
    def generate_answers(self, batch: list[dict], max_new_tokens: int = 200) -> list[str]:
        """Free generation of rationale and answer, left-padded so every row continues from its own end."""
        embeds, mask, _ = self._assemble(batch, [[] for _ in batch], left_pad=True)
        ids = self.llm.generate(inputs_embeds=embeds, attention_mask=mask, max_new_tokens=max_new_tokens,
                                do_sample=False, pad_token_id=self.tokenizer.eos_token_id)
        return self.tokenizer.batch_decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
