# Oval Ghost V7 — P0 correctness patch

V7 is a conservative patch on the V6 agent, which achieved a **2.67 practice score**. It deliberately keeps V6's overall strategy and focuses on specific correctness risks identified during an independent audit. It is an **unscored candidate** until the competition runs its 48-match practice evaluation.

## Changes from V6

1. **Laser line-of-sight gate.** Do not begin a laser charge at a remembered target behind a solid. If a charge is already in progress and the target becomes occluded or disappears, rotate toward a prism-clear upward ray and release only after the torso is aligned with that safe direction. Gun fire in the laser branch is also suppressed when the target ray is blocked.
2. **Mortar lead convergence.** Iterate target lead, ballistic pitch, and flight time together, recompute pitch at the final predicted target point, and remove the old 2.5 s time cap. The shell TTL from the live config supplies the flight-time bound.
3. **Mortar path validation.** Check the early ballistic arc over the longer solved flight time with adaptive spatial sampling rather than truncating the path at 3 s.
4. **Spatial-bin padding.** Expand prism indexing by 16 m so collision queries still find nearby edges for a large cube-grown mech. This is designed to cover the finite match cube supply (36 crate cubes + 24 NPC cubes + 9 supply-drop cubes + up to 30 kill-bonus cubes = 99 cubes; radius 14.875 m at 99 cubes).
5. **Cover-ray height.** Use terrain height at the candidate cover point, falling back to the current feet height only when no terrain sample is available.
6. **Lightning fallback cleanup.** Remove a duplicate fallback that could bypass the primary lightning branch's range/LOS/energy checks under altered weapon configs.

## Build

```sh
docker build -t oval-ghost-v7 .
```

The Dockerfile uses Python's standard library only and starts `bot.py` with unbuffered output.

## Official conformance check

From the extracted competition kit:

```sh
python3 check/check.py --map-dir /path/to/mechfight-kit/arena -- python3 -u /path/to/oval-ghost-v7/bot.py
```

## Focused regression tests

The included `test_v7.py` uses the official check stream and map. Set the kit directory before running:

```sh
MECHFIGHT_KIT_DIR=/path/to/mechfight-kit python3 test_v7.py
```

`MECHFIGHT_KIT_DIR` should point to the extracted directory containing `check/stream.jsonl.gz` and `arena/`.

## Submission policy

Keep the V6 submission (2.67) as the best-known version unless V7's scored result is higher. Passing `check.py` verifies protocol/timing, not gameplay quality.
