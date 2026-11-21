# Oval Ghost V9.2 — latency-safe tactical integration

V9.2 is a guarded improvement over the V9.1 candidate. It addresses the latency and policy issues identified in the independent review while preserving V9.1's combat, aiming, weapon selection and 24-direction movement policy.

## Changes in V9.2

- **Precomputed navigation graph:** builds a 16 m static traversability graph during the `hello` startup budget. Runtime A* traverses cached adjacency lists rather than repeatedly doing polygon and terrain checks.
- **Persistent detour waypoint:** a stagnation-triggered A* waypoint is held for up to 1.5 seconds (or until reached / the strategic goal changes), instead of being forgotten on the next observation.
- **Reduced tree-LOS work:** tree concealment is evaluated only for the three most goal-aligned movement directions, rather than all 24 directions.
- **Drop policy stability:** supply-drop goals are ignored while outside the current zone; the ETA cutoff that caused a one-second landed-drop goal flip has been removed because drops persist after landing.
- **Recovery-aware optional firing:** sounds alone no longer count as a visible mech for the suppression helper. Optional fire is suppressed only after the damage timer has progressed for at least 2 seconds; visible-mech self-defence is never suppressed.
- **Jump-only mortar check:** the bot no longer reruns full projectile CPA solely to obtain the jump flag; ContextSteerer handles movement danger, while a small mortar-only routine handles jump timing.
- **Lightning beam polyline distance:** threat bearing checks use every consecutive beam segment, not only the chord from first to last point.

## Notes on the independent audit

The audit's report of an unfiltered `_remember_beams` path was not reproduced in this V9.1 source: the function already rejected beams whose segment was more than 35 m from the mech before updating `last_attacker_id` / `last_threat_bearing`. V9.2 retains that filter and improves polyline handling for lightning.

## Validation performed

- Official `check/check.py`: PASS, 300/300 observations, 0 late, 0 wrong tick, 0 bad lines.
- Official checker timing on this machine: p50 1.2 ms, p90 1.8 ms, p99 2.6 ms, max 3.2 ms.
- Unit/integration suites: 23 tests PASS against the extracted arena.
- Real map graph: 2,120 walkable 16 m cells and 12,920 directed edges; graph precomputation about 0.40–0.46 s during startup.
- A* query on the cached graph: max about 1.4 ms in the tested long-route case.
- Full `Bot.act()` stress test with 15 mechs, 40 projectiles, beam/sound inputs and repeated stagnation: p50 5.99 ms, p90 6.48 ms, p99 10.06 ms, max 11.96 ms (local machine).

These tests verify protocol, latency and selected code paths. They do **not** establish that V9.2 scores better in the 48-match practice runner. Docker sandbox parity has not been independently verified here.

## Files

- `bot.py`, `v9_core.py`, `mechfight.py`
- `test_v9_integrated.py`, `test_v9_reference.py`, `test_v9_tactical.py`, `test_v9_2.py`
- `AUDIT_NOTES.md`, `VALIDATION.md`

## Promotion policy

V8's reported 2.92 remains the best verified practice score unless a newer candidate earns a higher actual score. Do not overwrite or discard the higher-scoring commit.
