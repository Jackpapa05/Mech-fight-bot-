# Oval Survivor — Mech Royale bot

A survival-first Python bot for `mechfight/1`. Standard-library only; uses the provided `mechfight.py` wrapper.

## Build and conformance check

From this directory:

```sh
python3 -u bot.py
```

The command above expects a protocol stream on stdin. Run the kit conformance check from the extracted kit directory:

```sh
python3 check/check.py -- python3 -u ../mechfight-bot/bot.py
```

For Docker submission, this folder is already arranged with `Dockerfile` at the top level. Build it with:

```sh
docker build -t oval-survivor .
```

The bot uses observation/config values at runtime and loads `/arena/v2/world.json` when available. It falls back to zone navigation if the map file is unavailable.

## Current strategy

- Zone-aware movement with local static-prism avoidance.
- Health-aware disengagement and lateral movement around nearby threats.
- Incoming projectile checks with emergency dodging and mortar-jump response.
- Predictive gun leading; weapon-specific laser, mortar and lightning behaviour.
- Opportunistic cubes, weapon pickups, crates and uncontested supply drops.
- Defensive and mobility-focused upgrade choices.

This is a first strategic candidate, not a guaranteed winning bot. `check.py` validates protocol/timing, not game performance. Submit it to obtain the 48-match practice score, then tune based on actual placements.
