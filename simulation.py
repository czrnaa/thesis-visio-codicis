"""
Standalone simulation
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

# (Optional) PDF export - requires: pip install fpdf2
try:
    from fpdf import FPDF
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

# ROAD NETWORK GRAPH (Bulacan)
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

# BULACAN-SPECIFIC RISK PROFILE
BULACAN_RISK_PROFILE = {
    "Hagonoy":               {"flood": 1.00, "traffic": 0.50, "vuln": 0.85},
    "Calumpit":              {"flood": 0.90, "traffic": 0.70, "vuln": 0.80},
    "Calumpit (Market)":     {"flood": 0.90, "traffic": 0.75, "vuln": 0.80},
    "Paombong":              {"flood": 0.85, "traffic": 0.50, "vuln": 0.70},
    "HQ_Malolos":            {"flood": 0.50, "traffic": 0.85, "vuln": 0.50},
    "Malolos (City Hall)":   {"flood": 0.50, "traffic": 0.85, "vuln": 0.50},
    "Plaridel":              {"flood": 0.55, "traffic": 0.80, "vuln": 0.50},
    "Plaridel (Muni Hall)":  {"flood": 0.55, "traffic": 0.80, "vuln": 0.50},
    "Guiguinto":             {"flood": 0.50, "traffic": 0.80, "vuln": 0.50},
    "Guiguinto (Plaza)":     {"flood": 0.50, "traffic": 0.80, "vuln": 0.50},
    "Balagtas":              {"flood": 0.45, "traffic": 0.90, "vuln": 0.45},
    "Bocaue":                {"flood": 0.50, "traffic": 0.90, "vuln": 0.50},
    "Bocaue (Crossing)":     {"flood": 0.50, "traffic": 0.95, "vuln": 0.50},
    "San Miguel":            {"flood": 0.30, "traffic": 0.55, "vuln": 0.55},
    "San Miguel (Viola St)": {"flood": 0.30, "traffic": 0.55, "vuln": 0.55},
}


def edge_risk(u, v, kind):
    """Average the two endpoints' risk scores for the given hazard kind."""
    return 0.5 * (BULACAN_RISK_PROFILE[u][kind] + BULACAN_RISK_PROFILE[v][kind])


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
FLOOD_DEPTH_THRESHOLD_CM = 25            # Mamuyac (2025): closure threshold
FLOOD_CAPACITY_DROP_RANGE = (0.40, 0.70)  # 40-70% capacity drop above threshold

# --- Heavy-traffic constants (BPR, calibrated for Bulacan corridors) --------
# t = t_0 * (1 + alpha * (V/C)^beta), alpha = 0.15, beta = 4 (HCM standard).
BPR_ALPHA = 0.15
BPR_BETA  = 4

# --- Road-block constants ---------------------------------------------------
# S(e) = w_D * D + w_O * O + w_R * R, edge blocked iff S(e) >= S_THRESH.
ROADBLOCK_W_DAMAGE      = 0.40
ROADBLOCK_W_OBSTRUCTION = 0.40
ROADBLOCK_W_RISK        = 0.20
ROADBLOCK_S_THRESHOLD   = 0.60
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
    rng = random.Random(seed)
    weights = build_base_weights()
    blocked = set()
    depths = {e: 0.0 for e in weights}

    if level == 1:
        cap_lo, cap_hi, fraction = 15.0, 40.0, 0.40
    elif level == 2:
        cap_lo, cap_hi, fraction = 40.0, 100.0, 0.70
    elif level == 3:
        cap_lo, cap_hi, fraction = 80.0, 200.0, 1.00
    else:
        raise ValueError(f"Unknown flood level: {level}")

    undirected = list({tuple(sorted(e)) for e in weights})
    affected = rng.sample(undirected, k=max(1, int(len(undirected) * fraction)))

    for (a, b) in affected:
        cap = rng.uniform(cap_lo, cap_hi)            # storm-level depth cap
        risk = edge_risk(a, b, "flood")              # Bulacan geography
        # Beta-like draw biased toward the cap by local risk
        d = cap * risk * rng.uniform(0.7, 1.0)
        depths[(a, b)] = d
        depths[(b, a)] = d

        if d < FLOOD_DEPTH_THRESHOLD_CM:
            mult = 1.0 + 0.008 * d
        else:
            r = rng.uniform(*FLOOD_CAPACITY_DROP_RANGE)
            mult = 1.0 / (1.0 - r)

        weights[(a, b)] *= mult
        weights[(b, a)] *= mult

        if d >= FLOOD_DEPTH_THRESHOLD_CM:
            p_close = min(1.0, (d - FLOOD_DEPTH_THRESHOLD_CM) / 50.0)
            if rng.random() < p_close:
                blocked.add((a, b))
                blocked.add((b, a))

    return weights, blocked, depths


