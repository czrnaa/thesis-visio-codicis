"""
Disaster-Response Routing Simulation
    * Three disaster levels:
        Level 1 - Minor    : small delays, no blockages.
        Level 2 - Moderate : significant slowdowns and higher traversal cost.
        Level 3 - Severe   : selected roads are blocked / inaccessible.
    * Two routing algorithms are compared:
        - Traditional A*
        - Optimized ABSRA (Arc-flag Bidirectional Search A*)
    * Metrics reported per scenario:
        - Path cost (route efficiency)
        - Number of nodes explored
        - Execution time
"""

import math
import heapq
import time
import random
from copy import deepcopy

# 1. ROAD NETWORK GRAPH (Bulacan)
NODE_LOCATIONS = {
    "HQ_Malolos":            {"lat": 14.8437, "lon": 120.8113},
    "Paombong":              {"lat": 14.8322, "lon": 120.7890},
    "Hagonoy":               {"lat": 14.8320, "lon": 120.7380},
    "Calumpit":              {"lat": 14.9140, "lon": 120.7650},
    "Plaridel":              {"lat": 14.8870, "lon": 120.8570},
    "Guiguinto":             {"lat": 14.8300, "lon": 120.8800},
    "Balagtas":              {"lat": 14.8150, "lon": 120.9100},
    "Bocaue":                {"lat": 14.7960, "lon": 120.9250},
    "San Miguel":            {"lat": 15.1450, "lon": 120.9780},
    "Malolos (City Hall)":   {"lat": 14.8450, "lon": 120.8150},
    "Plaridel (Muni Hall)":  {"lat": 14.8890, "lon": 120.8600},
    "Calumpit (Market)":     {"lat": 14.9160, "lon": 120.7680},
    "Guiguinto (Plaza)":     {"lat": 14.8320, "lon": 120.8830},
    "Bocaue (Crossing)":     {"lat": 14.7980, "lon": 120.9280},
    "San Miguel (Viola St)": {"lat": 15.1485, "lon": 120.9820},
}

GRAPH_CONNECTIONS = {
    "HQ_Malolos":   ["Paombong", "Guiguinto", "Plaridel", "Malolos (City Hall)"],
    "Paombong":     ["HQ_Malolos", "Hagonoy"],
    "Hagonoy":      ["Paombong"],
    "Plaridel":     ["HQ_Malolos", "Calumpit", "Guiguinto", "San Miguel", "Plaridel (Muni Hall)"],
    "Calumpit":     ["Plaridel", "Calumpit (Market)"],
    "Guiguinto":    ["HQ_Malolos", "Plaridel", "Balagtas", "Guiguinto (Plaza)"],
    "Balagtas":     ["Guiguinto", "Bocaue"],
    "Bocaue":       ["Balagtas", "Bocaue (Crossing)"],
    "San Miguel":   ["Plaridel", "San Miguel (Viola St)"],
    "Malolos (City Hall)":   ["HQ_Malolos"],
    "Plaridel (Muni Hall)":  ["Plaridel"],
    "Calumpit (Market)":     ["Calumpit"],
    "Guiguinto (Plaza)":     ["Guiguinto"],
    "Bocaue (Crossing)":     ["Bocaue"],
    "San Miguel (Viola St)": ["San Miguel"],
}

NODE_REGIONS = {
    "HQ_Malolos": "Central", "Paombong": "Central", "Hagonoy": "Central",
    "Plaridel": "Central", "Malolos (City Hall)": "Central",
    "Plaridel (Muni Hall)": "Central",
    "Calumpit": "Northern", "Calumpit (Market)": "Northern",
    "San Miguel": "Northern", "San Miguel (Viola St)": "Northern",
    "Guiguinto": "Southern", "Guiguinto (Plaza)": "Southern",
    "Balagtas": "Southern", "Bocaue": "Southern",
    "Bocaue (Crossing)": "Southern",
}
REGIONS = ["Central", "Northern", "Southern"]


def haversine_km(a, b):
    lat1, lon1 = NODE_LOCATIONS[a]["lat"], NODE_LOCATIONS[a]["lon"]
    lat2, lon2 = NODE_LOCATIONS[b]["lat"], NODE_LOCATIONS[b]["lon"]
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def heuristic(a, b):
    return haversine_km(a, b)


