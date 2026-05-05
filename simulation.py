"""
Disaster-Response Routing Simulation
Standalone simulation:
    * Three disaster levels:
        Level 1 - Minor : small delays, no blockages.
        Level 2 - Moderate : significant slowdowns and higher traversal cost.
        Level 3 - Severe : selected roads are blocked / inaccessible.
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

# ROAD NETWORK GRAPH (Bulacan)
# Mirrors the structure used in main.py so results are comparable.
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
    """Great-circle distance in km between two node names."""
    lat1, lon1 = NODE_LOCATIONS[a]["lat"], NODE_LOCATIONS[a]["lon"]
    lat2, lon2 = NODE_LOCATIONS[b]["lat"], NODE_LOCATIONS[b]["lon"]
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def heuristic(a, b):
    """Admissible heuristic - straight-line distance in km."""
    return haversine_km(a, b)


# DISASTER SIMULATION
FLOOD_DEPTH_THRESHOLD_CM = 25            # Mamuyac (2025)
FLOOD_CAPACITY_DROP_RANGE = (0.40, 0.70)  # 40-70% drop above threshold
def build_base_weights():
    """Base edge cost = real distance (km). Symmetric."""
    weights = {}
    for u, neighbors in GRAPH_CONNECTIONS.items():
        for v in neighbors:
            weights[(u, v)] = haversine_km(u, v)
    return weights


def simulate_disaster(level, seed=42):
    rng = random.Random(seed)
    weights = build_base_weights()
    blocked = set()

    # All directed edges in the graph
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
        # Block ~20% of edges (and their reverse, to keep the graph consistent)
        block_candidates = rng.sample(edges, k=max(1, int(len(edges) * 0.20)))
        for (u, v) in block_candidates:
            blocked.add((u, v))
            blocked.add((v, u))

    elif level != 0:
        raise ValueError(f"Unknown disaster level: {level}")

    return weights, blocked


def simulate_flood_disaster(level, seed=42):
    """
    Empirical flood model based on Mamuyac (2025) analysis.
    For each affected edge a flood depth (cm) is sampled from a severity-
    dependent distribution, then translated into routing impact:
        depth < 25 cm  : passable, minor slowdown (linear penalty up to 1.20x)
        depth >= 25 cm : capacity drops r ~ U(0.40, 0.70)
                         -> cost multiplier = 1 / (1 - r)  (1.67x .. 3.33x)
                         AND with closure probability p = min(1, (d-25)/50)
                         the edge (and its reverse) is marked impassable.
    Severity controls the depth distribution and the affected fraction:
        Level 1 (Minor)    : depth ~ U(0, 30) cm,    30% of edges affected
        Level 2 (Moderate) : depth ~ U(10, 60) cm,   50% of edges affected
        Level 3 (Severe)   : depth ~ U(20, 100) cm,  70% of edges affected
    Returns (weights, blocked, depths) where `depths` maps directed edge to
    its sampled flood depth in cm (0 for unaffected edges).
    """
    rng = random.Random(seed)
    weights = build_base_weights()
    blocked = set()
    depths = {e: 0.0 for e in weights}

    if level == 1:
        depth_lo, depth_hi, fraction = 0.0, 30.0, 0.30
    elif level == 2:
        depth_lo, depth_hi, fraction = 10.0, 60.0, 0.50
    elif level == 3:
        depth_lo, depth_hi, fraction = 20.0, 100.0, 0.70
    else:
        raise ValueError(f"Unknown flood level: {level}")

    # Sample affected edges as undirected pairs so both directions share depth
    undirected = list({tuple(sorted(e)) for e in weights})
    affected = rng.sample(undirected, k=max(1, int(len(undirected) * fraction)))

    for (a, b) in affected:
        d = rng.uniform(depth_lo, depth_hi)
        depths[(a, b)] = d
        depths[(b, a)] = d

        if d < FLOOD_DEPTH_THRESHOLD_CM:
            mult = 1.0 + 0.008 * d            # up to ~1.20x at 25 cm
        else:
            r = rng.uniform(*FLOOD_CAPACITY_DROP_RANGE)
            mult = 1.0 / (1.0 - r)            # 1.67x .. 3.33x

        weights[(a, b)] *= mult
        weights[(b, a)] *= mult

        if d >= FLOOD_DEPTH_THRESHOLD_CM:
            p_close = min(1.0, (d - FLOOD_DEPTH_THRESHOLD_CM) / 50.0)
            if rng.random() < p_close:
                blocked.add((a, b))
                blocked.add((b, a))

    return weights, blocked, depths


# ROUTING ALGORITHMS
def a_star(start, goal, weights, blocked):
    """Traditional A* over the disaster-modified graph."""
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
    Pre-compute arc flags for both search directions.
    fwd_flags[(u,v)] = R if edge (u,v) lies on a shortest path TO some node
                      in region R - used by forward search toward goal_region.
    bwd_flags[(u,v)] = R if edge (u,v) lies on a shortest path FROM some node
                      in region R - used by backward search expanding the
                      predecessor edge while traveling toward start_region.
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

        # Forward flags: reverse Dijkstra from each target in region.
        # dist_to[t][u] = shortest cost u -> t.
        for t in members:
            d = _dijkstra(t, rev_adj)
            for (u, v), w in weights.items():
                if (u, v) in blocked:
                    continue
                if d[u] < math.inf and d[v] < math.inf and \
                        abs(d[u] - (w + d[v])) < 1e-9:
                    fwd_flags[(u, v)].add(region)

        # Backward flags: forward Dijkstra from each source in region.
        # dist_from[s][v] = shortest cost s -> v.
        for s in members:
            d = _dijkstra(s, adj)
            for (u, v), w in weights.items():
                if (u, v) in blocked:
                    continue
                if d[u] < math.inf and d[v] < math.inf and \
                        abs(d[v] - (d[u] + w)) < 1e-9:
                    bwd_flags[(u, v)].add(region)

    return fwd_flags, bwd_flags


def absra(start, goal, weights, blocked):
    """
    Optimized routing: Arc-flag Bidirectional Search A*.
    Forward + backward A* meet in the middle; arc flags prune any edge that
    cannot lie on a shortest path toward the goal/start region.
    """
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS:
        return None, 0, math.inf
    if start == goal:
        return [start], 0, 0.0

    fwd_flags, bwd_flags = _build_arc_flags(weights, blocked)
    goal_region = NODE_REGIONS.get(goal)
    start_region = NODE_REGIONS.get(start)

    rev_adj = {n: [] for n in NODE_LOCATIONS}
    for (u, v), w in weights.items():
        if (u, v) in blocked:
            continue
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
            if u in fwd_closed:
                continue
            fwd_closed.add(u)
            explored += 1
            for v in GRAPH_CONNECTIONS.get(u, []):
                if (u, v) in blocked:
                    continue
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
            if u in bwd_closed:
                continue
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

    # Reconstruct path: start -> meeting (forward) + meeting -> goal (backward)
    fwd_path = []
    n = meeting
    while n is not None:
        fwd_path.append(n)
        n = fwd_par.get(n)
    fwd_path.reverse()

    bwd_path = []
    n = bwd_par.get(meeting)
    while n is not None:
        bwd_path.append(n)
        n = bwd_par.get(n)

    return fwd_path + bwd_path, explored, best_cost


# BENCHMARK HARNESS
def measure(fn, *args, repeats=5):
    """Run fn several times, return the best (min) wall-clock time + result."""
    best_t = math.inf
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn(*args)
        t1 = time.perf_counter()
        best_t = min(best_t, t1 - t0)
    return result, best_t


def run_scenario(start, goal, level, seed=42, disaster_type="generic"):
    if disaster_type == "flood":
        weights, blocked, depths = simulate_flood_disaster(level, seed=seed)
    else:
        weights, blocked = simulate_disaster(level, seed=seed)
        depths = None

    (a_path, a_exp, a_cost), a_t = measure(a_star, start, goal, weights, blocked)
    (b_path, b_exp, b_cost), b_t = measure(absra, start, goal, weights, blocked)

    result = {
        "level": level,
        "start": start,
        "goal": goal,
        "disaster_type": disaster_type,
        "blocked_edges": len(blocked) // 2,
        "a_star":  {"path": a_path, "cost": a_cost, "explored": a_exp, "time_ms": a_t * 1000},
        "absra":   {"path": b_path, "cost": b_cost, "explored": b_exp, "time_ms": b_t * 1000},
    }

    if depths is not None:
        # Summarize using undirected edges so each road is counted once
        seen, undirected_depths = set(), []
        for (u, v), d in depths.items():
            key = tuple(sorted((u, v)))
            if key in seen:
                continue
            seen.add(key)
            undirected_depths.append(d)
        flooded = [d for d in undirected_depths if d > 0]
        over = [d for d in undirected_depths if d >= FLOOD_DEPTH_THRESHOLD_CM]
        result["flood"] = {
            "max_depth_cm":   max(undirected_depths) if undirected_depths else 0.0,
            "mean_depth_cm":  (sum(flooded) / len(flooded)) if flooded else 0.0,
            "edges_flooded": len(flooded),
            "edges_over_threshold": len(over),
        }

    return result


def fmt_path(p):
    if not p:
        return "(no route)"
    return " -> ".join(p)


def print_report(rows):
    level_names = {0: "No Disaster", 1: "Minor", 2: "Moderate", 3: "Severe"}
    print("=" * 88)
    print(f"{'Lvl':<4}{'Start -> Goal':<42}{'Algo':<8}{'Cost(km)':>10}{'Nodes':>8}{'Time(ms)':>12}")
    print("-" * 88)
    for r in rows:
        sg = f"{r['start']} -> {r['goal']}"
        lvl = f"{r['level']}({level_names[r['level']][0]})"
        for algo_key, algo_label in [("a_star", "A*"), ("absra", "ABSRA")]:
            a = r[algo_key]
            cost = f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF"
            print(f"{lvl:<4}{sg:<42}{algo_label:<8}{cost:>10}{a['explored']:>8}{a['time_ms']:>12.3f}")
        print("-" * 88)


def print_flood_report(rows):
    """Per-scenario flood depth statistics + routing comparison."""
    print("=" * 104)
    print(f"{'Lvl':<4}{'Start -> Goal':<42}"
          f"{'MaxDepth':>10}{'>25cm':>8}{'Closed':>8}"
          f"{'A* km':>9}{'ABSRA km':>10}{'A* nodes':>10}{'ABSRA':>7}")
    print("-" * 104)
    for r in rows:
        f = r["flood"]
        sg = f"{r['start']} -> {r['goal']}"
        a, b = r["a_star"], r["absra"]
        a_cost = f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF"
        b_cost = f"{b['cost']:.2f}" if b['cost'] != math.inf else "INF"
        print(f"L{r['level']:<3}{sg:<42}"
              f"{f['max_depth_cm']:>9.1f}{f['edges_over_threshold']:>8}"
              f"{r['blocked_edges']:>8}{a_cost:>9}{b_cost:>10}"
              f"{a['explored']:>10}{b['explored']:>7}")
    print("-" * 104)


def print_paths(rows):
    print()
    print("Resolved routes:")
    for r in rows:
        print(f"  [L{r['level']}] {r['start']} -> {r['goal']}  (blocked roads: {r['blocked_edges']})")
        print(f"      A*    : {fmt_path(r['a_star']['path'])}")
        print(f"      ABSRA : {fmt_path(r['absra']['path'])}")


# MAIN
def main():
    test_cases = [
        ("HQ_Malolos", "Hagonoy"),
        ("HQ_Malolos", "San Miguel (Viola St)"),
        ("HQ_Malolos", "Bocaue (Crossing)"),
        ("HQ_Malolos", "Calumpit (Market)"),
        ("Plaridel",   "Bocaue"),
    ]

    def aggregate(rows, header):
        print()
        print(header)
        print(f"{'Level':<10}{'Algo':<8}{'AvgCost':>10}{'AvgNodes':>10}"
              f"{'AvgTime(ms)':>14}{'Reachable':>12}")
        for level in (1, 2, 3):
            subset = [r for r in rows if r["level"] == level]
            for algo_key, label in [("a_star", "A*"), ("absra", "ABSRA")]:
                reached = [r[algo_key] for r in subset if r[algo_key]["path"]]
                if not reached:
                    print(f"L{level:<9}{label:<8}{'-':>10}{'-':>10}{'-':>14}"
                          f"{0:>5}/{len(subset)}")
                    continue
                avg_cost = sum(x["cost"] for x in reached) / len(reached)
                avg_nodes = sum(x["explored"] for x in reached) / len(reached)
                avg_time = sum(x["time_ms"] for x in reached) / len(reached)
                print(f"L{level:<9}{label:<8}{avg_cost:>10.2f}{avg_nodes:>10.1f}"
                      f"{avg_time:>14.3f}{len(reached):>5}/{len(subset)}")

    # ---- Generic disaster sweep ----
    print("\n### GENERIC DISASTER SCENARIOS ###")
    generic_rows = [run_scenario(s, g, lvl, seed=2026 + lvl)
                    for lvl in (1, 2, 3) for s, g in test_cases]
    print_report(generic_rows)
    print_paths(generic_rows)
    aggregate(generic_rows, "Generic-disaster summary (averaged across test cases):")

    # ---- Flood-specific sweep (Mamuyac, 2025) ----
    print("\n### FLOOD SCENARIOS - Mamuyac (2025) empirical model ###")
    print(f"Threshold: {FLOOD_DEPTH_THRESHOLD_CM} cm; "
          f"capacity drop above threshold: "
          f"{int(FLOOD_CAPACITY_DROP_RANGE[0]*100)}-"
          f"{int(FLOOD_CAPACITY_DROP_RANGE[1]*100)}%")
    flood_rows = [run_scenario(s, g, lvl, seed=4040 + lvl, disaster_type="flood")
                  for lvl in (1, 2, 3) for s, g in test_cases]
    print_flood_report(flood_rows)
    print_paths(flood_rows)
    aggregate(flood_rows, "Flood-scenario summary (averaged across test cases):")


if __name__ == "__main__":
    main()