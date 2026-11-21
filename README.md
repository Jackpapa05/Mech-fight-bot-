# Oval Ghost V5 — V1 combat + conditional cover

A conservative hybrid candidate. It preserves V1's original target selection, active firing, movement steering, projectile dodging, and zone navigation. New logic is limited to conditional cover movement, basic threat-memory, opportunistic isolated-NPC farming, context-sensitive second-weapon preference, and a narrow health-regeneration pause.

## Design rationale

- V2/V3's low scores showed that feature growth alone did not improve the policy.
- V4 scored 1.90 versus V1's 1.94, so it did not establish a better result.
- V5 keeps V1's combat logic intact: cover and recovery affect movement only, and do not gate firing at visible mechs.
- NPC drones are targeted only when no mech is visible, the nearest known mech is distant, health is good, and the mech is in-zone. NPC aiming uses the documented smaller NPC height.
- Building cover is only requested for close, visible threats when the mech is exposed and has a meaningful danger trigger.

## Build and check

```sh
python3 -u bot.py
python3 /path/to/mechfight-kit/check/check.py --map-dir /arena -- python3 -u bot.py
docker build -t oval-ghost-v5 .
```

Uses Python standard library only and the provided `mechfight.py` protocol wrapper.

**Important:** `check.py` verifies protocol and timing, not in-game performance. V5 must earn a practice score before it can replace V1 as the final entry.