# DISASTER SIMULATION
def build_base_weights():
    weights = {}
    for u, neighbors in GRAPH_CONNECTIONS.items():
        for v in neighbors:
            weights[(u, v)] = haversine_km(u, v)
    return weights


def simulate_disaster(level, seed=42):
    """
    Level 1 (Minor)    - 30% of edges get 1.2-1.5x cost multiplier.
    Level 2 (Moderate) - 50% of edges get 1.8-2.8x cost multiplier.
    Level 3 (Severe)   - 50% slowdown 2.5-4.0x AND ~20% of edges blocked.
    """
    rng = random.Random(seed)
    weights = build_base_weights()
    blocked = set()
    edges = list(weights.keys())

    if level == 1:
        affected = rng.sample(edges, k=max(1, int(len(edges) * 0.30)))
        for e in affected:
            weights[e] *= rng.uniform(1.2, 1.5)
    elif level == 2:
        affected = rng.sample(edges, k=max(1, int(len(edges) * 0.50)))
        for e in affected:
            weights[e] *= rng.uniform(1.8, 2.8)
    elif level == 3:
        slow = rng.sample(edges, k=max(1, int(len(edges) * 0.50)))
        for e in slow:
            weights[e] *= rng.uniform(2.5, 4.0)
        block_candidates = rng.sample(edges, k=max(1, int(len(edges) * 0.20)))
        for (u, v) in block_candidates:
            blocked.add((u, v))
            blocked.add((v, u))
    elif level != 0:
        raise ValueError(f"Unknown disaster level: {level}")

    return weights, blocked


# ROUTING ALGORITHMS
def a_star(start, goal, weights, blocked):
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS:
        return None, 0, math.inf
    if start == goal:
        return [start], 0, 0.0

    open_set = [(heuristic(start, goal), start)]
    came_from = {}
    g = {n: math.inf for n in NODE_LOCATIONS}
    g[start] = 0.0
    closed = set()
    explored = 0

    while open_set:
        _, u = heapq.heappop(open_set)
        if u in closed:
            continue
        closed.add(u)
        explored += 1

        if u == goal:
            path = [u]
            while path[-1] in came_from:
                path.append(came_from[path[-1]])
            return path[::-1], explored, g[goal]

        for v in GRAPH_CONNECTIONS.get(u, []):
            if (u, v) in blocked:
                continue
            new_g = g[u] + weights[(u, v)]
            if new_g < g[v]:
                g[v] = new_g
                came_from[v] = u
                heapq.heappush(open_set, (new_g + heuristic(v, goal), v))

    return None, explored, math.inf


def _dijkstra(source, adj):
    dist = {n: math.inf for n in NODE_LOCATIONS}
    dist[source] = 0.0
    heap = [(0.0, source)]
    visited = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        for v, w in adj[u]:
            if v in visited:
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def _build_arc_flags(weights, blocked):
    """
    fwd_flags[(u,v)] = R if edge is on a shortest path TO some node in R
    bwd_flags[(u,v)] = R if edge is on a shortest path FROM some node in R
    """
    fwd_flags = {e: set() for e in weights}
    bwd_flags = {e: set() for e in weights}

    adj = {n: [] for n in NODE_LOCATIONS}
    rev_adj = {n: [] for n in NODE_LOCATIONS}
    for (u, v), w in weights.items():
        if (u, v) in blocked:
            continue
        adj[u].append((v, w))
        rev_adj[v].append((u, w))

    for region in REGIONS:
        members = [n for n, r in NODE_REGIONS.items() if r == region]
        for t in members:
            d = _dijkstra(t, rev_adj)
            for (u, v), w in weights.items():
                if (u, v) in blocked: continue
                if d[u] < math.inf and d[v] < math.inf and \
                        abs(d[u] - (w + d[v])) < 1e-9:
                    fwd_flags[(u, v)].add(region)
        for s in members:
            d = _dijkstra(s, adj)
            for (u, v), w in weights.items():
                if (u, v) in blocked: continue
                if d[u] < math.inf and d[v] < math.inf and \
                        abs(d[v] - (d[u] + w)) < 1e-9:
                    bwd_flags[(u, v)].add(region)
    return fwd_flags, bwd_flags


