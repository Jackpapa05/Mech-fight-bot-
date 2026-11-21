"""
Oval Ghost V9 — Complete Production Subsystems Module (v9_core.py)
Designed as a drop-in extension for V7 (commit 5119005) without rewriting V7 combat/aiming.
Includes:
1. TreeIndex: 32m spatial-hashed vision-only tree occlusion (handles crownX/crownY offsets).
2. ThreatTracker: Multi-modal enemy intelligence (obs.mechs, 3rd-party-filtered obs.beams, events, sounds).
3. unilateral_vo_danger: Non-cooperative 24-dir projectile avoidance with early mortar ground-impact
   truncation and straight-ray-only prism occlusion.
4. CoarseNavGraph: 16m traversability grid + throttled A* fallback on steering stagnation.
5. ContextSteerer: 24-direction Context Steering with probabilistic danger union, hard constraints,
   and smooth neighbor interpolation.
6. rooftop_reachable / should_jet_climb: Energy-aware rooftop & ledge jetpack gating.
"""

from __future__ import annotations

import heapq
import math
from array import array
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]

NUM_DIRS = 24
DIR_VECS: List[Vec2] = [
    (math.cos(2.0 * math.pi * k / NUM_DIRS), math.sin(2.0 * math.pi * k / NUM_DIRS))
    for k in range(NUM_DIRS)
]


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def unit(x: float, y: float) -> Vec2:
    r = math.hypot(x, y)
    return (0.0, 0.0) if r <= 1e-9 else (x / r, y / r)


def combine_danger(d_old: float, d_add: float) -> float:
    return 1.0 - (1.0 - clamp(d_old, 0.0, 1.0)) * (1.0 - clamp(d_add, 0.0, 1.0))


def point_to_segment_dist2(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    u = 0.0 if den <= 1e-12 else clamp(((px - ax) * dx + (py - ay) * dy) / den, 0.0, 1.0)
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def _segment_vertical_cylinder_interval(
    a: Vec3, b: Vec3, cx: float, cy: float, radius: float, z_min: float, z_max: float
) -> Optional[Tuple[float, float]]:
    """Parameter interval where segment a->b intersects a vertical cylinder."""
    ax, ay, az = a
    bx, by, bz = b
    dx, dy, dz = bx - ax, by - ay, bz - az
    aa = dx * dx + dy * dy
    ex, ey = ax - cx, ay - cy
    cc = ex * ex + ey * ey - radius * radius
    if aa <= 1e-12:
        if cc > 0.0:
            return None
        lo, hi = 0.0, 1.0
    else:
        bb = 2.0 * (ex * dx + ey * dy)
        disc = bb * bb - 4.0 * aa * cc
        if disc < 0.0:
            return None
        root = math.sqrt(max(0.0, disc))
        lo = max(0.0, (-bb - root) / (2.0 * aa))
        hi = min(1.0, (-bb + root) / (2.0 * aa))
        if lo > hi:
            return None
    if abs(dz) <= 1e-12:
        if az < z_min or az > z_max:
            return None
    else:
        z1, z2 = (z_min - az) / dz, (z_max - az) / dz
        zlo, zhi = min(z1, z2), max(z1, z2)
        lo, hi = max(lo, zlo), min(hi, zhi)
        lo, hi = max(0.0, lo), min(1.0, hi)
        if lo > hi:
            return None
    return lo, hi


def _segment_first_blocked_point(
    a: Vec3, b: Vec3, blocked_fn: Callable[[Vec3, Vec3], bool], iterations: int = 7
) -> Optional[Tuple[Vec3, float]]:
    """Find a conservative first blocked point on a short segment by bisection."""
    if not blocked_fn(a, b):
        return None
    lo, hi = 0.0, 1.0
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        q = (a[0] + (b[0] - a[0]) * mid, a[1] + (b[1] - a[1]) * mid, a[2] + (b[2] - a[2]) * mid)
        if blocked_fn(a, q):
            hi = mid
        else:
            lo = mid
    u = hi
    point = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)
    return point, u


