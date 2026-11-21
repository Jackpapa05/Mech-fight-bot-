# V8 validation record

## Reported competitive baseline

The team reports V7 scored **2.71** in the 48-match practice evaluation. V7 remains the best-known scored build until another scored result exceeds 2.71.

## Official conformance check

Command:

```sh
python3 check/check.py --map-dir /path/to/mechfight-kit/arena -- python3 -u bot.py
```

Result in this environment:

- 300 / 300 observations answered
- 0 missed 50 ms deadlines
- 0 late answers
- 0 wrong ticks
- 0 malformed protocol lines
- 0 debug-cap violations
- Response time: p50 0.6 ms, p90 1.3 ms, p99 1.9 ms, max 6.3 ms
- Result: PASS

These are local measurements, not the official Docker sandbox's timing.

## Focused regression tests

`python3 test_v8.py`:

- Reproduces a mortar path with an actual 8.95 m closest approach against a 9.0 m danger threshold; V7's coarse-sample distance misses it, V8's refined-distance recomputation detects it.
- Confirms straight bullets whose trajectory is blocked by a solid/terrain ray do not trigger a dodge.
- Confirms visible beam source records shooter ID and direction.
- Confirms an older sound does not overwrite a newer beam threat.

Result: 4 tests passed.

## Synthetic stress test

A local 150-tick stress harness with 15 visible mechs, 12 NPCs, 50 projectiles, 12 sounds, and 8 beams measured:

- p50: 0.178 ms
- p90: 0.234 ms
- p99: 0.297 ms
- max: 0.364 ms

This was a Python `act()` microbenchmark using synthetic observations and the local map, not a full Docker run.

## Not yet verified

- V8 has not received a 48-match practice score.
- Docker build/run was not performed because Docker is unavailable in this environment.
- Gun-projectile shooter-velocity inheritance remains unspecified by the protocol and unverified empirically; V8 keeps V7's current internally consistent assumption.
- Projectile occlusion uses a straight ray for gun/NPC bullets. It is intentionally not applied to ballistic mortars.

## V7 vs V8 action comparison on the supplied 300-observation replay

Both bots were run sequentially over the same observations with their own persistent state. Results:

- Observations containing beams: 5 / 300
- Projectiles in the replay: 30 gun projectiles; no mortar projectiles
- Different movement commands: 0
- Different boost commands: 0
- Different fire commands: 0
- Different jump commands: 0
- Different aim commands: 1

This is useful for confirming that the narrow patch does not broadly alter V7's recorded behaviour. It also means the supplied replay does **not** exercise the mortar-CPA fix, and scored games are needed to determine whether the new handling improves placements.
