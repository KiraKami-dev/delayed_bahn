"""Example training script for a Nebius Serverless AI job.

Fine-tunes a small causal LM (distilgpt2 by default) on a tiny inline corpus so
the whole run finishes in a few minutes on one L40S. Swap in your own data /
model; keep this file under 64 KiB (it is injected into the container).

Outputs go to $NEBIUS_OUTPUT_DIR when a bucket is mounted at /outputs
(NEBIUS_OUTPUT_VOLUME in .env or --output on the CLI), else to ./out inside
the container disk, which is discarded when the job ends.
"""
import argparse
import json
import os
import time

import torch


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.environ.get("MODEL_NAME", "distilgpt2"))
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--max-steps", type=int, default=50)
    args = p.parse_args()

    out_dir = os.environ.get("NEBIUS_OUTPUT_DIR", "./out")
    os.makedirs(out_dir, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} gpu={torch.cuda.get_device_name(0) if device == 'cuda' else '-'} torch={torch.__version__}", flush=True)

    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.model)
    tok.pad_token = tok.pad_token or tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model).to(device)

    corpus = [
        "Temporal reasoning means ordering events and understanding durations.",
        "A workflow retries a failed activity until it succeeds or times out.",
        "The model learns to predict the next token from context.",
        "Serverless jobs release their GPU when the container exits.",
    ] * 32
    enc = tok(corpus, return_tensors="pt", padding=True, truncation=True, max_length=48)
    ds = torch.utils.data.TensorDataset(enc["input_ids"], enc["attention_mask"])
    dl = torch.utils.data.DataLoader(ds, batch_size=args.batch_size, shuffle=True)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    model.train()
    step, t0, history = 0, time.time(), []
    for epoch in range(args.epochs):
        for input_ids, attn in dl:
            input_ids, attn = input_ids.to(device), attn.to(device)
            loss = model(input_ids=input_ids, attention_mask=attn, labels=input_ids).loss
            loss.backward()
            opt.step()
            opt.zero_grad()
            step += 1
            history.append({"step": step, "loss": round(loss.item(), 4)})
            if step % 10 == 0:
                print(f"epoch={epoch} step={step} loss={loss.item():.4f} elapsed={time.time() - t0:.0f}s", flush=True)
            if step >= args.max_steps:
                break
        if step >= args.max_steps:
            break

    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    with open(os.path.join(out_dir, "train_history.json"), "w") as f:
        json.dump({"args": vars(args), "steps": history, "seconds": time.time() - t0}, f, indent=2)
    print(f"saved model + history to {out_dir}", flush=True)


if __name__ == "__main__":
    main()
