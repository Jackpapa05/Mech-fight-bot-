# V8.1.2 validation report

## Official checker

Command:

```bash
python3 check/check.py --map-dir /mnt/data/arena_extracted/arena -- python3 -u bot.py
```

Result: **PASS**

- Observations: 300 / 300
- Missed 50 ms deadlines: 0
- Wrong ticks: 0
- Invalid protocol lines: 0
- Local timing: p50 0.7 ms / p90 1.3 ms / p99 1.8 ms / max 2.6 ms

## Regression tests

`ARENA_DIR=/mnt/data/arena_extracted/arena ./run_tests.sh`

Result: **19 / 19 PASS**.

Coverage includes third-party beam filtering and lightning polylines, zone waypoint safety and obstacle fallback, supply-drop stability/guards, mortar terrain and wall impact, target scoring, and laser range selection.

## Additional stress test

`_incoming_threat` called with 40 simulated mortar projectiles over 120 runs on the actual loaded OSU map:

- p50: 6.019 ms
- p90: 6.447 ms
- p99: 12.322 ms
- max: 14.481 ms

This is a targeted local stress scenario, not a full-agent worst-case guarantee.

## Caveats

- Measurements are from this machine, not the competition's exact 1-CPU / 512 MB Docker sandbox.
- Docker is unavailable in this environment, so image build and sandbox timing were not verified locally.
- `check.py` is a protocol/timing conformance test, not a gameplay simulation.
- V8.1.2 has not received a scored practice run. V8 remains the best-scoring verified version at 2.92 until a higher score is returned.
