# Oval Ghost V8.1.2 — Minimal V8-based candidate

Base: the team's V8 bot (reported practice score: **2.92**). This candidate deliberately avoids the V9 A* / ContextSteering subsystem and preserves V8's lightweight combat and movement loop.

## Changes retained from the V8.1 line

1. **Beam filtering:** excludes self-generated beams and updates defensive threat memory only when the beam polyline passes within 35 m. Every consecutive segment is checked, including lightning chains.
2. **Zone rotation:** moves toward an interior point on the next safe ring (68% radius, with at least 18 m margin), but uses the zone centre for tiny final rings. Candidate waypoints are checked against the actual mech footprint and terrain; if a building occupies the nominal point, the bot searches nearby directions on the same ring.
3. **Supply drops:** considers pre-rotation up to 12 s before landing only while in-zone and with sufficient separation from tracked enemies; rejects drops outside the projected safe area or with two or more nearby enemies. Low-health approaches use stricter distance limits.
4. **Mortar avoidance:** truncates predictions at the first sampled terrain or solid-prism impact, interpolates the impact point, checks splash line-of-sight, and only applies parabolic refinement to a convex free-flight minimum.
5. **Target priority:** modestly rewards nearby weak targets and mortar carriers when carrying a laser, without allowing a distant target bonus to override a close threat.
6. **Laser range policy:** uses a 55 m engagement floor when a lightning holder is the target or a lightning threat is within 60 m; otherwise retains the 38 m floor to preserve opportunities against mortar carriers.

## Validation performed

- Official `check/check.py`: PASS, 300/300 observations, no late answers, no wrong ticks, no invalid protocol lines.
- Local recorded-checker timing: p50 0.7 ms, p90 1.3 ms, p99 1.8 ms, max 2.6 ms (one run; local machine, not the 1-CPU Docker sandbox).
- Focused regression suite: 19/19 PASS, including zone-ring building fallback, lightning polyline filtering, supply-drop guards, mortar terrain/wall impacts, target prioritisation, and laser engagement thresholds.
- 40-projectile mortar-heavy local stress test of `_incoming_threat`: p50 6.019 ms, p90 6.447 ms, p99 12.322 ms, max 14.481 ms across 120 calls on this machine.

## Important limitations

- Mortar collision is approximated with 50 ms shell segments and a bounded binary search at the first blocked segment; it is not a full engine-physics replication.
- Projectile physics (including whether gun bullets inherit shooter velocity) remains based on the current consistent V8 assumption; empirical engine verification is still valuable.
- The zone waypoint is a heuristic; the scored 48-match result determines whether it helps.
- Local tests and checker timings do not prove better placement. This candidate must beat V8's reported 2.92 in the practice scorer before it should replace V8.
- Docker is not installed in this environment, so the exact competition container has not been built locally.

## Build and test

```bash
python3 /path/to/mechfight-kit/check/check.py --map-dir /path/to/mechfight-kit/arena -- python3 -u bot.py
ARENA_DIR=/path/to/mechfight-kit/arena ./run_tests.sh
docker build -t oval-ghost-v8-1-2 .
```

`Dockerfile` is at the repository root and uses `COPY . .`.