def simulate_heavy_traffic(level, seed=42):
    """
    Severity (V/C ceilings before per-edge scaling, % of edges affected):
        Level 1 (Light congestion)  : V/C_max ~ U(0.90, 1.10),  40% of edges
        Level 2 (Heavy congestion)  : V/C_max ~ U(1.10, 1.50),  70% of edges
        Level 3 (Gridlock)          : V/C_max ~ U(1.50, 2.00),  100% of edges
    Heavy traffic alone never blocks an edge.
    Returns (weights, blocked, vc_ratios).
    """
    rng = random.Random(seed)
    weights = build_base_weights()
    blocked = set()
    vc_ratios = {e: 1.0 for e in weights}

    if level == 1:
        vc_lo, vc_hi, fraction = 0.90, 1.10, 0.40
    elif level == 2:
        vc_lo, vc_hi, fraction = 1.10, 1.50, 0.70
    elif level == 3:
        vc_lo, vc_hi, fraction = 1.50, 2.00, 1.00
    else:
        raise ValueError(f"Unknown heavy-traffic level: {level}")

    undirected = list({tuple(sorted(e)) for e in weights})
    affected = rng.sample(undirected, k=max(1, int(len(undirected) * fraction)))

    for (a, b) in affected:
        cap = rng.uniform(vc_lo, vc_hi)
        risk = edge_risk(a, b, "traffic")
        # V/C floor pegged at 0.6, ceiling at the storm cap; risk biases up
        vc = 0.6 + (cap - 0.6) * (0.5 + 0.5 * risk) * rng.uniform(0.85, 1.0)
        vc_ratios[(a, b)] = vc
        vc_ratios[(b, a)] = vc
        mult = 1.0 + BPR_ALPHA * (vc ** BPR_BETA)
        weights[(a, b)] *= mult
        weights[(b, a)] *= mult

    return weights, blocked, vc_ratios


def simulate_road_block(level, seed=42):
    """
    Severity (component ceilings before vulnerability bias, % affected):
        Level 1 (Localized incidents): comp ~ U(0.05, 0.45), 40% of edges
        Level 2 (Multiple incidents) : comp ~ U(0.30, 0.75), 70% of edges
        Level 3 (Widespread damage)  : comp ~ U(0.55, 1.00), 100% of edges
    Returns (weights, blocked, severities).
    """
    rng = random.Random(seed)
    weights = build_base_weights()
    blocked = set()
    severities = {e: 0.0 for e in weights}

    if level == 1:
        comp_lo, comp_hi, fraction = 0.05, 0.45, 0.40
    elif level == 2:
        comp_lo, comp_hi, fraction = 0.30, 0.75, 0.70
    elif level == 3:
        comp_lo, comp_hi, fraction = 0.55, 1.00, 1.00
    else:
        raise ValueError(f"Unknown road-block level: {level}")

    undirected = list({tuple(sorted(e)) for e in weights})
    affected = rng.sample(undirected, k=max(1, int(len(undirected) * fraction)))

    for (a, b) in affected:
        risk = edge_risk(a, b, "vuln")
        # Bias: vulnerable corridors land closer to comp_hi
        bias = 0.5 + 0.5 * risk

        def draw():
            return min(1.0, rng.uniform(comp_lo, comp_hi) * bias)

        D, O, R = draw(), draw(), draw()
        S = (ROADBLOCK_W_DAMAGE * D
             + ROADBLOCK_W_OBSTRUCTION * O
             + ROADBLOCK_W_RISK * R)
        severities[(a, b)] = S
        severities[(b, a)] = S

        if S >= ROADBLOCK_S_THRESHOLD:
            blocked.add((a, b))
            blocked.add((b, a))
        else:
            mult = 1.0 + 2.0 * S
            weights[(a, b)] *= mult
            weights[(b, a)] *= mult

    return weights, blocked, severities

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