class TreeIndex:
    """Spatial-hashed tree index for vision-only occlusion (never blocks projectiles)."""

    def __init__(self, world: Dict[str, Any], bin_size: float = 32.0) -> None:
        self.bin_size = bin_size
        self.trees: List[Tuple[float, float, float, float, float, float, float, float, float]] = []
        self.bins: Dict[Tuple[int, int], List[int]] = {}
        rules = world.get("rules", {}) or {}
        self.canopy_density = float(rules.get("canopyDensity", 0.35))
        self.canopy_block_t = float(rules.get("canopyBlockT", 0.25))

        trees_obj = world.get("trees", {}) or {}
        fields = list(trees_obj.get("fields", []) or [])
        data = trees_obj.get("data", []) or []
        if not fields or not data:
            return

        stride = len(fields)
        idx = {name: i for i, name in enumerate(fields)}
        ix, iy, iz, ih = idx.get("x"), idx.get("y"), idx.get("z"), idx.get("height")
        icr, icb, itr = idx.get("crownR"), idx.get("crownBase"), idx.get("trunkR")
        icx, icy = idx.get("crownX"), idx.get("crownY")
        if ix is None or iy is None or iz is None or ih is None:
            return

        for i in range(len(data) // stride):
            b = i * stride
            x = float(data[b + ix])
            y = float(data[b + iy])
            z = float(data[b + iz])
            h = float(data[b + ih])
            crown_r = float(data[b + icr]) if icr is not None else 4.0
            crown_base = float(data[b + icb]) if icb is not None else h * 0.35
            trunk_r = float(data[b + itr]) if itr is not None else 0.45
            cx = float(data[b + icx]) if icx is not None else x
            cy = float(data[b + icy]) if icy is not None else y
            t_idx = len(self.trees)
            self.trees.append((x, y, z, h, crown_r, crown_base, trunk_r, cx, cy))

            pad = max(crown_r, trunk_r) + math.hypot(cx - x, cy - y) + 1.0
            for bx in range(int(math.floor((x - pad) / bin_size)), int(math.floor((x + pad) / bin_size)) + 1):
                for by in range(int(math.floor((y - pad) / bin_size)), int(math.floor((y + pad) / bin_size)) + 1):
                    self.bins.setdefault((bx, by), []).append(t_idx)

    def vision_blocked_by_trees(self, a: Vec3, b: Vec3) -> bool:
        """Check vision-only trunk/canopy occlusion using segment-cylinder intervals.

        Trees never block weapon projectiles; callers must use this only for vision.
        """
        if not self.trees:
            return False
        ax, ay, az = a
        bx, by, bz = b
        seg_len = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)
        if seg_len <= 1e-9:
            return False

        seen = set()
        opacity = 0.0
        ix0 = int(math.floor(min(ax, bx) / self.bin_size))
        ix1 = int(math.floor(max(ax, bx) / self.bin_size))
        iy0 = int(math.floor(min(ay, by) / self.bin_size))
        iy1 = int(math.floor(max(ay, by) / self.bin_size))
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                for t_idx in self.bins.get((ix, iy), ()):
                    if t_idx in seen:
                        continue
                    seen.add(t_idx)
                    tx, ty, tz, th, crown_r, crown_base, trunk_r, crx, cry = self.trees[t_idx]

                    trunk_interval = _segment_vertical_cylinder_interval(
                        a, b, tx, ty, trunk_r, tz, tz + crown_base + 0.5
                    )
                    if trunk_interval is not None:
                        return True

                    crown_interval = _segment_vertical_cylinder_interval(
                        a, b, crx, cry, crown_r, tz + crown_base, tz + th
                    )
                    if crown_interval is not None:
                        chord_3d = seg_len * max(0.0, crown_interval[1] - crown_interval[0])
                        opacity += chord_3d * self.canopy_density
                        if opacity >= self.canopy_block_t:
                            return True
        return False



