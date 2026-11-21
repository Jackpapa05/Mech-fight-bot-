"""Regression tests for V9.2 latency, route persistence, drops, and regen policy."""
import math
import os
import time
import unittest

from v9_core import ContextSteerer, choose_supply_drop_goal, should_suppress_optional_fire

ARENA = os.environ.get("MECHFIGHT_ARENA", "/mnt/data/arena_local/arena")


class FakeTreeIndex:
    def __init__(self):
        self.calls = 0
    def vision_blocked_by_trees(self, _a, _b):
        self.calls += 1
        return True


class FakeBot:
    def __init__(self, nav=None, tree=True):
        self.nav_graph = nav
        self.tree_index = FakeTreeIndex() if tree else None
        self.ray_calls = 0
    def _terrain_segment_clear(self, *_args):
        return True
    def _blocked(self, *_args):
        return False
    def _terrain_height(self, _x, _y):
        return 0.0
    def _ray_blocked(self, *_args):
        self.ray_calls += 1
        return False


class FakeNav:
    def __init__(self):
        self.calls = 0
    def find_waypoint(self, _now, _start, _goal, _radius, _height):
        self.calls += 1
        return (0.0, 30.0)


class TestV92(unittest.TestCase):
    def test_supply_drop_goal_does_not_flip_at_landing(self):
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "in_zone": True,
              "hp": 700, "max_hp": 1400, "energy": 40, "max_energy": 100,
              "cubes": 2, "stats": {"walk_speed": 12, "boost_speed": 20}}
        threats = []
        p = [120.0, 0.0, 0.0]
        obs = {"t": 90, "zone": {"next_center": [0, 0], "next_radius": 300},
               "drops": [{"id": 20001, "pos": p, "lands_in": 1.0, "holder": None}]}
        before = choose_supply_drop_goal(obs, me, threats)
        obs["drops"][0]["lands_in"] = 0.0
        after = choose_supply_drop_goal(obs, me, threats)
        self.assertEqual(before, after)
        self.assertIsNotNone(before)

    def test_supply_drop_is_rejected_outside_zone(self):
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "in_zone": False,
              "hp": 500, "max_hp": 1400, "energy": 20, "max_energy": 100, "cubes": 0}
        obs = {"drops": [{"id": 20001, "pos": [10, 0, 0], "lands_in": 0, "holder": None}]}
        self.assertIsNone(choose_supply_drop_goal(obs, me, []))

    def test_regen_suppression_only_after_timer_has_progressed(self):
        me = {"hp": 1000.0, "max_hp": 1400.0}
        self.assertFalse(should_suppress_optional_fire(me, False, time_since_damage=0.2))
        self.assertTrue(should_suppress_optional_fire(me, False, time_since_damage=2.1))
        self.assertFalse(should_suppress_optional_fire(me, True, time_since_damage=10.0))

    def test_tree_raycasts_are_limited_to_top_three_directions(self):
        bot = FakeBot(tree=True)
        steerer = ContextSteerer()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "energy": 0,
              "stats": {"radius": 2.5, "height": 9.0, "eye_height": 8.0,
                        "step_up": 1.5, "max_slope_deg": 50,
                        "walk_speed": 12, "boost_speed": 20}}
        threats = [{"pos": [50.0, 0.0, 0.0]}, {"pos": [0.0, 50.0, 0.0]}]
        obs = {"t": 1.0, "projectiles": [], "zone": {"center": [0, 0], "radius": 500}}
        steerer.evaluate(bot, obs, me, (100.0, 0.0), 1.0, threats)
        self.assertLessEqual(bot.ray_calls, 6)
        self.assertLessEqual(bot.tree_index.calls, 6)

    def test_nav_waypoint_persists_after_stagnation_trigger(self):
        nav = FakeNav()
        bot = FakeBot(tree=False)
        steerer = ContextSteerer(nav=nav)
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "energy": 0,
              "stats": {"radius": 2.5, "height": 9.0, "step_up": 1.5,
                        "max_slope_deg": 50, "walk_speed": 12, "boost_speed": 20}}
        obs = {"t": 0.0, "projectiles": [], "zone": {"center": [0, 0], "radius": 500}}
        steerer.evaluate(bot, obs, me, (100.0, 0.0), 1.0, [])
        obs["t"] = 0.9
        move2, _ = steerer.evaluate(bot, obs, me, (100.0, 0.0), 1.0, [])
        obs["t"] = 1.0
        move3, _ = steerer.evaluate(bot, obs, me, (100.0, 0.0), 1.0, [])
        self.assertEqual(nav.calls, 1)
        self.assertGreater(move2[1], 0.5)
        self.assertGreater(move3[1], 0.5)

    def test_real_arena_nav_graph_precomputed_and_fast(self):
        import mechfight as mf
        mf.run = lambda _factory: None
        from bot import Bot
        started = time.perf_counter()
        bot = Bot({"type": "hello", "seed": 1, "config": {}, "map": {"dir": ARENA}})
        startup_ms = (time.perf_counter() - started) * 1000.0
        self.assertTrue(bot.nav_graph.graph_ready)
        self.assertGreater(len(bot.nav_graph.walkable), 1000)
        cells = list(bot.nav_graph.walkable)
        start_cell = next(c for c in cells if bot.nav_graph.adjacency.get(c))
        goal_cell = max(cells, key=lambda c: abs(c[0] - start_cell[0]) + abs(c[1] - start_cell[1]))
        start_xy = bot.nav_graph._center(*start_cell)
        goal_xy = bot.nav_graph._center(*goal_cell)
        z = bot._terrain_height(*start_xy) or 0.0
        samples = []
        for i in range(5):
            t0 = time.perf_counter()
            bot.nav_graph.find_waypoint(float(i + 1), (start_xy[0], start_xy[1], z), goal_xy, 2.5, 9.0)
            samples.append((time.perf_counter() - t0) * 1000.0)
        print(f"\nV9.2 map nav: startup={startup_ms:.2f} ms, graph={bot.nav_graph.build_ms:.2f} ms, A* max={max(samples):.3f} ms")
        self.assertLess(startup_ms, 5000.0)
        self.assertLess(max(samples), 10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
