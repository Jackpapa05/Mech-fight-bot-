import math
import os
import unittest
from bot import Bot

ARENA = os.environ.get("ARENA_DIR", "/mnt/data/arena_extracted/arena")


def make_bot():
    return Bot({
        "type": "hello", "protocol": "mechfight/1", "slot": 0, "seed": 7,
        "map": {"dir": ARENA, "files": ["v2/world.json", "v2/terrain.i16"]},
        "config": {},
    })


class TestV811Corrections(unittest.TestCase):
    def test_final_zone_does_not_use_edge_waypoint(self):
        b = make_bot()
        me = {"pos": [10.0, 0.0, 0.0], "in_zone": True}
        obs = {"t": 200.0, "zone": {
            "center": [0.0, 0.0], "radius": 70.0,
            "next_center": [20.0, 0.0], "next_radius": 25.0,
            "shrink_start": 190.0, "shrink_end": 220.0,
        }}
        self.assertEqual(b._zone_goal(obs, me), (0.0, 0.0))

    def test_large_zone_waypoint_keeps_at_least_18m_margin(self):
        b = make_bot()
        me = {"pos": [200.0, 0.0, 0.0], "in_zone": True}
        obs = {"t": 200.0, "zone": {
            "center": [0.0, 0.0], "radius": 500.0,
            "next_center": [0.0, 0.0], "next_radius": 46.0,
            "shrink_start": 190.0, "shrink_end": 220.0,
        }}
        goal = b._zone_goal(obs, me)
        self.assertAlmostEqual(math.hypot(goal[0], goal[1]), 28.0, places=5)
        self.assertGreaterEqual(46.0 - math.hypot(goal[0], goal[1]), 18.0 - 1e-6)

    def test_low_hp_drop_requires_close_and_extra_enemy_separation(self):
        b = make_bot()
        zone = {"center": [0.0, 0.0], "radius": 500.0,
                "next_center": [0.0, 0.0], "next_radius": 400.0,
                "shrink_start": 1000.0, "shrink_end": 1100.0}
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "in_zone": True,
              "hp": 700.0, "max_hp": 1400.0, "energy": 30.0, "max_energy": 100.0,
              "weapons": []}
        far_drop = {"id": 20001, "pos": [100.0, 0.0, 0.0], "lands_in": 8.0, "holder": None}
        goal, _, kind = b._choose_resource_goal({"t": 0.0, "zone": zone, "drops": [far_drop]}, me, [], (0.0, 0.0))
        self.assertNotEqual(kind, "drop")
        near_drop = dict(far_drop, pos=[60.0, 0.0, 0.0])
        goal, obj, kind = b._choose_resource_goal({"t": 0.0, "zone": zone, "drops": [near_drop]}, me, [], (0.0, 0.0))
        self.assertEqual(kind, "drop")
        self.assertEqual(obj["id"], 20001)

    def test_lightning_chain_polyline_checks_every_segment(self):
        b = make_bot()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        obs = {"beams": [{"by": 5, "kind": "lightning", "age": 0.1,
                          "path": [[120.0, 120.0, 7.0], [80.0, 60.0, 6.0],
                                   [5.0, 2.0, 5.0], [-40.0, 30.0, 4.0]]}]}
        b._remember_beams(obs, me, 10.0)
        self.assertEqual(b.last_attacker_id, 5)
        self.assertIsNotNone(b.last_threat_bearing)

    def test_target_scoring_keeps_close_threat_ahead_of_distant_weak_enemy(self):
        b = make_bot()
        me = {"pos": [0.0, 0.0, 0.0], "weapons": [{"kind": "gun"}, {"kind": "laser"}]}
        close = {"pos": [25.0, 0.0, 0.0], "hp": 900.0, "weapons": ["gun"]}
        distant_weak = {"pos": [110.0, 0.0, 0.0], "hp": 300.0, "weapons": ["gun", "mortar"]}
        self.assertLess(b._target_priority_score(me, close), b._target_priority_score(me, distant_weak))

    def test_laser_floor_depends_on_lightning_threat(self):
        b = make_bot()
        me = {"pos": [0.0, 0.0, 0.0]}
        target = {"pos": [80.0, 0.0, 0.0], "weapons": ["gun", "mortar"]}
        self.assertEqual(b._laser_engagement_floor(target, [target], me), 38.0)
        lightning_target = dict(target, weapons=["gun", "lightning"])
        self.assertEqual(b._laser_engagement_floor(lightning_target, [lightning_target], me), 55.0)
        close_lightning = {"pos": [45.0, 0.0, 0.0], "weapons": ["lightning"]}
        self.assertEqual(b._laser_engagement_floor(target, [target, close_lightning], me), 55.0)

    def test_mortar_wall_impact_threatens_same_side_but_wall_blocks_other_side(self):
        b = make_bot()
        b._terrain_height = lambda x, y: 0.0
        # Simplified vertical wall at x=10 m. A shell travels from x=20 toward x=0.
        b._ray_blocked = lambda a, q: (float(a[0]) - 10.0) * (float(q[0]) - 10.0) <= 0.0 and abs(float(a[0]) - float(q[0])) > 1e-5
        projectile = {"kind": "mortar", "pos": [20.0, 0.0, 5.0], "vel": [-40.0, 0.0, -2.0]}
        same_side = {"pos": [14.0, 0.0, 0.0], "vel": [0.0, 0.0, 0.0],
                     "stats": {"height": 9.0, "radius": 2.5}, "grounded": True}
        _, urgent_same, _ = b._incoming_threat({"projectiles": [projectile]}, same_side)
        self.assertTrue(urgent_same)
        opposite_side = {"pos": [4.0, 0.0, 0.0], "vel": [0.0, 0.0, 0.0],
                         "stats": {"height": 9.0, "radius": 2.5}, "grounded": True}
        _, urgent_opposite, _ = b._incoming_threat({"projectiles": [projectile]}, opposite_side)
        self.assertFalse(urgent_opposite)


if __name__ == "__main__":
    unittest.main(verbosity=2)
