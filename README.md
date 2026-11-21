# Oval Ghost V9 — Integrated Context-Steering Candidate

V9 is an experimental candidate built on the V8 bot, which currently has a reported practice score of **2.92**. It preserves V8's target selection, weapons, aiming, laser safety, upgrades, and resource-goal logic while adding Gemini's tactical movement/perception subsystems.

## Files

- `bot.py` — V8 combat base with V9 movement and threat tracking integrated.
- `v9_core.py` — tree visibility index, multimodal threat tracker, projectile danger evaluator, 24-direction context steering, and bounded coarse A* fallback.
- `mechfight.py` — official standard-library protocol wrapper.
- `Dockerfile` — competition container entrypoint.
- `test_v9_integrated.py` — integration tests using actual V8 map/collision/terrain methods and extracted arena files.
- `test_v9_reference.py` — Gemini's reference subsystem test/benchmark.
- `AUDIT_NOTES.md`, `VALIDATION.md` — engineering notes and validation results.

## Local validation

From the project directory:

```bash
python3 /path/to/mechfight-kit/check/check.py --map-dir /path/to/arena -- python3 -u bot.py
MECHFIGHT_ARENA=/path/to/arena python3 -m unittest test_v9_integrated.py -v
MECHFIGHT_ARENA=/path/to/arena python3 -m unittest test_v9_reference.py -v
```

The submitted repository should have `Dockerfile` at its root. Upload the contents of this directory, not the ZIP file itself.

## Caution

V9 has passed local protocol and integration tests, but **has not yet produced a scored practice result**. Keep V8 (2.92) as the selected best until V9 scores higher. The official checker validates protocol/timing, not gameplay placement.