class ThreatTracker:
    """Fuses obs.mechs, 3rd-party-filtered obs.beams, events, and sounds with timestamp ordering."""

    def __init__(self) -> None:
        self.enemies: Dict[int, Dict[str, Any]] = {}
        self.last_attacker_id: Optional[int] = None
        self.last_attacker_t: float = -999.0
        self.defensive_bearing: Optional[float] = None
        self.defensive_bearing_t: float = -999.0

    def update(self, obs: Dict[str, Any], me: Dict[str, Any]) -> None:
        now = float(obs.get("t", 0.0))
        mx, my, _ = me["pos"]

        for m in obs.get("mechs", []) or []:
            if m.get("kind") != "mech":
                continue
            mid = int(m["id"])
            self.enemies[mid] = {
                "id": mid,
                "pos": list(m["pos"]),
                "vel": list(m.get("vel", (0.0, 0.0, 0.0))),
                "hp": m.get("hp"),
                "weapons": list(m.get("weapons", []) or []),
                "charging": bool(m.get("charging", False)),
                "cubes": int(m.get("cubes", 0)),
                "last_seen_t": now,
            }

        # Beam tracking: filter out 3rd-party beams not aimed near us (>35m from segment)
        for b in obs.get("beams", []) or []:
            by_id = b.get("by")
            path = b.get("path") or []
            age = float(b.get("age", 0.0))
            if by_id is None or len(path) < 2 or by_id == me.get("id") or age > 1.2:
                continue
            mid = int(by_id)
            p0, p1 = path[0], path[-1]
            near_us = point_to_segment_dist2(mx, my, float(p0[0]), float(p0[1]), float(p1[0]), float(p1[1])) <= 35.0
            ev_t = now - age
            ex = self.enemies.get(mid)
            if ex is None or ev_t > ex["last_seen_t"]:
                self.enemies[mid] = {
                    "id": mid,
                    "pos": [float(p0[0]), float(p0[1]), max(0.0, float(p0[2]) - 7.0)],
                    "vel": ex["vel"] if ex else [0.0, 0.0, 0.0],
                    "hp": ex["hp"] if ex else None,
                    "weapons": [str(b.get("kind", "laser"))],
                    "charging": False,
                    "cubes": ex["cubes"] if ex else 0,
                    "last_seen_t": ev_t,
                }
            if near_us and ev_t > self.defensive_bearing_t:
                self.defensive_bearing = math.atan2(float(p0[1]) - my, float(p0[0]) - mx)
                self.defensive_bearing_t = ev_t

        for ev in obs.get("events", []) or []:
            if ev.get("type") == "damaged" and ev.get("weapon") != "zone":
                by_id = ev.get("by")
                if by_id is not None:
                    self.last_attacker_id = int(by_id)
                    self.last_attacker_t = now
                if ev.get("bearing") is not None:
                    self.defensive_bearing = float(ev["bearing"])
                    self.defensive_bearing_t = now

        for s in obs.get("sounds", []) or []:
            kind = str(s.get("kind", ""))
            age = float(s.get("age", 9.9))
            dist_band = str(s.get("dist", "far"))
            # Far sounds are useful ambient information but should not rotate the
            # mech's rear armour toward a distant third-party fight.
            if (kind in ("gun", "mortar", "explosion", "laser", "laser_charge", "lightning")
                    and age <= 1.0 and dist_band in ("near", "mid")):
                ev_t = now - age
                if ev_t > self.defensive_bearing_t:
                    self.defensive_bearing = float(s.get("bearing", 0.0))
                    self.defensive_bearing_t = ev_t

        for k in [k for k, v in self.enemies.items() if now - v["last_seen_t"] > 5.0]:
            del self.enemies[k]

    def prioritized_threats(self, obs: Dict[str, Any], me: Dict[str, Any]) -> List[Dict[str, Any]]:
        now = float(obs.get("t", 0.0))
        mx, my, _ = me["pos"]
        ranked = []
        for e in self.enemies.values():
            d = math.hypot(e["pos"][0] - mx, e["pos"][1] - my)
            score = (100.0 / max(15.0, d)) * max(0.2, 1.0 - (now - e["last_seen_t"]) / 5.5)
            if e["charging"]:
                score += 45.0
            if e["id"] == self.last_attacker_id and (now - self.last_attacker_t) <= 6.0:
                score += 30.0
            if "laser" in e["weapons"] or "mortar" in e["weapons"]:
                score += 18.0
            if e["hp"] is not None and float(e["hp"]) < 450.0:
                score += 15.0
            ranked.append((score, {**e, "dist": d, "threat_score": score}))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked]


