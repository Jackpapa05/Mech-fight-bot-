# Oval Sentinel V2 — Mech Royale bot

A standard-library-only Python agent for `mechfight/1`.

## Build and check

```sh
python3 -u bot.py
python3 /path/to/mechfight-kit/check/check.py --map-dir /arena -- python3 -u bot.py
```

For the competition Docker sandbox, mount the kit's `arena/` folder at `/arena`:

```sh
docker build -t oval-sentinel .
docker run --rm -i --network none --cpus 1 --memory 512m --read-only \
  --tmpfs /tmp:rw,size=64m --user 65534:65534 \
  -v "$PWD/arena:/arena:ro" oval-sentinel
```

## Strategy

- Quiet movement when there is no immediate danger (keeps ground speed below the step-sound threshold).
- Zone prediction and urgent zone escape.
- Static map loading, terrain sampling, obstacle-aware A* ground navigation.
- Local cover search that evaluates line-of-sight blocking against visible threats.
- Projectile prediction and emergency dodge/jump.
- Conservative engagement logic, with disengagement/healing windows.
- Selective NPC/crate farming, cube and drop prioritisation, and weapon pickups.
- Predictive gun lead, weapon-specific laser/mortar/lightning choices, and adaptive upgrades.

`check.py` validates protocol compliance and decision latency, not match outcomes. The 48-match practice score is the only evidence that a strategy change improves gameplay. Keep the last best-scoring commit as a fallback.
