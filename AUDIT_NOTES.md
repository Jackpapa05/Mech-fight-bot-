# V8 engineering notes

## Evidence-based changes

- The V7 mortar CPA routine refined `best_t` with parabolic interpolation but left `best_d` and `best_delta` at the nearest 50 ms sample. A reproducible geometry with a true 8.95 m pass and a 9.0 m danger threshold showed the coarse sample could classify the shell as safe. V8 recomputes full relative position, distance, and lateral vector at the refined time.
- Straight projectile CPA now checks whether the segment from the observed projectile position to its predicted closest-approach position intersects a building/bridge/terrain according to V7's existing `_ray_blocked` model. If obstructed, that projectile is not treated as a direct threat.
- Visible laser/lightning beams expose a shooter ID and path whose first point is the shooter muzzle. V8 records the bearing from the mech to that muzzle and uses timestamp ordering so older sounds cannot overwrite newer beam/damage evidence.

## Important limitations

- The projectile occlusion check is a straight-segment check and applies only to gun/NPC bullets, not ballistic mortar shells.
- Beam data is event-like and only visible when the beam or part of it is in view; it is supplementary evidence, not persistent enemy localization.
- The protocol does not explicitly specify whether shooter velocity is inherited by gun projectiles. V8 retains V7's internally consistent non-inherited world-space projectile assumption; this remains unverified.
- No expected practice-score improvement is claimed. Only scored matches can establish that.
