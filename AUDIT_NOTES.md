# V8.1.2 audit notes

Base: V8 (team-reported practice score 2.92). V9's A*/ContextSteering system is not included.

## Gemini findings reviewed against the actual V8.1 ZIP

- **Zone waypoint:** the original V8.1 ZIP used `next_r > 35` and `0.68 * next_r` without a late-circle margin or structure test. V8.1.2 applies the edge heuristic only above 45 m, retains at least 18 m radial margin, and checks the mech footprint at the candidate point. If blocked, it tries alternate bearings on the same ring and falls back to the zone centre.
- **Supply drop:** selection requires the mech to be in-zone, a distant nearest tracked enemy, an unoccupied holder state, a safe projected-zone point, fewer than two tracked enemies within 55 m, and a 12 s landing window. Low-HP approaches have tighter distance/separation thresholds. No arrival-time cutoff is used, avoiding a goal flip at `lands_in == 0`.
- **Beam polyline:** every consecutive segment is checked; self beams are ignored. `last_attacker_id`/bearing are updated only for a beam segment within 35 m.
- **Mortar:** prediction now stops at first terrain or solid-prism intersection, estimates the impact point, and checks splash LOS. The ballistic sweep remains an approximation (0.05 s segments), not an exact reproduction of server collision integration.
- **Target score:** flat bonuses were replaced by modest conditional values: 15 for a mortar holder only when we have a laser; 18 for a sub-350 HP enemy within 90 m, otherwise 8. Close immediate threats remain preferred in the regression case.
- **Laser floor:** 55 m if the target holds lightning or another lightning holder is within 60 m; otherwise 38 m. This avoids needlessly surrendering laser-vs-mortar cook-off opportunities.

## Additional issues found and corrected

- V8.1.1 had tests calling `_target_priority_score` and `_laser_engagement_floor` methods that did not exist because their logic was embedded inline. V8.1.2 extracts those exact policies into methods and tests the production implementation.
- The nominal 68%-radius zone waypoint could lie inside an actual OSU building. V8.1.2 tries alternate bearings and includes a regression test using the real arena.

## Not claimed

No score improvement is claimed. Only the practice match runner can establish whether this beats V8's reported 2.92.
