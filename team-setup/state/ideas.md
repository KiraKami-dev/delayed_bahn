# Ideas

Pre-decision brainstorm log. See AGENTS.md rule 6 / spec 4.1c.

Format:
`- [T+HH:MM] <idea> — <raised by> — status: <raised|exploring|adopted|discarded>`

- [i-0d84fe9a184e4804a2844ba77fbafee8] [T+06:06] Model per station instead of per train number — per train number fractures the data too much; check whether it beats looking at connections separately — Claude Code analysis via team — status: exploring
- [i-7c98338748134ca895dd736a3d6c1c51] [T+06:06] Feed the previous and next train's delay in as input: if the first train is 10 min late the connecting train probably also has delay (series of delays) — team — status: raised
- [i-4231d348c1d04f20926620f759d200bc] [T+06:06] (3D) map view: type from → to, it visualises and zooms in, then shows the probability of making it; first version just shows delays — team — status: raised
- [i-b131c9f9c2014d63a15e485c85cd270b] [T+06:06] Level 3: give the causes / possibility of a disaster happening — a scientific evaluation, not a feature — team — status: raised
- [i-394c6dd8fa92481fad97a5dc9451ad6c] [T+06:06] Register several API client IDs / secrets to get past the 60 requests per minute limit — team — status: raised
- [i-0bafcc879cae4dedb516fa594995754c] [T+06:06] Shared DB text sometimes contains more than one connection: use a grammar to find which one / where the information is; maybe turn the text into a URL — team — status: exploring
- [i-cb3693fed13a47eca49a97654efcedb1] [T+06:06] Check whether push notifications work in the PWA — team — status: exploring
- [i-c602e8a339be48beb175d92b9ac2d6ec] [T+06:06] Agentic workflow for the data pipeline (bonus points) — team — status: exploring
