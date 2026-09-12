# Decisions

Append-only decision log. Never rewrite an existing line. See AGENTS.md
rule 7 for the supersede convention.

Format:
`- [T+HH:MM] <decision> — <who decided> — <one-line reason>`

- [d-020b45fffbfa4944bcbeab4fdeb94920] [T+06:06] Track picked: Temporal AI. Problem: predict Deutsche Bahn delays per train, chained across a journey, and output the probability that the traveller's plan fails — team — biggest real pain with DB; one route becomes storyline, training data and demo
- [d-40e4d3c0fdda4369b9de4e812dddc398] [T+06:06] Core model predicts the delay of each train separately, not one delay for the whole journey; delays are chained across the journey afterwards — team — per-journey prediction hides where the connection breaks
- [d-0f4b8420f4b049fca9ec870a0beff5da] [T+06:06] Work is split in two: (1) delay probability estimation is the core; (2) recommendations are a completely separate algorithm built on top, only after the core works — team — the main core thing is only about predicting the delays
- [d-b0ac7d7a2f22470f852d1de5e7765563] [T+06:06] Build order is fixed: core delay prediction → recommendation algorithm → level 3 causes (scientific evaluation, not a shipped feature) — team — level by level; each layer needs the previous one
- [d-89d11bd8aedf45c69b737483f4b27ada] [T+06:06] Inference runs on the backend; the web app calls it. No on-device model — team — model is ~10 GB, no sense on the phone
- [d-6725e837b7b04d6f8f36eb5dc64c81d6] [T+06:06] Training data window is October 2025 to August 2026 (~8 months, ~10–20 GB), trained on the storyline route — team — data format changed in October; smaller window is probably enough and fits the GPU time
- [d-ee6a60cf528e43dc947bcc502899496d] [T+06:06] Baseline is the given one: raw data pasted, not fine-tuned, into GPT / Claude Opus; success is the fine-tuned 0.5B or 3B model beating it — team — the track gives this baseline
- [d-c5b0229b6df548b7aef368e219223598] [T+06:06] Frontend is a PWA (installable web app); no separate Android / iOS builds — team — time constraint; web installs like an app
- [d-ee495c8dfbe544208e9945b448c34890] [T+06:06] Entry point is the DB app Share flow: share the raw connection text to our app, we extract the journey and return the failure probability plus recommendation — team — we build on top of DB, we are not making an exchange just because they are bad
- [d-87f8fa723555480193229a11015dc8df] [T+06:06] Keep the currently working API connection; rate limit is 60 requests per minute per client ID/secret — team — API confirmed working, stick with this
- [d-59fdbe5b63ce48738a1f59151e9af8ae] [T+06:06] Round-one focus is data, training, GPU access and pitch; one person writes the pitch now while the rest builds; regroup around midnight — team — nothing else was missing when asked
- [d-5561ef83780446f79e00952938aaaee5] [T+06:06] Team discussions are audio-recorded and transcribed from now on; the structured record lives in state/meetings/ — team — so decisions are not lost