def _undirected_values(per_edge):
    """Collapse a directed-edge dict to a list of one value per road."""
    seen, vals = set(), []
    for (u, v), x in per_edge.items():
        key = tuple(sorted((u, v)))
        if key in seen:
            continue
        seen.add(key)
        vals.append(x)
    return vals


def run_scenario(start, goal, level, seed=42, disaster_type="generic"):
    if disaster_type == "flood":
        weights, blocked, depths = simulate_flood_disaster(level, seed=seed)
        per_edge_metric = ("flood", depths)
    elif disaster_type == "heavy_traffic":
        weights, blocked, vc = simulate_heavy_traffic(level, seed=seed)
        per_edge_metric = ("heavy_traffic", vc)
    elif disaster_type == "road_block":
        weights, blocked, sev = simulate_road_block(level, seed=seed)
        per_edge_metric = ("road_block", sev)
    else:
        weights, blocked = simulate_disaster(level, seed=seed)
        per_edge_metric = (None, None)

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

    kind, table = per_edge_metric
    if kind == "flood":
        vals = _undirected_values(table)
        flooded = [d for d in vals if d > 0]
        over = [d for d in vals if d >= FLOOD_DEPTH_THRESHOLD_CM]
        result["flood"] = {
            "max_depth_cm":   max(vals) if vals else 0.0,
            "mean_depth_cm":  (sum(flooded) / len(flooded)) if flooded else 0.0,
            "edges_flooded": len(flooded),
            "edges_over_threshold": len(over),
        }
    elif kind == "heavy_traffic":
        vals = _undirected_values(table)
        congested = [vc for vc in vals if vc > 1.0]
        result["heavy_traffic"] = {
            "max_vc":     max(vals) if vals else 1.0,
            "mean_vc":    (sum(congested) / len(congested)) if congested else 1.0,
            "edges_congested": len(congested),
            "edges_over_capacity": sum(1 for vc in vals if vc >= 1.0),
        }
    elif kind == "road_block":
        vals = _undirected_values(table)
        affected_vals = [s for s in vals if s > 0]
        over = [s for s in vals if s >= ROADBLOCK_S_THRESHOLD]
        result["road_block"] = {
            "max_severity":  max(vals) if vals else 0.0,
            "mean_severity": (sum(affected_vals) / len(affected_vals)) if affected_vals else 0.0,
            "edges_affected": len(affected_vals),
            "edges_blocked":  len(over),
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


def print_traffic_report(rows):
    """Per-scenario heavy-traffic statistics + routing comparison."""
    print("=" * 104)
    print(f"{'Lvl':<4}{'Start -> Goal':<42}"
          f"{'MaxV/C':>8}{'>=1.0':>7}"
          f"{'A* km':>9}{'ABSRA km':>10}{'A* nodes':>10}{'ABSRA':>7}{'BlkRoads':>10}")
    print("-" * 104)
    for r in rows:
        h = r["heavy_traffic"]
        sg = f"{r['start']} -> {r['goal']}"
        a, b = r["a_star"], r["absra"]
        a_cost = f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF"
        b_cost = f"{b['cost']:.2f}" if b['cost'] != math.inf else "INF"
        print(f"L{r['level']:<3}{sg:<42}"
              f"{h['max_vc']:>8.2f}{h['edges_over_capacity']:>7}"
              f"{a_cost:>9}{b_cost:>10}"
              f"{a['explored']:>10}{b['explored']:>7}{r['blocked_edges']:>10}")
    print("-" * 104)


def print_block_report(rows):
    """Per-scenario road-block statistics + routing comparison."""
    print("=" * 104)
    print(f"{'Lvl':<4}{'Start -> Goal':<42}"
          f"{'MaxS':>7}{'>=0.6':>7}{'Closed':>8}"
          f"{'A* km':>9}{'ABSRA km':>10}{'A* nodes':>10}{'ABSRA':>7}")
    print("-" * 104)
    for r in rows:
        rb = r["road_block"]
        sg = f"{r['start']} -> {r['goal']}"
        a, b = r["a_star"], r["absra"]
        a_cost = f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF"
        b_cost = f"{b['cost']:.2f}" if b['cost'] != math.inf else "INF"
        print(f"L{r['level']:<3}{sg:<42}"
              f"{rb['max_severity']:>7.2f}{rb['edges_blocked']:>7}"
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


def generate_pdf_report(generic_rows, flood_rows, traffic_rows, block_rows,
                        output_path="simulation_report.pdf"):
    """Save all simulation results to a PDF report (requires fpdf2)."""
    if not _PDF_AVAILABLE:
        print("[PDF] fpdf2 not installed — run: pip install fpdf2")
        return

    import datetime
    level_names = {1: "Minor", 2: "Moderate", 3: "Severe"}

    class _ReportPDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 5, "VisioCodicis  |  Disaster Routing Simulation", align="R")
            self.ln(7)
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 6, f"Page {self.page_no()}", align="C")
            self.set_text_color(0, 0, 0)

    pdf = _ReportPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def section_title(txt):
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(45, 90, 160)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 8, f"  {txt}", border=0, fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    def draw_table(headers, col_widths, data_rows, font_size=7):
        pdf.set_font("Helvetica", "B", font_size)
        pdf.set_fill_color(190, 210, 235)
        for h, w in zip(headers, col_widths):
            pdf.cell(w, 6, h, border=1, fill=True, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", font_size)
        for i, row in enumerate(data_rows):
            if i % 2 == 0:
                pdf.set_fill_color(255, 255, 255)
            else:
                pdf.set_fill_color(242, 246, 252)
            for val, w in zip(row, col_widths):
                pdf.cell(w, 5, str(val), border=1, fill=True, align="C")
            pdf.ln()
        pdf.ln(4)

    # Cover
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 14, "VisioCodicis: Disaster Routing Simulation", align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7,
             f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             align="C")
    pdf.ln()
    pdf.cell(0, 7,
             "Routing area: Bulacan, Philippines   |   A* vs. ABSRA (Arc-flag Bidirectional Search A*)",
             align="C")
    pdf.ln(10)
    pdf.set_text_color(0, 0, 0)

    # 1. Generic
    section_title("1. Baseline Synthetic Disaster Scenarios")
    hdrs = ["Lvl", "Start -> Goal", "Algo", "Cost (km)", "Nodes", "Time (ms)"]
    cws  = [14, 84, 16, 24, 20, 24]
    rows_data = []
    for r in generic_rows:
        sg  = f"{r['start']} -> {r['goal']}"
        lbl = f"L{r['level']} {level_names[r['level']]}"
        for key, albl in [("a_star", "A*"), ("absra", "ABSRA")]:
            a = r[key]
            cost = f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF"
            rows_data.append([lbl, sg, albl, cost, str(a['explored']), f"{a['time_ms']:.3f}"])
    draw_table(hdrs, cws, rows_data)

    # 2. Flood
    section_title("2. Flood Scenarios  (Mamuyac 2025 threshold: 25 cm | NDRRMC Carina Jul 2024)")
    hdrs = ["Lvl", "Start -> Goal", "MaxDepth(cm)", ">25cm edges", "Closed roads",
            "A* (km)", "ABSRA (km)", "A* Nodes", "ABSRA Nodes"]
    cws  = [12, 74, 24, 20, 20, 20, 22, 20, 22]
    rows_data = []
    for r in flood_rows:
        f  = r["flood"]
        sg = f"{r['start']} -> {r['goal']}"
        a, b = r["a_star"], r["absra"]
        rows_data.append([
            f"L{r['level']}", sg,
            f"{f['max_depth_cm']:.1f}", str(f['edges_over_threshold']),
            str(r['blocked_edges']),
            f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF",
            f"{b['cost']:.2f}" if b['cost'] != math.inf else "INF",
            str(a['explored']), str(b['explored']),
        ])
    draw_table(hdrs, cws, rows_data)

    # 3. Heavy Traffic
    section_title("3. Heavy-Traffic Scenarios  (BPR model | DPWH Region III / TomTom 2024)")
    hdrs = ["Lvl", "Start -> Goal", "Max V/C", "Edges >= 1.0", "A* (km)",
            "ABSRA (km)", "A* Nodes", "ABSRA Nodes", "Blocked roads"]
    cws  = [12, 72, 18, 20, 20, 22, 20, 22, 22]
    rows_data = []
    for r in traffic_rows:
        h  = r["heavy_traffic"]
        sg = f"{r['start']} -> {r['goal']}"
        a, b = r["a_star"], r["absra"]
        rows_data.append([
            f"L{r['level']}", sg,
            f"{h['max_vc']:.2f}", str(h['edges_over_capacity']),
            f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF",
            f"{b['cost']:.2f}" if b['cost'] != math.inf else "INF",
            str(a['explored']), str(b['explored']), str(r['blocked_edges']),
        ])
    draw_table(hdrs, cws, rows_data)

    # 4. Road Block
    section_title("4. Road-Block Scenarios  (DPWH Region III | Bulacan DEO post-typhoon bulletins)")
    hdrs = ["Lvl", "Start -> Goal", "Max S", "Edges >= 0.6", "Closed roads",
            "A* (km)", "ABSRA (km)", "A* Nodes", "ABSRA Nodes"]
    cws  = [12, 74, 16, 18, 18, 20, 22, 20, 22]
    rows_data = []
    for r in block_rows:
        rb = r["road_block"]
        sg = f"{r['start']} -> {r['goal']}"
        a, b = r["a_star"], r["absra"]
        rows_data.append([
            f"L{r['level']}", sg,
            f"{rb['max_severity']:.2f}", str(rb['edges_blocked']),
            str(r['blocked_edges']),
            f"{a['cost']:.2f}" if a['cost'] != math.inf else "INF",
            f"{b['cost']:.2f}" if b['cost'] != math.inf else "INF",
            str(a['explored']), str(b['explored']),
        ])
    draw_table(hdrs, cws, rows_data)

    # 5. Aggregate Summary
    pdf.add_page()
    section_title("5. Algorithm Comparison Summary  (averaged per scenario type & level)")
    hdrs = ["Scenario", "Level", "Algorithm", "Avg Cost (km)", "Avg Nodes",
            "Avg Time (ms)", "Reachable"]
    cws  = [32, 20, 22, 30, 24, 28, 22]
    rows_data = []
    for label, rows in [("Generic", generic_rows), ("Flood", flood_rows),
                        ("Traffic", traffic_rows), ("Road-Block", block_rows)]:
        for level in (1, 2, 3):
            subset = [r for r in rows if r["level"] == level]
            for algo_key, albl in [("a_star", "A*"), ("absra", "ABSRA")]:
                reached = [r[algo_key] for r in subset if r[algo_key]["path"]]
                if not reached:
                    rows_data.append([label, f"L{level}", albl, "-", "-", "-",
                                      f"0/{len(subset)}"])
                else:
                    avg_c = sum(x["cost"]     for x in reached) / len(reached)
                    avg_n = sum(x["explored"] for x in reached) / len(reached)
                    avg_t = sum(x["time_ms"]  for x in reached) / len(reached)
                    rows_data.append([label, f"L{level}", albl,
                                      f"{avg_c:.2f}", f"{avg_n:.1f}", f"{avg_t:.3f}",
                                      f"{len(reached)}/{len(subset)}"])
    draw_table(hdrs, cws, rows_data, font_size=8)

    pdf.output(output_path)
    print(f"\n[PDF] Report saved -> {output_path}")


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

    # ---- Synthetic baseline sweep (no Bulacan-specific calibration) ----
    print("\n### BASELINE SYNTHETIC DISASTER SCENARIOS (no calibration) ###")
    generic_rows = [run_scenario(s, g, lvl, seed=2026 + lvl)
                    for lvl in (1, 2, 3) for s, g in test_cases]
    print_report(generic_rows)
    aggregate(generic_rows, "Baseline summary (averaged across test cases):")

    # ---- Flood-specific sweep (Mamuyac, 2025; Bulacan calibration) ----
    print("\n### FLOOD SCENARIOS - Bulacan (NDRRMC Carina Jul 2024, "
          "Bulacan PDRRMO, Project NOAH, PAGASA Pampanga River basin) ###")
    print(f"Mamuyac (2025) threshold: {FLOOD_DEPTH_THRESHOLD_CM} cm; "
          f"capacity drop above threshold: "
          f"{int(FLOOD_CAPACITY_DROP_RANGE[0]*100)}-"
          f"{int(FLOOD_CAPACITY_DROP_RANGE[1]*100)}%. "
          "Per-edge depth scaled by Bulacan flood-risk profile "
          "(Hagonoy 1.00 -> San Miguel 0.30).")
    flood_rows = [run_scenario(s, g, lvl, seed=4040 + lvl, disaster_type="flood")
                  for lvl in (1, 2, 3) for s, g in test_cases]
    print_flood_report(flood_rows)
    aggregate(flood_rows, "Flood-scenario summary (averaged across test cases):")

    # ---- Heavy-traffic sweep (BPR, Bulacan corridor calibration) ----
    print("\n### HEAVY-TRAFFIC SCENARIOS - Bulacan MacArthur Hwy / NLEX corridor ###")
    print(f"BPR: t = t_0 * (1 + {BPR_ALPHA} * (V/C)^{BPR_BETA}); "
          f"V/C calibrated from DPWH Region III peak-hour observations "
          "(Bocaue-Balagtas NLEX, MacArthur Hwy Plaridel-Guiguinto-Malolos), "
          "TomTom Traffic Index 2024.")
    traffic_rows = [run_scenario(s, g, lvl, seed=5050 + lvl, disaster_type="heavy_traffic")
                    for lvl in (1, 2, 3) for s, g in test_cases]
    print_traffic_report(traffic_rows)
    aggregate(traffic_rows, "Heavy-traffic summary (averaged across test cases):")

    # ---- Road-block sweep (severity index, Bulacan road vulnerability) ----
    print("\n### ROAD-BLOCK SCENARIOS - Bulacan (DPWH Region III road status) ###")
    print(f"S = {ROADBLOCK_W_DAMAGE}*D + {ROADBLOCK_W_OBSTRUCTION}*O + "
          f"{ROADBLOCK_W_RISK}*R; block iff S >= {ROADBLOCK_S_THRESHOLD}. "
          "Per-edge components biased by Bulacan road-vulnerability profile "
          "(Hagonoy 0.85 -> Malolos urban core 0.50). Calibrated from "
          "DPWH Region III (Bulacan 1st & 2nd DEO) post-typhoon road status "
          "bulletins, NDRRMC Final Reports on Typhoons Carina and Kristine.")
    block_rows = [run_scenario(s, g, lvl, seed=6060 + lvl, disaster_type="road_block")
                  for lvl in (1, 2, 3) for s, g in test_cases]
    print_block_report(block_rows)
    aggregate(block_rows, "Road-block summary (averaged across test cases):")

    generate_pdf_report(generic_rows, flood_rows, traffic_rows, block_rows)


if __name__ == "__main__":
    main()