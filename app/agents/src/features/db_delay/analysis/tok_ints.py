"""Are integer minutes single tokens in the Llama 3.2 tokenizer?"""

from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained("unsloth/Llama-3.2-3B")
for fmt in ("{}", " {}"):
    multi = [n for n in range(1000) if len(tok.encode(fmt.format(n), add_special_tokens=False)) != 1]
    print(f"format {fmt!r}: {len(multi)} of 0..999 are not a single token, e.g. {multi[:8]}")
for text in ("Answer: 8", "Answer: 123", "Answer: 1234", "Answer:8", "Answer: -3", "Answer: cancelled"):
    print(repr(text), "->", tok.tokenize(text))
