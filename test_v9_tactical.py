import math
import unittest

from v9_core import (
    ThreatTracker, choose_defensive_aim, choose_supply_drop_goal,
    should_suppress_optional_fire,
)


class TestV9TacticalHelpers(unittest.TestCase):
    def test_supply_drop_pre_rotation_when_safe(self):
        me = {
            "id": 0, "pos": [0.0, 0.0, 0.0], "hp": 700.0, "max_hp": 1400.0,
            "energy": 30.0, "max_energy": 100.0, "cubes": 3,
            "stats": {"walk_speed": 11.7, "boost_speed": 19.5},
        }
        obs = {
            "t": 70.0,
            "zone": {"next_center": [0.0, 0.0], "next_radius": 300.0},
            "drops": [{"id": 20001, "pos": [100.0, 0.0, 0.0], "lands_in": 10.0, "holder": None}],
        }
        selected = choose_supply_drop_goal(obs, me, [])
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0], (100.0, 0.0))
        self.assertGreater(selected[1], 1.0)

    def test_supply_drop_avoids_enemy_holder_and_contested_ring(self):
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "hp": 500.0, "max_hp": 1400.0, "energy": 20.0, "max_energy": 100.0, "cubes": 0}
        obs = {"zone": {"next_center": [0.0, 0.0], "next_radius": 300.0}, "drops": [
            {"id": 20001, "pos": [80.0, 0.0, 0.0], "lands_in": 0.0, "holder": 4}
        ]}
        self.assertIsNone(choose_supply_drop_goal(obs, me, []))
        obs["drops"][0]["holder"] = None
        threats = [{"id": 4, "pos": [82.0, 0.0, 0.0], "last_seen_t": 10.0}]
        obs["t"] = 10.2
        self.assertIsNone(choose_supply_drop_goal(obs, me, threats))

    def test_supply_drop_rejects_outside_next_zone(self):
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "hp": 500.0, "max_hp": 1400.0, "energy": 20.0, "max_energy": 100.0, "cubes": 0}
        obs = {"zone": {"next_center": [0.0, 0.0], "next_radius": 50.0},
               "drops": [{"id": 20001, "pos": [100.0, 0.0, 0.0], "lands_in": 0.0, "holder": None}]}
        self.assertIsNone(choose_supply_drop_goal(obs, me, []))

    def test_optional_fire_suppressed_but_visible_enemy_not_suppressed(self):
        damaged = {"hp": 1000.0, "max_hp": 1400.0}
        self.assertTrue(should_suppress_optional_fire(damaged, has_visible_enemy=False))
        self.assertFalse(should_suppress_optional_fire(damaged, has_visible_enemy=True))
        healthy = {"hp": 1300.0, "max_hp": 1400.0}
        self.assertFalse(should_suppress_optional_fire(healthy, has_visible_enemy=False))

    def test_defensive_aim_uses_fresh_evidence_not_stale_memory(self):
        tracker = ThreatTracker()
        tracker.defensive_bearing = 1.0
        tracker.defensive_bearing_t = 8.0
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        self.assertIsNone(choose_defensive_aim(10.0, me, tracker, []))
        tracker.defensive_bearing_t = 9.5
        self.assertAlmostEqual(choose_defensive_aim(10.0, me, tracker, []), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
