# Oval Ghost V8 — focused threat-awareness candidate

V8 is a narrow experimental patch based on V7 (practice score reported by the team: 2.71). It does **not** replace the best-known V7 build until V8 receives its own 48-match score.

## Changes from V7

1. **Mortar CPA consistency:** after refining the closest-approach time from the 50 ms samples, recompute the true 3D separation and lateral dodge vector at that refined time. V7 refined time but retained distance/direction from the coarse sample.
2. **Projectile path occlusion:** for straight gun/NPC bullets, do not dodge when the projectile's current path to its predicted closest-approach point is blocked by a solid or terrain ridge. This is separate from tree vision because trees do not block shots.
3. **Beam-based threat memory:** use observed laser/lightning beam source positions and shooter IDs to update the threat bearing when the beam is newer than existing damage/sound evidence. This helps orient toward the attacker when no mech is currently visible.
4. **Timestamp ordering:** older sounds do not overwrite a newer beam/damage observation.

## Deliberately not included

No new 24-direction steering, ORCA, rooftop planner, tree-vision model, or large strategy rewrite is included. Those need separate testing. This candidate preserves V7's broader action policy.

## Build and test

```sh
python3 check/check.py --map-dir /path/to/mechfight-kit/arena -- python3 -u bot.py
python3 test_v8.py
```

## Submission policy

V7's reported score of 2.71 remains the best-known result until V8's scored practice result is higher. The conformance check is not a gameplay simulation.
