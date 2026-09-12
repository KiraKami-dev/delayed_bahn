# MCP Setup

All MCP servers are optional; none is required for bootstrap or shared memory.
Enable only a server with an immediate use case. `.mcp.json` ships definitions
for the four servers below. Each person approves and authenticates only the
ones they need; cloning does not establish a connection.

## Shared definitions

1. **Context7** — live documentation for unfamiliar libraries and partner SDKs.
2. **GitHub** — repository issues and pull requests from the agent.
3. **Serena** — symbol-level code navigation across the product's features.
4. **Playwright** — visible-surface smoke checks and browser automation.

Notes, decisions and status remain in the dashboard and repository files.
No external note-taking or voiceover service is assumed by the template.

## Additional opt-in tools

- **Graphify** — a vendored skill for building and querying knowledge graphs
  from code and documents. The CLI is a separate `graphifyy` installation;
  vendoring the skill does not install it. Review and install a suitable
  version in an isolated environment only when requested. Once configured,
  `graphify --mcp` is the optional MCP command. It is deliberately absent from
  the shared `.mcp.json`, so teammates without it do not get startup failures.
  Code parsing can be local; document/semantic processing may use models or
  external services. Review the selected workflow before sending any data.
- **Higgsfield** — optional image/video-generation tooling for demo assets.
  It is not vendored, installed by bootstrap, or enabled in `.mcp.json`.
  Follow the provider's current CLI setup for `@higgsfield/cli`, authenticate
  individually, and keep account-specific configuration local. Check costs
  and data handling before using generation features.

These tools are not prerequisites for the demo or for using the new skills.
The optional OpenMontage workflow is described in `pitch-and-demo.md`.

## Authentication and harness setup

- **Claude Code:** review the project-scoped definitions in `.mcp.json` and
  approve only the servers needed for the current work.
- **Codex:** configure equivalent servers using Codex's own supported MCP
  configuration. A Claude project definition does not configure Codex.
- **Other harnesses:** use their native local MCP configuration; shared skill
  content remains available under `.agents/skills/`.
- Authentication and API keys are per-person. Keep tokens and account-specific
  endpoints out of Git. Bootstrap does not authenticate external services.
- Set up optional services before the event. Missing tools should not delay
  the local dashboard, shared markdown workflow, or core smoke checks.
