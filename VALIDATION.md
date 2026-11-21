# V3.1 validation notes

- V3.1 is an experimental candidate intended to address observed V2 policy regressions.
- The supplied replay contains 300 observations. V2's action output commanded no movement on many early observations when there were no visible enemies/resources and zone pressure had not yet crossed its trigger. V3 added exploration; V3.1 additionally makes the next announced circle a proactive navigation target and increases travel speed.
- These are policy hypotheses, not evidence of a higher match score.
- Must be checked with the competition's `check/check.py` and then scored in 48 practice matches before replacing the current best entry.
