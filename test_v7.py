#!/usr/bin/env python3
"""Focused regression checks for Oval Ghost V7 P0 fixes (stdlib only)."""
from __future__ import annotations
import gzip
import json
import math
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = Path(os.environ.get('MECHFIGHT_KIT_DIR', '/mnt/data/mechfight-kit-extract/mechfight-kit'))
ARENA = KIT / 'arena'
# Import the bot class without starting the protocol stdin/stdout loop.
_source = (HERE / 'bot.py').read_text(encoding='utf-8')
_source = _source.rsplit('\nmf.run(Bot)', 1)[0] + '\n'
_namespace = {'__name__': 'oval_ghost_v7_test'}
exec(compile(_source, str(HERE / 'bot.py'), 'exec'), _namespace)
Bot = _namespace['Bot']


def load_hello():
    with gzip.open(KIT / 'check' / 'stream.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            obj = json.loads(line)
            if obj.get('type') == 'hello':
                obj['map']['dir'] = str(ARENA)
                return obj
    raise RuntimeError('hello not found in checker stream')


class V7RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hello = load_hello()
        cls.bot = Bot(cls.hello)

    def test_mortar_long_range_not_truncated_at_2_5s(self):
        me = {'pos': [0.0, 0.0, 0.0], 'stats': {'muzzle_height': 7.0}}
        target = {'kind': 'mech', 'pos': [200.0, 0.0, 0.0], 'vel': [0.0, 0.0, 0.0], 'cubes': 0}
        weapon = {'stats': {'speed': 72.0}}
        _, pitch, horizontal = self.bot._mortar_aim(me, target, weapon)
        flight_t = horizontal / (72.0 * max(0.15, math.cos(pitch)))
        self.assertGreater(flight_t, 2.5)
        self.assertLess(flight_t, 6.5)

    def test_mortar_lead_and_returned_range_are_consistent(self):
        me = {'pos': [0.0, 0.0, 0.0], 'stats': {'muzzle_height': 7.0}}
        target = {'kind': 'mech', 'pos': [180.0, 12.0, 0.0], 'vel': [8.0, -2.0, 0.0], 'cubes': 0}
        weapon = {'stats': {'speed': 72.0}}
        _, pitch, horizontal = self.bot._mortar_aim(me, target, weapon)
        flight_t = horizontal / (72.0 * max(0.15, math.cos(pitch)))
        expected = math.hypot(target['pos'][0] + target['vel'][0] * flight_t,
                              target['pos'][1] + target['vel'][1] * flight_t)
        self.assertLess(abs(horizontal - expected), 0.15)

    def test_spatial_bins_include_prism_with_large_mech_radius(self):
        fake = Bot.__new__(Bot)
        fake.bin_size = 32.0
        fake.prisms = [{'bbox': (36.0, 0.0, 40.0, 4.0)}]
        fake.prism_bins = {}
        idx = 0
        p = fake.prisms[0]
        pad = 16.0
        for ix in range(math.floor((p['bbox'][0] - pad) / 32.0), math.floor((p['bbox'][2] + pad) / 32.0) + 1):
            for iy in range(math.floor((p['bbox'][1] - pad) / 32.0), math.floor((p['bbox'][3] + pad) / 32.0) + 1):
                fake.prism_bins.setdefault((ix, iy), []).append(idx)
        found = fake._prisms_in_bbox(0.0, -4.0, 4.0, 4.0)
        self.assertEqual(len(found), 1)

    def test_laser_does_not_start_charge_without_los(self):
        # Start from a real schema-shaped observation, then provide a remembered
        # enemy and a laser secondary. Force geometry to report a blocked ray.
        with gzip.open(KIT / 'check' / 'stream.jsonl.gz', 'rt', encoding='utf-8') as f:
            obs = next(json.loads(line) for line in f if json.loads(line).get('type') == 'obs')
        me = obs['self']
        x, y, z = me['pos']
        me['weapons'] = [me['weapons'][0], {
            'kind': 'laser', 'cooldown': 0.0, 'charge': 0.0,
            'stats': {'damage': 315, 'charge': 0.75, 'range': 280.0}
        }]
        enemy = {'id': 8, 'kind': 'mech', 'pos': [x + 100.0, y, z], 'vel': [0.0, 0.0, 0.0],
                 'hp': 900, 'max_hp': 1400, 'weapons': ['gun'], 'cubes': 0, 'charging': False}
        obs['mechs'] = [enemy]
        bot = Bot(self.hello)
        bot._ray_blocked = lambda a, b: True
        action = bot.act(obs)
        self.assertFalse(action['fire'][1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
