# Timeline

`submit_target = submission_deadline + submit_target_offset_hours`.
The offset defaults to -2 hours. The planning window is **build start to
submit target**, not build start to the advertised deadline. All gate and
task percentages use this same window; timezone-aware timestamps prevent
machines in different zones from showing different deadlines.

| Stage | % of planning window | Exit condition |
|---|---|---|
| reveal-capture | before build; before event if tracks published | real reveal files and rubric |
| challenge-pick | before build | accepted challenge decision |
| demo-script | 0–3% | demo and explicit exclusions |
| contract-freeze | 3–7% | real contract, mocks and architecture |
| parallel-build | 7–55% | happy path connected |
| integration | 55–65% | merged demo and smoke pass |
| feature-freeze | 65% | no new features |
| polish-and-pitch | 65–90% | pitch, demo rehearsal, backup recording |
| buffer | 90–100% | submit; no new build work |

For a 12-hour advertised window and a -2-hour target: planning lasts 10 hours,
polish ends at hour 9, buffer ends at hour 10. For 48 hours: planning lasts
46 hours, polish ends at hour 41.4, buffer ends at hour 46. Neither schedule
runs required work past the early submission target.

Blank dates are allowed; the dashboard asks for configuration rather than
inventing countdowns. Invalid ordering or missing timezone offsets produces
a warning and unresolved times. Use one explicit offset per timestamp.

The sleep rota records per-person coverage; it does not magically turn sleep
into productive capacity. Pick realistic task targets around onboarding,
meals and sleep. No universal rule requires the whole team to remain awake.
Protect the presentation and submission buffers rather than reclaiming them.
