# Oval Ghost V4 — cover-first survival bot

A Python `mechfight/1` bot built from the V1 implementation, with a more deliberate cover-first and zone-rotation policy.

## Strategy

- Keep V1's simple local movement steering, predictive gun aim, weapon handling, projectile checks and upgrade selection as the baseline.
- Prefer moving along a protected inner arc of the safe zone rather than always beelining for the centre.
- When nearby mechs or recent close-range weapon sounds threaten the mech, search nearby building footprints for a point on the far side that blocks approximate line of sight.
- Avoid optional long-range mech engagements. Return fire when an enemy is close, charging, recently attacked us, or is a weak nearby target.
- Use a second weapon opportunistically: favour lightning as close-range defence and laser when the likely engagement is farther away; avoid preferring mortar as the default pickup.
- Attack nearby NPC drones only when no mech is close, health is adequate, and the mech is inside the zone.
- Pause optional fighting and crate farming while recovering health. Regeneration timing tracks both `damaged` and successful `hit` events.
- Dodge visible incoming projectiles before following the strategic movement goal.

The building line-of-sight and cover checks are geometric approximations based on the static prism map. This version does not implement full 3D rooftop pathfinding or jet-assisted climbs.

## Build and check

The submission root contains `Dockerfile`, `bot.py`, and `mechfight.py`.

```sh
python3 -u bot.py
python3 /path/to/mechfight-kit/check/check.py --map-dir /arena -- python3 -u bot.py
```

For the competition Docker build:

```sh
docker build -t oval-ghost-v4 .
```

The bot uses only the Python standard library and loads `/arena/v2/world.json` when available.

## Important

Passing `check.py` verifies protocol correctness and response timing, not match strategy. This candidate has not yet received a scored practice result. Keep the previously best-scoring V1 submission as the fallback until the official 48-match score for V4 is available.
