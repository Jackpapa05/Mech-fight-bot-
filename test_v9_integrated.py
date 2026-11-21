"""Integration checks using the actual V8 bot geometry and extracted OSU arena."""
import math
import os
import statistics
import sys
import time
import unittest

ROOT = os.path.dirname(__file__)
ARENA = os.environ.get("MECHFIGHT_ARENA", "/mnt/data/arena_local/arena")

import mechfight as mf
mf.run = lambda _factory: None  # Prevent the stdin loop when importing bot.py in tests.
from bot import Bot
from v9_core import ContextSteerer, ThreatTracker, TreeIndex, unilateral_vo_danger


class TestV9Integrated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hello = {"type": "hello", "seed": 7, "config": {}, "map": {"dir": ARENA}}
        cls.bot = Bot(hello)
        with open(os.path.join(ARENA, "v2", "world.json"), "r", encoding="utf-8") as f:
            import json
            cls.world = json.load(f)

    def test_actual_map_loaded(self):
        self.assertEqual(len(self.bot.prisms), 259)
        self.assertIsNotNone(self.bot.tree_index)
        self.assertEqual(len(self.bot.tree_index.trees), 1560)
        self.assertEqual(len(self.bot.terrain_values), 1070 * 724)

    def test_tree_crown_vision_occlusion(self):
        ti = self.bot.tree_index
        tree = next(t for t in ti.trees if t[4] >= 3.0 and t[3] - t[5] > 1.0)
        tx, ty, tz, height, crown_r, crown_base, trunk_r, cx, cy = tree
        z = tz + crown_base + 0.5
        a = (cx - crown_r - 2.0, cy, z)
        b = (cx + crown_r + 2.0, cy, z)
        self.assertTrue(ti.vision_blocked_by_trees(a, b))

    def test_tree_vision_does_not_affect_weapon_los(self):
        ti = self.bot.tree_index
        tree = ti.trees[0]
        tx, ty, tz, height, crown_r, crown_base, trunk_r, cx, cy = tree
        z = tz + crown_base + 0.5
        a = (cx - crown_r - 2.0, cy, z)
        b = (cx + crown_r + 2.0, cy, z)
        self.assertTrue(ti.vision_blocked_by_trees(a, b))
        # Trees are not solids: the weapon-ray implementation should not report
        # a tree collision (it only tests prism and terrain geometry).
        self.assertFalse(self.bot._ray_blocked(a, b))

    def test_beam_third_party_does_not_set_defensive_bearing(self):
        tracker = ThreatTracker()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        obs = {"t": 10.0, "mechs": [], "events": [], "sounds": [],
               "beams": [{"by": 4, "kind": "laser", "age": 0.1,
                          "path": [[120.0, 120.0, 7.0], [150.0, 130.0, 7.0]]}]}
        tracker.update(obs, me)
        self.assertIsNone(tracker.defensive_bearing)
        self.assertIn(4, tracker.enemies)

    def test_beam_near_self_sets_defensive_bearing(self):
        tracker = ThreatTracker()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        obs = {"t": 10.0, "mechs": [], "events": [], "sounds": [],
               "beams": [{"by": 4, "kind": "laser", "age": 0.1,
                          "path": [[-40.0, 0.0, 7.0], [40.0, 0.0, 7.0]]}]}
        tracker.update(obs, me)
        self.assertIsNotNone(tracker.defensive_bearing)

    def test_bullet_behind_solid_is_culled_but_unblocked_bullet_is_dangerous(self):
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        projectile = [{"kind": "gun", "pos": [-35.0, 0.0, 4.5], "vel": [252.0, 0.0, 0.0]}]
        clear = unilateral_vo_danger(me, projectile, 14.0, 2.5, 9.0)
        blocked = unilateral_vo_danger(me, projectile, 14.0, 2.5, 9.0,
                                       ray_blocked_fn=lambda _a, _b: True)
        self.assertGreater(max(clear), 0.0)
        self.assertEqual(max(blocked), 0.0)

    def test_mortar_ground_impact_uses_splash(self):
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        projectile = [{"kind": "mortar", "pos": [20.0, 0.0, 4.0], "vel": [-40.0, 0.0, -5.0]}]
        danger = unilateral_vo_danger(me, projectile, 14.0, 2.5, 9.0,
                                     terrain_height_fn=lambda _x, _y: 0.0)
        self.assertGreater(max(danger), 0.0)

    def test_context_steerer_stress(self):
        steerer = ContextSteerer()
        tracker = ThreatTracker()
        me = {"id": 0, "pos": [40.0, -70.0, 0.0], "energy": 80.0,
              "stats": {"radius": 2.5, "height": 9.0, "eye_height": 8.0,
                        "step_up": 1.5, "max_slope_deg": 50.0,
                        "walk_speed": 11.7, "boost_speed": 19.5}}
        obs = {"t": 120.0, "mechs": [], "projectiles": [], "beams": [], "sounds": [],
               "events": [], "zone": {"center": [0.0, 0.0], "radius": 500.0}}
        for i in range(15):
            obs["mechs"].append({"id": i + 1, "kind": "mech", "pos": [40.0 + i * 8.0, -20.0, 0.0],
                                 "vel": [0.0, 0.0, 0.0], "hp": 900, "weapons": ["gun", "laser"],
                                 "charging": i == 0, "cubes": 2})
        for i in range(40):
            obs["projectiles"].append({"kind": "mortar" if i % 8 == 0 else "gun",
                                       "pos": [100.0, -80.0 + i * 2.0, 10.0],
                                       "vel": [-72.0 if i % 8 == 0 else -200.0, 0.0, 1.0]})
        tracker.update(obs, me)
        threats = tracker.prioritized_threats(obs, me)
        timings = []
        for n in range(50):
            obs["t"] += 0.1
            t0 = time.perf_counter()
            move, urgent = steerer.evaluate(self.bot, obs, me, (0.0, 0.0), 1.0, threats)
            timings.append((time.perf_counter() - t0) * 1000.0)
            self.assertAlmostEqual(math.hypot(*move), 1.0, places=5)
        timings.sort()
        p99 = timings[min(len(timings)-1, int(len(timings)*0.99))]
        print(f"\nIntegrated V9 steering: p50={statistics.median(timings):.3f} ms, p99={p99:.3f} ms, max={timings[-1]:.3f} ms")
        self.assertLess(timings[-1], 15.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
