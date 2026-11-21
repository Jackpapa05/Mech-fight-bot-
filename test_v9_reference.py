"""Tests and real-map benchmark for V9 core against extracted arena/v2/world.json & terrain.i16."""
import json
import os
import statistics
import time
import unittest
from array import array

from v9_core import CoarseNavGraph, ContextSteerer, ThreatTracker, TreeIndex, unilateral_vo_danger


class RealArenaMockBot:
    def __init__(self, world_path: str, terrain_path: str):
        with open(world_path) as f:
            self.world = json.load(f)
        self.t_meta = self.world["terrain"]
        self.t_vals = array("h")
        with open(terrain_path, "rb") as f:
            self.t_vals.frombytes(f.read())
        self.tree_index = TreeIndex(self.world)

    def _terrain_height(self, x: float, y: float):
        nx, ny = int(self.t_meta["nx"]), int(self.t_meta["ny"])
        fx = (x - float(self.t_meta["minX"])) / float(self.t_meta["step"])
        fy = (y - float(self.t_meta["minY"])) / float(self.t_meta["step"])
        if fx < 0 or fy < 0 or fx >= nx - 1 or fy >= ny - 1:
            return None
        i, j = int(fx), int(fy)
        return self.t_vals[j * nx + i] * 0.01

    def _blocked(self, x: float, y: float, z: float, height: float, radius: float) -> bool:
        return False

    def _terrain_segment_clear(self, x: float, y: float, z: float, dx: float, dy: float, dist: float, step_up: float, max_slope: float) -> bool:
        return True

    def _ray_blocked(self, a, b) -> bool:
        return False


class TestV9RealArena(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        arena_dir = os.environ.get("MECHFIGHT_ARENA", "/arena")
        cls.bot = RealArenaMockBot(
            os.path.join(arena_dir, "v2", "world.json"),
            os.path.join(arena_dir, "v2", "terrain.i16"),
        )

    def test_real_trees_loaded(self):
        self.assertEqual(len(self.bot.tree_index.trees), 1560)
        self.assertAlmostEqual(self.bot.tree_index.canopy_density, 0.35)
        self.assertAlmostEqual(self.bot.tree_index.canopy_block_t, 0.25)

    def test_mortar_early_ground_impact_triggers_dodge(self):
        me = {"id": 0, "pos": [0.0, 0.0, 10.0], "stats": {"radius": 2.5, "height": 9.0}}
        # Mortar at (20, 0, 14) falling onto terrain height 10.0m near (4, 0) in ~0.4s
        proj = [{"kind": "mortar", "pos": [20.0, 0.0, 14.0], "vel": [-40.0, 0.0, -5.0]}]
        danger = unilateral_vo_danger(
            me, proj, move_speed=22.0, mech_radius=2.5, mech_height=9.0,
            terrain_height_fn=lambda x, y: 10.0,
        )
        self.assertGreater(max(danger), 0.35)

    def test_beam_third_party_filter(self):
        tracker = ThreatTracker()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        obs = {
            "t": 15.0,
            "mechs": [],
            "beams": [
                {"by": 4, "kind": "laser", "path": [[120.0, 120.0, 7.0], [150.0, 130.0, 7.0]], "age": 0.1},
            ],
            "events": [],
            "sounds": [],
        }
        tracker.update(obs, me)
        # Shooter is tracked, but defensive_bearing should NOT spin toward 3rd-party fight
        self.assertIn(4, tracker.enemies)
        self.assertIsNone(tracker.defensive_bearing)

    def test_coarse_nav_and_context_steerer_benchmark(self):
        nav = CoarseNavGraph(self.bot)
        steerer = ContextSteerer(nav=nav)
        tracker = ThreatTracker()
        me = {
            "id": 0, "pos": [0.0, 0.0, 5.0], "energy": 80.0,
            "stats": {"radius": 2.5, "height": 9.0, "step_up": 1.5, "max_slope_deg": 50.0, "walk_speed": 14.0, "boost_speed": 22.0},
        }
        obs = {
            "t": 50.0,
            "mechs": [{"id": i, "kind": "mech", "pos": [i * 15.0, -30.0, 5.0], "vel": [5.0, 0.0, 0.0], "hp": 900, "weapons": ["gun", "laser"], "charging": i == 1, "cubes": 2} for i in range(1, 16)],
            "projectiles": [{"kind": "mortar" if i % 5 == 0 else "gun", "pos": [40.0, i * 2.0, 8.0], "vel": [-200.0, 0.0, 2.0]} for i in range(40)],
            "beams": [{"by": 2, "kind": "laser", "path": [[60.0, 20.0, 7.0], [5.0, 0.0, 5.0]], "age": 0.1}],
            "sounds": [],
            "events": [],
            "zone": {"center": [40.0, -70.0], "radius": 240.0},
        }
        lats = []
        for tick in range(100):
            obs["t"] = 50.0 + tick * 0.1
            t0 = time.perf_counter()
            tracker.update(obs, me)
            th = tracker.prioritized_threats(obs, me)
            steerer.evaluate(self.bot, obs, me, goal=(40.0, -70.0), goal_weight=1.0, threats=th)
            for item in th[:3]:
                self.bot.tree_index.vision_blocked_by_trees((0.0, 0.0, 13.0), (item["pos"][0], item["pos"][1], 9.5))
            lats.append((time.perf_counter() - t0) * 1000.0)
        lats.sort()
        print(f"\nV9 Real-Arena Stress (1560 trees, 15 mechs, 40 proj): p50={statistics.median(lats):.3f} ms, p99={lats[98]:.3f} ms, max={lats[-1]:.3f} ms")
        self.assertLess(lats[-1], 10.0)


if __name__ == "__main__":
    unittest.main()