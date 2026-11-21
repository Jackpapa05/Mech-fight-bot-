"""Mech Royale survival-first bot. Standard library only."""
from __future__ import annotations

import json
import math
import os
import random
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import mechfight as mf

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def unit(x: float, y: float) -> Vec2:
    n = math.hypot(x, y)
    if n < 1e-9:
        return (0.0, 0.0)
    return (x / n, y / n)


def dist2(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def dist3(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def point_in_ring(x: float, y: float, flat: Sequence[float]) -> bool:
    """Ray-cast test for a flat [x0,y0,...] polygon ring."""
    inside = False
    n = len(flat) // 2
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = flat[2 * i], flat[2 * i + 1]
        xj, yj = flat[2 * j], flat[2 * j + 1]
        if ((yi > y) != (yj > y)):
            den = (yj - yi) or 1e-12
            xcross = (xj - xi) * (y - yi) / den + xi
            if x < xcross:
                inside = not inside
        j = i
    return inside


def solve_intercept(r: Vec3, v: Vec3, speed: float, max_t: float = 2.5) -> float:
    """Positive intercept time for a straight projectile; robust fallback to direct aim."""
    a = v[0] * v[0] + v[1] * v[1] + v[2] * v[2] - speed * speed
    b = 2.0 * (r[0] * v[0] + r[1] * v[1] + r[2] * v[2])
    c = r[0] * r[0] + r[1] * r[1] + r[2] * r[2]
    if abs(a) < 1e-8:
        t = -c / b if abs(b) > 1e-8 else 0.0
        return clamp(t, 0.0, max_t) if t > 0 else 0.0
    disc = b * b - 4.0 * a * c
    if disc < 0:
        return 0.0
    root = math.sqrt(disc)
    roots = [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]
    good = [q for q in roots if 0.01 < q <= max_t]
    return min(good) if good else 0.0


class Bot:
    name = "Oval-survivor-v1"

    def __init__(self, hello: mf.Hello):
        self.hello = hello
        self.cfg = hello.get("config", {})
        self.rng = random.Random(int(hello.get("seed", 1)))
        self.strafe_sign = -1.0 if self.rng.random() < 0.5 else 1.0
        self.last_target: Optional[int] = None
        self.last_goal: Optional[Vec2] = None
        self.last_damage_t = -999.0
        self.last_attacker_bearing: Optional[float] = None
        self.last_threat_t = -999.0
        self.prisms: List[Dict[str, Any]] = []
        self._load_map()

    def _load_map(self) -> None:
        """Load static solid geometry once. If unavailable, navigation still works."""
        map_dir = (self.hello.get("map") or {}).get("dir", "/arena")
        path = os.path.join(map_dir, "v2", "world.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                world = json.load(f)
            for p in world.get("prisms", []):
                ring = p.get("ring") or []
                if len(ring) < 6:
                    continue
                xs = ring[0::2]
                ys = ring[1::2]
                self.prisms.append({
                    "kind": p.get("kind", "building"),
                    "base": float(p.get("base", -1e6)),
                    "top": float(p.get("top", 1e6)),
                    "ring": ring,
                    "holes": p.get("holes") or [],
                    "bbox": (min(xs), min(ys), max(xs), max(ys)),
                })
        except Exception:
            self.prisms = []

    def _blocked(self, x: float, y: float, z: float, height: float) -> bool:
        # The mech is a vertical cylinder. This center-point test catches the main
        # building/wall hazards and deliberately allows walking under high bridges.
        head = z + height
        for p in self.prisms:
            x0, y0, x1, y1 = p["bbox"]
            if x < x0 - 2.5 or x > x1 + 2.5 or y < y0 - 2.5 or y > y1 + 2.5:
                continue
            if head <= p["base"] + 0.05 or z >= p["top"] - 0.05:
                continue
            if not point_in_ring(x, y, p["ring"]):
                continue
            in_hole = False
            for h in p["holes"]:
                if point_in_ring(x, y, h):
                    in_hole = True
                    break
            if not in_hole:
                return True
        return False

    def _steer(self, me: Dict[str, Any], goal: Vec2) -> Vec2:
        x, y, z = me["pos"]
        dx, dy = goal[0] - x, goal[1] - y
        ux, uy = unit(dx, dy)
        if ux == 0.0 and uy == 0.0:
            return (0.0, 0.0)
        height = float(me.get("stats", {}).get("eye_height", self.cfg.get("mech", {}).get("eye_height", 8.0)))
        base_ang = math.atan2(uy, ux)
        # Local angular search: route around nearby walls instead of repeatedly
        # pushing directly into a building. The search is small enough for 50 ms.
        offsets = [0, 22, -22, 45, -45, 70, -70, 100, -100, 135, -135, 180]
        best_score = -1e30
        best = (ux, uy)
        for off in offsets:
            a = base_ang + math.radians(off)
            vx, vy = math.cos(a), math.sin(a)
            hits = 0.0
            # Test several points along the proposed movement segment.
            for d in (4.0, 8.0, 13.0, 19.0):
                if self._blocked(x + vx * d, y + vy * d, z, height):
                    hits += (1.0 if d <= 8.0 else 0.65)
            alignment = vx * ux + vy * uy
            # Prefer progress, strongly penalize walking into solids.
            score = 3.0 * alignment - 5.0 * hits
            if score > best_score:
                best_score, best = score, (vx, vy)
        return best

    def _zone_goal(self, obs: mf.Observation, me: Dict[str, Any]) -> Vec2:
        z = obs.get("zone", {})
        pos = me["pos"]
        center = z.get("center", [0.0, 0.0])
        next_c = z.get("next_center", center)
        radius = float(z.get("radius", 9999.0))
        next_r = float(z.get("next_radius", radius))
        t = float(obs.get("t", 0.0))
        d_now = dist2(pos, center)
        d_next = dist2(pos, next_c)
        # If outside the current ring, immediately return. Otherwise drift into
        # the next ring before the damaging shrink begins.
        if d_now > radius - 8.0 or not me.get("in_zone", True):
            return (float(center[0]), float(center[1]))
        shrink_start = float(z.get("shrink_start", 1e9))
        shrink_end = float(z.get("shrink_end", 1e9))
        urgency = clamp((t - (shrink_start - 18.0)) / max(1.0, shrink_end - (shrink_start - 18.0)), 0.0, 1.0)
        # Begin moving toward the next circle when nearing its boundary or when
        # the shrink is approaching. Do not over-travel if already well inside.
        if d_next > max(15.0, next_r * 0.72) or urgency > 0.15:
            return (float(next_c[0]), float(next_c[1]))
        return (float(center[0]), float(center[1]))

    def _choose_resource_goal(self, obs: mf.Observation, me: Dict[str, Any], enemies: List[Dict[str, Any]], zone_goal: Vec2) -> Tuple[Vec2, Optional[Dict[str, Any]], str]:
        x, y, z = me["pos"]
        enemy_dists = [dist3(e["pos"], me["pos"]) for e in enemies]
        nearest_enemy = min(enemy_dists) if enemy_dists else 9999.0
        hp_frac = float(me.get("hp", 1)) / max(1.0, float(me.get("max_hp", 1)))
        candidates: List[Tuple[float, Vec2, Optional[Dict[str, Any]], str]] = []

        # Supply drops are worth a great deal, but contesting a drop is dangerous.
        for d in obs.get("drops", []) or []:
            if float(d.get("lands_in", 9999.0)) > 0.0:
                continue
            holder = d.get("holder")
            if holder is not None and holder != me.get("id"):
                continue
            p = d.get("pos", [x, y, z])
            dd = dist2((x, y), p)
            if dd > 190.0 or nearest_enemy < 38.0:
                continue
            # More attractive if damaged or short on energy/cubes.
            value = 150.0 + (1.0 - hp_frac) * 55.0 + (1.0 - float(me.get("energy", 0)) / max(1.0, float(me.get("max_energy", 100)))) * 20.0
            score = value - 0.75 * dd
            if holder == me.get("id"):
                score += 80.0
            candidates.append((score, (float(p[0]), float(p[1])), d, "drop"))

        # Loose cubes: efficient, low-commitment upgrades.
        for c in obs.get("cubes", []) or []:
            p = c.get("pos", [x, y, z])
            dd = dist2((x, y), p)
            if dd > 75.0 or nearest_enemy < 24.0:
                continue
            score = 95.0 - 1.05 * dd
            if hp_frac < 0.45:
                score -= 15.0
            candidates.append((score, (float(p[0]), float(p[1])), c, "cube"))

        # Weapon pickups, but never replace the gun and avoid duplicate weapons.
        weapons = me.get("weapons", []) or []
        held = {w.get("kind") for w in weapons if isinstance(w, dict)}
        if len(weapons) > 1 and weapons[1] is not None:
            second = weapons[1].get("kind")
        else:
            second = None
        for p in obs.get("pickups", []) or []:
            kind = p.get("kind")
            if kind == "gun" or kind in held or second is not None:
                continue
            dd = dist2((x, y), p.get("pos", [x, y, z]))
            if dd > 60.0 or nearest_enemy < 30.0:
                continue
            pref = {"laser": 82.0, "mortar": 78.0, "lightning": 72.0}.get(kind, 50.0)
            score = pref - 0.9 * dd
            candidates.append((score, (float(p["pos"][0]), float(p["pos"][1])), p, "weapon"))

        # Crates can be farmed for a cube and sometimes a weapon. Only farm when
        # there is no immediate combat pressure.
        if nearest_enemy > 85.0 and hp_frac > 0.35:
            crates = obs.get("crates", []) or []
            for c in crates:
                p = c.get("pos", [x, y, z])
                dd = dist2((x, y), p)
                if dd > 85.0:
                    continue
                score = 68.0 - 0.55 * dd
                candidates.append((score, (float(p[0]), float(p[1])), c, "crate"))

        if candidates:
            candidates.sort(key=lambda q: q[0], reverse=True)
            score, p, obj, kind = candidates[0]
            # Never abandon zone safety for an only marginal resource.
            if score > 14.0:
                if kind == "drop" and dist2(p, zone_goal) > 210.0 and not me.get("in_zone", True):
                    return zone_goal, None, "zone"
                return p, obj, kind
        return zone_goal, None, "zone"

    def _incoming_threat(self, obs: mf.Observation, me: Dict[str, Any]) -> Tuple[Vec2, bool, bool]:
        """Return a lateral escape vector, whether to boost, and whether to jump."""
        px, py, pz = me["pos"]
        vx0, vy0, vz0 = me.get("vel", [0.0, 0.0, 0.0])
        threat_x = threat_y = 0.0
        urgent = False
        jump = False
        for p in obs.get("projectiles", []) or []:
            pos = p.get("pos", [0.0, 0.0, 0.0])
            vel = p.get("vel", [0.0, 0.0, 0.0])
            # Mortar shells accelerate downward; other listed projectiles fly straight.
            kind = p.get("kind", "gun")
            best_t = 0.0
            best_d = 1e9
            best_delta = (0.0, 0.0)
            for t in (0.1, 0.2, 0.35, 0.5, 0.7, 0.9):
                sx = pos[0] + vel[0] * t
                sy = pos[1] + vel[1] * t
                sz = pos[2] + vel[2] * t
                if kind == "mortar":
                    sz -= 0.5 * float(self.cfg.get("weapons", {}).get("mortar", {}).get("gravity", 22.0)) * t * t
                mx = px + vx0 * t
                my = py + vy0 * t
                mz = pz + vz0 * t + (0.0 if me.get("grounded", True) else -3.0 * t * t)
                dd = math.sqrt((sx - mx) ** 2 + (sy - my) ** 2 + (sz - (mz + 4.5)) ** 2)
                if dd < best_d:
                    best_d, best_t, best_delta = dd, t, (mx - sx, my - sy)
            radius = 9.0 if kind == "mortar" else 4.5
            if best_d < radius and best_t <= 0.7:
                ex, ey = unit(best_delta[0], best_delta[1])
                if ex == 0.0 and ey == 0.0:
                    # Side-step relative to projectile path.
                    ex, ey = unit(-vel[1], vel[0])
                threat_x += ex * (radius - best_d + 1.0) / max(0.12, best_t)
                threat_y += ey * (radius - best_d + 1.0) / max(0.12, best_t)
                urgent = True
                if kind == "mortar" and best_t < 0.55 and me.get("grounded", False):
                    jump = True
        if urgent:
            return unit(threat_x, threat_y), True, jump
        return (0.0, 0.0), False, False

    def _target_aim(self, me: Dict[str, Any], target: Dict[str, Any], weapon: Dict[str, Any], kind: str) -> Tuple[float, float, float]:
        mx, my, mz = me["pos"]
        tx, ty, tz = target["pos"]
        tv = target.get("vel", [0.0, 0.0, 0.0])
        mv = me.get("vel", [0.0, 0.0, 0.0])
        cubes = float(target.get("cubes", 0.0))
        target_center_z = tz + 4.5 * (1.0 + 0.05 * cubes)
        muzzle_z = mz + float(me.get("stats", {}).get("muzzle_height", 7.0))
        speed = float(weapon.get("stats", {}).get("speed", 252.0))
        if kind == "gun":
            r = (tx - mx, ty - my, target_center_z - muzzle_z)
            rv = (tv[0] - mv[0], tv[1] - mv[1], tv[2] - mv[2])
            t = solve_intercept(r, rv, speed)
            tx += tv[0] * t
            ty += tv[1] * t
            target_center_z += tv[2] * t
        else:
            # Hitscan laser/lightning aim at the current target center.
            t = 0.0
        dx, dy = tx - mx, ty - my
        horizontal = max(0.01, math.hypot(dx, dy))
        yaw = math.atan2(dy, dx)
        pitch = math.atan2(target_center_z - muzzle_z, horizontal)
        return yaw, pitch, horizontal

    def _mortar_aim(self, me: Dict[str, Any], target: Dict[str, Any], weapon: Dict[str, Any]) -> Tuple[float, float, float]:
        mx, my, mz = me["pos"]
        tx, ty, tz = target["pos"]
        tv = target.get("vel", [0.0, 0.0, 0.0])
        dx, dy = tx - mx, ty - my
        R = max(0.1, math.hypot(dx, dy))
        yaw = math.atan2(dy + tv[1] * min(0.8, R / 72.0), dx + tv[0] * min(0.8, R / 72.0))
        muzzle_z = mz + float(me.get("stats", {}).get("muzzle_height", 7.0)) + 2.5
        target_z = tz + 4.5
        h = target_z - muzzle_z
        v = float(weapon.get("stats", {}).get("speed", 72.0))
        g = float(self.cfg.get("weapons", {}).get("mortar", {}).get("gravity", 22.0))
        disc = v ** 4 - g * (g * R * R + 2.0 * h * v * v)
        if disc <= 0:
            pitch = math.radians(42.0)
        else:
            # Low trajectory is more accurate; splash provides tolerance.
            tan_theta = (v * v - math.sqrt(disc)) / (g * R)
            pitch = math.atan(tan_theta)
        return yaw, clamp(pitch, -0.2, 1.15), R

    def _choose_upgrade(self, offer: Dict[str, Any], me: Dict[str, Any]) -> int:
        choices = offer.get("choices", [])
        if not choices:
            return 0
        hp_frac = float(me.get("hp", 1)) / max(1.0, float(me.get("max_hp", 1)))
        energy_frac = float(me.get("energy", 0)) / max(1.0, float(me.get("max_energy", 100)))
        has = {u for u in (me.get("upgrades", []) or [])}
        values = {
            "armor": 10.0,
            "plating": 9.5,
            "nanites": 8.8,
            "servos": 8.2,
            "sensors": 8.0,
            "jets": 7.4,
            "capacitor": 7.0,
            "reactor": 6.7,
            "gyros": 6.5,
            "gun_damage": 7.6,
            "gun_rate": 7.3,
            "gun_velocity": 6.9,
            "gun_mag": 5.8,
            "mortar_reload": 7.2,
            "mortar_splash": 7.0,
            "mortar_velocity": 6.2,
            "laser_damage": 8.0,
            "laser_charge": 7.7,
            "laser_pierce": 6.5,
            "lightning_efficiency": 8.1,
            "lightning_range": 7.2,
            "lightning_chain": 7.0,
        }
        best_i, best_v = 0, -1e9
        for i, c in enumerate(choices):
            cid = c.get("id", "")
            v = values.get(cid, 5.0)
            if cid == "armor" and hp_frac < 0.6:
                v += 2.0
            if cid == "plating" and hp_frac < 0.85:
                v += 1.8
            if cid == "nanites" and hp_frac < 0.7:
                v += 1.5
            if cid in ("capacitor", "reactor", "jets") and energy_frac < 0.35:
                v += 1.4
            if cid == "sensors" and float(me.get("t", 0)) < 180:
                v += 0.5
            if cid.startswith("gun_") and hp_frac < 0.4:
                v -= 0.3
            if cid in has:
                v -= 0.5
            if v > best_v:
                best_i, best_v = i, v
        return best_i

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        t = float(obs.get("t", 0.0))
        enemies = [m for m in (obs.get("mechs", []) or []) if m.get("kind") == "mech"]
        enemies.sort(key=lambda e: dist3(e["pos"], me["pos"]))
        nearby = [e for e in enemies if dist3(e["pos"], me["pos"]) < 100.0]
        hp_frac = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        energy = float(me.get("energy", 0.0))
        max_energy = max(1.0, float(me.get("max_energy", 100.0)))

        action: mf.Action = {"tick": obs["tick"]}
        if obs.get("offer"):
            action["pick"] = self._choose_upgrade(obs["offer"], me)

        # Choose a combat target; close and weakened opponents are more valuable.
        target = None
        if enemies:
            def target_score(e: Dict[str, Any]) -> float:
                d = dist3(e["pos"], me["pos"])
                ehp = float(e.get("hp", e.get("max_hp", 900.0)))
                return d + 0.018 * ehp - (10.0 if e.get("charging") else 0.0)
            target = min(enemies, key=target_score)
            self.last_target = int(target.get("id", -1))

        zone_goal = self._zone_goal(obs, me)
        resource_goal, resource_obj, resource_kind = self._choose_resource_goal(obs, me, enemies, zone_goal)
        goal = resource_goal

        # If a crate was selected, shoot it while moving toward it. Crate fire is
        # deliberately lower priority than any visible hostile mech.
        utility_target = None
        if target is None and resource_kind == "crate":
            utility_target = resource_obj

        # Aim/weapon choice.
        aim_yaw = math.atan2(zone_goal[1] - y, zone_goal[0] - x)
        aim_pitch = 0.0
        fire = [False, False]
        weapons = me.get("weapons", []) or []
        w0 = weapons[0] if len(weapons) > 0 and isinstance(weapons[0], dict) else None
        w1 = weapons[1] if len(weapons) > 1 and isinstance(weapons[1], dict) else None
        current_target = target

        if current_target is not None:
            d = dist3(current_target["pos"], me["pos"])
            second_kind = w1.get("kind") if w1 else None
            if second_kind == "mortar" and 30.0 < d < 220.0:
                aim_yaw, aim_pitch, hrange = self._mortar_aim(me, current_target, w1)
                err = abs(wrap(aim_yaw - float(me.get("aim", [aim_yaw, 0.0])[0])))
                if float(w1.get("cooldown", 0.0)) <= 0.02 and err < 0.35:
                    fire[1] = True
            elif second_kind == "laser" and d > 38.0 and not any("lightning" in (e.get("weapons") or []) for e in nearby if dist3(e["pos"], me["pos"]) < 65.0):
                aim_yaw, aim_pitch, hrange = self._target_aim(me, current_target, w1, "laser")
                charge = float(w1.get("charge", 0.0))
                cooldown = float(w1.get("cooldown", 0.0))
                if cooldown <= 0.02:
                    # Charge to ~0.65 s then release. The full-charge auto-fire
                    # is avoided so the beam is released on a deliberate tick.
                    fire[1] = charge < 0.64
                # Gun and laser share aim; a gun shot is also useful while the
                # laser charges, but only when the enemy is in gun range.
                if w0 and d < float(w0.get("stats", {}).get("range", 230.0)):
                    gy, gp, _ = self._target_aim(me, current_target, w0, "gun")
                    if abs(wrap(gy - aim_yaw)) < 0.07 and abs(gp - aim_pitch) < 0.07:
                        if float(w0.get("reload", 0.0)) <= 0.0 and float(w0.get("ammo", 1.0)) > 0:
                            fire[0] = True
            elif second_kind == "lightning" and d <= float(w1.get("stats", {}).get("range", 45.0)) * 1.08:
                # Lightning is instant and only cares about yaw/cone.
                aim_yaw, aim_pitch, hrange = self._target_aim(me, current_target, w1, "lightning")
                yaw_err = abs(wrap(aim_yaw - float(me.get("aim", [aim_yaw, 0.0])[0])))
                if yaw_err < math.radians(23.0) and float(w1.get("cooldown", 0.0)) <= 0.02 and energy >= float(w1.get("stats", {}).get("energy", 3.0)):
                    fire[1] = True
                if w0 and d < float(w0.get("stats", {}).get("range", 230.0)):
                    gy, gp, _ = self._target_aim(me, current_target, w0, "gun")
                    if abs(wrap(gy - aim_yaw)) < 0.08 and abs(gp - aim_pitch) < 0.08:
                        if float(w0.get("reload", 0.0)) <= 0.0 and float(w0.get("ammo", 1.0)) > 0:
                            fire[0] = True
            else:
                # Gun-only attack, including when a secondary is out of range.
                if w0:
                    aim_yaw, aim_pitch, hrange = self._target_aim(me, current_target, w0, "gun")
                    yaw_err = abs(wrap(aim_yaw - float(me.get("aim", [aim_yaw, 0.0])[0])))
                    pitch_err = abs(aim_pitch - float(me.get("aim", [aim_yaw, 0.0])[1]))
                    if hrange <= float(w0.get("stats", {}).get("range", 230.0)) and yaw_err < 0.18 and pitch_err < 0.18:
                        if float(w0.get("ammo", 0.0)) > 0 and float(w0.get("reload", 0.0)) <= 0.0:
                            fire[0] = True
                # If the secondary can contribute at short range and is not a
                # laser/mortar, use it when aligned.
                if w1 and w1.get("kind") == "lightning" and d <= 45.0:
                    ly, lp, _ = self._target_aim(me, current_target, w1, "lightning")
                    if abs(wrap(ly - float(me.get("aim", [ly, 0.0])[0]))) < math.radians(23) and float(w1.get("cooldown", 0.0)) <= 0.02 and energy >= 3.0:
                        aim_yaw, aim_pitch = ly, lp
                        fire[1] = True
        elif utility_target is not None and w0:
            # Crate center is roughly 1.2 m above its base; it is stationary.
            p = utility_target.get("pos", [x, y, z])
            dx, dy = p[0] - x, p[1] - y
            aim_yaw = math.atan2(dy, dx)
            aim_pitch = math.atan2((p[2] + 1.2) - (z + float(me.get("stats", {}).get("muzzle_height", 7.0))), max(0.1, math.hypot(dx, dy)))
            err = abs(wrap(aim_yaw - float(me.get("aim", [aim_yaw, 0.0])[0])))
            if math.hypot(dx, dy) < float(w0.get("stats", {}).get("range", 230.0)) and err < 0.18:
                if float(w0.get("ammo", 0.0)) > 0 and float(w0.get("reload", 0.0)) <= 0.0:
                    fire[0] = True
        elif not enemies:
            # No visible target: turn toward the freshest directional threat.
            bearing = None
            for ev in reversed(obs.get("events", []) or []):
                if ev.get("type") == "damaged" and ev.get("bearing") is not None and ev.get("weapon") != "zone":
                    bearing = float(ev["bearing"])
                    break
            if bearing is None:
                sounds = [s for s in (obs.get("sounds", []) or []) if s.get("kind") in ("gun", "mortar", "explosion", "laser", "laser_charge", "lightning") and float(s.get("age", 99.0)) < 0.45]
                if sounds:
                    sounds.sort(key=lambda s: float(s.get("age", 99.0)))
                    bearing = float(sounds[0].get("bearing", aim_yaw))
            if bearing is not None:
                aim_yaw, aim_pitch = bearing, 0.0

        # Reload early when there is no magazine left. Never spam reload while one is active.
        if w0 and float(w0.get("ammo", 1.0)) <= 0.0 and float(w0.get("reload", 0.0)) <= 0.0:
            action["reload"] = True

        # Movement: resource/zone objective, local wall avoidance, and threat response.
        move = self._steer(me, goal)
        dodge, urgent, jump = self._incoming_threat(obs, me)
        boost = False
        if urgent:
            move = unit(move[0] * 0.25 + dodge[0] * 1.5, move[1] * 0.25 + dodge[1] * 1.5)
            boost = energy > 12.0
        else:
            # Avoid being surrounded or chased when health is low. In healthier
            # states, orbit the nearest attacker to make leading shots harder.
            if nearby:
                nearest = min(nearby, key=lambda e: dist3(e["pos"], me["pos"]))
                ex, ey = unit(x - nearest["pos"][0], y - nearest["pos"][1])
                nd = dist2((x, y), nearest["pos"])
                if hp_frac < 0.58 or len(nearby) >= 3:
                    weight = 1.2 if hp_frac < 0.58 else 0.75
                    move = unit(move[0] + ex * weight, move[1] + ey * weight)
                elif nd < 85.0:
                    tangent = (-ey * self.strafe_sign, ex * self.strafe_sign)
                    move = unit(move[0] * 0.65 + tangent[0] * 0.75, move[1] * 0.65 + tangent[1] * 0.75)
            # Use boost sparingly: zone escape and short high-value rotations.
            dist_goal = dist2((x, y), goal)
            outside = not me.get("in_zone", True)
            boost = energy > 48.0 and (outside or (dist_goal > 90.0 and energy > 72.0))
            if hp_frac < 0.3 and nearby and energy > 18.0:
                boost = True
        # A mech that gets damaged from behind should turn its torso toward the source.
        for ev in reversed(obs.get("events", []) or []):
            if ev.get("type") == "damaged" and ev.get("bearing") is not None:
                if ev.get("rear") or target is None:
                    aim_yaw, aim_pitch = float(ev["bearing"]), 0.0
                break

        action.update({
            "move": [float(move[0]), float(move[1])],
            "boost": bool(boost),
            "jump": bool(jump and me.get("grounded", False)),
            "aim": [float(aim_yaw), float(clamp(aim_pitch, -0.7, 1.3))],
            "fire": [bool(fire[0]), bool(fire[1])],
        })

        # Explicitly take nearby weapon pickups; movement goal gets us there first.
        if resource_kind == "weapon" and resource_obj is not None:
            p = resource_obj.get("pos", [x, y, z])
            if dist2((x, y), p) <= float(self.cfg.get("loot", {}).get("pickup_radius", 4.0)) + 0.5 and abs(z - p[2]) <= 4.0:
                action["take"] = resource_obj.get("id")

        # Keep debug output small; this is useful in the spectator/debug tooling.
        if target is not None:
            tp = target["pos"]
            mf.draw.line([x, y, z + 7.0], [tp[0], tp[1], tp[2] + 4.5], "#ff5040")
        mf.draw.point([goal[0], goal[1], z], "#40c0ff", 5)
        mf.draw.label(f"hp {int(me.get('hp', 0))} | {len(enemies)} seen | {resource_kind}")
        return action


mf.run(Bot)