def absra(start, goal, weights, blocked):
    """Arc-flag Bidirectional Search A* - the optimized algorithm."""
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS:
        return None, 0, math.inf
    if start == goal:
        return [start], 0, 0.0

    fwd_flags, bwd_flags = _build_arc_flags(weights, blocked)
    goal_region = NODE_REGIONS.get(goal)
    start_region = NODE_REGIONS.get(start)

    rev_adj = {n: [] for n in NODE_LOCATIONS}
    for (u, v), w in weights.items():
        if (u, v) in blocked: continue
        rev_adj[v].append((u, w))

    fwd_g = {n: math.inf for n in NODE_LOCATIONS}; fwd_g[start] = 0.0
    bwd_g = {n: math.inf for n in NODE_LOCATIONS}; bwd_g[goal] = 0.0
    fwd_par, bwd_par = {start: None}, {goal: None}
    fwd_open = [(heuristic(start, goal), start)]
    bwd_open = [(heuristic(goal, start), goal)]
    fwd_closed, bwd_closed = set(), set()

    explored = 0
    best_cost = math.inf
    meeting = None

    while fwd_open or bwd_open:
        f_min = fwd_open[0][0] if fwd_open else math.inf
        b_min = bwd_open[0][0] if bwd_open else math.inf
        if f_min + b_min >= best_cost:
            break

        if f_min <= b_min and fwd_open:
            _, u = heapq.heappop(fwd_open)
            if u in fwd_closed: continue
            fwd_closed.add(u)
            explored += 1
            for v in GRAPH_CONNECTIONS.get(u, []):
                if (u, v) in blocked: continue
                if goal_region and v != goal and goal_region not in fwd_flags.get((u, v), set()):
                    continue
                ng = fwd_g[u] + weights[(u, v)]
                if ng < fwd_g[v]:
                    fwd_g[v] = ng
                    fwd_par[v] = u
                    heapq.heappush(fwd_open, (ng + heuristic(v, goal), v))
                    total = fwd_g[v] + bwd_g[v]
                    if total < best_cost:
                        best_cost = total
                        meeting = v
        elif bwd_open:
            _, u = heapq.heappop(bwd_open)
            if u in bwd_closed: continue
            bwd_closed.add(u)
            explored += 1
            for v, w in rev_adj[u]:
                if start_region and v != start and start_region not in bwd_flags.get((v, u), set()):
                    continue
                ng = bwd_g[u] + w
                if ng < bwd_g[v]:
                    bwd_g[v] = ng
                    bwd_par[v] = u
                    heapq.heappush(bwd_open, (ng + heuristic(v, start), v))
                    total = fwd_g[v] + bwd_g[v]
                    if total < best_cost:
                        best_cost = total
                        meeting = v

    if meeting is None:
        return None, explored, math.inf

    fwd_path, n = [], meeting
    while n is not None:
        fwd_path.append(n); n = fwd_par.get(n)
    fwd_path.reverse()
    bwd_path, n = [], bwd_par.get(meeting)
    while n is not None:
        bwd_path.append(n); n = bwd_par.get(n)

    return fwd_path + bwd_path, explored, best_cost

# BENCHMARK HARNESS
def measure(fn, *args, repeats=5):
    best_t, result = math.inf, None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn(*args)
        best_t = min(best_t, time.perf_counter() - t0)
    return result, best_t


def run_scenario(start, goal, level, seed=42):
    weights, blocked = simulate_disaster(level, seed=seed)
    (a_path, a_exp, a_cost), a_t = measure(a_star, start, goal, weights, blocked)
    (b_path, b_exp, b_cost), b_t = measure(absra,  start, goal, weights, blocked)
    return {
        "level": level, "start": start, "goal": goal,
        "blocked_edges": len(blocked) // 2,
        "a_star":  {"path": a_path, "cost": a_cost, "explored": a_exp, "time_ms": a_t * 1000},
        "absra":   {"path": b_path, "cost": b_cost, "explored": b_exp, "time_ms": b_t * 1000},
    }


def main():
    test_cases = [
        ("HQ_Malolos", "Hagonoy"),
        ("HQ_Malolos", "San Miguel (Viola St)"),
        ("HQ_Malolos", "Bocaue (Crossing)"),
        ("HQ_Malolos", "Calumpit (Market)"),
        ("Plaridel",   "Bocaue"),
    ]
    rows = [run_scenario(s, g, lvl, seed=2026 + lvl)
            for lvl in (1, 2, 3) for s, g in test_cases]
