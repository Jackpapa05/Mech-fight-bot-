"""Focused tests for V8's mortar CPA and beam-threat memory changes."""
from pathlib import Path
import math
import sys

BOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BOT_DIR))
src = (BOT_DIR / "bot.py").read_text(encoding="utf-8")
src = src.rsplit("\nmf.run(Bot)", 1)[0] + "\n"
ns = {"__name__": "v8_test_module"}
exec(compile(src, str(BOT_DIR / "bot.py"), "exec"), ns)
Bot = ns["Bot"]


def make_bot():
    bot = Bot.__new__(Bot)
    bot.cfg = {
        "weapons": {"mortar": {"gravity": 22.0, "splash_radius": 7.0}},
        "projectile": {"gun_radius": 0.3, "npc_radius": 0.3},
    }
    bot.last_threat_t = -999.0
    bot.last_threat_bearing = None
    bot.last_attacker_bearing = None
    bot.last_threat_kind = None
    bot.last_threat_dist = "far"
    bot.last_attacker_id = None
    return bot


def test_mortar_cpa_uses_refined_distance():
    bot = make_bot()
    bot._ray_blocked = lambda a, b: False
    me = {
        "pos": [0.0, 0.0, 0.0],
        "vel": [0.0, 0.0, 0.0],
        "stats": {"height": 9.0, "radius": 2.5},
        "grounded": False,
    }
    t_star = 0.225
    g = 22.0
    projectile = {
        "kind": "mortar",
        "pos": [-72.0 * t_star, 8.95, 4.5 + 0.5 * g * t_star * t_star],
        "vel": [72.0, 0.0, 0.0],
    }
    _, urgent, _ = bot._incoming_threat({"projectiles": [projectile]}, me)
    assert urgent, "refined 8.95 m pass should cross the 9 m mortar-danger threshold"


def test_wall_blocked_linear_projectile_does_not_trigger_dodge():
    bot = make_bot()
    bot._ray_blocked = lambda a, b: True
    me = {
        "pos": [0.0, 0.0, 0.0],
        "vel": [0.0, 0.0, 0.0],
        "stats": {"height": 9.0, "radius": 2.5},
        "grounded": True,
    }
    projectile = {
        "kind": "gun",
        "pos": [-20.0, 0.0, 4.5],
        "vel": [100.0, 0.0, 0.0],
    }
    _, urgent, _ = bot._incoming_threat({"projectiles": [projectile]}, me)
    assert not urgent, "a straight projectile path blocked by a solid should not cause a dodge"


def test_beam_records_source_direction_and_id():
    bot = make_bot()
    me = {"pos": [0.0, 0.0, 0.0]}
    obs = {
        "beams": [{
            "by": 7,
            "kind": "laser",
            "age": 0.1,
            "path": [[10.0, 10.0, 8.0], [100.0, 100.0, 8.0]],
        }]
    }
    bot._remember_beams(obs, me, 10.0)
    assert bot.last_attacker_id == 7
    assert bot.last_threat_kind == "laser"
    assert bot.last_threat_dist == "near"
    assert abs(bot.last_threat_bearing - math.pi / 4.0) < 1e-9
    assert abs(bot.last_threat_t - 9.9) < 1e-9


def test_old_sound_does_not_overwrite_newer_beam():
    bot = make_bot()
    bot.last_threat_t = 9.9
    bot.last_threat_bearing = 1.2
    bot.last_threat_kind = "laser"
    bot.last_threat_dist = "near"
    me = {"pos": [0.0, 0.0, 0.0]}
    threat = bot._sound_threat({
        "t": 10.0,
        "sounds": [{"kind": "mortar", "age": 0.8, "bearing": -1.0, "dist": "mid"}],
    }, me)
    assert bot.last_threat_kind == "laser"
    assert abs(bot.last_threat_bearing - 1.2) < 1e-9
    assert threat is not None


if __name__ == "__main__":
    tests = [
        test_mortar_cpa_uses_refined_distance,
        test_wall_blocked_linear_projectile_does_not_trigger_dodge,
        test_beam_records_source_direction_and_id,
        test_old_sound_does_not_overwrite_newer_beam,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"{len(tests)} focused tests passed")
