"""Mech Royale survival-first bot. Standard library only."""
from __future__ import annotations

import json
import math
import os
import random
import time
from array import array
from typing import Any, Dict, List, Optional, Sequence, Tuple

import mechfight as mf
from v9_core import (CoarseNavGraph, ContextSteerer, ThreatTracker, TreeIndex,
                     choose_defensive_aim, choose_supply_drop_goal,
                     should_suppress_optional_fire)

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


def point_segment_distance(x: float, y: float, ax: float, ay: float,
                           bx: float, by: float) -> float:
    """Minimum 2-D distance from a point to a finite segment."""
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den <= 1e-12:
        return math.hypot(x - ax, y - ay)
    u = clamp(((x - ax) * dx + (y - ay) * dy) / den, 0.0, 1.0)
    return math.hypot(x - (ax + u * dx), y - (ay + u * dy))


def ring_edge_distance(x: float, y: float, flat: Sequence[float]) -> float:
    n = len(flat) // 2
    if n < 2:
        return 1e9
    best = 1e9
    j = n - 1
    for i in range(n):
        best = min(best, point_segment_distance(
            x, y, float(flat[2*j]), float(flat[2*j+1]),
            float(flat[2*i]), float(flat[2*i+1])))
        j = i
    return best


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
    name = "Oval-Ghost-v9.2-latency-safe"

    def __init__(self, hello: mf.Hello):
        self.hello = hello
        self.cfg = hello.get("config", {})
        self.rng = random.Random(int(hello.get("seed", 1)))
        self.strafe_sign = -1.0 if self.rng.random() < 0.5 else 1.0
        self.last_target: Optional[int] = None
        self.last_goal: Optional[Vec2] = None
        self.last_damage_t = -999.0
        self.last_attacker_id: Optional[int] = None
        self.last_attacker_bearing: Optional[float] = None
        self.last_threat_t = -999.0
        self.last_threat_bearing: Optional[float] = None
        self.last_threat_kind: Optional[str] = None
        self.last_threat_dist: str = "far"
        self.prisms: List[Dict[str, Any]] = []
        self.prism_bins: Dict[Tuple[int, int], List[int]] = {}
        self.bin_size = 32.0
        self.terrain_values: Optional[array] = None
        self.terrain_meta: Dict[str, Any] = {}
        self.tree_index: Optional[TreeIndex] = None
        self.threat_tracker = ThreatTracker()
        self.nav_graph = CoarseNavGraph(self)
        self.context_steerer = ContextSteerer(nav=self.nav_graph)
        self._load_map()

    def _load_map(self) -> None:
        """Load static solid geometry once. If unavailable, navigation still works."""
        map_dir = (self.hello.get("map") or {}).get("dir", "/arena")
        path = os.path.join(map_dir, "v2", "world.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                world = json.load(f)
            self.tree_index = TreeIndex(world)
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
            # Index static structures once at startup. The map is identical in
            # every match, so per-tick collision queries can examine only nearby
            # prisms rather than all 259 structures.
            for idx, prism in enumerate(self.prisms):
                x0, y0, x1, y1 = prism["bbox"]
                # Cubes enlarge the mech without a hard size cap. The match's
                # finite cube sources make a 16 m index margin conservative for
                # any realistic match loadout (and avoids missing an edge prism
                # when the mech's grown radius crosses a 32 m bin boundary).
                index_pad = 16.0
                ix0 = math.floor((x0 - index_pad) / self.bin_size)
                ix1 = math.floor((x1 + index_pad) / self.bin_size)
                iy0 = math.floor((y0 - index_pad) / self.bin_size)
                iy1 = math.floor((y1 + index_pad) / self.bin_size)
                for ix in range(ix0, ix1 + 1):
                    for iy in range(iy0, iy1 + 1):
                        self.prism_bins.setdefault((ix, iy), []).append(idx)

            self.terrain_meta = dict(world.get("terrain", {}))
            terrain_path = os.path.join(map_dir, "v2", "terrain.i16")
            try:
                with open(terrain_path, "rb") as f:
                    raw = f.read()
                values = array("h")
                values.frombytes(raw)
                # Match the map's explicit little-endian int16 format.
                import sys
                if sys.byteorder != "little":
                    values.byteswap()
                nx = int(self.terrain_meta.get("nx", 0))
                ny = int(self.terrain_meta.get("ny", 0))
                if nx > 1 and ny > 1 and len(values) == nx * ny:
                    self.terrain_values = values
            except (OSError, ValueError, TypeError):
                self.terrain_values = None
        except Exception:
            self.prisms = []
            self.prism_bins = {}
            self.terrain_values = None
        # Static walkability/edge graph is built once during the 20 s hello
        # startup allowance. Per-tick A* then visits only cached adjacency lists.
        try:
            self.nav_graph.build_static_graph()
        except Exception:
            self.nav_graph.graph_ready = False

    def _prisms_in_bbox(self, min_x: float, min_y: float,
                        max_x: float, max_y: float) -> List[Dict[str, Any]]:
        """Return unique map prisms intersecting an XY query box."""
        if not self.prism_bins:
            return self.prisms
        ix0 = math.floor(min_x / self.bin_size)
        ix1 = math.floor(max_x / self.bin_size)
        iy0 = math.floor(min_y / self.bin_size)
        iy1 = math.floor(max_y / self.bin_size)
        ids = set()
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                ids.update(self.prism_bins.get((ix, iy), ()))
        return [self.prisms[i] for i in ids]

    def _terrain_height(self, x: float, y: float) -> Optional[float]:
        """Bilinear terrain sample; map heights are int16 centimetres."""
        if self.terrain_values is None:
            return None
        nx = int(self.terrain_meta.get("nx", 0))
        ny = int(self.terrain_meta.get("ny", 0))
        step = float(self.terrain_meta.get("step", 1.0))
        min_x = float(self.terrain_meta.get("minX", 0.0))
        min_y = float(self.terrain_meta.get("minY", 0.0))
        fx, fy = (x - min_x) / step, (y - min_y) / step
        if fx < 0.0 or fy < 0.0 or fx >= nx - 1 or fy >= ny - 1:
            return None
        i, j = int(fx), int(fy)
        u, v = fx - i, fy - j
        k = j * nx + i
        h00 = self.terrain_values[k] * 0.01
        h10 = self.terrain_values[k + 1] * 0.01
        h01 = self.terrain_values[k + nx] * 0.01
        h11 = self.terrain_values[k + nx + 1] * 0.01
        h0 = h00 * (1.0 - u) + h10 * u
        h1 = h01 * (1.0 - u) + h11 * u
        return h0 * (1.0 - v) + h1 * v

    def _terrain_segment_clear(self, x: float, y: float, z: float,
                               dx: float, dy: float, distance: float,
                               step_up: float, max_slope_deg: float) -> bool:
        """Reject ground paths that cross a cliff or an unwalkable slope.

        This check is intentionally skipped while the mech is on a bridge or
        rooftop, where the ground height is not the surface under its feet.
        """
        start_h = self._terrain_height(x, y)
        if start_h is None or abs(z - start_h) > 2.0 or distance <= 0.0:
            return True
        count = max(1, int(math.ceil(distance / 1.0)))
        prev_h = start_h
        prev_x, prev_y = x, y
        max_slope = math.tan(math.radians(max_slope_deg))
        for i in range(1, count + 1):
            frac = i / count
            qx, qy = x + dx * distance * frac, y + dy * distance * frac
            h = self._terrain_height(qx, qy)
            if h is None:
                return False
            run = max(0.25, math.hypot(qx - prev_x, qy - prev_y))
            rise = abs(h - prev_h)
            if rise > step_up + 0.08 or rise / run > max_slope + 0.05:
                return False
            prev_h, prev_x, prev_y = h, qx, qy
        return True

    def _blocked(self, x: float, y: float, z: float, height: float,
                 radius: Optional[float] = None) -> bool:
        # The mech is a vertical cylinder. Test the horizontal footprint against
        # polygon edges, not only the center point; cube growth increases radius.
        if radius is None:
            radius = float(self.cfg.get("mech", {}).get("radius", 2.5))
        head = z + height
        for p in self._prisms_in_bbox(x - radius, y - radius, x + radius, y + radius):
            x0, y0, x1, y1 = p["bbox"]
            if x < x0 - radius or x > x1 + radius or y < y0 - radius or y > y1 + radius:
                continue
            if head <= p["base"] + 0.05 or z >= p["top"] - 0.05:
                continue
            inside_outer = point_in_ring(x, y, p["ring"])
            containing_hole = None
            for hole in p["holes"]:
                if point_in_ring(x, y, hole):
                    containing_hole = hole
                    break
            if inside_outer and containing_hole is None:
                return True
            if containing_hole is not None:
                # A mech in a courtyard/hole is safe only if its whole footprint
                # fits within that hole.
                if ring_edge_distance(x, y, containing_hole) < radius:
                    return True
            elif not inside_outer and ring_edge_distance(x, y, p["ring"]) < radius:
                # The center is outside, but the mech's cylinder overlaps a wall.
                return True
        return False

    def _ray_blocked(self, a: Vec3, b: Vec3) -> bool:
        """Approximate a weapon/vision ray against static building prisms."""
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
        min_x, max_x = min(ax, bx), max(ax, bx)
        min_y, max_y = min(ay, by), max(ay, by)
        seg_len = math.sqrt((bx-ax)**2 + (by-ay)**2 + (bz-az)**2)
        steps = max(3, min(42, int(seg_len / 5.0) + 1))
        for prism in self._prisms_in_bbox(min_x, min_y, max_x, max_y):
            x0, y0, x1, y1 = prism["bbox"]
            if x1 < min_x or x0 > max_x or y1 < min_y or y0 > max_y:
                continue
            if max(az, bz) < prism["base"] or min(az, bz) > prism["top"]:
                continue
            # Restrict sampling to the part of the segment overlapping this prism's bbox.
            lo, hi = 0.0, 1.0
            valid = True
            for start, delta, low, high in ((ax, bx-ax, x0, x1), (ay, by-ay, y0, y1)):
                if abs(delta) < 1e-9:
                    if start < low or start > high:
                        valid = False
                        break
                else:
                    t1, t2 = (low-start)/delta, (high-start)/delta
                    if t1 > t2:
                        t1, t2 = t2, t1
                    lo, hi = max(lo, t1), min(hi, t2)
                    if lo > hi:
                        valid = False
                        break
            if not valid:
                continue
            local_steps = max(2, min(12, int((hi-lo) * steps) + 2))
            for k in range(local_steps + 1):
                u = lo + (hi-lo) * (k / local_steps)
                px, py, pz = ax + (bx-ax)*u, ay + (by-ay)*u, az + (bz-az)*u
                if pz < prism["base"] or pz > prism["top"]:
                    continue
                if not point_in_ring(px, py, prism["ring"]):
                    continue
                if any(point_in_ring(px, py, hole) for hole in prism["holes"]):
                    continue
                return True
        # Terrain ridges can also occlude a shot even when no building prism
        # intersects the segment. Sample at a modest interval to catch hills.
        if self.terrain_values is not None:
            horizontal = math.hypot(bx - ax, by - ay)
            samples = max(3, min(80, int(horizontal / 4.0) + 1))
            for k in range(1, samples):
                u = k / samples
                px = ax + (bx - ax) * u
                py = ay + (by - ay) * u
                pz = az + (bz - az) * u
                ground = self._terrain_height(px, py)
                if ground is not None and pz < ground + 0.12:
                    return True
        return False

    def _covered_from(self, me: Dict[str, Any], threat: Dict[str, Any]) -> bool:
        """Whether a solid blocks a rough eye-to-torso ray from this threat."""
        ep = threat.get("pos", [0.0, 0.0, 0.0])
        mp = me["pos"]
        eeye = float(ep[2]) + 6.0
        mcenter = float(mp[2]) + 4.5
        return self._ray_blocked((float(ep[0]), float(ep[1]), eeye),
                                 (float(mp[0]), float(mp[1]), mcenter))

    def _safe_zone_point(self, x: float, y: float, obs: mf.Observation) -> bool:
        zone = obs.get("zone", {})
        t = float(obs.get("t", 0.0))
        start = float(zone.get("shrink_start", 1e9))
        if t >= start - 12.0:
            c = zone.get("next_center", zone.get("center", [0.0, 0.0]))
            r = float(zone.get("next_radius", zone.get("radius", 9999.0)))
            margin = min(28.0, max(8.0, r * 0.18))
        else:
            c = zone.get("center", [0.0, 0.0])
            r = float(zone.get("radius", 9999.0))
            margin = 18.0
        return dist2((x, y), c) <= max(0.0, r - margin)

    def _cover_goal(self, obs: mf.Observation, me: Dict[str, Any], threats: List[Dict[str, Any]]) -> Optional[Vec2]:
        """Choose a nearby point on the far side of a building from known threats."""
        if not self.prisms or not threats:
            return None
        x, y, z = me["pos"]
        height = float(me.get("stats", {}).get("eye_height", self.cfg.get("mech", {}).get("eye_height", 8.0)))
        radius = float(me.get("stats", {}).get("radius", self.cfg.get("mech", {}).get("radius", 2.5)))
        candidates: Dict[Tuple[int, int], Vec2] = {}
        active = []
        for threat in threats[:4]:
            tp = threat.get("pos", [0.0, 0.0, 0.0])
            if dist2((x, y), tp) > 190.0:
                continue
            active.append(threat)
        if not active:
            return None
        for prism in self.prisms:
            x0, y0, x1, y1 = prism["bbox"]
            # Only consider structures near the mech and in the general threat sector.
            if x1 < x-82 or x0 > x+82 or y1 < y-82 or y0 > y+82:
                continue
            cx, cy = (x0+x1)*0.5, (y0+y1)*0.5
            if min(dist2((cx, cy), t.get("pos", [0, 0, 0])) for t in active) > 230.0:
                continue
            pad = 7.5
            raw = [
                (x0-pad, (y0+y1)*0.5), (x1+pad, (y0+y1)*0.5),
                ((x0+x1)*0.5, y0-pad), ((x0+x1)*0.5, y1+pad),
                (x0-pad, y0-pad), (x0-pad, y1+pad),
                (x1+pad, y0-pad), (x1+pad, y1+pad),
            ]
            for qx, qy in raw:
                if dist2((x, y), (qx, qy)) > 78.0:
                    continue
                if self._blocked(qx, qy, z, height, radius):
                    continue
                if not self._safe_zone_point(qx, qy, obs):
                    continue
                key = (round(qx/3.0), round(qy/3.0))
                candidates[key] = (qx, qy)
        if not candidates:
            return None
        best: Optional[Vec2] = None
        best_score = -1e30
        for q in candidates.values():
            protected = 0
            closest = 9999.0
            for threat in active:
                tp = threat.get("pos", [0.0, 0.0, 0.0])
                dd = dist2(q, tp)
                closest = min(closest, dd)
                start = (float(tp[0]), float(tp[1]), float(tp[2]) + 6.0)
                candidate_floor = self._terrain_height(q[0], q[1])
                if candidate_floor is None:
                    candidate_floor = float(z)
                end = (q[0], q[1], float(candidate_floor) + 4.5)
                if self._ray_blocked(start, end):
                    protected += 1
            if protected == 0:
                continue
            move_cost = dist2((x, y), q)
            close_penalty = max(0.0, 38.0-closest) * 1.1
            # Prefer a nearby point that blocks more threats without sitting next to them.
            score = protected * 36.0 - move_cost * 0.72 - close_penalty
            if score > best_score:
                best_score, best = score, q
        return best


    def _steer(self, me: Dict[str, Any], goal: Vec2) -> Vec2:
        x, y, z = me["pos"]
        dx, dy = goal[0] - x, goal[1] - y
        ux, uy = unit(dx, dy)
        if ux == 0.0 and uy == 0.0:
            return (0.0, 0.0)
        height = float(me.get("stats", {}).get("eye_height", self.cfg.get("mech", {}).get("eye_height", 8.0)))
        radius = float(me.get("stats", {}).get("radius", self.cfg.get("mech", {}).get("radius", 2.5)))
        step_up = float(me.get("stats", {}).get("step_up", self.cfg.get("mech", {}).get("step_up", 1.2)))
        max_slope = float(self.cfg.get("mech", {}).get("max_slope_deg", 50.0))
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
            if not self._terrain_segment_clear(x, y, z, vx, vy, 19.0, step_up, max_slope):
                hits += 3.0
            # Test several points along the proposed movement segment.
            for d in (4.0, 8.0, 13.0, 19.0):
                if self._blocked(x + vx * d, y + vy * d, z, height, radius):
                    hits += (1.0 if d <= 8.0 else 0.65)
            alignment = vx * ux + vy * uy
            # Prefer progress, strongly penalize walking into solids.
            score = 3.0 * alignment - 5.0 * hits
            if score > best_score:
                best_score, best = score, (vx, vy)
        return best

    def _sound_threat(self, obs: mf.Observation, me: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert recent directional sounds into a temporary approximate threat."""
        t = float(obs.get("t", 0.0))
        danger = {"gun", "mortar", "explosion", "laser", "laser_charge", "lightning", "npc_gun"}
        for sound in obs.get("sounds", []) or []:
            kind = str(sound.get("kind", ""))
            age = float(sound.get("age", 99.0))
            heard_t = t - age
            if kind in danger and age <= 1.2 and heard_t + 1e-6 >= self.last_threat_t:
                self.last_threat_bearing = float(sound.get("bearing", 0.0))
                self.last_threat_kind = kind
                self.last_threat_dist = str(sound.get("dist", "far"))
                self.last_threat_t = heard_t
        if self.last_threat_bearing is None or t - self.last_threat_t > 2.0:
            return None
        d = {"near": 42.0, "mid": 112.0, "far": 225.0}.get(self.last_threat_dist, 150.0)
        x, y, z = me["pos"]
        return {"kind": "sound", "id": -1,
                "pos": [x + math.cos(self.last_threat_bearing)*d,
                        y + math.sin(self.last_threat_bearing)*d, z],
                "vel": [0.0, 0.0, 0.0], "sound_kind": self.last_threat_kind}


    def _remember_beams(self, obs: mf.Observation, me: Dict[str, Any], now: float) -> None:
        """Remember only beams whose path passed close enough to threaten us.

        A beam from a distant third-party duel must not overwrite our defensive
        bearing or mark its shooter as our last attacker.
        """
        mx, my, _ = me.get("pos", [0.0, 0.0, 0.0])
        my_id = me.get("id")
        candidates = []
        for beam in obs.get("beams", []) or []:
            kind = str(beam.get("kind", ""))
            age = float(beam.get("age", 99.0))
            path = beam.get("path") or []
            by = beam.get("by")
            if kind not in ("laser", "lightning") or len(path) < 2 or age > 1.0:
                continue
            if by is not None and my_id is not None and int(by) == int(my_id):
                continue
            src, dst = path[0], path[-1]
            if len(src) < 2 or len(dst) < 2:
                continue
            # Lightning paths may contain several chain segments. Measure the
            # polyline, not the misleading chord from its first to last point.
            beam_dist = min(
                point_segment_distance(float(mx), float(my),
                                       float(path[i][0]), float(path[i][1]),
                                       float(path[i + 1][0]), float(path[i + 1][1]))
                for i in range(len(path) - 1)
            )
            if beam_dist > 35.0:
                continue
            dx, dy = float(src[0]) - float(mx), float(src[1]) - float(my)
            candidates.append((now - age, math.hypot(dx, dy), math.atan2(dy, dx), kind, by))
        if not candidates:
            return
        beam_t, distance, bearing, kind, by = max(candidates, key=lambda q: (q[0], -q[1]))
        if beam_t + 1e-6 < self.last_threat_t:
            return
        self.last_threat_bearing = bearing
        self.last_attacker_bearing = bearing
        self.last_threat_t = beam_t
        self.last_threat_kind = kind
        self.last_threat_dist = "near" if distance < 60.0 else ("mid" if distance < 160.0 else "far")
        if by is not None:
            try:
                self.last_attacker_id = int(by)
            except (TypeError, ValueError):
                pass


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

    def _weapon_value(self, kind: Optional[str], enemy_dist: float,
                      enemy_weapons: Sequence[str], enemy_charging: bool) -> float:
        """Contextual value of a secondary weapon for the current matchup."""
        held = set(enemy_weapons)
        if kind == "lightning":
            value = 8.7 if ("laser" in held or enemy_charging) else (7.5 if enemy_dist <= 50.0 else 5.4)
            if enemy_dist > 70.0:
                value -= 1.0
            return value
        if kind == "laser":
            value = 9.0 if "mortar" in held else (8.3 if enemy_dist >= 75.0 else 6.1)
            if "lightning" in held and enemy_dist < 65.0:
                value -= 2.2
            return value
        if kind == "mortar":
            value = 8.5 if "lightning" in held and 45.0 <= enemy_dist <= 150.0 else (7.4 if enemy_dist <= 180.0 else 6.3)
            if enemy_dist < 35.0:
                value -= 1.8
            return value
        return 0.0

    def _choose_resource_goal(self, obs: mf.Observation, me: Dict[str, Any], enemies: List[Dict[str, Any]], zone_goal: Vec2) -> Tuple[Vec2, Optional[Dict[str, Any]], str]:
        x, y, z = me["pos"]
        enemy_dists = [dist3(e["pos"], me["pos"]) for e in enemies]
        nearest_enemy = min(enemy_dists) if enemy_dists else 9999.0
        nearest_enemy_obj = min(enemies, key=lambda e: dist3(e["pos"], me["pos"])) if enemies else None
        enemy_weapons = (nearest_enemy_obj.get("weapons", []) or []) if nearest_enemy_obj else []
        enemy_charging = bool(nearest_enemy_obj.get("charging", False)) if nearest_enemy_obj else False
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
        current_secondary = weapons[1] if len(weapons) > 1 and isinstance(weapons[1], dict) else None
        if current_secondary is not None:
            second = current_secondary.get("kind")
        else:
            second = None
        for p in obs.get("pickups", []) or []:
            kind = p.get("kind")
            if kind == "gun" or kind in held:
                continue
            dd = dist2((x, y), p.get("pos", [x, y, z]))
            if dd > 60.0 or nearest_enemy < 55.0:
                continue
            candidate_value = self._weapon_value(kind, nearest_enemy, enemy_weapons, enemy_charging)
            if second is None:
                pref = 86.0 + candidate_value * 1.2
            else:
                # Swaps are deliberately conservative: don't drop a working
                # secondary unless the new weapon has a clear matchup advantage.
                if float(current_secondary.get("charge", 0.0)) > 0.01:
                    continue
                current_value = self._weapon_value(second, nearest_enemy, enemy_weapons, enemy_charging)
                if candidate_value < current_value + 1.25:
                    continue
                pref = 91.0 + (candidate_value - current_value) * 5.0
            score = pref - 0.9 * dd
            candidates.append((score, (float(p["pos"][0]), float(p["pos"][1])), p,
                                "weapon" if second is None else "weapon_swap"))

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
        """Return an escape vector using closest-approach rather than sparse samples.

        Gun and NPC bullets use an exact constant-velocity CPA. Mortar shells
        include gravity and are checked with a short, bounded ballistic sweep.
        """
        px, py, pz = me["pos"]
        mv = me.get("vel", [0.0, 0.0, 0.0])
        vx0, vy0, vz0 = float(mv[0]), float(mv[1]), float(mv[2])
        threat_x = threat_y = 0.0
        urgent = False
        jump = False
        gravity = float(self.cfg.get("weapons", {}).get("mortar", {}).get("gravity", 22.0))
        self_stats = me.get("stats", {}) or {}
        mech_center_z = float(self_stats.get("height", self.cfg.get("mech", {}).get("height", 9.0))) * 0.5
        mech_radius = float(self_stats.get("radius", self.cfg.get("mech", {}).get("radius", 2.5)))
        for p in obs.get("projectiles", []) or []:
            pos = p.get("pos", [0.0, 0.0, 0.0])
            vel = p.get("vel", [0.0, 0.0, 0.0])
            kind = p.get("kind", "gun")
            if kind == "mortar":
                # Ballistic path: 0.05 s samples are sufficiently dense for the
                # slower mortar shell; refine locally around its closest sample.
                best_t, best_d, best_delta = 0.0, 1e9, (0.0, 0.0)
                best_idx = 0
                samples = []
                for idx in range(19):
                    tt = idx * 0.05
                    sx = float(pos[0]) + float(vel[0]) * tt
                    sy = float(pos[1]) + float(vel[1]) * tt
                    sz = float(pos[2]) + float(vel[2]) * tt - 0.5 * gravity * tt * tt
                    mx = px + vx0 * tt
                    my = py + vy0 * tt
                    mz = pz + vz0 * tt
                    dd = math.sqrt((sx-mx)**2 + (sy-my)**2 +
                                   (sz-(mz+mech_center_z))**2)
                    samples.append((dd, tt, (mx-sx, my-sy)))
                    if dd < best_d:
                        best_d, best_t, best_delta, best_idx = dd, tt, (mx-sx, my-sy), idx
                # Parabolic interpolation around the minimum, bounded to the
                # neighbouring 0.05 s interval.
                if 0 < best_idx < len(samples) - 1:
                    d0, d1, d2 = samples[best_idx-1][0], samples[best_idx][0], samples[best_idx+1][0]
                    den = d0 - 2.0*d1 + d2
                    if abs(den) > 1e-8:
                        offset = clamp(0.025 * (d0-d2) / den, -0.05, 0.05)
                        best_t = clamp(best_t + offset, 0.0, 0.9)
                # Re-evaluate the complete relative position at the refined time.
                # The previous implementation refined best_t but retained best_d
                # and best_delta from the nearest 50 ms sample. That could miss a
                # shell whose true closest pass was just inside the danger radius.
                sx = float(pos[0]) + float(vel[0]) * best_t
                sy = float(pos[1]) + float(vel[1]) * best_t
                sz = float(pos[2]) + float(vel[2]) * best_t - 0.5 * gravity * best_t * best_t
                mx = px + vx0 * best_t
                my = py + vy0 * best_t
                mz = pz + vz0 * best_t
                best_d = math.sqrt((sx-mx)**2 + (sy-my)**2 +
                                   (sz-(mz+mech_center_z))**2)
                best_delta = (mx-sx, my-sy)
                radius = max(7.0, float(self.cfg.get("weapons", {}).get("mortar", {}).get("splash_radius", 7.0)) + 2.0)
            else:
                # Exact closest point of approach for a linear projectile.
                rx = float(pos[0]) - px
                ry = float(pos[1]) - py
                rz = float(pos[2]) - (pz + mech_center_z)
                rvx = float(vel[0]) - vx0
                rvy = float(vel[1]) - vy0
                rvz = float(vel[2]) - vz0
                vv = rvx*rvx + rvy*rvy + rvz*rvz
                best_t = clamp(-(rx*rvx + ry*rvy + rz*rvz) / vv, 0.0, 0.9) if vv > 1e-9 else 0.0
                sx = float(pos[0]) + float(vel[0]) * best_t
                sy = float(pos[1]) + float(vel[1]) * best_t
                sz = float(pos[2]) + float(vel[2]) * best_t
                mx = px + vx0 * best_t
                my = py + vy0 * best_t
                mz = pz + vz0 * best_t
                best_d = math.sqrt((sx-mx)**2 + (sy-my)**2 +
                                   (sz-(mz+mech_center_z))**2)
                best_delta = (mx-sx, my-sy)
                # If a solid/terrain ridge blocks the projectile's straight path
                # to its predicted closest point, it cannot hit us along this
                # trajectory. Do not waste a dodge by stepping out from cover.
                if self._ray_blocked(
                        (float(pos[0]), float(pos[1]), float(pos[2])),
                        (sx, sy, sz)):
                    continue
                projectile_cfg = self.cfg.get("projectile", {})
                projectile_radius = max(float(projectile_cfg.get("gun_radius", 0.3)),
                                         float(projectile_cfg.get("npc_radius", 0.3)))
                radius = max(4.5, mech_radius + projectile_radius + 1.0)

            if best_d < radius and best_t <= 0.72:
                ex, ey = unit(best_delta[0], best_delta[1])
                if ex == 0.0 and ey == 0.0:
                    # Side-step relative to projectile path.
                    ex, ey = unit(-float(vel[1]), float(vel[0]))
                threat_x += ex * (radius - best_d + 1.0) / max(0.12, best_t)
                threat_y += ey * (radius - best_d + 1.0) / max(0.12, best_t)
                urgent = True
                if kind == "mortar" and best_t < 0.55 and me.get("grounded", False):
                    jump = True
        if urgent:
            return unit(threat_x, threat_y), True, jump
        return (0.0, 0.0), False, False

    def _incoming_mortar_jump(self, obs: mf.Observation, me: Dict[str, Any]) -> bool:
        """Cheap jump-only check; ContextSteerer already handles full projectile CPA."""
        if not me.get("grounded", False):
            return False
        px, py, pz = (float(v) for v in me["pos"])
        mv = me.get("vel", (0.0, 0.0, 0.0))
        vx, vy, vz = (float(mv[i]) if i < len(mv) else 0.0 for i in range(3))
        stats = me.get("stats", {}) or {}
        height = float(stats.get("height", self.cfg.get("mech", {}).get("height", 9.0)))
        radius = float(stats.get("radius", self.cfg.get("mech", {}).get("radius", 2.5)))
        center_offset = height * 0.5
        mortar_cfg = self.cfg.get("weapons", {}).get("mortar", {}) or {}
        gravity = float(mortar_cfg.get("gravity", 22.0))
        splash = float(mortar_cfg.get("splash_radius", 7.0))
        danger_r = max(7.0, splash + radius + 0.5)
        for proj in obs.get("projectiles", []) or []:
            if proj.get("kind") != "mortar":
                continue
            pos = proj.get("pos", (0.0, 0.0, 0.0))
            vel = proj.get("vel", (0.0, 0.0, 0.0))
            for step in range(1, 12):
                dt = step * 0.05
                if dt > 0.55:
                    break
                sx = float(pos[0]) + float(vel[0]) * dt
                sy = float(pos[1]) + float(vel[1]) * dt
                sz = float(pos[2]) + float(vel[2]) * dt - 0.5 * gravity * dt * dt
                ground = self._terrain_height(sx, sy)
                if ground is not None and sz <= ground:
                    sz = ground
                    impact = True
                else:
                    impact = False
                mx = px + vx * dt
                my = py + vy * dt
                mz = pz + vz * dt + center_offset
                if math.sqrt((mx - sx) ** 2 + (my - sy) ** 2 + (mz - sz) ** 2) <= danger_r:
                    return True
                if impact:
                    break
        return False

    def _target_aim(self, me: Dict[str, Any], target: Dict[str, Any], weapon: Dict[str, Any], kind: str) -> Tuple[float, float, float]:
        mx, my, mz = me["pos"]
        tx, ty, tz = target["pos"]
        tv = target.get("vel", [0.0, 0.0, 0.0])
        cubes = float(target.get("cubes", 0.0))
        target_center_z = tz + (1.75 if target.get("kind") == "npc" else 4.5 * (1.0 + 0.05 * cubes))
        muzzle_z = mz + float(me.get("stats", {}).get("muzzle_height", 7.0))
        speed = float(weapon.get("stats", {}).get("speed", 252.0))
        if kind == "gun":
            r = (tx - mx, ty - my, target_center_z - muzzle_z)
            # The protocol specifies a 252 m/s world-space projectile and does
            # not specify shooter-velocity inheritance. Solve against target
            # world velocity. If the server later documents inheritance, both
            # the relative-velocity equation AND the aim vector must change.
            rv = (float(tv[0]), float(tv[1]), float(tv[2]))
            max_t = float(weapon.get("stats", {}).get("range", 230.0)) / max(1.0, speed)
            t = solve_intercept(r, rv, speed, max_t=max_t)
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

    def _laser_safe_abort_aim(self, me: Dict[str, Any], preferred_yaw: float,
                              weapon: Dict[str, Any]) -> Tuple[float, float]:
        """Find an upward, prism-clear direction for releasing a stale laser charge."""
        x, y, z = me["pos"]
        muzzle_z = z + float(me.get("stats", {}).get("muzzle_height", 7.0))
        actual = me.get("aim", [preferred_yaw, 0.0])
        actual_yaw = float(actual[0])
        max_pitch = float(self.cfg.get("mech", {}).get("max_pitch", 1.3))
        pitch = min(max_pitch, 1.15)
        ray_len = float(weapon.get("stats", {}).get("range", 280.0))
        # Try away from the target first, then lateral directions. The ray is
        # deliberately checked for the full hitscan range, not just nearby cover.
        candidates = [
            wrap(preferred_yaw + math.pi),
            wrap(actual_yaw + math.pi / 2.0),
            wrap(actual_yaw - math.pi / 2.0),
            wrap(preferred_yaw + math.pi / 2.0),
            wrap(preferred_yaw - math.pi / 2.0),
            wrap(actual_yaw),
        ]
        cp = math.cos(pitch)
        sp = math.sin(pitch)
        start = (float(x), float(y), float(muzzle_z))
        for yaw in candidates:
            end = (float(x) + ray_len * cp * math.cos(yaw),
                   float(y) + ray_len * cp * math.sin(yaw),
                   float(muzzle_z) + ray_len * sp)
            if not self._ray_blocked(start, end):
                return yaw, pitch
        # Last resort: steepest permitted upward angle. It is still preferable
        # to retaining a charge while walking at half speed into the wall.
        return actual_yaw, max_pitch

    def _mortar_aim(self, me: Dict[str, Any], target: Dict[str, Any], weapon: Dict[str, Any]) -> Tuple[float, float, float]:
        """Solve a low-arc ballistic intercept with a converged target lead.

        Mortar range can require more than 2.5 s of flight time. The shell TTL
        comes from the live config; use it as the physical upper bound instead
        of silently truncating long shots.
        """
        mx, my, mz = me["pos"]
        tx, ty, tz = target["pos"]
        tv = target.get("vel", [0.0, 0.0, 0.0])
        muzzle_z = mz + float(me.get("stats", {}).get("muzzle_height", 7.0)) + 2.5
        cubes = float(target.get("cubes", 0.0))
        target_z0 = tz + (1.75 if target.get("kind") == "npc" else 4.5 * (1.0 + 0.05 * cubes))
        mortar_cfg = self.cfg.get("weapons", {}).get("mortar", {})
        v = float(weapon.get("stats", {}).get("speed", mortar_cfg.get("speed", 72.0)))
        g = float(mortar_cfg.get("gravity", 22.0))
        ttl = float(mortar_cfg.get("ttl", 7.0))
        max_flight = max(0.5, min(6.5, ttl - 0.1))
        flight_t = min(max_flight, math.hypot(float(tx) - mx, float(ty) - my) / max(1.0, v * math.cos(math.radians(42.0))))
        pitch = math.radians(42.0)
        aim_x, aim_y = float(tx), float(ty)

        # Fixed-point iteration: predicted target location determines range and
        # pitch; pitch determines flight time; repeat until those agree.
        for _ in range(10):
            aim_x = float(tx) + float(tv[0]) * flight_t
            aim_y = float(ty) + float(tv[1]) * flight_t
            target_z = target_z0 + float(tv[2]) * flight_t
            horizontal = max(0.1, math.hypot(aim_x - mx, aim_y - my))
            height_delta = target_z - muzzle_z
            disc = v ** 4 - g * (g * horizontal * horizontal + 2.0 * height_delta * v * v)
            if disc >= 0.0:
                tan_theta = (v * v - math.sqrt(max(0.0, disc))) / max(1e-6, g * horizontal)
                pitch = math.atan(tan_theta)
            else:
                # No low-arc solution at this range/height; keep a conservative
                # 42-degree lob and let the path/score checks decide whether use.
                pitch = math.radians(42.0)
            cos_pitch = max(0.15, math.cos(pitch))
            next_t = min(max_flight, horizontal / max(1.0, v * cos_pitch))
            if abs(next_t - flight_t) < 0.002:
                flight_t = next_t
                break
            flight_t = next_t

        # Recompute once at the final lead so returned pitch and yaw correspond
        # to the same predicted target position (no stale final pitch).
        aim_x = float(tx) + float(tv[0]) * flight_t
        aim_y = float(ty) + float(tv[1]) * flight_t
        target_z = target_z0 + float(tv[2]) * flight_t
        horizontal = max(0.1, math.hypot(aim_x - mx, aim_y - my))
        height_delta = target_z - muzzle_z
        disc = v ** 4 - g * (g * horizontal * horizontal + 2.0 * height_delta * v * v)
        if disc >= 0.0:
            tan_theta = (v * v - math.sqrt(max(0.0, disc))) / max(1e-6, g * horizontal)
            pitch = math.atan(tan_theta)
        else:
            pitch = math.radians(42.0)
        yaw = math.atan2(aim_y - my, aim_x - mx)
        return yaw, clamp(pitch, -0.2, 1.15), horizontal

    def _mortar_path_clear(self, me: Dict[str, Any], yaw: float,
                           pitch: float, horizontal_range: float,
                           weapon: Dict[str, Any]) -> bool:
        """Check the early ballistic arc against structures and terrain."""
        speed = float(weapon.get("stats", {}).get("speed", 72.0))
        gravity = float(self.cfg.get("weapons", {}).get("mortar", {}).get("gravity", 22.0))
        cos_pitch = max(0.15, math.cos(pitch))
        ttl = float(self.cfg.get("weapons", {}).get("mortar", {}).get("ttl", 7.0))
        flight_t = clamp(horizontal_range / max(1.0, speed * cos_pitch), 0.05, min(6.5, ttl - 0.1))
        x, y, z = me["pos"]
        muzzle_z = float(me.get("stats", {}).get("muzzle_height", 7.0)) + 2.5
        # Ignore the final 15% so the intended target/building splash does not
        # incorrectly count as an obstruction.
        end_t = flight_t * 0.85
        # Keep path samples dense enough to catch a building crossed by a long
        # shell arc; 8 m spacing is a practical accuracy/runtime compromise.
        steps = max(10, min(40, int(math.ceil(speed * end_t / 8.0))))
        prev = (float(x), float(y), float(z) + muzzle_z)
        for i in range(1, steps + 1):
            tt = end_t * i / steps
            point = (float(x) + speed * math.cos(pitch) * math.cos(yaw) * tt,
                     float(y) + speed * math.cos(pitch) * math.sin(yaw) * tt,
                     float(z) + muzzle_z + speed * math.sin(pitch) * tt - 0.5 * gravity * tt * tt)
            if self._ray_blocked(prev, point):
                return False
            prev = point
        return True

    def _choose_upgrade(self, offer: Dict[str, Any], me: Dict[str, Any], now: float) -> int:
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
            if cid == "sensors" and now < 180.0:
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
        self.threat_tracker.update(obs, me)
        prioritized_threats = self.threat_tracker.prioritized_threats(obs, me)
        actors = obs.get("mechs", []) or []
        enemies = [m for m in actors if m.get("kind") == "mech"]
        npcs = [m for m in actors if m.get("kind") == "npc"]
        enemies.sort(key=lambda e: dist3(e["pos"], me["pos"]))
        npcs.sort(key=lambda e: dist3(e["pos"], me["pos"]))
        nearby = [e for e in enemies if dist3(e["pos"], me["pos"]) < 100.0]
        hp_frac = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        energy = float(me.get("energy", 0.0))
        max_energy = max(1.0, float(me.get("max_energy", 100.0)))
        nearest_enemy_dist = dist3(enemies[0]["pos"], me["pos"]) if enemies else 9999.0
        nearest_npc_dist = dist3(npcs[0]["pos"], me["pos"]) if npcs else 9999.0

        # Track both damage dealt and received: either resets the regeneration timer.
        for ev in obs.get("events", []) or []:
            if ev.get("type") in ("damaged", "hit"):
                self.last_damage_t = t
            if ev.get("type") == "damaged":
                if ev.get("bearing") is not None and ev.get("weapon") != "zone":
                    self.last_attacker_bearing = float(ev["bearing"])
                    self.last_threat_bearing = float(ev["bearing"])
                    self.last_threat_t = t
                    self.last_threat_kind = str(ev.get("weapon", "unknown"))
                    self.last_threat_dist = "near"
                if ev.get("by") is not None:
                    self.last_attacker_id = int(ev["by"])

        # Prefer the mech that actually hit our rear armour when it is still
        # represented in the server-provided 5 s vision memory.
        rear_attacker_id = None
        for ev in reversed(obs.get("events", []) or []):
            if (ev.get("type") == "damaged" and ev.get("rear")
                    and ev.get("weapon") != "zone" and ev.get("by") is not None):
                rear_attacker_id = int(ev["by"])
                break

        self._remember_beams(obs, me, t)
        sound_threat = self._sound_threat(obs, me)
        recent_alert = sound_threat is not None and self.last_threat_dist in ("near", "mid")
        action: mf.Action = {"tick": obs["tick"]}
        if obs.get("offer"):
            action["pick"] = self._choose_upgrade(obs["offer"], me, t)

        # Choose a combat target; close and weakened opponents are more valuable.
        target = None
        if enemies:
            def target_score(e: Dict[str, Any]) -> float:
                d = dist3(e["pos"], me["pos"])
                ehp = float(e.get("hp", e.get("max_hp", 900.0)))
                return d + 0.018 * ehp - (10.0 if e.get("charging") else 0.0)
            target = min(enemies, key=target_score)
            self.last_target = int(target.get("id", -1))
            if rear_attacker_id is not None:
                rear_attacker = next((e for e in enemies if int(e.get("id", -2)) == rear_attacker_id), None)
                if rear_attacker is not None:
                    target = rear_attacker
                    self.last_target = rear_attacker_id

        # Optional farming is deferred while damaged and recovering. This gate
        # never applies to a visible hostile mech, so self-defence is preserved.
        suppress_optional_fire = should_suppress_optional_fire(
            me, has_visible_enemy=bool(enemies),
            time_since_damage=t - self.last_damage_t,
        )

        # Opportunistic drone farming: two cubes are valuable, but do not detour
        # toward a drone while a mech is close, threat sounds are recent, or
        # optional damage would reset a useful regeneration window.
        if (target is None and npcs and nearest_npc_dist < 68.0
                and nearest_enemy_dist > 145.0 and hp_frac > 0.66
                and me.get("in_zone", True) and not recent_alert
                and not suppress_optional_fire):
            target = npcs[0]

        zone_goal = self._zone_goal(obs, me)
        resource_goal, resource_obj, resource_kind = self._choose_resource_goal(obs, me, enemies, zone_goal)
        goal = resource_goal
        movement_goal_weight = 1.0

        # Pre-rotate toward a safe, upcoming supply drop. Existing cover and
        # zone-emergency decisions below retain priority over this opportunity.
        drop_choice = None
        if me.get("in_zone", True) and nearest_enemy_dist > 65.0 and not recent_alert:
            drop_choice = choose_supply_drop_goal(obs, me, prioritized_threats)
        if drop_choice is not None:
            goal, movement_goal_weight = drop_choice
            resource_obj = None
            resource_kind = "drop_preposition"

        # Use cover only when there is a concrete reason: close line-of-sight threats,
        # multiple nearby mechs, or very recent damage. This changes movement, not firing.
        exposed_threats = [e for e in enemies
                           if dist3(e["pos"], me["pos"]) < 155.0 and not self._covered_from(me, e)]
        cover_trigger = (hp_frac < 0.68 or len(nearby) >= 2 or
                         (t - self.last_damage_t) < 0.9 or nearest_enemy_dist < 62.0)
        cover_goal = self._cover_goal(obs, me, exposed_threats) if (cover_trigger and exposed_threats) else None
        if cover_goal is not None:
            goal = cover_goal
            movement_goal_weight = 1.0
            resource_obj = None
            resource_kind = "cover"

        # Recover only when genuinely safe and not in an active engagement.
        # Keep this narrow so it cannot suppress self-defence against visible mechs.
        recovering = (hp_frac < 0.78 and (t - self.last_damage_t) >= 5.0
                      and not enemies and me.get("in_zone", True)
                      and not recent_alert and nearest_npc_dist > 75.0)
        if recovering and cover_goal is None and drop_choice is None:
            # Movement itself does NOT reset regeneration. Keep rotating toward
            # safety instead of becoming a stationary target while healing.
            goal = zone_goal
            movement_goal_weight = 1.0
            resource_obj = None
            resource_kind = "recover"
        elif suppress_optional_fire and target is None and resource_kind == "crate" and drop_choice is None and cover_goal is None:
            goal = zone_goal
            movement_goal_weight = 1.0
            resource_obj = None
            resource_kind = "regen_hold"

        # If a crate was selected, shoot it while moving toward it. Crate fire is
        # deliberately lower priority than any visible hostile mech.
        utility_target = None
        if (target is None and resource_kind == "crate" and not recovering
                and not suppress_optional_fire):
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
                actual_aim = me.get("aim", [aim_yaw, aim_pitch])
                yaw_err = abs(wrap(aim_yaw - float(actual_aim[0])))
                pitch_err = abs(aim_pitch - float(actual_aim[1]))
                if (float(w1.get("cooldown", 0.0)) <= 0.02
                        and yaw_err < 0.18 and pitch_err < 0.20
                        and self._mortar_path_clear(me, aim_yaw, aim_pitch, hrange, w1)):
                    fire[1] = True
            elif second_kind == "laser" and d > 38.0 and not any("lightning" in (e.get("weapons") or []) for e in nearby if dist3(e["pos"], me["pos"]) < 65.0):
                target_aim_yaw, target_aim_pitch, hrange = self._target_aim(me, current_target, w1, "laser")
                charge = float(w1.get("charge", 0.0))
                cooldown = float(w1.get("cooldown", 0.0))
                actual_aim = me.get("aim", [target_aim_yaw, target_aim_pitch])
                muzzle_z = z + float(me.get("stats", {}).get("muzzle_height", 7.0))
                target_z = float(current_target["pos"][2]) + (1.75 if current_target.get("kind") == "npc" else 4.5 * (1.0 + 0.05 * float(current_target.get("cubes", 0.0))))
                laser_los = not self._ray_blocked(
                    (x, y, muzzle_z),
                    (float(current_target["pos"][0]), float(current_target["pos"][1]), target_z))
                if cooldown <= 0.02:
                    max_charge = float(w1.get("stats", {}).get("charge", 0.75))
                    desired_charge = min(max_charge - 0.04, max(0.15, max_charge * 0.84))
                    if laser_los:
                        aim_yaw, aim_pitch = target_aim_yaw, target_aim_pitch
                        laser_aligned = (abs(wrap(target_aim_yaw - float(actual_aim[0]))) < 0.075
                                         and abs(target_aim_pitch - float(actual_aim[1])) < 0.075)
                        if charge <= 0.01:
                            # Never start a charge against a target hidden by a solid.
                            fire[1] = bool(laser_aligned)
                        elif charge < desired_charge or not laser_aligned:
                            fire[1] = True
                        else:
                            fire[1] = False
                    elif charge > 0.01:
                        # A remembered enemy can remain in obs for 5 s after it
                        # ducks behind a building. Do not keep charging at the wall.
                        # Turn to a verified clear upward ray, then release the
                        # charged shot in that harmless direction.
                        safe_yaw, safe_pitch = self._laser_safe_abort_aim(me, target_aim_yaw, w1)
                        aim_yaw, aim_pitch = safe_yaw, safe_pitch
                        safe_aligned = (abs(wrap(safe_yaw - float(actual_aim[0]))) < 0.09
                                        and abs(safe_pitch - float(actual_aim[1])) < 0.09)
                        fire[1] = not safe_aligned
                    else:
                        # No line of sight and no charge in progress: do not start.
                        aim_yaw, aim_pitch = target_aim_yaw, target_aim_pitch
                        fire[1] = False
                else:
                    aim_yaw, aim_pitch = target_aim_yaw, target_aim_pitch
                # Gun shares the torso aim and cannot pass through a building.
                # Avoid wasting ammunition at a remembered but occluded target.
                if laser_los and w0 and d < float(w0.get("stats", {}).get("range", 230.0)):
                    gy, gp, _ = self._target_aim(me, current_target, w0, "gun")
                    if (abs(wrap(gy - float(actual_aim[0]))) < 0.12
                            and abs(gp - float(actual_aim[1])) < 0.12):
                        if float(w0.get("reload", 0.0)) <= 0.0 and float(w0.get("ammo", 1.0)) > 0:
                            fire[0] = True
            elif second_kind == "lightning" and d <= float(w1.get("stats", {}).get("range", 45.0)) * 1.08:
                # Lightning is instant and only cares about yaw/cone.
                aim_yaw, aim_pitch, hrange = self._target_aim(me, current_target, w1, "lightning")
                actual_aim = me.get("aim", [aim_yaw, aim_pitch])
                yaw_err = abs(wrap(aim_yaw - float(actual_aim[0])))
                muzzle_z = z + float(me.get("stats", {}).get("muzzle_height", 7.0))
                target_z = float(current_target["pos"][2]) + (1.75 if current_target.get("kind") == "npc" else 4.5)
                lightning_los = not self._ray_blocked(
                    (x, y, muzzle_z),
                    (float(current_target["pos"][0]), float(current_target["pos"][1]), target_z))
                if (yaw_err < math.radians(23.0) and lightning_los
                        and float(w1.get("cooldown", 0.0)) <= 0.02
                        and energy >= float(w1.get("stats", {}).get("energy", 3.0))):
                    fire[1] = True
                if w0 and d < float(w0.get("stats", {}).get("range", 230.0)):
                    gy, gp, _ = self._target_aim(me, current_target, w0, "gun")
                    if (abs(wrap(gy - float(actual_aim[0]))) < 0.12
                            and abs(gp - float(actual_aim[1])) < 0.12):
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
        elif utility_target is not None and w0:
            # Crate center is roughly 1.2 m above its base; it is stationary.
            p = utility_target.get("pos", [x, y, z])
            dx, dy = p[0] - x, p[1] - y
            aim_yaw = math.atan2(dy, dx)
            aim_pitch = math.atan2((p[2] + 1.2) - (z + float(me.get("stats", {}).get("muzzle_height", 7.0))), max(0.1, math.hypot(dx, dy)))
            actual_aim = me.get("aim", [aim_yaw, aim_pitch])
            err = abs(wrap(aim_yaw - float(actual_aim[0])))
            pitch_err = abs(aim_pitch - float(actual_aim[1]))
            if (math.hypot(dx, dy) < float(w0.get("stats", {}).get("range", 230.0))
                    and err < 0.18 and pitch_err < 0.18):
                if float(w0.get("ammo", 0.0)) > 0 and float(w0.get("reload", 0.0)) <= 0.0:
                    fire[0] = True
        elif not enemies:
            # No visible target: use the freshest timestamp-ordered threat
            # evidence (current damage event, beam source, or heard sound).
            # _remember_beams and _sound_threat have already updated this memory;
            # do not let an older sound in this observation override a newer beam.
            bearing = None
            for ev in reversed(obs.get("events", []) or []):
                if ev.get("type") == "damaged" and ev.get("bearing") is not None and ev.get("weapon") != "zone":
                    bearing = float(ev["bearing"])
                    break
            tracker_bearing = self.threat_tracker.defensive_bearing
            tracker_age = t - self.threat_tracker.defensive_bearing_t
            if bearing is None and tracker_bearing is not None and 0.0 <= tracker_age < 1.5:
                bearing = tracker_bearing
            if bearing is None and self.last_threat_bearing is not None and t - self.last_threat_t < 2.0:
                bearing = self.last_threat_bearing
            if bearing is None:
                bearing = choose_defensive_aim(t, me, self.threat_tracker, prioritized_threats)
            if bearing is not None:
                aim_yaw, aim_pitch = bearing, 0.0

        # Reload early when there is no magazine left. Never spam reload while one is active.
        if w0 and float(w0.get("ammo", 1.0)) <= 0.0 and float(w0.get("reload", 0.0)) <= 0.0:
            action["reload"] = True

        # V9 movement: 24-direction interest/danger steering with map geometry,
        # projectile VO and a limited cover/retreat preference. Keep V8 combat.
        jump = self._incoming_mortar_jump(obs, me)  # steering handles full CPA; this only gates jump
        strafe_vec: Optional[Vec2] = None
        strafe_weight = 0.0
        if nearby:
            nearest = min(nearby, key=lambda e: dist3(e["pos"], me["pos"]))
            ex, ey = unit(x - float(nearest["pos"][0]), y - float(nearest["pos"][1]))
            nd = dist2((x, y), nearest["pos"])
            if hp_frac < 0.58 or len(nearby) >= 3:
                strafe_vec = (ex, ey)
                strafe_weight = 1.2 if hp_frac < 0.58 else 0.75
            elif nd < 85.0:
                strafe_vec = (-ey * self.strafe_sign, ex * self.strafe_sign)
                strafe_weight = 0.75

        move, urgent = self.context_steerer.evaluate(
            self, obs, me, goal, movement_goal_weight, prioritized_threats, strafe_vec, strafe_weight
        )
        boost = False
        if urgent:
            boost = energy > 12.0
        else:
            dist_goal = dist2((x, y), goal)
            outside = not me.get("in_zone", True)
            boost = energy > 48.0 and (outside or (dist_goal > 90.0 and energy > 72.0))
            if hp_frac < 0.3 and nearby and energy > 18.0:
                boost = True

        # A rear hit from a shooter outside current vision should orient the
        # torso defensively. Do this before action assembly, and never let a
        # zone-damage event override a valid combat aim.
        if target is None:
            for ev in reversed(obs.get("events", []) or []):
                if (ev.get("type") == "damaged" and ev.get("weapon") != "zone"
                        and ev.get("bearing") is not None):
                    aim_yaw, aim_pitch = float(ev["bearing"]), 0.0
                    break

        # Also handle an in-progress laser charge if the remembered target has
        # just disappeared or the normal laser branch was bypassed (e.g. close
        # range). Never let a charged beam release into a known solid.
        if w1 and w1.get("kind") == "laser" and float(w1.get("charge", 0.0)) > 0.01:
            charge_target_clear = False
            if current_target is not None:
                target_pos = current_target.get("pos", [x, y, z])
                target_z = float(target_pos[2]) + (1.75 if current_target.get("kind") == "npc" else 4.5 * (1.0 + 0.05 * float(current_target.get("cubes", 0.0))))
                muzzle_z = z + float(me.get("stats", {}).get("muzzle_height", 7.0))
                charge_target_clear = not self._ray_blocked(
                    (x, y, muzzle_z),
                    (float(target_pos[0]), float(target_pos[1]), target_z))
            if not charge_target_clear:
                safe_yaw, safe_pitch = self._laser_safe_abort_aim(me, aim_yaw, w1)
                aim_yaw, aim_pitch = safe_yaw, safe_pitch
                actual_aim = me.get("aim", [safe_yaw, safe_pitch])
                safely_aligned = (abs(wrap(safe_yaw - float(actual_aim[0]))) < 0.09
                                  and abs(safe_pitch - float(actual_aim[1])) < 0.09)
                fire[1] = not safely_aligned

        action.update({
            "move": [float(move[0]), float(move[1])],
            "boost": bool(boost),
            "jump": bool(jump and me.get("grounded", False)),
            "aim": [float(aim_yaw), float(clamp(aim_pitch, -0.7, 1.3))],
            "fire": [bool(fire[0]), bool(fire[1])],
        })

        # Explicitly take nearby weapon pickups; movement goal gets us there first.
        if resource_kind in ("weapon", "weapon_swap") and resource_obj is not None:
            p = resource_obj.get("pos", [x, y, z])
            if dist2((x, y), p) <= float(self.cfg.get("loot", {}).get("pickup_radius", 4.0)) + 0.5 and abs(z - p[2]) <= 4.0:
                action["take"] = resource_obj.get("id")
                if resource_kind == "weapon_swap" and w1 is not None:
                    action["drop"] = 1

        # Keep debug output small; this is useful in the spectator/debug tooling.
        if target is not None:
            tp = target["pos"]
            target_h = 1.75 if target.get("kind") == "npc" else 4.5
            mf.draw.line([x, y, z + 7.0], [tp[0], tp[1], tp[2] + target_h], "#ff5040")
        if cover_goal is not None:
            mf.draw.point([cover_goal[0], cover_goal[1], z], "#40d080", 6)
        mf.draw.point([goal[0], goal[1], z], "#40c0ff", 5)
        mode = "recover" if recovering else ("cover" if cover_goal is not None else resource_kind)
        mf.draw.label(f"hp {int(me.get('hp', 0))} | {len(enemies)} seen | {mode}")
        return action


mf.run(Bot)
