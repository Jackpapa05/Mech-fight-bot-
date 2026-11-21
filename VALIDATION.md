# Oval Ghost V4 validation record

## Official conformance check

Command:

```sh
python3 /mnt/data/mechfight-kit/check/check.py --map-dir /mnt/data/mechfight-kit/arena -- python3 -u bot.py
```

Result: **PASS**

- Recorded observations: 300 / 300 answered
- Missed 50 ms deadlines: 0
- Stale/older answers: 0
- Wrong ticks: 0
- Invalid protocol lines: 0
- Debug drawings over caps: 0
- Ready time on this host: 863 ms
- Action response time on this host: p50 1.3 ms, p90 2.2 ms, p99 3.6 ms, maximum 4.3 ms

## Recorded-replay action summary

The same 300 observations were supplied sequentially to V1 and V4. This is an action-output comparison only; the replay does not simulate how the world would react to those actions.

| Metric | V1 | V4 |
|---|---:|---:|
| Non-zero movement commands | 300 | 300 |
| Boost commands | 111 | 97 |
| Slot 0 fire-trigger commands | 123 | 48 |
| Slot 1 fire-trigger commands | 0 | 0 |
| Decisions labelled as cover | 0 | 139 |
| Decisions labelled as recovery | 0 | 0 |

The lower firing count is intentional in this candidate: it avoids optional engagements and suppresses direct shots when the approximate building ray test finds an obstruction. This is a strategic hypothesis, not evidence of a higher placement score.

## Limitations

- The official checker is not a game simulation; it does not score survival or placement.
- The recorded replay does not react to the bot's actions.
- Cover and ray tests are approximations using the static building prism geometry.
- No full 3D rooftop routing or jet-assisted building climb is implemented.
- Docker image build was not run in this environment; the Dockerfile follows the supplied kit layout and uses the standard-library-only bot.
- The required next experiment is the official 48-match practice score. Do not replace the previous best entry unless V4 scores higher.
