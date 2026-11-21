# V9.1 integration notes

Base: V8 combat policy + existing V9 integrated movement/perception candidate. Latest Gemini V9 helpers have been integrated selectively.

## Added in V9.1

1. Conservative supply-drop pre-rotation (`choose_supply_drop_goal`): only drops landing within 13 seconds or already landed; rejects drops held by another mech; rejects drops outside the next safe circle; rejects very-close or multiple nearby tracked threats; estimates reachability; scores missing HP, energy and cube value. Existing cover and zone-emergency logic retain priority.
2. Defensive aim helper: uses fresh defensive bearing and very recent tracked enemies only; rejects stale five-second enemy memory as a torso-facing command.
3. Optional-fire suppression: below 85% HP with no visible mech or near/mid recent alert, do not farm NPCs or crates, preserving the regeneration window. This does not suppress visible-mech self-defence.

## Deliberately not integrated

- No automatic rooftop route/jet climb. `rooftop_reachable` remains advisory only.
- No blind supply-drop contesting against a known holder.
- No optional-fire suppression against visible hostile mechs.

## Known caveat

The helper's threat/zone/travel filters are conservative heuristics, not a full drop-capture planner. Practice score must decide whether the feature helps.