def unilateral_vo_danger(
    me: Dict[str, Any],
    projectiles: Sequence[Dict[str, Any]],
    move_speed: float,
    mech_radius: float,
    mech_height: float,
    gravity: float = 22.0,
    ray_blocked_fn: Optional[Callable[[Vec3, Vec3], bool]] = None,
    terrain_height_fn: Optional[Callable[[float, float], Optional[float]]] = None,
) -> List[float]:
    """Evaluate projectile danger for 24 candidate horizontal movement directions.

    Straight bullets are checked against their own forward segment to predicted CPA.
    Mortars are never culled by straight-line LOS: their ballistic path is sampled,
    and the sweep is truncated at terrain or prism impact before checking splash.
    """
    danger = [0.0] * NUM_DIRS
    if not projectiles:
        return danger
    mx, my, mz = (float(v) for v in me["pos"])
    mech_center_z = mz + mech_height * 0.5

    for p in projectiles:
        kind = str(p.get("kind", "gun"))
        px, py, pz = (float(v) for v in p["pos"])
        pvx, pvy, pvz = (float(v) for v in p.get("vel", (0.0, 0.0, 0.0)))
        rx0, ry0, rz0 = mx - px, my - py, mech_center_z - pz
        if abs(rx0) > 160.0 and abs(ry0) > 160.0:
            continue

        safe_r = max(7.0, mech_radius + 4.5) if kind == "mortar" else max(4.2, mech_radius + 1.3)

        if kind == "mortar":
            # Build the projectile path once, independent of candidate movement.
            trajectory: List[Tuple[float, Vec3]] = [(0.0, (px, py, pz))]
            prev_t = 0.0
            prev = (px, py, pz)
            impact = False
            impact_t = 1.2
            # 50 ms sampling is sufficiently fine for a 72 m/s mortar while
            # keeping the work bounded (24 directions × at most 24 samples).
            for step in range(1, 25):
                tt = step * 0.05
                sx = px + pvx * tt
                sy = py + pvy * tt
                sz = pz + pvz * tt - 0.5 * gravity * tt * tt
                curr = (sx, sy, sz)

                ground_hit = False
                gh = terrain_height_fn(sx, sy) if terrain_height_fn is not None else None
                if gh is not None and sz <= gh:
                    curr = (sx, sy, float(gh))
                    ground_hit = True

                solid_hit = False
                hit_point = curr
                hit_t = tt
                if not ground_hit and ray_blocked_fn is not None and ray_blocked_fn(prev, curr):
                    # The segment is short (3.6 m at the default mortar speed);
                    # use its midpoint as a conservative impact estimate rather
                    # than performing multiple expensive bisection raycasts.
                    frac = 0.5
                    hit_t = prev_t + (tt - prev_t) * frac
                    hit_point = (
                        prev[0] + (curr[0] - prev[0]) * frac,
                        prev[1] + (curr[1] - prev[1]) * frac,
                        prev[2] + (curr[2] - prev[2]) * frac,
                    )
                    solid_hit = True

                if ground_hit or solid_hit:
                    trajectory.append((hit_t, hit_point))
                    impact = True
                    impact_t = hit_t
                    break

                trajectory.append((tt, curr))
                prev_t, prev = tt, curr

            for k, (ux, uy) in enumerate(DIR_VECS):
                best_d, best_t = 1e9, 1.2
                for tt, shell in trajectory:
                    mx_t = mx + ux * move_speed * tt
                    my_t = my + uy * move_speed * tt
                    mz_t = mech_center_z
                    dd = math.sqrt((mx_t - shell[0]) ** 2 + (my_t - shell[1]) ** 2 + (mz_t - shell[2]) ** 2)
                    if dd < best_d:
                        best_d, best_t = dd, tt
                if best_d < safe_r and best_t <= (impact_t if impact else 1.2):
                    val = clamp(((safe_r - best_d) / safe_r) * clamp(0.90 / (best_t + 0.15), 0.25, 1.0) * 1.15, 0.0, 1.0)
                    if val > danger[k]:
                        danger[k] = val
            continue

        # Straight gun/NPC bullets: cull once only when a solid intercepts the
        # projectile before it enters the full 0.85 s reachable envelope of our
        # mech. If it enters that envelope first, keep it as a threat for all
        # candidate paths (conservative at corner exits).
        if ray_blocked_fn is not None:
            pv2 = pvx * pvx + pvy * pvy + pvz * pvz
            reach_r = mech_radius + move_speed * 0.85 + 3.0
            c = rx0 * rx0 + ry0 * ry0 + rz0 * rz0 - reach_r * reach_r
            t_enter = 0.0
            if c > 0.0 and pv2 > 1e-8:
                bb = 2.0 * (rx0 * pvx + ry0 * pvy + rz0 * pvz)
                disc = bb * bb - 4.0 * pv2 * c
                if disc < 0.0:
                    continue
                t_enter = (-bb - math.sqrt(max(0.0, disc))) / (2.0 * pv2)
                if t_enter < 0.0 or t_enter > 0.85:
                    continue
            if t_enter > 0.05:
                envelope_point = (px + pvx * t_enter, py + pvy * t_enter, pz + pvz * t_enter)
                if ray_blocked_fn((px, py, pz), envelope_point):
                    continue

        for k, (ux, uy) in enumerate(DIR_VECS):
            rvx, rvy, rvz = ux * move_speed - pvx, uy * move_speed - pvy, -pvz
            vv = rvx * rvx + rvy * rvy + rvz * rvz
            best_t = 0.0 if vv <= 1e-6 else clamp(-(rx0 * rvx + ry0 * rvy + rz0 * rvz) / vv, 0.0, 0.85)
            dd = math.sqrt((rx0 + rvx * best_t) ** 2 + (ry0 + rvy * best_t) ** 2 + (rz0 + rvz * best_t) ** 2)
            if dd < safe_r:
                val = clamp(((safe_r - dd) / safe_r) * clamp(0.90 / (best_t + 0.15), 0.25, 1.0) * 1.15, 0.0, 1.0)
                if val > danger[k]:
                    danger[k] = val
    return danger



