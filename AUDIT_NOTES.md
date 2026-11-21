# V9.2 response to independent V9.1 audit

## Findings addressed

1. A* latency: replaced repeated runtime geometry checks with a static 16 m graph built during hello; A* uses cached adjacency. A long-route A* call was measured at <= 1.4 ms locally.
2. Tree raycasts: limited tree concealment raycasts to the top three interest directions (at most six candidate-threat line checks), not 24 directions x two threats.
3. Active-goal amnesia: persist the detour waypoint for up to 1.5 s and invalidate it when reached, expired, or the strategic goal changes materially.
4. Duplicate projectile CPA: ContextSteerer continues to calculate 24-direction projectile danger. The old full `_incoming_threat` pass is no longer invoked just to retrieve `jump`; a mortar-only jump check remains.
5. Supply-drop logic: helper and call-site both reject drops while outside the current zone; ETA rejection removed to avoid landed-drop goal oscillation.
6. Optional fire: visible mechs alone disable suppression; recent sound alerts no longer do. Suppression begins only when `time_since_damage >= 2 s` and HP is below 85%.

## Audit point not reproduced as reported

V9.1's `_remember_beams` already checked the 2D distance from the mech to the beam segment and continued when the distance exceeded 35 m. Therefore, the claimed unfiltered path that always overwrote `last_attacker_id` was not present in the source we inspected. V9.2 retains this filter and computes distance against each consecutive segment, which is more accurate for multi-hop lightning paths.

## Remaining limitations

- Static navigation graph is precomputed for a conservative 4 m mech radius. If live radius exceeds this, A* bypasses the graph and direct local steering remains responsible for movement safety.
- The coarse graph is a fallback route guide, not a proof that every traversed cell is collision-free at arbitrary cube counts.
- Beam proximity is a heuristic, not proof that the beam was aimed at the mech.
- The jump-only mortar check uses a short bounded trajectory sample; the full ContextSteerer danger evaluator remains authoritative for movement direction.
- No practice score has been measured for V9.2.
