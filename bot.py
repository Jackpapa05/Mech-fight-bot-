"""Oval Sentinel V2 - survival, map navigation, cover, loot and tactical combat.

Standard-library-only agent for mechfight/1.  The official wrapper handles JSONL I/O.
"""
from __future__ import annotations

import array
import heapq
import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import mechfight as mf

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
PI2 = 2.0 * math.pi


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def wrap(a: float) -> float:
    return (a + math.pi) % PI2 - math.pi


def unit(x: float, y: float) -> Vec2:
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-9 else (0.0, 0.0)


def d2(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def d3(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def dot2(a: Vec2, b: Vec2) -> float:
    return a[0] * b[0] + a[1] * b[1]


def point_in_ring(x: float, y: float, flat: Sequence[float]) -> bool:
    inside = False
    n = len(flat) // 2
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = flat[2 * i], flat[2 * i + 1]
        xj, yj = flat[2 * j], flat[2 * j + 1]
        if (yi > y) != (yj > y):
            den = yj - yi
            if abs(den) < 1e-12:
                den = 1e-12
            if x < (xj - xi) * (y - yi) / den + xi:
                inside = not inside
        j = i
    return inside


def point_segment_dist2(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den <= 1e-12:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = clamp(((px - ax) * dx + (py - ay) * dy) / den, 0.0, 1.0)
    qx, qy = ax + t * dx, ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


def ring_edge_dist2(x: float, y: float, flat: Sequence[float]) -> float:
    n = len(flat) // 2
    if n < 2:
        return 1e30
    best = 1e30
    for i in range(n):
        j = (i + 1) % n
        best = min(best, point_segment_dist2(x, y, flat[2*i], flat[2*i+1], flat[2*j], flat[2*j+1]))
    return best


def solve_intercept(r: Vec3, v: Vec3, speed: float, max_t: float = 2.5) -> float:
    # Relative velocity is target velocity minus shooter velocity; projectiles
    # inherit the launcher's velocity in world space.
    a = dot3(v, v) - speed * speed
    b = 2.0 * dot3(r, v)
    c = dot3(r, r)
    if abs(a) < 1e-9:
        t = -c / b if abs(b) > 1e-9 else 0.0
        return clamp(t, 0.0, max_t) if t > 0.0 else 0.0
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return 0.0
    sd = math.sqrt(disc)
    roots = [(-b - sd) / (2.0 * a), (-b + sd) / (2.0 * a)]
    valid = [q for q in roots if 0.01 < q <= max_t]
    return min(valid) if valid else 0.0


def dot3(a: Vec3, b: Vec3) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


class World:
    """Compact ground-level map, collision-aware A* and line-of-sight helper."""
    GRID = 8.0
    BIN = 48.0

    def __init__(self, map_dir: str, mech_height: float = 9.0, radius: float = 2.5):
        self.ok = False
        self.prisms: List[Dict[str, Any]] = []
        self.bins: Dict[Tuple[int, int], List[int]] = {}
        self.mechanics_height = mech_height
        self.radius = radius
        self.max_slope = math.tan(math.radians(50.0))
        self.min_x = self.min_y = 0.0
        self.max_x = self.max_y = 0.0
        self.terr_min_x = self.terr_min_y = 0.0
        self.terr_nx = self.terr_ny = 0
        self.terr_step = 1.0
        self.terrain = array.array('h')
        self.cols = self.rows = 0
        self.grid_x0 = self.grid_y0 = 0.0
        self.heights: List[float] = []
        self.blocked: bytearray = bytearray()
        try:
            with open(os.path.join(map_dir, 'v2', 'world.json'), 'r', encoding='utf-8') as f:
                w = json.load(f)
            b = w['bounds']
            self.min_x, self.max_x = float(b['minX']), float(b['maxX'])
            self.min_y, self.max_y = float(b['minY']), float(b['maxY'])
            td = w['terrain']
            self.terr_min_x, self.terr_min_y = float(td['minX']), float(td['minY'])
            self.terr_nx, self.terr_ny = int(td['nx']), int(td['ny'])
            self.terr_step = float(td.get('step', 1.0))
            with open(os.path.join(map_dir, 'v2', 'terrain.i16'), 'rb') as f:
                raw = f.read()
            self.terrain = array.array('h')
            self.terrain.frombytes(raw)
            if sys.byteorder != 'little':
                self.terrain.byteswap()
            for p in w.get('prisms', []):
                ring = p.get('ring') or []
                if len(ring) < 6:
                    continue
                xs, ys = ring[0::2], ring[1::2]
                self.prisms.append({
                    'base': float(p.get('base', -1e6)),
                    'top': float(p.get('top', 1e6)),
                    'ring': ring,
                    'holes': p.get('holes') or [],
                    'bbox': (min(xs), min(ys), max(xs), max(ys)),
                })
            self._build_bins()
            self._build_grid()
            self.ok = True
        except Exception as exc:
            # Map failure must not prevent a protocol-valid bot from playing.
            print('map load skipped: ' + repr(exc), file=sys.stderr)

    def _bin_key(self, x: float, y: float) -> Tuple[int, int]:
        return (int(math.floor(x / self.BIN)), int(math.floor(y / self.BIN)))

    def _build_bins(self) -> None:
        bins: Dict[Tuple[int, int], List[int]] = {}
        for k, p in enumerate(self.prisms):
            x0, y0, x1, y1 = p['bbox']
            ix0, iy0 = self._bin_key(x0 - self.radius - 1, y0 - self.radius - 1)
            ix1, iy1 = self._bin_key(x1 + self.radius + 1, y1 + self.radius + 1)
            for ix in range(ix0, ix1 + 1):
                for iy in range(iy0, iy1 + 1):
                    bins.setdefault((ix, iy), []).append(k)
        self.bins = bins

    def terrain_z(self, x: float, y: float) -> float:
        if not self.terrain:
            return 0.0
        fx = (x - self.terr_min_x) / self.terr_step
        fy = (y - self.terr_min_y) / self.terr_step
        i = int(clamp(math.floor(fx), 0, self.terr_nx - 2))
        j = int(clamp(math.floor(fy), 0, self.terr_ny - 2))
        tx, ty = clamp(fx - i, 0.0, 1.0), clamp(fy - j, 0.0, 1.0)
        q = j * self.terr_nx + i
        a = self.terrain[q] * 0.01
        b = self.terrain[q + 1] * 0.01
        c = self.terrain[q + self.terr_nx] * 0.01
        d = self.terrain[q + self.terr_nx + 1] * 0.01
        return (a*(1-tx)*(1-ty) + b*tx*(1-ty) + c*(1-tx)*ty + d*tx*ty)

    def _vertical_overlap(self, p: Dict[str, Any], z: float, h: float) -> bool:
        return not (z + h <= p['base'] + 0.05 or z >= p['top'] - 0.05)

    def _circle_hits_prism(self, x: float, y: float, z: float, p: Dict[str, Any], r: float) -> bool:
        if not self._vertical_overlap(p, z, self.mechanics_height):
            return False
        x0, y0, x1, y1 = p['bbox']
        if x < x0-r or x > x1+r or y < y0-r or y > y1+r:
            return False
        ring = p['ring']
        outer_in = point_in_ring(x, y, ring)
        outer_d = ring_edge_dist2(x, y, ring)
        inside_hole = False
        hole_near = False
        for hring in p['holes']:
            if point_in_ring(x, y, hring):
                inside_hole = True
                if ring_edge_dist2(x, y, hring) <= r*r:
                    hole_near = True
                break
        if outer_in and not inside_hole:
            return True
        if outer_in and inside_hole:
            return hole_near
        return outer_d <= r*r

    def _blocked_at(self, x: float, y: float, z: float) -> bool:
        key = self._bin_key(x, y)
        for idx in self.bins.get(key, ()):
            if self._circle_hits_prism(x, y, z, self.prisms[idx], self.radius + 0.7):
                return True
        return False

    def _build_grid(self) -> None:
        g = self.GRID
        self.grid_x0 = self.min_x + g * 0.5
        self.grid_y0 = self.min_y + g * 0.5
        self.cols = int((self.max_x - self.min_x) / g) + 1
        self.rows = int((self.max_y - self.min_y) / g) + 1
        n = self.cols * self.rows
        self.heights = [0.0] * n
        self.blocked = bytearray(n)
        for j in range(self.rows):
            y = self.grid_y0 + j*g
            for i in range(self.cols):
                x = self.grid_x0 + i*g
                idx = j*self.cols + i
                z = self.terrain_z(x, y)
                self.heights[idx] = z
                if self._blocked_at(x, y, z):
                    self.blocked[idx] = 1

    def xy(self, idx: int) -> Vec2:
        j, i = divmod(idx, self.cols)
        return (self.grid_x0 + i*self.GRID, self.grid_y0 + j*self.GRID)

    def cell(self, x: float, y: float) -> int:
        i = int(round((x - self.grid_x0) / self.GRID))
        j = int(round((y - self.grid_y0) / self.GRID))
        i = int(clamp(i, 0, self.cols-1))
        j = int(clamp(j, 0, self.rows-1))
        return j*self.cols + i

    def nearest_open(self, idx: int, max_r: int = 5) -> int:
        if not self.blocked[idx]:
            return idx
        j0, i0 = divmod(idx, self.cols)
        best, bestd = idx, 1e30
        for r in range(1, max_r+1):
            for dj in range(-r, r+1):
                for di in range(-r, r+1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    i, j = i0+di, j0+dj
                    if 0 <= i < self.cols and 0 <= j < self.rows:
                        ni = j*self.cols+i
                        if not self.blocked[ni]:
                            dd = di*di+dj*dj
                            if dd < bestd:
                                best, bestd = ni, dd
            if bestd < 1e30:
                return best
        return idx

    def _neighbors(self, idx: int):
        j, i = divmod(idx, self.cols)
        z0 = self.heights[idx]
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                if di == 0 and dj == 0:
                    continue
                ni, nj = i+di, j+dj
                if ni < 0 or nj < 0 or ni >= self.cols or nj >= self.rows:
                    continue
                q = nj*self.cols+ni
                if self.blocked[q]:
                    continue
                # Prevent diagonal corner-cutting through building corners.
                if di and dj and (self.blocked[j*self.cols+ni] or self.blocked[nj*self.cols+i]):
                    continue
                dist = self.GRID * (1.41421356 if di and dj else 1.0)
                dz = self.heights[q] - z0
                if abs(dz) > max(1.2, self.max_slope*dist):
                    continue
                yield q, dist + abs(dz)*0.35

    def path(self, start_xy: Vec2, goal_xy: Vec2, max_expand: int = 2800) -> List[Vec2]:
        if not self.ok or not self.cols:
            return []
        s = self.nearest_open(self.cell(*start_xy), 4)
        g0 = self.cell(*goal_xy)
        g = self.nearest_open(g0, 7)
        if self.blocked[s] or self.blocked[g]:
            return []
        if s == g:
            return [self.xy(g)]
        goalp = self.xy(g)
        openq: List[Tuple[float, float, int]] = []
        heapq.heappush(openq, (d2(self.xy(s), goalp), 0.0, s))
        came: Dict[int, int] = {}
        gscore: Dict[int, float] = {s: 0.0}
        closed = set()
        found = False
        expansions = 0
        while openq and expansions < max_expand:
            _, gc, cur = heapq.heappop(openq)
            if cur in closed:
                continue
            if cur == g:
                found = True
                break
            closed.add(cur)
            expansions += 1
            for nxt, cost in self._neighbors(cur):
                if nxt in closed:
                    continue
                ng = gc + cost
                if ng < gscore.get(nxt, 1e30):
                    gscore[nxt] = ng
                    came[nxt] = cur
                    f = ng + 1.20*d2(self.xy(nxt), goalp)
                    heapq.heappush(openq, (f, ng, nxt))
        if not found:
            # Return the best partial route toward the goal if the full route is cut off.
            if not closed:
                return []
            cur = min(closed, key=lambda q: d2(self.xy(q), goalp))
            if cur == s:
                return []
        else:
            cur = g
        ids = [cur]
        while cur != s and cur in came:
            cur = came[cur]
            ids.append(cur)
        ids.reverse()
        return [self.xy(q) for q in ids]

    def ray_blocked(self, a: Vec3, b: Vec3, step: float = 7.0) -> bool:
        dx, dy, dz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        length = math.sqrt(dx*dx+dy*dy+dz*dz)
        count = max(2, int(length/step))
        for k in range(1, count):
            f = k / count
            x, y, z = a[0]+dx*f, a[1]+dy*f, a[2]+dz*f
            # Terrain can occlude a low, long shot.
            if z < self.terrain_z(x, y) + 0.25:
                return True
            for idx in self.bins.get(self._bin_key(x, y), ()):
                p = self.prisms[idx]
                if p['base'] < z < p['top'] and point_in_ring(x, y, p['ring']):
                    in_hole = False
                    for h in p['holes']:
                        if point_in_ring(x, y, h):
                            in_hole = True
                            break
                    if not in_hole:
                        return True
        return False

    def visible_cover(self, candidate: Vec2, enemies: List[Dict[str, Any]]) -> Tuple[int, float]:
        if not self.ok:
            return (0, 0.0)
        z = self.terrain_z(candidate[0], candidate[1])
        blocked = 0
        nearest = 1e9
        for e in enemies:
            ep = e.get('pos', [0,0,0])
            dd = d2(candidate, ep)
            nearest = min(nearest, dd)
            a = (float(ep[0]), float(ep[1]), float(ep[2])+4.5)
            b = (candidate[0], candidate[1], z+7.5)
            if self.ray_blocked(a, b, 10.0):
                blocked += 1
        return blocked, nearest


class Bot:
    name = 'Oval-Sentinel-V2'

    def __init__(self, hello: mf.Hello):
        self.cfg = hello.get('config', {})
        self.rng = random.Random(int(hello.get('seed', 1)))
        map_dir = (hello.get('map') or {}).get('dir', '/arena')
        mech_cfg = self.cfg.get('mech', {})
        self.world = World(map_dir, float(mech_cfg.get('height', 9.0)), float(mech_cfg.get('radius', 2.5)))
        self.last_damage_t = -999.0
        self.last_attack_t = -999.0
        self.last_damage_bearing: Optional[float] = None
        self.last_attacker: Optional[int] = None
        self.last_enemy_contact_t = -999.0
        self.last_goal: Optional[Vec2] = None
        self.last_route: List[Vec2] = []
        self.last_route_t = -999.0
        self.last_route_goal: Optional[Vec2] = None
        self.last_cover_t = -999.0
        self.last_cover_goal: Optional[Vec2] = None
        self.last_target_id: Optional[int] = None
        self.last_weapon_kind: Optional[str] = None
        self.tick_count = 0
        self.strafe_sign = -1.0 if self.rng.random() < 0.5 else 1.0

    # -------- zone and navigation --------
    def _future_circle(self, obs: Dict[str, Any], horizon: float = 8.0) -> Tuple[Vec2, float]:
        z = obs.get('zone', {})
        c = z.get('center', [0.0, 0.0])
        nc = z.get('next_center', c)
        r = float(z.get('radius', 9999.0))
        nr = float(z.get('next_radius', r))
        t = float(obs.get('t', 0.0))
        ss = float(z.get('shrink_start', 1e9))
        se = float(z.get('shrink_end', 1e9))
        future_t = t + horizon
        # The current/next fields describe the active phase. Predict through
        # the remaining portion of this shrink, but don't extrapolate past it.
        if future_t <= ss or se <= ss:
            return (float(c[0]), float(c[1])), r
        f = clamp((future_t - ss) / (se - ss), 0.0, 1.0)
        return ((float(c[0]) + (float(nc[0])-float(c[0]))*f,
                 float(c[1]) + (float(nc[1])-float(c[1]))*f),
                r + (nr-r)*f)

    def _zone_goal(self, obs: Dict[str, Any], me: Dict[str, Any]) -> Optional[Vec2]:
        x, y = float(me['pos'][0]), float(me['pos'][1])
        z = obs.get('zone', {})
        c = z.get('center', [0.0, 0.0])
        r = float(z.get('radius', 9999.0))
        fc, fr = self._future_circle(obs, 10.0)
        dc = d2((x,y), c)
        df = d2((x,y), fc)
        # A 20-28m buffer prevents edge damage from small pathing errors.
        if not me.get('in_zone', True) or dc > r - 12.0:
            return (float(c[0]), float(c[1]))
        if df > fr - 24.0:
            ux, uy = unit(x-fc[0], y-fc[1])
            if ux == 0.0 and uy == 0.0:
                ux, uy = 1.0, 0.0
            safe_r = max(0.0, fr - 32.0)
            return (fc[0] + ux*safe_r, fc[1] + uy*safe_r)
        return None

    def _inside_predicted_zone(self, obs: Dict[str, Any], p: Vec2) -> bool:
        z = obs.get('zone', {})
        c = z.get('center', [0.0,0.0])
        r = float(z.get('radius', 9999.0))
        fc, fr = self._future_circle(obs, 8.0)
        return d2(p,c) < r-8.0 and d2(p,fc) < fr-18.0

    def _navigate(self, me: Dict[str, Any], goal: Vec2, urgent: bool = False) -> Vec2:
        pos = me['pos']
        x, y = float(pos[0]), float(pos[1])
        if d2((x,y), goal) < 5.0:
            return (0.0, 0.0)
        if self.world.ok:
            gcell = self.world.cell(goal[0], goal[1])
            recalc = (not self.last_route or self.last_route_goal is None or
                      d2(self.last_route_goal, goal) > 12.0 or
                      self.now - self.last_route_t > (0.65 if urgent else 1.2))
            if recalc:
                self.last_route = self.world.path((x,y), goal)
                self.last_route_goal = goal
                self.last_route_t = self.now
            waypoint = goal
            if self.last_route:
                # Pick a waypoint far enough ahead to smooth movement but not
                # so far that a corner cuts into a building.
                for q in self.last_route[1:]:
                    waypoint = q
                    if d2((x,y), q) >= 22.0:
                        break
            dx, dy = waypoint[0]-x, waypoint[1]-y
            return unit(dx,dy)
        # Safe fallback if map loading failed: steer away from nearby prism-free
        # samples is unavailable, so use the objective vector.
        return unit(goal[0]-x, goal[1]-y)

    def _cover_goal(self, obs: Dict[str, Any], me: Dict[str, Any], enemies: List[Dict[str, Any]]) -> Optional[Vec2]:
        if not self.world.ok or not enemies:
            return None
        t = float(obs.get('t',0.0))
        if self.last_cover_goal is not None and t-self.last_cover_t < 2.0:
            # Reuse a still-safe point; avoid path goal thrashing every tick.
            if self._inside_predicted_zone(obs, self.last_cover_goal):
                return self.last_cover_goal
        x, y = float(me['pos'][0]), float(me['pos'][1])
        ci = self.world.cell(x,y)
        cj, ii = divmod(ci,self.world.cols)
        best: Optional[Vec2] = None
        best_score = -1e30
        # Local 9x9 sample grid (~64m square). Evaluate cover against the actual
        # threat bearings rather than simply fleeing in a straight line.
        for dj in range(-3,4):
            for di in range(-3,4):
                i, j = ii+di, cj+dj
                if i < 0 or j < 0 or i >= self.world.cols or j >= self.world.rows:
                    continue
                idx = j*self.world.cols+i
                if self.world.blocked[idx]:
                    continue
                p = self.world.xy(idx)
                travel = d2((x,y),p)
                if travel < 8.0 or travel > 72.0 or not self._inside_predicted_zone(obs,p):
                    continue
                blocked, nearest = self.world.visible_cover(p, enemies[:3])
                # Prefer breaking line of sight and preserving a little standoff.
                score = blocked*18.0 + min(nearest,140.0)*0.09 - travel*0.13
                if nearest < 28.0:
                    score -= (28.0-nearest)*1.2
                if score > best_score:
                    best_score, best = score, p
        if best is not None:
            self.last_cover_goal, self.last_cover_t = best, t
        return best

    # -------- target/resource selection --------
    def _nearest_enemy_dist(self, me: Dict[str, Any], enemies: List[Dict[str, Any]]) -> float:
        return min((d3(me['pos'],e['pos']) for e in enemies), default=1e9)

    def _resource_goal(self, obs: Dict[str, Any], me: Dict[str, Any], enemies: List[Dict[str, Any]]) -> Tuple[Optional[Vec2], Optional[Dict[str, Any]], str]:
        x,y,z = me['pos']
        hp = float(me.get('hp',1.0))/max(1.0,float(me.get('max_hp',1.0)))
        cubes = int(me.get('cubes',0))
        nd = self._nearest_enemy_dist(me,enemies)
        nearby = sum(1 for e in enemies if d3(e['pos'],me['pos']) < 115.0)
        candidates: List[Tuple[float,Vec2,Dict[str,Any],str]] = []

        # Supply drops are the best single recovery opportunity, but only when
        # the approach and four-second capture window look reasonably safe.
        for drop in obs.get('drops',[]) or []:
            if float(drop.get('lands_in',999.0)) > 0.0:
                continue
            holder = drop.get('holder')
            if holder is not None and holder != me.get('id'):
                continue
            p = drop.get('pos',[x,y,z])
            dd = d2((x,y),p)
            if dd > 175.0 or nd < 52.0 or nearby >= 2 or not self._inside_predicted_zone(obs,(p[0],p[1])):
                continue
            progress = float(drop.get('progress',0.0)) if holder == me.get('id') else 0.0
            value = 175.0 + (1.0-hp)*75.0 + max(0,5-cubes)*7.0 + progress*15.0
            candidates.append((value-dd*0.78,(float(p[0]),float(p[1])),drop,'drop'))

        # Loose cubes are efficient; skip only when the pickup would be contested.
        for cube in obs.get('cubes',[]) or []:
            p = cube.get('pos',[x,y,z]); dd = d2((x,y),p)
            if dd > 58.0 or nd < 22.0 or abs(float(p[2])-float(z)) > 12.0:
                continue
            value = 118.0 - dd*1.35 + max(0,8-cubes)*2.0
            candidates.append((value,(float(p[0]),float(p[1])),cube,'cube'))

        weapons = me.get('weapons',[]) or []
        slot1 = weapons[1] if len(weapons)>1 else None
        held = {w.get('kind') for w in weapons if isinstance(w,dict)}
        if isinstance(slot1,dict) and slot1.get('kind')=='laser' and float(slot1.get('charge',0.0))>0.10:
            slot1='busy-laser'
        for pick in obs.get('pickups',[]) or []:
            kind = pick.get('kind')
            if kind == 'gun' or kind in held:
                continue
            p = pick.get('pos',[x,y,z]); dd = d2((x,y),p)
            if dd > 78.0 or nd < 48.0 or abs(float(p[2])-float(z)) > 16.0:
                continue
            if slot1 is None:
                pref = {'laser':112.0,'mortar':102.0,'lightning':96.0}.get(kind,60.0)
            else:
                old = slot1.get('kind') if isinstance(slot1,dict) else None
                # Only swap a clearly inferior secondary when the pickup is near.
                rank = {'laser':3,'mortar':2,'lightning':1}
                if old is None or rank.get(kind,0) <= rank.get(old,0) or dd > 14.0:
                    continue
                pref = 85.0
            candidates.append((pref-dd*0.8,(float(p[0]),float(p[1])),pick,'weapon'))

        # Farming NPCs and crates is profitable only when no mech is pressuring us.
        if nd > 105.0 and nearby == 0 and hp > 0.42:
            for npc in obs.get('mechs',[]) or []:
                if npc.get('kind') != 'npc':
                    continue
                p = npc.get('pos',[x,y,z]); dd = d3(me['pos'],p)
                if dd < 85.0:
                    candidates.append((88.0-dd*0.55,(float(p[0]),float(p[1])),npc,'npc'))
            for crate in obs.get('crates',[]) or []:
                p = crate.get('pos',[x,y,z]); dd = d2((x,y),p)
                if dd < 64.0 and abs(float(p[2])-float(z)) < 12.0:
                    candidates.append((70.0-dd*0.65,(float(p[0]),float(p[1])),crate,'crate'))

        if not candidates:
            return None,None,'none'
        candidates.sort(key=lambda q:q[0],reverse=True)
        _,goal,obj,kind = candidates[0]
        # Never take a resource route that exits the forecast safe circle.
        if not self._inside_predicted_zone(obs,goal) and kind != 'drop':
            return None,None,'none'
        return goal,obj,kind

    def _choose_enemy(self, me: Dict[str,Any], enemies: List[Dict[str,Any]]) -> Optional[Dict[str,Any]]:
        if not enemies:
            return None
        mx,my,mz = me['pos']
        def score(e: Dict[str,Any]) -> float:
            dist = d3(me['pos'],e['pos'])
            hp = float(e.get('hp',850.0)) / max(1.0,float(e.get('max_hp',1000.0)))
            # A low-health enemy is a likely kill/cube opportunity. Charging
            # laser users are also immediate threats worth tracking.
            s = dist + hp*28.0
            if e.get('charging'):
                s -= 20.0
            if self.last_attacker == e.get('id'):
                s -= 18.0
            return s
        return min(enemies,key=score)

    # -------- aiming and weapon control --------
    def _aim(self, me: Dict[str,Any], target: Dict[str,Any], kind: str, weapon: Dict[str,Any]) -> Tuple[float,float,float]:
        mx,my,mz = [float(v) for v in me['pos']]
        tx,ty,tz = [float(v) for v in target['pos']]
        tv = target.get('vel',[0.0,0.0,0.0])
        mv = me.get('vel',[0.0,0.0,0.0])
        if target.get('kind') == 'npc':
            target_z = tz + 1.8
        elif target.get('kind') == 'crate':
            target_z = tz + 1.3
        else:
            target_z = tz + 4.5*(1.0+0.05*float(target.get('cubes',0)))
        muzzle_z = mz + float(me.get('stats',{}).get('muzzle_height',7.0))
        dx,dy = tx-mx,ty-my
        horizontal = max(0.1,math.hypot(dx,dy))
        if kind == 'gun':
            speed = float(weapon.get('stats',{}).get('speed',252.0))
            r = (dx,dy,target_z-muzzle_z)
            rv = (float(tv[0])-float(mv[0]),float(tv[1])-float(mv[1]),float(tv[2])-float(mv[2]))
            it = solve_intercept(r,rv,speed,2.0)
            tx += float(tv[0])*it; ty += float(tv[1])*it; target_z += float(tv[2])*it
        elif kind == 'mortar':
            speed = float(weapon.get('stats',{}).get('speed',72.0))
            g = float(self.cfg.get('weapons',{}).get('mortar',{}).get('gravity',22.0))
            # Two-pass flight-time lead, with a low-arc solution for quicker hits.
            flight = min(2.5,horizontal/max(15.0,speed*0.72))
            tx += float(tv[0])*flight; ty += float(tv[1])*flight; target_z += float(tv[2])*flight
            dx,dy = tx-mx,ty-my
            horizontal = max(0.1,math.hypot(dx,dy))
            h = target_z - (muzzle_z+2.5)
            disc = speed**4 - g*(g*horizontal*horizontal+2.0*h*speed*speed)
            if disc > 0.0:
                tan_th = (speed*speed-math.sqrt(disc))/(g*horizontal)
                pitch = math.atan(tan_th)
            else:
                pitch = math.radians(43.0)
            return math.atan2(dy,dx),clamp(pitch,-0.2,1.15),horizontal
        yaw = math.atan2(ty-my,tx-mx)
        pitch = math.atan2(target_z-muzzle_z,max(0.1,math.hypot(tx-mx,ty-my)))
        return yaw,clamp(pitch,-0.7,1.3),math.hypot(tx-mx,ty-my)

    def _angle_error(self, me: Dict[str,Any], yaw: float, pitch: float) -> Tuple[float,float]:
        actual = me.get('aim',[yaw,pitch])
        return abs(wrap(yaw-float(actual[0]))),abs(pitch-float(actual[1]))

    def _weapon_action(self, me: Dict[str,Any], target: Dict[str,Any], attack_allowed: bool) -> Tuple[float,float,List[bool]]:
        weapons = me.get('weapons',[]) or []
        w0 = weapons[0] if len(weapons)>0 and isinstance(weapons[0],dict) else None
        w1 = weapons[1] if len(weapons)>1 and isinstance(weapons[1],dict) else None
        fire = [False,False]
        x,y,z = me['pos']
        aim_yaw = float(me.get('aim',[0.0,0.0])[0])
        aim_pitch = 0.0
        if target is None:
            return aim_yaw,aim_pitch,fire
        d = d3(me['pos'],target['pos'])
        if not attack_allowed:
            tx,ty=float(target['pos'][0]),float(target['pos'][1])
            return math.atan2(ty-y,tx-x),0.0,fire
        # Enemy tracks persist briefly after leaving vision. Do not waste shots
        # into a building at a remembered position; reposition or wait for LOS.
        if self.world.ok:
            if target.get('kind') == 'npc':
                tz=float(target['pos'][2])+1.8
            elif target.get('kind') == 'crate':
                tz=float(target['pos'][2])+1.3
            else:
                tz=float(target['pos'][2])+4.5*(1.0+0.05*float(target.get('cubes',0)))
            muzzle=(float(x),float(y),float(z)+float(me.get('stats',{}).get('muzzle_height',7.0)))
            center=(float(target['pos'][0]),float(target['pos'][1]),tz)
            if self.world.ray_blocked(muzzle,center,8.0):
                return math.atan2(center[1]-y,center[0]-x),0.0,fire

        # Prefer special weapons only when the engagement matches their range
        # and matchup. The arm gun remains our reliable fallback.
        chosen_slot = 0
        chosen_weapon = w0
        chosen_kind = w0.get('kind','gun') if w0 else 'gun'
        enemy_weapons = target.get('weapons',[]) or []
        nearby_lightning = any('lightning' in (e.get('weapons') or []) and d3(e['pos'],me['pos']) < 68.0
                               for e in (self._last_enemies or []))
        if w1:
            k = w1.get('kind')
            if k == 'lightning' and d <= min(47.0,float(w1.get('stats',{}).get('range',45.0))*1.03):
                chosen_slot,chosen_weapon,chosen_kind = 1,w1,'lightning'
            elif k == 'laser' and 48.0 < d < float(w1.get('stats',{}).get('range',280.0))-8 and not nearby_lightning:
                # Laser is particularly valuable into mortar carriers (cook-off).
                if 'mortar' in enemy_weapons or d > 70.0:
                    chosen_slot,chosen_weapon,chosen_kind = 1,w1,'laser'
            elif k == 'mortar' and 38.0 < d < 185.0 and d > 14.0:
                # Mortar controls close-range laser/lightning threats via knockback.
                if 'lightning' in enemy_weapons or d > 65.0:
                    chosen_slot,chosen_weapon,chosen_kind = 1,w1,'mortar'

        if chosen_weapon is None:
            return aim_yaw,aim_pitch,fire
        aim_yaw,aim_pitch,hrange = self._aim(me,target,chosen_kind,chosen_weapon)
        yaw_err,pitch_err = self._angle_error(me,aim_yaw,aim_pitch)
        stats = chosen_weapon.get('stats',{})
        cooldown = float(chosen_weapon.get('cooldown',0.0))

        if chosen_kind == 'gun':
            maxrange = float(stats.get('range',230.0))
            ammo = float(chosen_weapon.get('ammo',0.0))
            reload_s = float(chosen_weapon.get('reload',0.0))
            if hrange <= maxrange and ammo > 0 and reload_s <= 0.0 and cooldown <= 0.025 and yaw_err < 0.10 and pitch_err < 0.10:
                fire[chosen_slot] = True
        elif chosen_kind == 'laser':
            charge = float(chosen_weapon.get('charge',0.0))
            if cooldown <= 0.03 and hrange < float(stats.get('range',280.0)):
                # Hold to charge, release around 0.65s. Don't release grossly
                # misaligned; aim slew is fast enough to finish alignment.
                if charge < min(0.66,float(stats.get('charge',0.75))*0.90):
                    fire[1] = True
                elif yaw_err < 0.13 and pitch_err < 0.13:
                    fire[1] = False
                else:
                    fire[1] = True
        elif chosen_kind == 'mortar':
            if cooldown <= 0.03 and hrange < 225.0 and d > 14.0 and yaw_err < 0.14 and pitch_err < 0.16:
                fire[1] = True
        elif chosen_kind == 'lightning':
            energy = float(me.get('energy',0.0))
            cost = float(stats.get('energy',3.0))
            cone = math.radians(float(stats.get('cone_deg',30.0))*0.45)
            if hrange <= float(stats.get('range',45.0)) and yaw_err < cone and cooldown <= 0.025 and energy >= cost+2.0:
                fire[1] = True

        # The arm gun can fire during a laser charge or alongside lightning
        # when both weapons share essentially the same aim line.
        if chosen_kind in ('laser','lightning') and w0 and w0.get('kind')=='gun':
            gy,gp,gr=self._aim(me,target,'gun',w0)
            if gr <= float(w0.get('stats',{}).get('range',230.0)):
                same_line=abs(wrap(gy-aim_yaw))<0.09 and abs(gp-aim_pitch)<0.09
                gun_err_y,gun_err_p=self._angle_error(me,gy,gp)
                if same_line and gun_err_y<0.10 and gun_err_p<0.10 and float(w0.get('ammo',0.0))>0 and float(w0.get('reload',0.0))<=0.0 and float(w0.get('cooldown',0.0))<=0.025:
                    fire[0]=True

        # Reload before the next engagement, but never suppress a ready shot.
        if w0 and w0.get('kind') == 'gun':
            ammo = float(w0.get('ammo',0.0)); rel = float(w0.get('reload',0.0))
            if ammo <= 2 and rel <= 0.0 and d > 42.0:
                self._want_reload = True
        return aim_yaw,aim_pitch,fire

    # -------- projectile evasion, upgrade policy --------
    def _dodge(self, obs: Dict[str,Any], me: Dict[str,Any]) -> Tuple[Vec2,bool,bool]:
        px,py,pz = [float(v) for v in me['pos']]
        mv = me.get('vel',[0.0,0.0,0.0])
        total_x=total_y=0.0; urgent=False; jump=False; boost=False
        gravity=float(self.cfg.get('weapons',{}).get('mortar',{}).get('gravity',22.0))
        for p in obs.get('projectiles',[]) or []:
            pos=p.get('pos',[0,0,0]); vel=p.get('vel',[0,0,0]); kind=p.get('kind','gun')
            best_d=1e9; best_t=0.0; best_dx=best_dy=0.0
            for t in (0.08,0.16,0.25,0.36,0.48,0.62,0.78):
                sx=float(pos[0])+float(vel[0])*t
                sy=float(pos[1])+float(vel[1])*t
                sz=float(pos[2])+float(vel[2])*t-(0.5*gravity*t*t if kind=='mortar' else 0.0)
                mx=px+float(mv[0])*t; my=py+float(mv[1])*t
                mz=pz+float(mv[2])*t
                # Compare projectile with torso center, not feet.
                dd=math.sqrt((sx-mx)**2+(sy-my)**2+(sz-(mz+4.5))**2)
                if dd<best_d:
                    best_d,best_t,best_dx,best_dy=dd,t,mx-sx,my-sy
            radius=10.0 if kind=='mortar' else 4.2
            if best_d < radius and best_t < 0.72:
                ex,ey=unit(best_dx,best_dy)
                if ex==0 and ey==0:
                    ex,ey=unit(-float(vel[1]),float(vel[0]))
                weight=(radius-best_d+1.5)/max(0.09,best_t)
                total_x += ex*weight; total_y += ey*weight
                urgent=True; boost=True
                if kind=='mortar' and best_t<0.48 and me.get('grounded',False):
                    jump=True
        return unit(total_x,total_y),urgent,jump or False if urgent else False

    def _upgrade(self, offer: Dict[str,Any], me: Dict[str,Any]) -> int:
        choices=offer.get('choices',[])
        if not choices:
            return 0
        hp=float(me.get('hp',1.0))/max(1.0,float(me.get('max_hp',1.0)))
        energy=float(me.get('energy',0.0))/max(1.0,float(me.get('max_energy',100.0)))
        held={w.get('kind') for w in (me.get('weapons',[]) or []) if isinstance(w,dict)}
        levels={str(u):1 for u in (me.get('upgrades',[]) or [])}
        base={
            'armor':12.0,'plating':11.0,'nanites':10.2,'servos':8.6,
            'sensors':7.5,'jets':7.4,'reactor':7.1,'capacitor':6.7,
            'gyros':6.5,'gun_damage':7.9,'gun_rate':7.8,'gun_velocity':7.0,
            'gun_mag':5.8,'mortar_splash':7.8,'mortar_reload':7.6,
            'mortar_velocity':6.9,'laser_damage':8.7,'laser_charge':8.4,
            'laser_pierce':6.0,'lightning_efficiency':8.2,
            'lightning_range':7.4,'lightning_chain':7.3,
        }
        best_i,best_v=0,-1e30
        for i,c in enumerate(choices):
            cid=str(c.get('id',''))
            v=base.get(cid,5.0)
            if cid=='armor': v+=2.0 if hp<0.8 else 0.5
            if cid=='plating': v+=2.2 if hp<0.7 else 0.7
            if cid=='nanites': v+=2.5 if hp<0.8 else 0.8
            if cid in ('capacitor','reactor','jets'): v+=1.5 if energy<0.35 else 0.2
            if cid=='servos' and hp<0.65: v+=1.0
            if cid.startswith('laser_') and 'laser' not in held: v-=8.0
            if cid.startswith('mortar_') and 'mortar' not in held: v-=8.0
            if cid.startswith('lightning_') and 'lightning' not in held: v-=8.0
            if cid.startswith('gun_') and hp<0.3: v-=0.4
            if levels.get(cid,0): v-=0.15
            # Read max stack from live config when available.
            for u in self.cfg.get('upgrades',[]) or []:
                if u.get('id')==cid and u.get('max',99)<=levels.get(cid,0):
                    v=-1e9
            if v>best_v: best_v,best_i=v,i
        return best_i

    # -------- main policy --------
    def act(self, obs: mf.Observation) -> mf.Action:
        self.tick_count += 1
        me=obs['self']
        x,y,z=[float(v) for v in me['pos']]
        t=float(obs.get('t',0.0))
        self.now=t
        hp=float(me.get('hp',1.0)); maxhp=max(1.0,float(me.get('max_hp',1.0)))
        hp_frac=hp/maxhp
        energy=float(me.get('energy',0.0)); max_energy=max(1.0,float(me.get('max_energy',100.0)))
        enemies=[e for e in (obs.get('mechs',[]) or []) if e.get('kind')=='mech']
        npcs=[e for e in (obs.get('mechs',[]) or []) if e.get('kind')=='npc']
        enemies.sort(key=lambda e:d3(e['pos'],me['pos']))
        self._last_enemies=enemies
        nearest_enemy=self._nearest_enemy_dist(me,enemies)
        near_count=sum(1 for e in enemies if d3(e['pos'],me['pos'])<105.0)

        # Track damage and attacker bearings for armor orientation and disengagement.
        for ev in obs.get('events',[]) or []:
            if ev.get('type')=='damaged':
                self.last_damage_t=t
                if ev.get('bearing') is not None:
                    self.last_damage_bearing=float(ev['bearing'])
                if ev.get('by') is not None:
                    self.last_attacker=int(ev['by'])
            elif ev.get('type')=='hit':
                self.last_attack_t=t

        action: Dict[str,Any]={'tick':obs['tick']}
        if obs.get('offer'):
            action['pick']=self._upgrade(obs['offer'],me)

        zone_goal=self._zone_goal(obs,me)
        resource_goal,resource_obj,resource_kind=self._resource_goal(obs,me,enemies)

        # Priority: immediate zone escape > projectile dodge > tactical cover > loot.
        goal: Vec2=(x,y)
        goal_kind='hold'
        urgent_move=False
        dodge,dodge_urgent,jump=self._dodge(obs,me)
        if zone_goal is not None:
            goal=zone_goal
            goal_kind='zone'
            move=self._navigate(me,goal,True)
            urgent_move=True
            if dodge_urgent:
                move=unit(move[0]*0.30+dodge[0]*1.45,move[1]*0.30+dodge[1]*1.45)
        elif dodge_urgent:
            move=dodge
            urgent_move=True
        else:
            cover=None
            if enemies and nearest_enemy<165.0:
                cover=self._cover_goal(obs,me,enemies)
            if cover is not None and (near_count>=1 or hp_frac<0.78):
                goal=cover
                goal_kind='cover'
                urgent_move=near_count>=2 or hp_frac<0.50
            elif resource_goal is not None:
                goal=resource_goal
                goal_kind=resource_kind
            elif enemies and nearest_enemy<90.0:
                # No navigable cover point: create a standoff vector away
                # from the weighted centroid of close threats.
                # Choose the best escape sector instead of summing repulsion
                # vectors (which can cancel when attackers surround us).
                best_escape=None; best_escape_score=-1e30
                for k in range(24):
                    ang=PI2*k/24.0
                    ax,ay=math.cos(ang),math.sin(ang)
                    candidate=(x+ax*62.0,y+ay*62.0)
                    if self.world.ok:
                        ci=self.world.cell(*candidate)
                        if self.world.blocked[ci]:
                            continue
                    if not self._inside_predicted_zone(obs,candidate):
                        continue
                    min_sep=min((d2(candidate,e['pos']) for e in enemies),default=150.0)
                    blocked_count=0
                    if self.world.ok:
                        blocked_count,_=self.world.visible_cover(candidate,enemies[:3])
                    score=min(min_sep,150.0)*0.22+blocked_count*8.0
                    if score>best_escape_score:
                        best_escape_score,best_escape=score,candidate
                if best_escape is not None:
                    goal=best_escape
                else:
                    fx=fy=0.0
                    for e in enemies:
                        dd=d2((x,y),e['pos'])
                        if dd<110.0:
                            ux,uy=unit(x-float(e['pos'][0]),y-float(e['pos'][1]))
                            w=1.0/max(12.0,dd)**1.3
                            fx+=ux*w; fy+=uy*w
                    ax,ay=unit(fx,fy)
                    goal=(x+ax*65.0,y+ay*65.0)
                goal_kind='retreat'
                urgent_move=True
            else:
                goal=(x,y)
                goal_kind='hold'
            move=self._navigate(me,goal,urgent_move) if d2((x,y),goal)>5.0 else (0.0,0.0)

        # Determine a firing target. Avoid long duels while multiple house bots
        # are close: survival and recovery dominate the placement metric.
        target=self._choose_enemy(me,enemies)
        target_type='mech' if target else 'none'
        attack_allowed=False
        if target is not None:
            td=d3(me['pos'],target['pos'])
            target_hp=float(target.get('hp',1000.0))/max(1.0,float(target.get('max_hp',1000.0)))
            attack_allowed=(td<145.0 and hp_frac>0.48 and near_count<=1)
            if td<30.0 and hp_frac>0.25:
                attack_allowed=True
            if target_hp<0.30 and hp_frac>0.52 and near_count<=2:
                attack_allowed=True
            if self.last_attacker==target.get('id') and td<110 and hp_frac>0.38:
                attack_allowed=True
            # Take a healing window when no opponent is close enough to punish us.
            if hp_frac<0.72 and nearest_enemy>78.0 and t-self.last_damage_t<7.0:
                attack_allowed=False
        else:
            target=None

        # Farm drones or a chosen crate only if the arena is quiet around us.
        if target is None and near_count==0 and nearest_enemy>100.0 and hp_frac>0.42:
            if resource_kind=='npc' and resource_obj is not None:
                target=resource_obj; target_type='npc'; attack_allowed=True
            elif resource_kind=='crate' and resource_obj is not None:
                target=resource_obj; target_type='crate'; attack_allowed=True

        # An NPC can retaliate; stop farming if a mech appears or HP gets low.
        if target_type=='npc' and (nearest_enemy<95.0 or hp_frac<0.42):
            target=None; attack_allowed=False

        # Weapon code expects the target kind to distinguish NPC/crate aim heights.
        if target is not None:
            target_for_aim=dict(target)
            target_for_aim['kind']=target_type
        else:
            target_for_aim=None

        # Keep the torso facing the strongest threat when not actively firing.
        if target_for_aim is not None and target_type=='mech':
            aim_yaw,aim_pitch,fire=self._weapon_action(me,target_for_aim,attack_allowed)
        elif target_for_aim is not None and target_type in ('npc','crate'):
            aim_yaw,aim_pitch,fire=self._weapon_action(me,target_for_aim,attack_allowed)
        else:
            aim_yaw=float(me.get('aim',[0.0,0.0])[0]); aim_pitch=0.0; fire=[False,False]
            if enemies:
                closest=enemies[0]
                aim_yaw=math.atan2(float(closest['pos'][1])-y,float(closest['pos'][0])-x)
                aim_pitch=0.0
            elif self.last_damage_bearing is not None and t-self.last_damage_t<4.0:
                aim_yaw=self.last_damage_bearing
            else:
                sounds=[s for s in (obs.get('sounds',[]) or []) if s.get('kind') in ('gun','mortar','explosion','laser','laser_charge','lightning','crate','drop') and float(s.get('age',99.0))<0.8]
                if sounds:
                    sounds.sort(key=lambda s:float(s.get('age',99.0)))
                    aim_yaw=float(sounds[0].get('bearing',aim_yaw))
                else:
                    # Slowly sweep the torso when quiet. A stationary fixed gaze
                    # would miss most of the 120-degree pickup/vision wedge.
                    scan_origin=float(int(self.rng.random()*1000))*0.001 if not hasattr(self,'scan_origin') else self.scan_origin
                    self.scan_origin=scan_origin
                    aim_yaw=wrap(scan_origin + t*0.52)

        # If we were hit from behind this tick, rotate the armor toward the source.
        if self.last_damage_bearing is not None and t-self.last_damage_t<0.18 and not any(fire):
            aim_yaw=self.last_damage_bearing; aim_pitch=0.0

        # Reload early enough to avoid an empty magazine during the next encounter.
        weapons=me.get('weapons',[]) or []
        w0=weapons[0] if len(weapons)>0 and isinstance(weapons[0],dict) else None
        self._want_reload=False
        if w0 and w0.get('kind')=='gun':
            ammo=float(w0.get('ammo',0.0)); rel=float(w0.get('reload',0.0))
            if rel<=0.0 and ammo<=0.0:
                action['reload']=True
            elif rel<=0.0 and ammo<=2 and nearest_enemy>55.0 and target_type not in ('npc','crate'):
                action['reload']=True

        # Quiet travel (<=5 m/s) avoids step sounds; accelerate only when
        # escaping, racing the zone, or evading a projectile.
        dist_goal=d2((x,y),goal)
        # Move close enough to actually collect objects. NPC farming deliberately
        # holds a ~58m standoff so the drone's 45m aggro radius does not trigger.
        stop_range=5.0
        if goal_kind in ('cube','weapon'):
            stop_range=2.2
        elif goal_kind=='drop':
            stop_range=7.0
        elif goal_kind=='npc':
            stop_range=58.0
        elif goal_kind=='crate':
            stop_range=16.0
        if dist_goal<stop_range and not dodge_urgent:
            move=(0.0,0.0)
        moving=math.hypot(move[0],move[1])>0.01
        boost=False
        if moving:
            if urgent_move:
                throttle=0.92
            else:
                walk_speed=float(me.get('stats',{}).get('walk_speed',11.7))
                step_limit=float(self.cfg.get('sound',{}).get('step_speed',5.0))
                throttle=min(0.40,max(0.18,(step_limit-0.45)/max(1.0,walk_speed)))
            move=(move[0]*throttle,move[1]*throttle)
            if urgent_move and energy>18.0:
                boost=True
        # If in the danger zone, do not conserve energy at the cost of zone damage.
        if not me.get('in_zone',True) and energy>5.0:
            boost=True
            move=unit(move[0],move[1])

        # A supply drop capture requires staying alone in its ring. Once our
        # progress starts, avoid moving unless a threat contests it.
        if resource_kind=='drop' and resource_obj is not None:
            dp=resource_obj.get('pos',[0,0,0])
            if d2((x,y),dp)<7.5 and nearest_enemy>40.0:
                move=(0.0,0.0); boost=False; fire=[False,False]

        # Don't attack while healing if no urgent enemy is in our face.
        if hp_frac<0.68 and nearest_enemy>75.0:
            if target_type in ('npc','crate'):
                fire=[False,False]

        # Weapon pickup must be explicit. Pick it up once inside the small radius.
        if resource_kind=='weapon' and resource_obj is not None:
            pp=resource_obj.get('pos',[x,y,z])
            if d2((x,y),pp)<=float(self.cfg.get('loot',{}).get('pickup_radius',4.0))+0.3 and abs(float(z)-float(pp[2]))<=4.0:
                action['take']=resource_obj.get('id')
                # The policy only selects a swap when the secondary is clearly
                # inferior; explicitly drop slot 1 so the pickup can succeed.
                if len(weapons)>1 and isinstance(weapons[1],dict):
                    action['drop']=1

        action.update({
            'move':[float(clamp(move[0],-1.0,1.0)),float(clamp(move[1],-1.0,1.0))],
            'boost':bool(boost),
            'jump':bool(jump and me.get('grounded',False)),
            'aim':[float(aim_yaw),float(clamp(aim_pitch,-0.7,1.3))],
            'fire':[bool(fire[0]),bool(fire[1])],
        })

        # Keep debug payload intentionally tiny: all strategic state is local.
        # Drawing is optional and omitted to minimise protocol bytes/CPU.
        return action


mf.run(Bot)
