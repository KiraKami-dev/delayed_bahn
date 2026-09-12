# Pitch — seed (write in parallel with the build)

**Owner:** unassigned — see task "Write the pitch" on the board.

## Storyline
- Hook: "I was too frustrated to come to Zurich." One real route, our biggest trouble with Deutsche Bahn: `<ROUTE>`.
- The failure: delays chain. Train 1 is 5 min late, you still catch train 2, the delay is now 15 min, you miss train 3. Half an hour of buffer did not help.
- The insight: predict each train's delay separately, chain them, and give one number: the probability your plan fails.
- The product: press Share in the DB app, share to our PWA, get the number and what to do. We build on top of DB, we are not replacing it.
- The advice principle: the least stressful journey, not the fastest. Weather-forecast analogy: not "it will rain", but "take an umbrella". It can also say "this connection is good".
- The proof: fine-tuned 0.5B / 3B model vs the given baseline (raw data into GPT / Claude Opus) on Oct→Aug data for the route.
- What's next: causes (level 3), series of delays, map view.

## Still needed
- Route name, real numbers from the evaluation, one chart.
- Time check against `event.json` pitch length once known.
