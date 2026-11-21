# Oval Ghost V9 Candidate — Validation

## Baseline

- V8 is the current best-scoring version with a reported practice score of **2.92**.
- V9 is an experimental candidate based on V8. No practice score is claimed for V9.

## Official conformance check

Command used:

```bash
python3 /path/to/mechfight-kit/check/check.py \
  --map-dir /mnt/data/arena_local/arena \
  -- python3 -u bot.py
```

Latest run:

- Result: PASS
- Observations: 300/300
- Missed 50 ms deadlines: 0
- Wrong ticks: 0
- Bad protocol lines: 0
- p50: 1.6 ms
- p90: 2.3 ms
- p99: 2.8 ms
- Max: 44.6 ms (single-machine wall-time outlier; no deadline was missed)

The official checker verifies protocol and runtime behaviour, not match placement. This was not a Docker-sandbox run.

## Integrated real-arena tests

Command:

```bash
MECHFIGHT_ARENA=/path/to/arena python3 -m unittest test_v9_integrated.py -v
```

Result: **8/8 PASS**.

Tests cover:

- Actual 259 prisms, 1,560 trees, and 774,680 terrain samples loaded through the V8 bot.
- Tree crown vision blocking while weapon LOS remains unblocked by trees.
- Third-party beam filtering and near-self beam threat detection.
- Straight projectile occlusion and danger evaluation.
- Mortar early-ground-impact splash response.
- Integrated 24-direction steering stress using real V8 geometry methods.

Integrated steering stress: p50 5.25 ms, p99 5.94 ms, max 5.94 ms in the local process.

## Gemini reference subsystem tests

Command:

```bash
MECHFIGHT_ARENA=/path/to/arena python3 -m unittest test_v9_reference.py -v
```

Result: **4/4 PASS**. This is a supplementary subsystem test. Its `RealArenaMockBot` intentionally stubs collision and terrain path methods; use `test_v9_integrated.py` for tests invoking the actual bot geometry.

## Important limitations

- This is not a scored 48-match result.
- Docker was not available in the local environment, so the exact 1-CPU / 512 MB / read-only container run was not reproduced.
- The coarse A* graph is a bounded, throttled fallback, not a fully precomputed global traversability map.
- Rooftop reachability is not yet connected to a full jump/jet route planner.
- Tree visibility uses a vertical-cylinder approximation and a short-horizon movement bonus; it is not an exact recreation of the server's complete vision engine.
- Mortar impact points are estimated from short trajectory segments and local map geometry.
- Gun projectile shooter-velocity inheritance remains unverified from public protocol information.

## Promotion rule

Do not replace V8's 2.92 as the best submission unless V9 achieves a strictly higher practice score.
