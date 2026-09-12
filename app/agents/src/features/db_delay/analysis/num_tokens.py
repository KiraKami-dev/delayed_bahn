"""Number tokens in Llama 3.2: standard vocab ids, answer formats, and pretrained numeric proximity."""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

tok = AutoTokenizer.from_pretrained("unsloth/Llama-3.2-3B")
ids = [tok.convert_tokens_to_ids(str(n)) for n in range(1000)]
print("vocab size:", len(tok))
print("ids of 0, 1, 8, 9, 10, 99, 100, 999:", [ids[n] for n in (0, 1, 8, 9, 10, 99, 100, 999)])
print("0..999 contiguous ids:", ids == list(range(ids[0], ids[0] + 1000)), "all known:", tok.unk_token_id not in ids)
for text in ("Answer: cancelled", "Answer:cancelled", "Answer: Cancelled", "Answer: 0", "Answer: 999"):
    print(repr(text), "->", tok.tokenize(text))

model = AutoModelForCausalLM.from_pretrained("unsloth/Llama-3.2-3B", dtype=torch.bfloat16)
weights = model.get_output_embeddings().weight.float()
emb = torch.nn.functional.normalize(weights[ids], dim=1)
sim = emb @ emb.T
print("\ncosine similarity of pretrained output embeddings:")
for a, b in ((8, 9), (8, 10), (8, 20), (8, 80), (8, 500), (100, 101), (100, 900)):
    print(f"  {a} vs {b}: {sim[a, b]:.3f}")
print("mean similarity by numeric distance, over 0..120:")
for dist in (1, 2, 5, 10, 30, 100, 300):
    print(f"  distance {dist:3d}: {float(torch.stack([sim[i, i + dist] for i in range(121)]).mean()):.3f}")
