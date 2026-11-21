# Oval Ghost V6 — audited correctness candidate

V6 is a cautious follow-up to V5, which scored **2.17** in the practice series. It keeps V5's broad decision policy while applying targeted fixes from an independent source audit.

## Main changes from V5

- Terrain height data is loaded once at startup and used for bilinear terrain samples.
- Static prisms are indexed into 32 m spatial bins for faster nearby collision queries.
- Movement collision checks account for the mech's circular footprint and cube-grown radius, including building edges and holes.
- Ground navigation rejects sampled routes that cross sharp terrain steps or slopes beyond the configured limit; this check is skipped on roofs/bridges.
- Incoming straight projectiles use closest-point-of-approach (CPA); mortar shells use a short ballistic sweep with a local refinement.
- Mortar firing waits for actual torso yaw and pitch alignment and checks the early arc against buildings and terrain.
- Laser charging starts only after pre-aim; release waits until the actual torso aim is aligned.
- Lightning requires an approximate clear line to the target and sufficient energy.
- Gun shots fired alongside a secondary weapon are gated against the actual torso aim, not merely the requested aim.
- Health recovery no longer freezes movement. The rules require five seconds without dealing or taking damage; walking does not cancel regeneration.
- The sensors-upgrade early-game bonus uses the observation's match time.
- A secondary weapon may be swapped using `drop: 1` + `take` when a pickup has a clear matchup advantage and it is safe to approach.
- Rear-hit orientation explicitly ignores zone damage and prioritizes the visible attacker when possible.
- Gun lead now uses target world velocity. This follows the protocol's stated projectile speed; shooter-velocity inheritance is not specified. If the server documents inheritance, both the intercept equation and lead vector must be changed together.

## Build and check

```sh
python3 -u bot.py
python3 /path/to/mechfight-kit/check/check.py --map-dir /arena -- python3 -u bot.py

docker build -t oval-ghost-v6 .
```

Uses Python standard library only. The Docker entrypoint is `python3 -u /bot/bot.py`.

## Submission policy

V6 is an **unscored candidate**. Do not replace V5 as the selected final entry unless V6's actual practice score beats 2.17. The official conformance checker is not a gameplay simulation.
