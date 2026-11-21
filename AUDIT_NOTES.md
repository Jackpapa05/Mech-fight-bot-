# V7 audit notes

Source: V6 bot plus the independent Gemini audit supplied by the team.

## Applied P0 corrections

- Gate laser charge on unobstructed line of sight to the current target.
- If an existing laser charge loses its target line, direct the torso along a clear upward ray and release only after aim alignment; also cover the case where the target disappears from the observation.
- Solve mortar flight time and low-arc pitch iteratively without the previous 2.5-second cap; recompute the final pitch against the final lead point.
- Extend mortar path checking to the full relevant flight interval with adaptive sample count.
- Expand static prism spatial-bin padding to 16 m to account for cube-grown mech radius.
- Sample terrain at candidate cover positions for line-of-sight height.
- Remove the duplicate lightning fallback that bypassed the main branch's full checks.

## Deliberately not included

The V7 patch does not implement the larger P1/P2 proposals (24-slot context steering, ORCA/velocity obstacles, persistent enemy threat table, tree-occlusion cover scoring, or coarse A*). Those are larger strategic changes and should be tested separately after V7's result.

## Important uncertainty

The protocol gives the gun's projectile speed but does not explicitly state whether shooter velocity is inherited. The bot retains V6's consistent world-space projectile assumption; this needs empirical verification using observed projectile velocity while the mech is boosting laterally.
