# Validation

## Official conformance checker

Run against the supplied `check/check.py` and the kit's 300-observation recorded stream:

- Observations answered: 300/300
- Missed 50 ms deadlines: 0
- Wrong ticks: 0
- Invalid protocol lines: 0
- Debug drawings over limits: 0
- Response time on this machine: p50 1.1 ms, p90 1.7 ms, p99 2.3 ms, max 4.0 ms
- Result: PASS

## Same-input action comparison with V1

On the same 300 recorded observations:

- `move`, `boost`, `jump`, `fire`, `reload`, `take`, and `pick` matched V1 exactly.
- `aim` differed on 61 observations because V5 retains recent sound/damage bearings for threat awareness.
- The recorded stream did not trigger the conditional cover or recovery behaviours, so this replay does not validate those strategic additions.

## Limits

This is not a game simulation. The observation stream does not react to the bot's actions. No Docker image build was run in this environment. Only an official scored practice match can establish whether V5 improves on V1's 1.94 score.
