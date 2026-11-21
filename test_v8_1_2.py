import math
import os
import unittest
from bot import Bot

ARENA = os.environ.get("ARENA_DIR", "/mnt/data/arena_extracted/arena")


def make_bot():
    return Bot({
        "type": "hello", "protocol": "mechfight/1", "slot": 0, "seed": 11,
        "map": {"dir": ARENA, "files": ["v2/world.json", "v2/terrain.i16"]},
        "config": {},
    })


class TestV812Corrections(unittest.TestCase):
    def test_zone_goal_rotates_around_blocked_inner_ring_point(self):
        b = make_bot()
        me = {"pos": [200.0, 0.0, 0.0], "in_zone": True}
        obs = {"t": 200.0, "zone": {
            "center": [0.0, 0.0], "radius": 500.0,
            "next_center": [0.0, 0.0], "next_radius": 46.0,
            "shrink_start": 190.0, "shrink_end": 220.0,
        }}
        # The nominal waypoint at (28, 0) is blocked; alternate ring samples
        # should be checked and a clear point selected at the same radius.
        b._zone_waypoint_clear = lambda x, y, me: math.hypot(x - 28.0, y) > 0.5
        goal = b._zone_goal(obs, me)
        self.assertGreater(math.hypot(*goal), 27.999)
        self.assertLess(math.hypot(*goal), 28.001)
        self.assertGreater(abs(goal[1]), 1.0)

    def test_zone_goal_falls_back_to_center_if_all_ring_samples_blocked(self):
        b = make_bot()
        b._zone_waypoint_clear = lambda x, y, me: False
        me = {"pos": [200.0, 0.0, 0.0], "in_zone": True}
        obs = {"t": 200.0, "zone": {
            "center": [3.0, 4.0], "radius": 500.0,
            "next_center": [10.0, 20.0], "next_radius": 100.0,
            "shrink_start": 190.0, "shrink_end": 220.0,
        }}
        self.assertEqual(b._zone_goal(obs, me), (10.0, 20.0))

    def test_target_priority_bonus_is_modest(self):
        b = make_bot()
        me = {"pos": [0.0, 0.0, 0.0], "weapons": [{"kind": "laser"}]}
        close_threat = {"pos": [20.0, 0.0, 0.0], "hp": 900.0, "weapons": ["gun"]}
        distant_mortar = {"pos": [55.0, 0.0, 0.0], "hp": 900.0, "weapons": ["gun", "mortar"]}
        self.assertLess(b._target_priority_score(me, close_threat),
                        b._target_priority_score(me, distant_mortar))

    def test_low_hp_target_bonus_can_prioritize_nearby_finish(self):
        b = make_bot()
        me = {"pos": [0.0, 0.0, 0.0], "weapons": [{"kind": "gun"}]}
        healthy = {"pos": [75.0, 0.0, 0.0], "hp": 900.0, "weapons": ["gun"]}
        weak = {"pos": [75.0, 0.0, 0.0], "hp": 300.0, "weapons": ["gun"]}
        self.assertLess(b._target_priority_score(me, weak),
                        b._target_priority_score(me, healthy))

    def test_laser_floor_uses_lightning_counterplay(self):
        b = make_bot()
        me = {"pos": [0.0, 0.0, 0.0]}
        mortar_target = {"pos": [80.0, 0.0, 0.0], "weapons": ["gun", "mortar"]}
        lightning_target = {"pos": [80.0, 0.0, 0.0], "weapons": ["gun", "lightning"]}
        close_lightning = {"pos": [45.0, 0.0, 0.0], "weapons": ["lightning"]}
        self.assertEqual(b._laser_engagement_floor(mortar_target, [mortar_target], me), 38.0)
        self.assertEqual(b._laser_engagement_floor(lightning_target, [lightning_target], me), 55.0)
        self.assertEqual(b._laser_engagement_floor(mortar_target, [mortar_target, close_lightning], me), 55.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
