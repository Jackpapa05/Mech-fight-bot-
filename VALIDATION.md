# V6 validation

## Official conformance checker

Run against the supplied `check/check.py` and its 300-observation stream, with the provided map mounted at the local equivalent of `/arena`:

- Observations answered: 300/300
- Missed 50 ms deadlines: 0
- Wrong ticks: 0
- Invalid protocol lines: 0
- Debug drawings over limits: 0
- Response time on this machine: p50 0.6 ms, p90 1.2 ms, p99 1.7 ms, max 1.9 ms
- Result: PASS

Docker image build was not run because Docker is unavailable in this execution environment.

## Same-input comparison with V5

Both versions were run against the same 300 recorded observations:

| Behaviour | V5 | V6 |
|---|---:|---:|
| Movement commands | 300 | 300 |
| Boost commands | 86 | 93 |
| Gun firing commands | 123 | 123 |
| Secondary firing commands | 0 | 0 |
| Aim changed by >0.02 rad | — | 0 observations |

The supplied replay does not trigger all new behaviours (notably weapon swapping, visible lightning/mortar decisions, and some cover/recovery branches). Matching actions on this stream does not establish a higher match score.

## Additional tests

- Synthetic high-load observation with 16 mechs, 12 NPCs, 50 projectiles, 36 crates, 30 cubes, 40 pickups, 40 sounds, 10 events, and 10 beams: direct `Bot.act` maximum 3.4 ms over 100 repeats on this machine.
- CPA unit test detected a fast gun projectile crossing between the old coarse sampling times.
- Contextual secondary-weapon swap test passed.
- Upgrade-selection time-argument test passed.
- Map/terrain loaded successfully: 259 prisms, terrain grid loaded.
- Spatial-index equivalence: 1,000 collision-point queries and 200 ray queries matched non-indexed scans.

## Important limitations

- This is not an in-game simulation. The official checker observations do not react to bot actions.
- No scored practice result exists for V6 yet.
- The gun projectile model assumes no shooter-velocity inheritance because the protocol specifies projectile speed but does not document inheritance. This should be changed only if the server's actual projectile physics can be confirmed.
- Line-of-sight and ballistic-path tests are geometric approximations; live match results are the deciding evidence.
