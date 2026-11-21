# V9 Candidate Notes

## Base and scope

- Base: V8 source (`Oval-Ghost-v8-cpa-beam`), current reported practice score 2.92.
- Integrated Gemini's `v9_core.py` into a separate candidate; main was not modified.
- Preserves V8 target selection, weapon selection, aiming, laser safety, upgrades, and resource goal selection.
- Movement is replaced with 24-direction context steering and 5-second threat tracking.

## Independent changes applied during integration

1. Fixed V8 beam-memory false attribution: only beams whose path passes within 35 m of our mech can change defensive bearing/last-attacker memory; own beams are ignored.
2. Improved TreeIndex ray testing using segment/vertical-cylinder parameter intervals, accounting for crown offsets and partial vertical overlap.
3. Added small tree-concealment interest bonus to movement decisions. Trees remain vision-only and never block weapon rays.
4. Projectile occlusion is evaluated per candidate direction at that candidate's CPA; mortar is never culled by straight-line LOS.
5. Mortar danger path is sampled at 50 ms and truncated on terrain or prism impact before evaluating splash.
6. Coarse A* avoids map-out-of-bounds cells, disallows diagonal corner cutting, checks terrain edges, caches by goal, and returns the immediate next waypoint.
7. A* expansion budget limited to 180 per replan to reduce tail latency.
8. Distant sounds do not set the threat tracker's defensive bearing (they remain available to V8's original sound handler).

## Known limitations / not yet integrated

- Rooftop reachability helper remains advisory and does not command jump/jet navigation or guarantee a traversable approach.
- Tree concealment bonus is a short-horizon heuristic, not a full multi-enemy shared-vision simulator.
- A* is lazy/throttled, not a full precomputed traversability grid.
- Mortar impact is approximated by 50 ms trajectory segments and the bot's ray/terrain geometry; impact damage/splash can still be imperfect near complex prism edges.
- Shooter-velocity inheritance for gun bullets remains unverified by the public protocol.

## Scoring policy

V8 score 2.92 remains the benchmark. Do not promote V9 unless its actual practice score is strictly greater than 2.92.
