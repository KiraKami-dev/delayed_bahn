"""Load the OpenTSLM 3B soft-prompt checkpoint on the ungated Llama-3.2-3B mirror."""

import torch
from huggingface_hub import hf_hub_download
from opentslm.model.llm.OpenTSLMSP import OpenTSLMSP

BASE = "unsloth/Llama-3.2-3B"  # same safetensors SHA-256 as meta-llama/Llama-3.2-3B
CHECKPOINT = "OpenTSLM/llama-3.2-3b-m4-sp"

model = OpenTSLMSP(llm_id=BASE, device="cuda")
path = hf_hub_download(CHECKPOINT, "model_checkpoint.pt")
state = torch.load(path, map_location="cpu", weights_only=False)
print("checkpoint top-level keys:", list(state)[:10] if isinstance(state, dict) else type(state))
model.load_from_file(path)
model.eval()
tok = model.tokenizer
print("eos:", tok.eos_token, tok.eos_token_id, "pad:", tok.pad_token, tok.pad_token_id, "side:", tok.padding_side)
print("trainable params:", sum(p.numel() for p in model.parameters() if p.requires_grad))
print("gpu mem GB:", round(torch.cuda.max_memory_allocated() / 1e9, 1))
print("LOAD OK")
