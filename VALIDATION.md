# Oval Ghost V9.1 — Validation record

## Candidate status

V9.1 is unscored. Current reported best remains V8 at 2.92.

## Official conformance check

Command:

```bash
python3 /path/to/mechfight-kit/check/check.py --map-dir /mnt/data/arena_local/arena -- python3 -u bot.py
```

Latest local result:

- PASS
- 300/300 observations answered
- 0 missed 50 ms deadlines
- 0 wrong ticks
- 0 bad protocol lines
- 0 over-cap debug drawings
- p50 1.7 ms, p90 2.3 ms, p99 3.0 ms, max 43.8 ms (single local machine; not the 1-CPU Docker sandbox)

## Real-map integrated tests

```bash
MECHFIGHT_ARENA=/mnt/data/arena_local/arena python3 -m unittest test_v9_integrated.py -v
```

- 8/8 passed
- Uses actual V8 bot geometry, 259 prisms, 1,560 trees and 774,680 terrain samples
- Integrated steering stress: p50 5.286 ms, max 12.860 ms in this run

## Gemini reference tests

```bash
MECHFIGHT_ARENA=/mnt/data/arena_local/arena python3 -m unittest test_v9_reference.py -v
```

- 4/4 passed
- Its mock bot stubs collision, terrain-clearance and ray-blocking methods; these are supplementary algorithm tests, not proof of real navigation geometry.

## Added tactical helper tests

```bash
python3 -m unittest test_v9_tactical.py -v
```

- 5/5 passed
- Covers safe supply-drop selection, contested/held drop rejection, next-zone check, optional-fire suppression, and stale defensive-bearing rejection.

## Limitations

- No Docker binary was available; exact 1 CPU / 512 MB / read-only container run is not reproduced.
- No scored 48-match result exists yet.
- Rooftop reachability remains advisory, not a full jet-assisted navigation planner.
- The official checker does not simulate action consequences.
