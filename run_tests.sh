#!/bin/sh
set -eu
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
export ARENA_DIR="${ARENA_DIR:-/mnt/data/arena_extracted/arena}"
python3 - <<'PY'
import unittest
import test_v8, test_v8_1, test_v8_1_1, test_v8_1_2
suite = unittest.TestSuite()
for module in (test_v8, test_v8_1, test_v8_1_1, test_v8_1_2):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
