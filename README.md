# Oval Ghost V9.1 — V8 combat + V9 tactical movement and drop logic

V9.1 is an **unscored candidate** based on the V8 agent (reported practice score 2.92). It preserves V8 combat/aiming/weapon logic and the integrated V9 context-steering subsystem, then adds cautious supply-drop pre-rotation and recovery-aware optional-fire suppression from Gemini's latest proposal.

## Included

- `bot.py` — V8 combat policy with V9 movement/threat tracking, third-party beam filtering, safe pre-rotation and defensive aim fallback.
- `v9_core.py` — tree vision index, multimodal threat tracker, unilateral projectile avoidance, 24-direction context steering, bounded coarse A*, rooftop reachability helper, supply-drop selection and tactical helper functions.
- `mechfight.py` — competition protocol wrapper.
- `Dockerfile` — standard-library Python runtime.
- `test_v9_integrated.py` — tests using the real V8 map/geometry methods.
- `test_v9_reference.py` — Gemini's supplementary reference tests.
- `test_v9_tactical.py` — tests for supply-drop, defensive-aim and optional-fire helper logic.

## Important strategy safeguards

- A supply drop is only selected if it is not held by another mech, is within the next safe circle, has no very-close tracked threat and is plausibly reachable. Existing cover/emergency-zone decisions can override the drop goal.
- Optional NPC/crate fire is suppressed below 85% HP when there is no visible mech or recent near/mid threat. Visible-mech self-defence is never suppressed by this helper.
- Defensive aim uses recent threat evidence and avoids rotating toward stale five-second memories.
- Rooftop reachability is currently an advisory helper; this bot does **not** have a complete roof-route/jump/jet planner.

## Local validation

```bash
python3 /path/to/mechfight-kit/check/check.py --map-dir /path/to/arena -- python3 -u bot.py
MECHFIGHT_ARENA=/path/to/arena python3 -m unittest test_v9_integrated.py -v
MECHFIGHT_ARENA=/path/to/arena python3 -m unittest test_v9_reference.py -v
python3 -m unittest test_v9_tactical.py -v
```

The official checker validates protocol and timing, not gameplay placement. Docker sandbox parity has not been independently verified in this environment.

## Promotion rule

The current reported best is V8 at **2.92**. Do not replace it unless this candidate's actual 48-match practice score is strictly greater than 2.92.