class CoarseNavGraph:
    """16m coarse traversability grid built at hello; runs throttled A* only on steering stagnation."""

    def __init__(self, bot: Any, cell_size: float = 16.0) -> None:
        self.cell_size = cell_size
        self.last_replan_t: float = -999.0
        self.cached_waypoint: Optional[Vec2] = None
        self.cached_goal: Optional[Vec2] = None
        self.bot = bot

    def _cell(self, x: float, y: float) -> Tuple[int, int]:
        return (int(math.floor(x / self.cell_size)), int(math.floor(y / self.cell_size)))

    def _in_bounds(self, x: float, y: float) -> bool:
        meta = getattr(self.bot, "terrain_meta", {}) or {}
        if not meta:
            return True
        min_x = float(meta.get("minX", -1e9))
        min_y = float(meta.get("minY", -1e9))
        max_x = min_x + (int(meta.get("nx", 0)) - 1) * float(meta.get("step", 1.0))
        max_y = min_y + (int(meta.get("ny", 0)) - 1) * float(meta.get("step", 1.0))
        return min_x <= x <= max_x and min_y <= y <= max_y

    def _cell_clear(self, x: float, y: float, z: float, height: float, radius: float) -> bool:
        if not self._in_bounds(x, y):
            return False
        wz = self.bot._terrain_height(x, y)
        if wz is None:
            return False
        return not self.bot._blocked(x, y, wz, height, radius)

    def _center(self, ix: int, iy: int) -> Vec2:
        return ((ix + 0.5) * self.cell_size, (iy + 0.5) * self.cell_size)

    def find_waypoint(self, now: float, start: Vec3, goal: Vec2, radius: float, height: float) -> Vec2:
        if (now - self.last_replan_t < 0.5 and self.cached_waypoint is not None
                and self.cached_goal is not None
                and math.hypot(goal[0] - self.cached_goal[0], goal[1] - self.cached_goal[1]) < 24.0):
            return self.cached_waypoint
        self.last_replan_t = now
        if not self._in_bounds(goal[0], goal[1]):
            return goal
        sc = self._cell(start[0], start[1])
        gc = self._cell(goal[0], goal[1])
        if sc == gc:
            self.cached_waypoint = goal
            return goal

        pq: List[Tuple[float, Tuple[int, int]]] = [(0.0, sc)]
        came: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_cost: Dict[Tuple[int, int], float] = {sc: 0.0}
        best_node, best_h = sc, math.hypot(gc[0] - sc[0], gc[1] - sc[1])
        expands = 0

        # Keep worst-case planning bounded; local steering remains active while
        # this coarse fallback makes incremental progress.
        while pq and expands < 180:
            _, cur = heapq.heappop(pq)
            expands += 1
            if cur == gc:
                best_node = cur
                break
            cx, cy = cur
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nxt = (cx + dx, cy + dy)
                wx, wy = self._center(nxt[0], nxt[1])
                wz = self.bot._terrain_height(wx, wy)
                if wz is None or not self._cell_clear(wx, wy, wz, height, radius):
                    continue
                # Do not cut diagonally through the corner of two blocked cells.
                if dx != 0 and dy != 0:
                    side_a = self._center(cx + dx, cy)
                    side_b = self._center(cx, cy + dy)
                    if (not self._cell_clear(side_a[0], side_a[1], start[2], height, radius)
                            or not self._cell_clear(side_b[0], side_b[1], start[2], height, radius)):
                        continue
                cur_xy = self._center(cx, cy)
                cur_z = self.bot._terrain_height(cur_xy[0], cur_xy[1])
                if cur_z is None:
                    cur_z = start[2]
                edge_dx, edge_dy = wx - cur_xy[0], wy - cur_xy[1]
                edge_len = math.hypot(edge_dx, edge_dy)
                mech_cfg = getattr(self.bot, "cfg", {}).get("mech", {}) or {}
                step_up = float(mech_cfg.get("step_up", 1.2))
                max_slope = float(mech_cfg.get("max_slope_deg", 50.0))
                if not self.bot._terrain_segment_clear(cur_xy[0], cur_xy[1], cur_z, edge_dx / max(edge_len, 1e-9), edge_dy / max(edge_len, 1e-9), edge_len, step_up, max_slope):
                    continue
                step_c = 1.414 if (dx != 0 and dy != 0) else 1.0
                nc = g_cost[cur] + step_c
                if nc < g_cost.get(nxt, 1e9):
                    g_cost[nxt] = nc
                    came[nxt] = cur
                    h = math.hypot(gc[0] - nxt[0], gc[1] - nxt[1])
                    if h < best_h:
                        best_h = h
                        best_node = nxt
                    heapq.heappush(pq, (nc + h * 1.15, nxt))

        cur = best_node
        path = []
        while cur in came:
            path.append(self._center(cur[0], cur[1]))
            cur = came[cur]
        path.reverse()
        # The first reconstructed node is the immediate next waypoint; skipping
        # it can make the steering controller cut across the first obstacle.
        self.cached_waypoint = path[0] if path else goal
        self.cached_goal = (float(goal[0]), float(goal[1]))
        return self.cached_waypoint


