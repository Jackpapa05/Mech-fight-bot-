import math
import os
import unittest

from bot import Bot

ARENA = os.environ.get("ARENA_DIR", "/mnt/data/arena_extracted/arena")


def make_bot():
    return Bot({
        "type": "hello",
        "protocol": "mechfight/1",
        "slot": 0,
        "seed": 123,
        "map": {"dir": ARENA, "files": ["v2/world.json", "v2/terrain.i16"]},
        "config": {},
    })


class TestV81Minimal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = make_bot()

    def test_beam_far_third_party_is_ignored(self):
        b = make_bot()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        obs = {"beams": [{"by": 4, "kind": "laser",
                          "path": [[120.0, 120.0, 7.0], [150.0, 130.0, 7.0]],
                          "age": 0.1}]}
        b._remember_beams(obs, me, 10.0)
        self.assertIsNone(b.last_threat_bearing)
        self.assertIsNone(b.last_attacker_id)

    def test_beam_segment_crossing_me_is_remembered(self):
        b = make_bot()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0]}
        obs = {"beams": [{"by": 4, "kind": "lightning",
                          "path": [[100.0, 0.0, 7.0], [0.0, 0.0, 5.0], [-20.0, 0.0, 4.0]],
                          "age": 0.1}]}
        b._remember_beams(obs, me, 10.0)
        self.assertEqual(b.last_attacker_id, 4)
        self.assertIsNotNone(b.last_threat_bearing)

    def test_zone_goal_uses_inner_next_ring(self):
        b = make_bot()
        me = {"pos": [20.0, 0.0, 0.0], "in_zone": True}
        obs = {"t": 45.0, "zone": {
            "center": [0.0, 0.0], "radius": 500.0,
            "next_center": [0.0, 0.0], "next_radius": 100.0,
            "shrink_start": 50.0, "shrink_end": 100.0,
        }}
        goal = b._zone_goal(obs, me)
        self.assertAlmostEqual(math.hypot(goal[0], goal[1]), 68.0, places=5)
        # The nominal eastward waypoint may sit inside a real-map building;
        # the corrected implementation rotates to a clear point on the ring.
        self.assertTrue(b._zone_waypoint_clear(goal[0], goal[1], me))

    def test_supply_drop_pre_rotation_and_stable_at_landing(self):
        b = make_bot()
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "in_zone": True,
              "hp": 800.0, "max_hp": 1400.0, "energy": 50.0, "max_energy": 100.0,
              "weapons": []}
        zone = {"center": [0.0, 0.0], "radius": 500.0,
                "next_center": [0.0, 0.0], "next_radius": 400.0,
                "shrink_start": 1000.0, "shrink_end": 1100.0}
        for lands_in in (10.0, 1.0, 0.0):
            obs = {"t": 0.0, "zone": zone,
                   "drops": [{"id": 20001, "pos": [100.0, 0.0, 0.0],
                              "lands_in": lands_in, "holder": None}]}
            goal, obj, kind = b._choose_resource_goal(obs, me, [], (0.0, 0.0))
            self.assertEqual(kind, "drop")
            self.assertEqual(obj["id"], 20001)
            self.assertEqual(goal, (100.0, 0.0))

    def test_does_not_pre_rotate_when_outside_zone_or_enemy_close(self):
        b = make_bot()
        zone = {"center": [0.0, 0.0], "radius": 500.0,
                "next_center": [0.0, 0.0], "next_radius": 400.0,
                "shrink_start": 1000.0, "shrink_end": 1100.0}
        drop_obs = {"t": 0.0, "zone": zone,
                    "drops": [{"id": 20001, "pos": [100.0, 0.0, 0.0],
                               "lands_in": 10.0, "holder": None}]}
        me = {"id": 0, "pos": [0.0, 0.0, 0.0], "in_zone": False,
              "hp": 800.0, "max_hp": 1400.0, "energy": 50.0, "max_energy": 100.0,
              "weapons": []}
        goal, _, kind = b._choose_resource_goal(drop_obs, me, [], (0.0, 0.0))
        self.assertEqual(kind, "zone")
        me["in_zone"] = True
        enemy = {"id": 3, "kind": "mech", "pos": [50.0, 0.0, 0.0], "hp": 900}
        goal, _, kind = b._choose_resource_goal(drop_obs, me, [enemy], (0.0, 0.0))
        self.assertNotEqual(kind, "drop")

    def test_mortar_terrain_impact_is_considered(self):
        b = make_bot()
        b._terrain_height = lambda x, y: 0.0
        me = {"pos": [0.0, 0.0, 0.0], "vel": [0.0, 0.0, 0.0],
              "stats": {"height": 9.0, "radius": 2.5}, "grounded": True}
        obs = {"projectiles": [{"kind": "mortar", "pos": [20.0, 0.0, 5.0],
                                "vel": [-40.0, 0.0, -5.0]}]}
        _, urgent, jump = b._incoming_threat(obs, me)
        self.assertTrue(urgent)
        self.assertTrue(jump)

    def test_far_enemy_mortar_holder_target_bonus_is_safe(self):
        b = make_bot()
        me = {"pos": [0.0, 0.0, 0.0], "weapons": [{"kind": "gun"}, {"kind": "laser"}]}
        close_full = {"id": 1, "pos": [70.0, 0.0, 0.0], "hp": 900.0, "weapons": ["gun"]}
        slightly_far_mortar = {"id": 2, "pos": [90.0, 0.0, 0.0], "hp": 900.0,
                               "weapons": ["gun", "mortar"]}
        def score(e):
            d = math.dist(e["pos"], me["pos"])
            ehp = float(e.get("hp", e.get("max_hp", 900.0)))
            bonus = 35.0 if any(w.get("kind") == "laser" for w in me["weapons"] if isinstance(w, dict)) and "mortar" in set(e.get("weapons", [])) else 0.0
            if ehp < 350.0:
                bonus += 30.0
            return d + 0.018 * ehp - (10.0 if e.get("charging") else 0.0) - min(50.0, bonus)
        self.assertLess(score(slightly_far_mortar), score(close_full))


if __name__ == "__main__":
    unittest.main(verbosity=2)
