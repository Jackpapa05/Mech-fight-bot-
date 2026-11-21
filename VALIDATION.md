# Oval Sentinel V2 — validation record

## Official kit conformance check

Command used:

```sh
python3 check/check.py --map-dir /mnt/data/mechfight-kit/arena -- python3 -u /mnt/data/mechfight-bot-v2/bot.py
```

Result: **PASS**

- Recorded observations handled: 300 / 300
- Missed the 50 ms action budget: 0
- Wrong tick values: 0
- Invalid JSON/protocol lines: 0
- Responses to stale queued observations: 0
- Ready time: 1,097 ms
- Action time on this host: p50 0.2 ms, p90 0.3 ms, p99 2.7 ms, max 2.9 ms
- Static map loaded successfully: 134 × 91 navigation grid; 3,432 blocked cells
- A* test route from a real spawn sample to the next zone center: 59 waypoints, 1.81 ms

## Additional synthetic branch test

A 250-case synthetic observation fuzz test exercised varied enemy counts, NPCs, projectiles, crates, cubes, weapon slots, supply drops and upgrade offers.

- Exceptions: 0
- Invalid/non-finite movement or aim values: 0
- Decision-time p99: 5.66 ms
- Maximum observed decision time: 13.34 ms on this host

## Important limitation

The kit's conformance checker replays observations without simulating the consequences of the bot's actions. These tests establish protocol correctness, map loading and timing headroom, **not an improved match score**. The next required experiment is to submit V2 and compare its 48-match practice score against V1's 1.94.

A Docker image was not built in this environment because Docker is unavailable here. The provided Dockerfile uses only the Python standard library and preserves the official starter layout.
