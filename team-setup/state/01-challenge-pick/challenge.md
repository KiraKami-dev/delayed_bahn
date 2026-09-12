<!-- Chosen track + problem statement (verbatim). Frozen once written. -->

# Challenge pick — Temporal AI track

**Event:** Temporal AI hackathon, EHL Zurich, 12–13 Sep 2026
**Track:** Temporal AI
**Picked:** Sat 12 Sep 2026, team discussion (see `state/meetings/2026-09-12-team-discussion.md`)
**Decision:** locked — see `decisions.md`. No reopening.

## Problem we are solving

Deutsche Bahn (DB) journeys with connections fail because delays chain:
train 1 is 5 min late, you still catch train 2, the overall delay grows to
15 min, you miss train 3. Travellers get raw delay data, not a decision.

## What we build

1. **Core — delay prediction.** A fine-tuned small model (0.5B / 3B) that
   predicts the delay of **each train separately**, chained across the
   journey, and outputs the **probability that the plan fails** (missed
   connection / not arriving in time). Inference on the backend, not on
   the phone (model is ~10 GB).
2. **Recommendation — separate algorithm on top.** Turns the delay
   estimate into what to do: how much buffer to plan, whether a more
   reliable route exists, how early to come, what to do next if a train is
   cancelled. Principle: the least stressful journey, not the fastest.
   Weather-forecast analogy: not "it will rain" but "take an umbrella".
   It must also be able to say "this connection is good".
3. **Level 3 — causes.** Scientific evaluation of the causes / probability
   of a disaster. Not a feature; comes after 1 and 2.

## Product surface

A **PWA** (installable web app). Entry point: press **Share** in the DB app,
share the raw text to our app, we extract the journey and return the
probability plus recommendation. "We are building on top of DB — we are
not making an exchange just because they are bad."

## Baseline (given by the track)

Raw data pasted, not fine-tuned, into GPT / Claude Opus. If our fine-tuned
0.5B or 3B model beats that, that is the result.

## Storyline

One route: our biggest trouble with Deutsche Bahn ("too frustrated to come
to Zurich"). Training data and the demo are built for that route. The
route itself is still to be picked — task on the board.

## Organiser problem statement (verbatim)

_Not captured yet — paste the organiser's exact text here when available.
Nothing above is a substitute for it._
