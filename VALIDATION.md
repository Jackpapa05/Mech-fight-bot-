# V7 validation record

## Official checker

Command:

```sh
python3 check/check.py --map-dir /path/to/mechfight-kit/arena -- python3 -u bot.py
```

Result on the supplied 300-observation recording:

- 300 / 300 observations answered
- 0 missed 50 ms deadlines
- 0 late answers
- 0 wrong ticks
- 0 malformed protocol lines
- 0 debug-cap violations
- Local response time: p50 0.6 ms, p90 1.2 ms, p99 1.7 ms, max 1.8 ms
- Result: PASS

These timings are from the current execution environment, not the official Docker sandbox.

## Focused regression tests

`python3 test_v7.py`:

- Long-range mortar flight time is no longer truncated at 2.5 s.
- Moving-target mortar lead and returned range are internally consistent.
- Spatial-bin indexing returns a prism close to a query for a large-radius mech.
- Laser charge does not start when the target ray is blocked.

Result: 4 tests passed.

## Synthetic stress check

A local 100-tick synthetic observation stress run included 15 visible mechs, 12 NPCs, 50 projectiles, recent combat sounds, and a damage event:

- p50: 3.551 ms
- p90: 3.693 ms
- p99: 3.961 ms
- max: 4.123 ms

This is a synthetic local benchmark, not a guarantee for every match observation or hardware environment.

## Not yet verified

- V7 has not yet received a scored 48-match practice result.
- Docker image build/run was not tested here because Docker is unavailable in this environment.
- Shooter-velocity inheritance for gun projectiles remains unverified by the protocol. V7 retains V6's internally consistent world-velocity assumption pending an empirical match observation.
