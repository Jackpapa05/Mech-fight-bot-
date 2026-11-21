# V9.2 validation log

## Official checker

Command:

```bash
python3 /path/to/mechfight-kit/check/check.py --map-dir /path/to/arena -- python3 -u bot.py
```

Result on the available local runtime:

- 300 observations processed
- 300 answers in time
- 0 late answers
- 0 stale/incorrect ticks
- 0 bad lines
- 0 debug drawing cap violations
- p50 1.2 ms; p90 1.8 ms; p99 2.6 ms; max 3.2 ms
- PASS

## Unit / integration tests

```bash
MECHFIGHT_ARENA=/path/to/arena python3 -m unittest \
  test_v9_integrated.py test_v9_reference.py test_v9_tactical.py test_v9_2.py -v
```

Result: **23 tests passed**.

## Real-map navigation measurements

- Static graph build: approximately 0.40–0.46 s.
- Walkable cells: 2,120.
- Directed edges: 12,920.
- Long-route cached-graph A* max: approximately 1.4 ms.

## Full action stress test

Synthetic observation: 15 mechs, 40 projectiles, beams, sounds, repeated stationary/stagnation condition. 100 `Bot.act()` calls:

- p50: 5.99 ms
- p90: 6.48 ms
- p99: 10.06 ms
- max: 11.96 ms

## Important limits

These are local measurements, not a Docker sandbox guarantee. No gameplay score has been measured. The official conformance checker does not simulate the results of actions.
