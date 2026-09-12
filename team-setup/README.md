# team-setup/

Coordination layer for the hackathon build. Not product code — see `../app/`
for that. One screen, index only.

- **`state/`** — shared memory, inactive while `event.json` has `mode: example`.
  `event.json` contains event configuration; generated records may reference it. `team.json` is the roster. `pipeline.json` is the gate spine.
  `owners.md`, `decisions.md`, `ideas.md`, `research.json`, `partner-notes.md`
  are cross-cutting and span every stage. Numbered folders (`00-`..`06-`)
  hold one gate's outputs each.
- **`board/`** — Python file-backed API plus the Vite/React/shadcn UI in
  `board/web/`. From the repo root, run `npm --prefix team-setup/board/web ci`
  once, then `npm --prefix team-setup/board/web run dev` for both services.
  A built UI is also served by `python3 team-setup/board/serve.py`.
- **`hooks/`** — nonblocking Git warnings and optional local metadata.
  Prompt capture is off by default. Bootstrap preserves unrelated hooks.
- **`prompts/`** — plain markdown prompts, pasteable into any agent harness.
  `.claude/commands/` wraps these for Claude Code slash commands.
- **`playbooks/`** — human-facing, read once before the event.
- **`scripts/`** — `new-event.sh`, `snapshot.sh`, `restore.sh`, `smoke.sh`,
  `extract-story.sh`.

Start at the repo root `README.md` if you haven't yet. This folder is what
that README points into.
