# Oval Sentinel V3.1

Standard-library-only Python bot for `mechfight/1`.

## Changes over V2/V3 candidate

- Proactively moves toward a safe anchor inside the announced next zone, rather than waiting near the outer safe-zone edge.
- Uses full walk speed for long rotations and scales speed down only near the destination; boosts when an urgent retreat or zone deadline warrants it.
- Retains the map-aware ground A* navigator, cover evaluation, resource selection, predictive aiming, weapon policy, projectile dodge, upgrade selection and bounded exploration.

## Build and check

From this directory:

```sh
python3 check/check.py --map-dir /arena -- python3 -u bot.py
```

The official competition Dockerfile is at the repository root. Copy the contents of this directory to the root of a public GitHub repository.
