# Independent audit response — what V6 does and does not adopt

## Adopted

1. Fix the sensors-upgrade time check to use `obs.t`.
2. Replace sparse straight-projectile checks with continuous closest-point-of-approach; retain a bounded ballistic sweep for mortar shells.
3. Do not stop moving just to regenerate; movement does not reset the documented regeneration timer.
4. Gate laser release and mortar firing on actual torso alignment.
5. Gate simultaneous gun fire against actual torso aim.
6. Use the weapon triangle in secondary-pickup valuation and allow a safe slot-1 swap.
7. Improve collision clearance from point-in-polygon to circle-versus-polygon edge distance; load terrain and use it for coarse movement and ray checks.
8. Exclude zone damage from rear-threat orientation.

## Important qualification

The protocol already provides five seconds of real-position tracking after an enemy leaves view. That means the bot does not need to recreate that exact position-memory feature itself; it should consume the mech entries the server continues to provide. V6 keeps short-lived sound/threat-bearing memory for directional awareness.

## Not changed without evidence

The auditor correctly identified an inconsistency in V5's gun-intercept math: its time solve uses `target_velocity - shooter_velocity`, while its predicted target point uses target world velocity only. The protocol says the gun projectile speed is 252 m/s but does not state whether shooter velocity is inherited. V6 uses target world velocity only, which is the internally consistent model if projectile velocity is independent of shooter motion. If the server inherits shooter velocity, both the intercept solve and aim vector must instead use the relative-motion frame. This remains the main physics assumption to verify.

The audit's claimed specific `z + 6.5` ray-origin mismatch was not found in the V5 source inspected for this build: its ray checks are used for threat cover and candidate cover points. V6 separately uses the documented muzzle height for weapon-origin line checks.