class ContextSteerer:
    """24-direction Context Steering evaluator with hard constraints, VO, and stagnation A* fallback."""

    def __init__(self, nav: Optional[CoarseNavGraph] = None) -> None:
        self.prev_move: Vec2 = (0.0, 0.0)
        self.nav = nav
        self._stagnation_pos: Optional[Vec2] = None
        self._stagnation_t: float = 0.0

    def evaluate(
        self,
        bot: Any,
        obs: Dict[str, Any],
        me: Dict[str, Any],
        goal: Vec2,
        goal_weight: float,
        threats: Sequence[Dict[str, Any]],
        strafe_vec: Optional[Vec2] = None,
        strafe_weight: float = 0.0,
    ) -> Tuple[Vec2, bool]:
        now = float(obs.get("t", 0.0))
        mx, my, mz = float(me["pos"][0]), float(me["pos"][1]), float(me["pos"][2])
        stats = me.get("stats", {}) or {}
        radius = float(stats.get("radius", 2.5))
        height = float(stats.get("height", 9.0))
        step_up = float(stats.get("step_up", 1.5))
        max_slope = float(stats.get("max_slope_deg", 50.0))
        walk_speed = float(stats.get("walk_speed", 14.0))
        boost_speed = float(stats.get("boost_speed", 22.0))

        # Stagnation detection for coarse A* fallback
        active_goal = goal
        if self._stagnation_pos is None:
            self._stagnation_pos = (mx, my)
            self._stagnation_t = now
        elif now - self._stagnation_t >= 0.8:
            if math.hypot(mx - self._stagnation_pos[0], my - self._stagnation_pos[1]) < 2.0 and self.nav is not None:
                active_goal = self.nav.find_waypoint(now, (mx, my, mz), goal, radius, height)
            self._stagnation_pos = (mx, my)
            self._stagnation_t = now

        interest = [0.0] * NUM_DIRS
        danger = [0.0] * NUM_DIRS
        hard_blocked = [False] * NUM_DIRS

        gux, guy = unit(active_goal[0] - mx, active_goal[1] - my)
        px, py = self.prev_move
        for k, (dx, dy) in enumerate(DIR_VECS):
            val = max(0.0, dx * gux + dy * guy) * goal_weight
            if strafe_vec is not None and strafe_weight > 0.0:
                val += max(0.0, dx * strafe_vec[0] + dy * strafe_vec[1]) * strafe_weight
            if px != 0.0 or py != 0.0:
                val += max(0.0, dx * px + dy * py) * 0.18
            # Modest vision-only concealment preference. Buildings remain the
            # hard cover; tree crowns/trunks only reduce enemy vision, not shots.
            tree_index = getattr(bot, "tree_index", None)
            if tree_index is not None and threats:
                qx, qy = mx + dx * 14.0, my + dy * 14.0
                qz = bot._terrain_height(qx, qy)
                if qz is None:
                    qz = mz
                our_eye = (qx, qy, qz + float(stats.get("eye_height", 8.0)))
                conceal_count = 0
                for th in threats[:2]:
                    tp = th.get("pos", (0.0, 0.0, 0.0))
                    if math.hypot(float(tp[0]) - qx, float(tp[1]) - qy) > 160.0:
                        continue
                    enemy_eye = (float(tp[0]), float(tp[1]), float(tp[2]) + 8.0)
                    if not bot._ray_blocked(enemy_eye, our_eye) and tree_index.vision_blocked_by_trees(enemy_eye, our_eye):
                        conceal_count += 1
                val += min(0.30, conceal_count * 0.10)
            interest[k] = val

        for k, (dx, dy) in enumerate(DIR_VECS):
            if not bot._terrain_segment_clear(mx, my, mz, dx, dy, 14.0, step_up, max_slope):
                hard_blocked[k] = True
                danger[k] = 1.0
                continue
            if bot._blocked(mx + dx * 4.5, my + dy * 4.5, mz, height, radius):
                hard_blocked[k] = True
                danger[k] = 1.0
                continue
            if bot._blocked(mx + dx * 9.5, my + dy * 9.5, mz, height, radius):
                danger[k] = combine_danger(danger[k], 0.65)
            elif bot._blocked(mx + dx * 16.0, my + dy * 16.0, mz, height, radius):
                danger[k] = combine_danger(danger[k], 0.35)

        zone = obs.get("zone", {}) or {}
        zc = zone.get("center", (0.0, 0.0))
        zr = float(zone.get("radius", 9999.0))
        dz_c = math.hypot(mx - zc[0], my - zc[1])
        if dz_c > max(1.0, zr - 16.0):
            out_x, out_y = unit(mx - zc[0], my - zc[1])
            zone_sev = clamp((dz_c - (zr - 16.0)) / 18.0, 0.25, 0.95)
            for k, (dx, dy) in enumerate(DIR_VECS):
                out_dot = dx * out_x + dy * out_y
                if out_dot > 0.0:
                    danger[k] = combine_danger(danger[k], out_dot * zone_sev)

        energy = float(me.get("energy", 0.0))
        eval_speed = boost_speed if energy > 15.0 else walk_speed
        vo_danger = unilateral_vo_danger(
            me, obs.get("projectiles", []) or [], eval_speed, radius, height,
            ray_blocked_fn=getattr(bot, "_ray_blocked", None),
            terrain_height_fn=getattr(bot, "_terrain_height", None),
        )
        for k in range(NUM_DIRS):
            if vo_danger[k] > 0.0:
                danger[k] = combine_danger(danger[k], vo_danger[k])
        urgent_dodge = False

        for th in threats[:3]:
            tx, ty, _ = th["pos"]
            t_dist = math.hypot(tx - mx, ty - my)
            if t_dist < 1e-3:
                continue
            to_tx, to_ty = (tx - mx) / t_dist, (ty - my) / t_dist
            if th.get("charging") and t_dist < 260.0:
                for k, (dx, dy) in enumerate(DIR_VECS):
                    danger[k] = combine_danger(danger[k], 0.55 * abs(dx * to_tx + dy * to_ty))
            elif len(threats) >= 2 and t_dist < 90.0:
                for k, (dx, dy) in enumerate(DIR_VECS):
                    approach = max(0.0, dx * to_tx + dy * to_ty)
                    danger[k] = combine_danger(danger[k], 0.40 * approach * (1.0 - t_dist / 90.0))

        scores = [-1e9] * NUM_DIRS
        best_k, best_s = -1, -1e9
        for k in range(NUM_DIRS):
            if hard_blocked[k] or danger[k] >= 0.92:
                continue
            s = interest[k] - danger[k] * 1.15
            scores[k] = s
            if s > best_s:
                best_s, best_k = s, k

        if best_k == -1:
            min_d = 1e9
            for k in range(NUM_DIRS):
                if not hard_blocked[k] and danger[k] < min_d:
                    min_d, best_k = danger[k], k
            out = DIR_VECS[best_k if best_k != -1 else 0]
            self.prev_move = out
            return out, bool(best_k != -1 and vo_danger[best_k] >= 0.45)

        # Boost only when the selected direction itself remains dangerous. A
        # projectile threatening an unchosen direction should not drain energy.
        urgent_dodge = vo_danger[best_k] >= 0.45
        left_k = (best_k - 1) % NUM_DIRS
        right_k = (best_k + 1) % NUM_DIRS
        w_c = max(0.05, scores[best_k] + 1.0)
        w_l = max(0.0, scores[left_k] + 1.0) * 0.5 if scores[left_k] > -1e8 else 0.0
        w_r = max(0.0, scores[right_k] + 1.0) * 0.5 if scores[right_k] > -1e8 else 0.0
        out = unit(
            DIR_VECS[best_k][0] * w_c + DIR_VECS[left_k][0] * w_l + DIR_VECS[right_k][0] * w_r,
            DIR_VECS[best_k][1] * w_c + DIR_VECS[left_k][1] * w_l + DIR_VECS[right_k][1] * w_r,
        )
        self.prev_move = out
        return out, urgent_dodge


def rooftop_reachable(prism: Dict[str, Any], ground_z: float, energy: float) -> bool:
    rise = float(prism.get("top", 0.0)) - ground_z
    if rise <= 1.2:
        return True
    return energy >= 75.0 and rise <= min(45.0, energy * 0.50)