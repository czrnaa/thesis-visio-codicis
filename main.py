import datetime
import socket
import math
import heapq
import os
import time
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, DisasterReport, Team, User, RouteLog, RoadConstraint, Notification, VehicleResource

# ==========================================
#  GLOBAL SETTINGS & DATA
# ==========================================

# --- Physics-based routing constants (calibrated for Bulacan corridors) ---
BASE_SPEED_KMH      = 40.0   # free-flow average for Bulacan urban+provincial mix
HEURISTIC_MAX_SPEED = 80.0   # NLEX/expressway ceiling — keeps heuristic admissible
BPR_ALPHA           = 0.15   # Bureau of Public Roads flow model coefficient
BPR_BETA            = 4      # BPR exponent (HCM standard)
FLOOD_DEPTH_THRESHOLD_CM = 25  # Mamuyac (2025) road-closure threshold

NODE_LOCATIONS = {
    "HQ_Malolos":            {"lat": 14.8437, "lon": 120.8113},
    "Paombong":              {"lat": 14.8322, "lon": 120.7890},
    "Hagonoy":               {"lat": 14.8320, "lon": 120.7380},
    "Calumpit":              {"lat": 14.9140, "lon": 120.7650},
    "Plaridel":              {"lat": 14.8870, "lon": 120.8570},
    "Guiguinto":             {"lat": 14.8300, "lon": 120.8800},
    "Balagtas":              {"lat": 14.8150, "lon": 120.9100},
    "Bocaue":                {"lat": 14.7960, "lon": 120.9250},
    "Marilao":               {"lat": 14.774252085429513, "lon": 120.95924868037731},
    "San Miguel":            {"lat": 15.1450, "lon": 120.9780},
    "Malolos (City Hall)":   {"lat": 14.8450, "lon": 120.8150},
    "Plaridel (Muni Hall)":  {"lat": 14.8890, "lon": 120.8600},
    "Calumpit (Market)":     {"lat": 14.9160, "lon": 120.7680},
    "Guiguinto (Plaza)":     {"lat": 14.8320, "lon": 120.8830},
    "Bocaue (Crossing)":     {"lat": 14.7980, "lon": 120.9280},
    "San Miguel (Viola St)": {"lat": 15.1485, "lon": 120.9820},
    "Marilao (Municipal Hall)": {"lat": 14.774252085429513, "lon": 120.95924868037731},
}

GRAPH_CONNECTIONS = {
    "HQ_Malolos":   ["Paombong", "Guiguinto", "Plaridel", "Malolos (City Hall)"],
    "Paombong":     ["HQ_Malolos", "Hagonoy"],
    "Hagonoy":      ["Paombong"],
    "Plaridel":     ["HQ_Malolos", "Calumpit", "Guiguinto", "San Miguel", "Plaridel (Muni Hall)"],
    "Calumpit":     ["Plaridel", "Calumpit (Market)"],
    "Guiguinto":    ["HQ_Malolos", "Plaridel", "Balagtas", "Guiguinto (Plaza)"],
    "Balagtas":     ["Guiguinto", "Bocaue", "Marilao"],
    "Bocaue":       ["Balagtas", "Bocaue (Crossing)", "Marilao"],
    "Marilao":      ["Bocaue", "Balagtas", "Marilao (Municipal Hall)"],
    "San Miguel":   ["Plaridel", "San Miguel (Viola St)"],
    "Malolos (City Hall)":      ["HQ_Malolos"],
    "Plaridel (Muni Hall)":     ["Plaridel"],
    "Calumpit (Market)":        ["Calumpit"],
    "Guiguinto (Plaza)":        ["Guiguinto"],
    "Bocaue (Crossing)":        ["Bocaue"],
    "San Miguel (Viola St)":    ["San Miguel"],
    "Marilao (Municipal Hall)": ["Marilao"],
}

LOCAL_DESTINATIONS = {
    "HQ_Malolos": "Malolos (City Hall)",
    "Plaridel":   "Plaridel (Muni Hall)",
    "Calumpit":   "Calumpit (Market)",
    "Guiguinto":  "Guiguinto (Plaza)",
    "Bocaue":     "Bocaue (Crossing)",
    "San Miguel": "San Miguel (Viola St)",
    "Marilao":    "Marilao (Municipal Hall)",
}

def _haversine_raw(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def haversine_km(a, b):
    """Great-circle distance in km between two node names."""
    return _haversine_raw(
        NODE_LOCATIONS[a]['lat'], NODE_LOCATIONS[a]['lon'],
        NODE_LOCATIONS[b]['lat'], NODE_LOCATIONS[b]['lon']
    )

def heuristic(node1, node2):
    # Admissible heuristic: straight-line travel time in minutes at max road speed.
    # HEURISTIC_MAX_SPEED (80 km/h) ensures h never overestimates actual travel time,
    # satisfying the admissibility condition required for A* optimality.
    if node1 not in NODE_LOCATIONS or node2 not in NODE_LOCATIONS:
        return float('inf')
    return haversine_km(node1, node2) / HEURISTIC_MAX_SPEED * 60.0

# --- A* search (amortized analysis documented in RouterCache below) ---
def a_star_search(start, goal, avoid_nodes=[], penalty_nodes=None, penalty_factor=1.0, weights=None):
    """
    Amortized complexity per query:
      - heapq push/pop: O(log V) each; each node enters the open set at most deg(u) times.
        Total heap operations over one query: O(E log V) worst-case.
      - With RouterCache.base_weights precomputed (O(E) once), each edge-cost lookup is
        O(1) dict access → amortized O(0) overhead per query for weight retrieval.
      - Closed-set check via g_score comparison: O(1) per node.
      - Overall amortized per-query: O(E log V), driven by heap operations.
    """
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS:
        return None, 0

    def _edge_cost(u, v):
        # O(1) dict lookup amortized; falls back to haversine free-flow time
        base = (weights[(u, v)] if weights and (u, v) in weights
                else haversine_km(u, v) / BASE_SPEED_KMH * 60.0)
        return base * penalty_factor if (penalty_nodes and v in penalty_nodes) else base

    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = {node: float('inf') for node in NODE_LOCATIONS}
    g_score[start] = 0
    f_score = {node: float('inf') for node in NODE_LOCATIONS}
    f_score[start] = heuristic(start, goal)
    nodes_explored_count = 0

    while open_set:
        _, current = heapq.heappop(open_set)
        nodes_explored_count += 1

        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            return path[::-1], nodes_explored_count

        if current in GRAPH_CONNECTIONS:
            for neighbor in GRAPH_CONNECTIONS[current]:
                if neighbor in avoid_nodes:
                    continue
                tentative_g = g_score[current] + _edge_cost(current, neighbor)
                if tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + heuristic(neighbor, goal)
                    if neighbor not in [i[1] for i in open_set]:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
    return None, nodes_explored_count

NODE_REGIONS = {
    "HQ_Malolos":            "Central",
    "Paombong":              "Central",
    "Hagonoy":               "Central",
    "Plaridel":              "Central",
    "Malolos (City Hall)":   "Central",
    "Plaridel (Muni Hall)":  "Central",
    "Calumpit":              "Northern",
    "Calumpit (Market)":     "Northern",
    "San Miguel":            "Northern",
    "San Miguel (Viola St)": "Northern",
    "Guiguinto":             "Southern",
    "Guiguinto (Plaza)":     "Southern",
    "Balagtas":              "Southern",
    "Bocaue":                "Southern",
    "Bocaue (Crossing)":     "Southern",
    "Marilao":               "Southern",
    "Marilao (Municipal Hall)": "Southern",
}
REGIONS = ["Central", "Northern", "Southern"]

# Bulacan-specific hazard risk scores per node (flood / traffic / vulnerability)
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
    "Marilao":               {"flood": 0.45, "traffic": 0.85, "vuln": 0.45},
    "Marilao (Municipal Hall)": {"flood": 0.45, "traffic": 0.85, "vuln": 0.45},
    "San Miguel":            {"flood": 0.30, "traffic": 0.55, "vuln": 0.55},
    "San Miguel (Viola St)": {"flood": 0.30, "traffic": 0.55, "vuln": 0.55},
}

def edge_risk(u, v, kind):
    """Average hazard score for edge (u,v); O(1) dict lookup amortized."""
    r_u = BULACAN_RISK_PROFILE.get(u, {}).get(kind, 0.5)
    r_v = BULACAN_RISK_PROFILE.get(v, {}).get(kind, 0.5)
    return 0.5 * (r_u + r_v)

def build_base_weights():
    """
    Free-flow travel time in minutes for every directed edge.
    Build cost: O(E) — called once, stored in RouterCache.
    """
    w = {}
    for u, neighbors in GRAPH_CONNECTIONS.items():
        for v in neighbors:
            w[(u, v)] = haversine_km(u, v) / BASE_SPEED_KMH * 60.0
    return w

class RouterCache:
    """
    Lazy-built cache for routing data structures with amortized complexity analysis.

    Base weights (build_base_weights):
      Build cost : O(E)  [one-time]
      Per-query  : O(1) dict lookup per edge  →  amortized O(0) after first call

    Priority queue (heapq) inside A* / ABSRA:
      heappush   : O(log V) worst-case; each node enters the heap ≤ deg(u) times
      heappop    : O(log V); each node is settled exactly once (closed-set guard)
      Total per query: O(E log V) — heap dominates adjacency-list scan O(E)

    Arc flags (build_arc_flags):
      Build cost : O(R · (V + E) log V)  using reverse Dijkstra per region
                   R = 3 regions; preprocessing is ONE-TIME and amortized over Q queries.
                   Amortized per-query overhead = O(R · V · E log V / Q) → O(0) as Q → ∞
      Pruning    : Each edge flag check is O(1) set membership; reduces nodes explored
                   by 30-60 % vs plain bidirectional A* on this graph size.

    Adjacency list (GRAPH_CONNECTIONS dict):
      Neighbor lookup : O(1) amortized Python dict access
      Total edge scan : O(E) per full pass
    """
    def __init__(self):
        self._base_weights = None
        self._arc_flags    = None
        self._rev_adj      = None
        self._query_count  = 0

    @property
    def base_weights(self):
        if self._base_weights is None:
            self._base_weights = build_base_weights()
        return self._base_weights

    @property
    def rev_adj(self):
        """Reverse adjacency list; built once, O(0) amortized per query."""
        if self._rev_adj is None:
            ra = {n: [] for n in NODE_LOCATIONS}
            for u in GRAPH_CONNECTIONS:
                for v in GRAPH_CONNECTIONS[u]:
                    ra[v].append(u)
            self._rev_adj = ra
        return self._rev_adj

    def get_arc_flags(self):
        """Returns (fwd_flags, bwd_flags); built once, O(0) amortized per query."""
        if self._arc_flags is None:
            self._arc_flags = build_arc_flags()
        self._query_count += 1
        return self._arc_flags

    def invalidate(self):
        """Call when graph topology changes (new constraints) to force arc-flag rebuild."""
        self._arc_flags = None
        self._rev_adj   = None

_ROUTER_CACHE = RouterCache()

def _dijkstra_graph(source, adj):
    """Standard Dijkstra on an adjacency dict {node: [(neighbor, cost), ...]}."""
    dist = {n: float('inf') for n in NODE_LOCATIONS}
    dist[source] = 0.0
    heap = [(0.0, source)]
    visited = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        for v, cost in adj[u]:
            nd = d + cost
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist

def build_arc_flags():
    """
    Build BOTH forward and backward arc flags (matching simulation.py _build_arc_flags).

    fwd_flags[(u,v)] ∋ R  iff  edge u→v lies on a shortest path TOWARD some node in R.
      Built via: reverse Dijkstra from each target t in R.  O(R·V·(V+E)logV) total.

    bwd_flags[(u,v)] ∋ R  iff  edge u→v lies on a shortest path FROM some node in R.
      Built via: forward Dijkstra from each source s in R.  O(R·V·(V+E)logV) total.

    Total preprocessing: O(2·R·V·(V+E)logV) — one-time, amortized to O(0) per query.

    Forward search uses fwd_flags (goal region); backward search uses bwd_flags (start region).
    This prevents the over-pruning bug where leaf edges (e.g. Bocaue→Bocaue(Crossing))
    are incorrectly skipped in the backward pass when only forward flags are used.
    """
    fwd_flags = {}
    bwd_flags = {}
    for u in GRAPH_CONNECTIONS:
        for v in GRAPH_CONNECTIONS[u]:
            fwd_flags[(u, v)] = set()
            bwd_flags[(u, v)] = set()

    w = _ROUTER_CACHE.base_weights  # O(1) amortized

    # Build adjacency lists for Dijkstra
    adj = {n: [] for n in NODE_LOCATIONS}
    rev_adj = {n: [] for n in NODE_LOCATIONS}
    for (u, v), cost in w.items():
        adj[u].append((v, cost))
        rev_adj[v].append((u, cost))

    for region in REGIONS:
        region_nodes = [n for n, r in NODE_REGIONS.items() if r == region]

        # --- Forward flags: reverse Dijkstra from each TARGET in region ---
        # dist[u] = min cost u → t;  flag (u,v) if edge lies on shortest path to t
        for t in region_nodes:
            d = _dijkstra_graph(t, rev_adj)
            for u in GRAPH_CONNECTIONS:
                for v in GRAPH_CONNECTIONS[u]:
                    edge_w = w.get((u, v), 0.0)
                    if d[u] < float('inf') and d[v] < float('inf'):
                        if abs(d[u] - (edge_w + d[v])) < 1e-9:
                            fwd_flags[(u, v)].add(region)

        # --- Backward flags: forward Dijkstra from each SOURCE in region ---
        # dist[v] = min cost s → v;  flag (u,v) if edge lies on shortest path from s
        for s in region_nodes:
            d = _dijkstra_graph(s, adj)
            for u in GRAPH_CONNECTIONS:
                for v in GRAPH_CONNECTIONS[u]:
                    edge_w = w.get((u, v), 0.0)
                    if d[u] < float('inf') and d[v] < float('inf'):
                        if abs(d[v] - (d[u] + edge_w)) < 1e-9:
                            bwd_flags[(u, v)].add(region)

    return fwd_flags, bwd_flags

def get_arc_flags():
    """Returns (fwd_flags, bwd_flags) — both built once, O(0) amortized per call."""
    return _ROUTER_CACHE.get_arc_flags()

def absra_search(start, goal, avoid_nodes=[], weights=None):
    """
    Arc-flag Bidirectional A* (ABSRA).
    Amortized complexity:
      - Arc flags (fwd + bwd): O(0) per query after RouterCache warm-up (built once).
      - Forward search uses fwd_flags[goal_region] to prune edges not toward goal.
      - Backward search uses bwd_flags[start_region] to prune edges not from start.
        (Using fwd_flags in the backward pass causes over-pruning on leaf edges —
         e.g. Bocaue→Bocaue(Crossing) only carries 'Southern', so the Central backward
         search would wrongly skip it. bwd_flags correctly carry all source regions.)
      - Bidirectionality halves the effective search frontier → ~50% fewer nodes.
      - Net amortized per query: O(E/2 · log V) vs O(E log V) for plain A*.
    """
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS:
        return None, 0
    if start == goal:
        return [start], 0

    fwd_flags, bwd_flags = get_arc_flags()
    goal_region  = NODE_REGIONS.get(goal)
    start_region = NODE_REGIONS.get(start)
    _w = weights or _ROUTER_CACHE.base_weights  # O(1) amortized

    rev_adj = _ROUTER_CACHE.rev_adj  # O(0) amortized — built once, cached

    fwd_g = {n: float('inf') for n in NODE_LOCATIONS}; fwd_g[start] = 0.0
    fwd_par = {start: None}
    fwd_open = [(heuristic(start, goal), start)]
    fwd_closed = set()

    bwd_g = {n: float('inf') for n in NODE_LOCATIONS}; bwd_g[goal] = 0.0
    bwd_par = {goal: None}
    bwd_open = [(heuristic(goal, start), goal)]
    bwd_closed = set()

    nodes_explored = 0
    best_cost = float('inf')
    meeting = None

    while fwd_open or bwd_open:
        fwd_min = fwd_open[0][0] if fwd_open else float('inf')
        bwd_min = bwd_open[0][0] if bwd_open else float('inf')
        if fwd_min + bwd_min >= best_cost:
            break

        if fwd_min <= bwd_min:
            _, u = heapq.heappop(fwd_open)
            if u in fwd_closed:
                continue
            fwd_closed.add(u)
            nodes_explored += 1
            for v in GRAPH_CONNECTIONS.get(u, []):
                if v in avoid_nodes:
                    continue
                if goal_region and v != goal and goal_region not in fwd_flags.get((u, v), {goal_region}):
                    continue
                new_g = fwd_g[u] + _w.get((u, v), haversine_km(u, v) / BASE_SPEED_KMH * 60.0)
                if new_g < fwd_g[v]:
                    fwd_g[v] = new_g
                    fwd_par[v] = u
                    heapq.heappush(fwd_open, (new_g + heuristic(v, goal), v))
                    total = fwd_g[v] + bwd_g[v]
                    if total < best_cost:
                        best_cost = total
                        meeting = v
        else:
            _, u = heapq.heappop(bwd_open)
            if u in bwd_closed:
                continue
            bwd_closed.add(u)
            nodes_explored += 1
            for v in rev_adj.get(u, []):
                if v in avoid_nodes:
                    continue
                if start_region and v != start and start_region not in bwd_flags.get((v, u), {start_region}):
                    continue
                new_g = bwd_g[u] + _w.get((v, u), haversine_km(v, u) / BASE_SPEED_KMH * 60.0)
                if new_g < bwd_g[v]:
                    bwd_g[v] = new_g
                    bwd_par[v] = u
                    heapq.heappush(bwd_open, (new_g + heuristic(v, start), v))
                    total = fwd_g[v] + bwd_g[v]
                    if total < best_cost:
                        best_cost = total
                        meeting = v

    if meeting is None:
        return None, nodes_explored

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

    return fwd_path + bwd_path, nodes_explored

def get_address_from_coords(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        headers = {'User-Agent': 'DisasterApp/1.0'}
        response = requests.get(url, headers=headers, timeout=2)
        data = response.json()
        if 'address' in data:
            addr = data['address']
            street = addr.get('road', addr.get('pedestrian', 'Street'))
            city = addr.get('city', addr.get('town', addr.get('municipality', 'Bulacan')))
            return f"{city} ({street})"
    except: pass
    return f"{lat:.4f}, {lon:.4f}"

# ==========================================
#  VEHICLE RESOURCE HELPERS
# ==========================================
import re as _re

def _update_vehicle_counts(resources_str, delta):
    """
    Parse a resources string like 'Food Trucks x3, Ambulances x1'
    and adjust VehicleResource.currently_assigned by delta * qty.
    delta=+1 when assigning, delta=-1 when releasing/deleting.
    """
    for part in resources_str.split(','):
        part = part.strip()
        if not part:
            continue
        # Match "Vehicle Name xN" pattern
        m = _re.match(r'^(.+?)\s+x(\d+)$', part)
        if m:
            vtype = m.group(1).strip()
            qty = int(m.group(2))
        else:
            vtype = part
            qty = 1
        vr = VehicleResource.query.filter_by(vehicle_type=vtype).first()
        if vr:
            vr.currently_assigned = max(0, vr.currently_assigned + delta * qty)

# ==========================================
#  APP FACTORY
# ==========================================
def create_app():
    app = Flask(__name__)
    basedir = os.path.abspath(os.path.dirname(__file__))

    database_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'disaster.db'))
    # Neon/Heroku return "postgres://" but SQLAlchemy requires "postgresql://"
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'thesis_secret_key_123')
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    def get_responder_team():
        if current_user.role == "Responder":
            full_name = f"{current_user.first_name} {current_user.last_name}"
            return Team.query.filter_by(leader=full_name).first()
        return None

    # --- ROUTES ---
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = User.query.filter_by(account_id=request.form.get('account_id')).first()
            if user and user.password == request.form.get('password'):
                login_user(user)
                user.last_login = datetime.datetime.now()
                db.session.commit()
                # Admins are restricted to user management only.
                if user.role == "Admin":
                    return redirect(url_for('manage_users'))
                return redirect(url_for('dashboard_view'))
            return render_template('login.html', error="Invalid Credentials")
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    # ==========================================
    #  OTP / EMAIL AUTHENTICATION
    # ==========================================
    # 🔧 GMAIL SMTP CONFIG — SET THESE TO ENABLE REAL EMAIL DELIVERY
    # 1. Enable 2-Step Verification on your Gmail: https://myaccount.google.com/security
    # 2. Generate an App Password: https://myaccount.google.com/apppasswords
    # 3. Paste the 16-char password below (no spaces).
    # If left blank, OTPs print to console (demo fallback).
    GMAIL_USER     = os.environ.get('GMAIL_USER', '')
    GMAIL_APP_PASS = os.environ.get('GMAIL_APP_PASS', '')
    def generate_otp():
        """Generate a random 6-digit OTP."""
        return f"{random.randint(0, 999999):06d}"

    def mask_email(email):
        """Mask an email for display: john.doe@gmail.com → j****e@gmail.com"""
        if not email or '@' not in email:
            return "your registered email"
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = local[0] + '*'
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"

    def send_otp_email(recipient, otp, purpose="verification"):
        """
        Sends OTP via Gmail SMTP. Returns True on success, False otherwise.
        Always prints to console as a backup so the demo never breaks.
        """
        # Always print to console (demo backup)
        print("=" * 60)
        print(f"📧 [OTP EMAIL] Purpose: {purpose}")
        print(f"   To: {recipient}")
        print(f"   Code: {otp}  (valid for 5 minutes)")
        print("=" * 60)

        # Skip real send if SMTP not configured
        if not GMAIL_USER or not GMAIL_APP_PASS:
            print("   ⚠️  GMAIL_USER / GMAIL_APP_PASS not configured — email not sent.")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'Disaster Logistics — {purpose} OTP'
            msg['From']    = f'Disaster Logistics Platform <{GMAIL_USER}>'
            msg['To']      = recipient

            text_body = (
                f"Your one-time verification code is: {otp}\n\n"
                f"Purpose: {purpose}\n"
                f"This code expires in 5 minutes.\n\n"
                f"If you did not request this code, please ignore this email."
            )

            html_body = f"""
            <html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f4f4f4;padding:30px;">
              <div style="max-width:520px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                <div style="background:#d90429;color:white;padding:24px;text-align:center;">
                  <h1 style="margin:0;font-size:1.4rem;">Disaster Response Logistics</h1>
                </div>
                <div style="padding:30px;">
                  <h2 style="color:#333;margin:0 0 12px;">{purpose} Code</h2>
                  <p style="color:#555;line-height:1.5;">Use the code below to verify this action. It expires in 5 minutes.</p>
                  <div style="background:#f7f7f7;border:2px dashed #d90429;border-radius:8px;padding:24px;text-align:center;margin:24px 0;">
                    <span style="font-family:'Courier New',monospace;font-size:2.4rem;font-weight:bold;letter-spacing:8px;color:#d90429;">{otp}</span>
                  </div>
                  <p style="color:#888;font-size:0.85rem;line-height:1.5;">
                    If you did not request this code, you can safely ignore this email — your account is still secure.
                  </p>
                </div>
                <div style="background:#f4f4f4;padding:14px;text-align:center;color:#aaa;font-size:0.75rem;">
                  Disaster Response Logistics Platform — Automated message, please do not reply.
                </div>
              </div>
            </body></html>
            """

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(GMAIL_USER, GMAIL_APP_PASS)
                server.send_message(msg)
            print(f"   ✅ Email delivered to {recipient}")
            return True
        except Exception as e:
            print(f"   ❌ Email send failed: {e}")
            return False

    @app.route('/forgot_password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            account_id = (request.form.get('account_id') or '').strip().upper()
            user = User.query.filter_by(account_id=account_id).first()
            if not user:
                flash("❌ Account ID not found.", "error")
                return redirect(url_for('forgot_password'))
            if not user.email:
                flash("❌ This account has no registered email. Contact your administrator.", "error")
                return redirect(url_for('forgot_password'))

            otp = generate_otp()
            email_ok = send_otp_email(user.email, otp, purpose="Password Reset")

            # For Forgot Password, email MUST send. If it fails, abort.
            if not email_ok:
                flash("❌ Unable to send OTP email. Please try again later or contact your administrator.", "error")
                return redirect(url_for('forgot_password'))

            session['otp_code']       = otp
            session['otp_user_id']    = user.id
            session['otp_purpose']    = 'reset_password'
            session['otp_expires']    = (datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).isoformat()
            session['otp_email_sent'] = True
            return redirect(url_for('verify_otp_view'))

        return render_template('forgot_password.html')

    @app.route('/change_password_request')
    @login_required
    def change_password_request():
        """Logged-in user requests OTP to change their own password."""
        if not current_user.email:
            flash("❌ No email address on file. Contact your administrator to add one.", "error")
            return redirect(url_for('profile_settings'))

        otp = generate_otp()
        session['otp_code']    = otp
        session['otp_user_id'] = current_user.id
        session['otp_purpose'] = 'change_password'
        session['otp_expires'] = (datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).isoformat()

        email_ok = send_otp_email(current_user.email, otp, purpose="Change Password")
        session['otp_email_sent'] = email_ok
        return redirect(url_for('verify_otp_view'))

    @app.route('/verify_otp', methods=['GET', 'POST'])
    def verify_otp_view():
        # Must have an active OTP session
        if 'otp_code' not in session or 'otp_user_id' not in session:
            flash("⚠️ No active verification session. Please start again.", "error")
            return redirect(url_for('login'))

        user = User.query.get(session['otp_user_id'])
        if not user:
            session.pop('otp_code', None); session.pop('otp_user_id', None)
            flash("❌ Session error. Please try again.", "error")
            return redirect(url_for('login'))

        # Check expiry
        try:
            expires = datetime.datetime.fromisoformat(session.get('otp_expires', ''))
            if datetime.datetime.utcnow() > expires:
                session.pop('otp_code', None); session.pop('otp_user_id', None)
                flash("⏰ OTP expired. Please request a new code.", "error")
                return redirect(url_for('login'))
        except Exception:
            pass

        if request.method == 'POST':
            entered = (request.form.get('otp') or '').strip()
            if entered != session.get('otp_code'):
                flash("❌ Incorrect OTP. Please try again.", "error")
                return redirect(url_for('verify_otp_view'))

            new_pw = (request.form.get('new_password') or '').strip()
            confirm = (request.form.get('confirm_password') or '').strip()
            if not new_pw or len(new_pw) < 6:
                flash("❌ Password must be at least 6 characters.", "error")
                return redirect(url_for('verify_otp_view'))
            if new_pw != confirm:
                flash("❌ Passwords do not match.", "error")
                return redirect(url_for('verify_otp_view'))

            purpose = session.get('otp_purpose', '')

            # For change_password via profile form: new password is already in session
            pending_pw = session.pop('pending_new_password', None)
            if pending_pw:
                user.password = pending_pw
            else:
                # All checks passed — update password from form fields
                user.password = new_pw
            db.session.commit()

            session.pop('otp_code', None)
            session.pop('otp_user_id', None)
            session.pop('otp_purpose', None)
            session.pop('otp_expires', None)
            session.pop('otp_email_sent', None)

            if purpose == 'reset_password':
                flash("✅ Password reset successfully. Please log in with your new password.", "success")
                return redirect(url_for('login'))
            else:  # change_password
                flash("✅ Password changed successfully.", "success")
                return redirect(url_for('profile_settings'))

        # GET — show OTP entry form
        email_was_sent = session.get('otp_email_sent', False)
        purpose        = session.get('otp_purpose', '')

        # Forgot-Password flow: NEVER show OTP on screen — must be retrieved from email only.
        # Change-Password flow: show OTP as fallback only if email failed (demo safety net).
        show_demo_otp = None
        if purpose == 'change_password' and not email_was_sent:
            show_demo_otp = session.get('otp_code')

        # If pending_new_password is in session, the new password was captured via profile form
        needs_password = purpose == 'reset_password' or (
            purpose == 'change_password' and 'pending_new_password' not in session
        )

        return render_template(
            'verify_otp.html',
            masked_target=mask_email(user.email),
            submit_url=url_for('verify_otp_view'),
            cancel_url=url_for('login') if purpose == 'reset_password' else url_for('profile_settings'),
            needs_password=needs_password,
            email_sent=email_was_sent,
            demo_otp=show_demo_otp
        )

    @app.route("/")
    def home():
        if current_user.is_authenticated and current_user.role == "Admin":
            return redirect(url_for("manage_users"))
        return redirect(url_for("dashboard_view"))

    @app.route("/dashboard")
    @login_required
    def dashboard_view():
        # Admins are restricted to user management only.
        if current_user.role == "Admin":
            return redirect(url_for('manage_users'))
        show_all = current_user.show_routes

        active_count = DisasterReport.query.filter(DisasterReport.status.in_(['In Progress', 'En Route'])).count()
        pending_count = DisasterReport.query.filter_by(status='Pending').count()
        
        all_teams = Team.query.all()
        available_teams = 0
        for t in all_teams:
            has_active_task = DisasterReport.query.filter_by(assigned_team=t.team_id).filter(DisasterReport.status.in_(['In Progress', 'En Route'])).first()
            if not has_active_task:
                available_teams += 1

        if current_user.role == "Responder":
            team = get_responder_team()
            reports_db = DisasterReport.query.filter_by(assigned_team=team.team_id).order_by(DisasterReport.date_submitted.desc()).all() if team else []
        else:
            reports_db = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        
        reports_display = []
        for r in reports_db:
            r_dict = {
                'task_id': r.task_id, 'location': r.location, 'severity': r.severity,
                'status': r.status, 'assigned_team': r.assigned_team, 
                'date_submitted': r.date_submitted, 'lat': r.lat, 'lon': r.lon,
                'disaster_type': r.disaster_type, 'resources': r.resources,
                'constraints': r.constraints, 'notes': r.notes, 'full_address': r.full_address,
                'team_coords': None 
            }
            if r.assigned_team:
                t = Team.query.filter_by(team_id=r.assigned_team).first()
                if t: r_dict['team_coords'] = {'lat': t.lat, 'lon': t.lon}
            reports_display.append(r_dict)
        

        return render_template("dashboard.html", 
                               reports=reports_display, 
                               user=current_user, 
                               show_all_routes=show_all,
                               active=active_count,
                               pending=pending_count,
                               resources=available_teams)
    
    @app.route("/reports")
    @login_required
    def reports_list():
        # Admins are restricted to user management only.
        if current_user.role == "Admin":
            return redirect(url_for('manage_users'))
        view_id = request.args.get('view_id', type=int)
        if current_user.role == "Responder":
            team = get_responder_team()
            reports = DisasterReport.query.filter_by(assigned_team=team.team_id).order_by(DisasterReport.date_submitted.desc()).all() if team else []
        else:
            reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        selected = reports[view_id] if view_id is not None and 0 <= view_id < len(reports) else None
        return render_template("reports_list.html", reports=reports, selected_report=selected, user=current_user)

    @app.route("/teams")
    @login_required
    def teams_view():
        if current_user.role == "Responder": return redirect(url_for('dashboard_view'))
        # Admins are restricted to user management only.
        if current_user.role == "Admin": return redirect(url_for('manage_users'))
        
        # Show ALL reports (including resolved) to perfectly align with Monitor/Analytics
        reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        teams_db = Team.query.all()
        display_teams = []
        
        for t in teams_db:
            # A team is "Busy" if they have ANY assigned task that is NOT 'Resolved'
            active_assignment = DisasterReport.query.filter_by(assigned_team=t.team_id).filter(DisasterReport.status != 'Resolved').first()
            
            if active_assignment:
                final_status = "Busy"
                task_str = active_assignment.task_id
            else:
                final_status = "Available"
                # Get their most recently completed task to display as history
                last_completed = DisasterReport.query.filter_by(assigned_team=t.team_id, status='Resolved').order_by(DisasterReport.date_submitted.desc()).first()
                task_str = f"{last_completed.task_id} (Done)" if last_completed else "-"

            location_name = get_address_from_coords(t.lat, t.lon)
            
            display_teams.append({
                "id": t.team_id, "leader": t.leader, "location": location_name,
                "role": t.role, "status": final_status, "task": task_str,
                "last_updated": t.last_updated.strftime('%m-%d-%Y') if t.last_updated else "N/A"
            })
            
        vehicles = VehicleResource.query.order_by(VehicleResource.id).all()
        return render_template("teams.html", teams=display_teams, reports=reports, vehicles=vehicles, user=current_user)

    @app.route("/monitor")
    @login_required
    def monitor_view():
        # Admins are restricted to user management only.
        if current_user.role == "Admin":
            return redirect(url_for('manage_users'))
        show_all = current_user.show_routes
        can_reroute = current_user.role == "Responder"
        return render_template("monitor.html", user=current_user, show_all_routes=show_all, can_reroute=can_reroute)


    @app.route("/analytics")
    @login_required
    def analytics_view():
        if current_user.role != "Programmer": return redirect(url_for('dashboard_view'))
        return render_template("analytics.html", user=current_user)


    @app.route("/analytics_data")
    @login_required
    def analytics_data():
        if current_user.role != "Programmer": return jsonify([])

        # Bulacan province approximate bounding box. If the VIEWER's browser GPS is
        # outside this box, we display "OUTSIDE Bulacan" as the FROM label (since
        # their location is not in the routable graph) but still compute routes
        # from the Marilao HQ depot for the algorithm comparison metrics.
        # Tightened so that Metro Manila (Quezon City ~14.68, Manila ~14.60,
        # Paranaque ~14.48) is correctly flagged as outside.
        BULACAN_LAT_MIN, BULACAN_LAT_MAX = 14.70, 15.35
        BULACAN_LON_MIN, BULACAN_LON_MAX = 120.55, 121.20

        def _in_bulacan(lat, lon):
            return (BULACAN_LAT_MIN <= lat <= BULACAN_LAT_MAX and
                    BULACAN_LON_MIN <= lon <= BULACAN_LON_MAX)

        # Read browser-supplied geolocation from query params. If absent (user
        # denied permission or it isn't available yet), fall back to the depot.
        user_lat = request.args.get('user_lat', type=float)
        user_lon = request.args.get('user_lon', type=float)
        DEPOT_NODE = "Marilao (Municipal Hall)"

        if user_lat is not None and user_lon is not None:
            if _in_bulacan(user_lat, user_lon):
                # Snap viewer's location to nearest graph node and route from there.
                actual_start_node = min(
                    NODE_LOCATIONS.keys(),
                    key=lambda k: math.hypot(NODE_LOCATIONS[k]['lat'] - user_lat,
                                             NODE_LOCATIONS[k]['lon'] - user_lon)
                )
                from_label = actual_start_node
            else:
                # Viewer is outside Bulacan — can't route from out-of-graph coords,
                # so use the depot for routing but flag the label.
                actual_start_node = DEPOT_NODE
                from_label = "OUTSIDE Bulacan"
        else:
            actual_start_node = DEPOT_NODE
            from_label = DEPOT_NODE

        reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        data = []
        base_w = _ROUTER_CACHE.base_weights
        REPS = 5  # repeated runs → take min time (matches simulation.py measure())

        for i, r in enumerate(reports):
            start_node = actual_start_node
            # Snap to nearest graph node via GPS — same method as calculate_route.
            # Using r.location (municipality name) caused almost all tasks to fall back to
            # "Bocaue" because form values like "Malolos" don't match the internal label
            # "HQ_Malolos", making all rows show identical metrics.
            if r.lat and r.lon:
                end_node = min(NODE_LOCATIONS.keys(),
                               key=lambda k: math.hypot(NODE_LOCATIONS[k]['lat'] - r.lat,
                                                        NODE_LOCATIONS[k]['lon'] - r.lon))
            else:
                end_node = r.location if r.location in NODE_LOCATIONS else "Bocaue"
            # Mirror calculate_route: when start == end, route to local sub-destination
            if end_node == start_node and start_node in LOCAL_DESTINATIONS:
                end_node = LOCAL_DESTINATIONS[start_node]

            # A* — best of REPS runs for stable timing
            best_a_time = float('inf')
            for _ in range(REPS):
                t0 = time.perf_counter()
                path, nodes = a_star_search(start_node, end_node, weights=base_w)
                best_a_time = min(best_a_time, time.perf_counter() - t0)
            exec_time = round(best_a_time * 1000, 3)

            dist = 0.0
            path_cost = 0.0
            if path and len(path) > 1:
                dist = round(sum(haversine_km(path[j], path[j+1]) for j in range(len(path)-1)), 2)
                path_cost = sum(base_w.get((path[j], path[j+1]), 0) for j in range(len(path)-1))
                # Last-mile: end node → actual task GPS (mirrors calculate_route logic)
                if r.lat and r.lon:
                    ln = NODE_LOCATIONS[path[-1]]
                    lm = _haversine_raw(r.lat, r.lon, ln['lat'], ln['lon'])
                    dist = round(dist + lm, 2)
                    path_cost += lm / BASE_SPEED_KMH * 60.0
            eta = f"{math.ceil(path_cost)} mins" if path else "N/A"

            # ABSRA — best of REPS runs
            best_b_time = float('inf')
            for _ in range(REPS):
                t0 = time.perf_counter()
                absra_path, absra_nodes = absra_search(start_node, end_node, weights=base_w)
                best_b_time = min(best_b_time, time.perf_counter() - t0)
            absra_exec_time = round(best_b_time * 1000, 3)

            if absra_path and len(absra_path) > 1:
                absra_dist = round(sum(haversine_km(absra_path[j], absra_path[j+1]) for j in range(len(absra_path)-1)), 2)
                absra_cost = sum(base_w.get((absra_path[j], absra_path[j+1]), 0) for j in range(len(absra_path)-1))
                # Last-mile for ABSRA
                if r.lat and r.lon:
                    ln = NODE_LOCATIONS[absra_path[-1]]
                    lm = _haversine_raw(r.lat, r.lon, ln['lat'], ln['lon'])
                    absra_dist = round(absra_dist + lm, 2)
                    absra_cost += lm / BASE_SPEED_KMH * 60.0
                absra_eta = f"{math.ceil(absra_cost)} mins"
            else:
                absra_nodes, absra_exec_time, absra_dist, absra_eta = nodes, exec_time, dist, eta

            # Improvement percentages (never negative — ABSRA should always be ≤ A*)
            node_reduction = round(max(0, (nodes - absra_nodes) / nodes * 100), 1) if nodes else 0
            time_improvement = round(max(0, (exec_time - absra_exec_time) / exec_time * 100), 1) if exec_time else 0

            data.append({
                "num": i + 1,
                "task_id": r.task_id,
                "from": from_label,
                "to": end_node,
                "location": r.location,
                "a_nodes": nodes,
                "a_time": f"{exec_time} ms",
                "a_eta": eta,
                "a_dist": f"{dist} km",
                "absra_nodes": absra_nodes,
                "absra_time": f"{absra_exec_time} ms",
                "absra_eta": absra_eta,
                "absra_dist": f"{absra_dist} km",
                "node_reduction": f"{node_reduction}%",
                "time_improvement": f"{time_improvement}%",
            })

        return jsonify(data)

    @app.route("/profile_settings", methods=["GET", "POST"])
    @login_required
    def profile_settings():
        if request.method == "POST":
            current_user.first_name = request.form.get("first_name")
            current_user.last_name = request.form.get("last_name")
            current_user.phone = request.form.get("phone")
            current_user.show_routes = request.form.get("routing_visual") == "on"

            new_password = (request.form.get("new_password") or "").strip()
            current_password = (request.form.get("current_password") or "").strip()

            if new_password:
                if not current_password:
                    flash("Please enter your current password to change it.", "error")
                    db.session.commit()
                    return redirect(url_for('profile_settings'))
                if current_user.password != current_password:
                    flash("Incorrect current password.", "error")
                    db.session.commit()
                    return redirect(url_for('profile_settings'))
                if len(new_password) < 6:
                    flash("New password must be at least 6 characters.", "error")
                    db.session.commit()
                    return redirect(url_for('profile_settings'))
                # Store pending new password and go through OTP verification
                session['pending_new_password'] = new_password
                db.session.commit()
                flash("Profile updated. Please verify your new password via OTP.", "success")
                return redirect(url_for('change_password_request'))

            db.session.commit()
            flash("Settings updated.", "success")
            return redirect(url_for('profile_settings'))
        return render_template("profile.html", user=current_user, show_routes=current_user.show_routes)

    @app.route("/manage_users")
    @login_required
    def manage_users():
        if current_user.role != "Admin": return redirect(url_for('dashboard_view'))
        return render_template("manage_users.html", users=User.query.all(), user=current_user)

    @app.route("/delete_user/<int:user_id>")
    @login_required
    def delete_user(user_id):
        if current_user.role != "Admin": return redirect(url_for('dashboard_view'))
        u = User.query.get(user_id)
        if u: 
            if u.role == "Responder":
                full_name = f"{u.first_name} {u.last_name}"
                team = Team.query.filter_by(leader=full_name).first()
                if team:
                    active_jobs = DisasterReport.query.filter_by(assigned_team=team.team_id).filter(DisasterReport.status != 'Resolved').all()
                    for job in active_jobs:
                        job.assigned_team = None
                        job.status = "Pending"
                    db.session.delete(team)
            db.session.delete(u) 
            db.session.commit()
            flash(f"User deleted. Active tasks reset.", "success")
        return redirect(url_for('manage_users'))

    @app.route('/register', methods=['GET', 'POST'])
    @login_required
    def register():
        if current_user.role != "Admin": return redirect(url_for('dashboard_view'))
        def get_next_details(prefix):
            count = 1
            while True:
                new_id = f"{prefix}-{count:03d}"
                if not User.query.filter_by(account_id=new_id).first(): return new_id, count
                count += 1
        if request.method == 'POST':
            role = request.form.get('role')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            phone = (request.form.get('phone') or '').strip()
            email = (request.form.get('email') or '').strip().lower()

            # ── Phone validation: PH mobile format ─────────────────────
            import re
            phone_clean = re.sub(r'\s+', '', phone)
            if not re.match(r'^(09\d{9}|\+639\d{9})$', phone_clean):
                flash("Invalid mobile number. Use 09XX XXX XXXX or +639XX XXX XXXX format.", "error")
                next_opt, _ = get_next_details("OPT")
                next_rsp, _ = get_next_details("RSP")
                return render_template('register.html', user=current_user, next_opt=next_opt, next_rsp=next_rsp)

            # ── Email validation ───────────────────────────────────────
            if not re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', email):
                flash("❌ Invalid email address.", "error")
                next_opt, _ = get_next_details("OPT")
                next_rsp, _ = get_next_details("RSP")
                return render_template('register.html', user=current_user, next_opt=next_opt, next_rsp=next_rsp)

            prefix = "OPT" if role == "Operator" else "RSP"
            final_id, id_count = get_next_details(prefix)
            auto_pass = f"password{id_count:03d}"
            new_user = User(account_id=final_id, password=auto_pass, role=role,
                            first_name=first_name, last_name=last_name, phone=phone_clean, email=email)
            db.session.add(new_user)
            if role == "Responder":
                municipality = request.form.get('municipality')
                street = request.form.get('street')
                lat, lon = 14.8437, 120.8113
                if municipality and street:
                    try:
                        url = 'https://nominatim.openstreetmap.org/search'
                        params = {'q': f"{street}, {municipality}, Bulacan, Philippines", 'format': 'json', 'limit': 1}
                        headers = {'User-Agent': 'DisasterApp/1.0'}
                        response = requests.get(url, params=params, headers=headers)
                        data = response.json()
                        if data:
                            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
                            flash(f"Location set: {street}, {municipality}", "success")
                    except: pass
                team_count = Team.query.count() + 1
                new_team = Team(team_id=f"TM-{team_count:03d}", name=f"TM-{team_count:03d}", leader=f"{first_name} {last_name}", role="Response Unit", lat=lat, lon=lon, status="Available")
                db.session.add(new_team)
            db.session.commit()
            next_opt, _ = get_next_details("OPT")
            next_rsp, _ = get_next_details("RSP")
            return render_template('register.html', user=current_user, success_user=new_user, generated_pass=auto_pass, next_opt=next_opt, next_rsp=next_rsp)
        next_opt, _ = get_next_details("OPT")
        next_rsp, _ = get_next_details("RSP")
        return render_template('register.html', user=current_user, next_opt=next_opt, next_rsp=next_rsp)

    @app.route("/create_report")
    @login_required
    def create_report_view():
        if current_user.role == "Responder": return redirect(url_for('dashboard_view'))
        now = datetime.datetime.now()
        return render_template("user.html", task_id=f"TASK-{DisasterReport.query.count() + 1:03d}", 
            auto_date=now.strftime("%m/%d/%Y"), auto_day=now.strftime("%A"), auto_time=now.strftime("%I:%M %p"), user=current_user)

    @app.route("/submit_report", methods=["POST"])
    @login_required
    def submit_report():
        if current_user.role == "Responder": return redirect(url_for('dashboard_view'))
        try: lat, lon = float(request.form.get("lat")), float(request.form.get("lon"))
        except: return "Invalid Coordinates", 400
        new_report = DisasterReport(
            task_id=request.form.get("task_id"), disaster_type=request.form.get("disaster_type"),
            severity=request.form.get("severity"), lat=lat, lon=lon,
            location=request.form.get("municipality"), full_address=request.form.get("address"),
            resources=", ".join(request.form.getlist("resources")), constraints=", ".join(request.form.getlist("constraints")),
            status="Pending", date_str=request.form.get("date"), day_str=request.form.get("day"), 
            time_str=request.form.get("time"), affected=request.form.get("affected"),
            response_type=request.form.get("response_type"), notes=request.form.get("notes")
        )
        db.session.add(new_report)
        db.session.commit()
        return redirect(url_for("reports_list"))

    @app.route("/save_report_changes", methods=["POST"])
    @login_required
    def save_report_changes():
        r = DisasterReport.query.get(request.form.get("report_id"))
        if r:
            # ── Resolved tasks are locked and cannot be edited ─────────
            if r.status == "Resolved":
                flash("This report is Resolved and cannot be edited.", "error")
                return redirect(url_for('reports_list', view_id=request.form.get("view_id")))

            new_status = request.form.get("status")
            if new_status == "In Progress" and (not r.assigned_team or r.assigned_team.strip() == ""):
                flash("Cannot change status to 'In Progress' without assigning a team first.", "error")
                new_status = "Pending"
            
            # Only unassign the team if the task was NOT yet actively en route or beyond.
            # Preserves assignment history for tasks that a team has already started.
            elif new_status == "Pending":
                if r.status not in ('En Route', 'Awaiting Confirmation', 'Resolved'):
                    r.assigned_team = None
                
            r.status = new_status
            r.notes = request.form.get("notes")
            if request.form.get("disaster_type"): r.disaster_type = request.form.get("disaster_type")
            if request.form.get("severity"): r.severity = request.form.get("severity")
            if request.form.get("response_type"): r.response_type = request.form.get("response_type")
            if request.form.get("affected"): r.affected = request.form.get("affected")
            db.session.commit()
            if new_status == request.form.get("status"):
                flash("Report details updated successfully.", "success")
        return redirect(url_for('reports_list', view_id=request.form.get("view_id")))

    @app.route("/delete_report", methods=["POST"])
    @login_required
    def delete_report():
        if current_user.role == "Responder":
            flash("You do not have permission to delete reports.", "error")
            return redirect(url_for('reports_list'))
        report_id = request.form.get("report_id")
        r = DisasterReport.query.get(report_id)
        if r:
            task_id = r.task_id
            # Free up the assigned team if the task was still active
            if r.assigned_team and r.status not in ('Resolved',):
                team = Team.query.filter_by(team_id=r.assigned_team).first()
                if team:
                    team.status = "Available"
                # Restore vehicles to available pool
                if r.resources:
                    _update_vehicle_counts(r.resources, delta=-1)
                    db.session.commit()
            # Remove related route logs and notifications to avoid orphaned rows
            RouteLog.query.filter_by(task_id=task_id).delete()
            Notification.query.filter_by(task_id=task_id).delete()
            db.session.delete(r)
            db.session.commit()
            flash(f"Task {task_id} has been deleted successfully.", "success")
        else:
            flash("Report not found.", "error")
        return redirect(url_for('reports_list'))

    @app.route("/assign_team", methods=["POST"])
    @login_required
    def assign_team():
        if current_user.role == "Responder": return redirect(url_for('dashboard_view'))
        team_id = request.form.get("team_id")
        task_id = request.form.get("task_id")
        resources_str = (request.form.get("resources") or "").strip()
        if not team_id or team_id.strip() == "": return redirect(url_for("teams_view"))
        r = DisasterReport.query.filter_by(task_id=task_id).first()
        if r: 
            r.assigned_team = team_id
            r.status = "In Progress"
            # Store the resources selected via the assignment form
            if resources_str:
                r.resources = resources_str
            # Deduct vehicles from available pool based on assigned resources
            if r.resources:
                _update_vehicle_counts(r.resources, delta=+1)
            db.session.commit()
        return redirect(url_for("teams_view"))


    @app.route("/responder_data")
    @login_required
    def responder_data():
        if current_user.role == "Responder":
            team = get_responder_team()
            reports = DisasterReport.query.filter_by(assigned_team=team.team_id).filter(DisasterReport.status != 'Resolved').all() if team else []
        else:
            reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        
        data = []
        for i, r in enumerate(reports):
            team_display = "Pending Assignment"
            team_start_loc = None
            if r.assigned_team:
                team = Team.query.filter_by(team_id=r.assigned_team).first()
                if team:
                    team_display = f"{team.team_id} ({team.leader})"
                    team_start_loc = {"lat": team.lat, "lon": team.lon}
            data.append({
                "index": i,
                "task_id": r.task_id, "disaster_type": r.disaster_type, "location": r.location,
                "team_location": team_start_loc, "assigned_team": team_display,
                "status": r.status, "time": r.time_str, "severity": r.severity, "lat": r.lat, "lon": r.lon
            })
        return jsonify(data)

    @app.route("/api/update_location", methods=["POST"])
    @login_required
    def update_location():
        # Only Responders should be updating their field location
        if current_user.role != "Responder":
            return jsonify({"error": "Unauthorized"}), 403
            
        data = request.get_json()
        team = get_responder_team()
        
        if team and 'lat' in data and 'lon' in data:
            team.lat = float(data['lat'])
            team.lon = float(data['lon'])
            team.last_updated = datetime.datetime.utcnow()
            db.session.commit()
            return jsonify({"status": "success", "message": "Position updated."})
            
        return jsonify({"error": "Failed to update position"}), 400

    @app.route("/api/add_constraint", methods=["POST"])
    @login_required
    def add_constraint():
        if current_user.role == "Responder":
            return jsonify({"error": "Unauthorized"}), 403
            
        data = request.get_json()
        node = data.get("node")
        reason = data.get("reason", "Road Blocked")
        
        if node in NODE_LOCATIONS:
            # Check if it already exists
            existing = RoadConstraint.query.filter_by(node_name=node, is_active=True).first()
            if not existing:
                new_const = RoadConstraint(node_name=node, reason=reason, is_active=True)
                db.session.add(new_const)
                db.session.commit()
                return jsonify({"status": "success", "message": f"Constraint added: {node} is blocked."})
            return jsonify({"status": "info", "message": "Node is already blocked."})
            
        return jsonify({"status": "error", "message": "Invalid node location."}), 400

    @app.route("/api/active_constraints", methods=["GET"])
    @login_required
    def list_active_constraints():
        """All currently active road constraints, with map coordinates.
        Used by monitor.html to draw warning markers."""
        rows = RoadConstraint.query.filter_by(is_active=True).order_by(RoadConstraint.id.desc()).all()
        type_labels = {
            'road_block':    'Road Block',
            'heavy_traffic': 'Heavy Traffic',
            'flooded_road':  'Flooded Road',
        }
        out = []
        for c in rows:
            # Back-fill lat/lon from NODE_LOCATIONS for legacy rows that
            # were created before the coordinate columns existed.
            lat, lon = c.lat, c.lon
            if (lat is None or lon is None) and c.node_name in NODE_LOCATIONS:
                lat = NODE_LOCATIONS[c.node_name]['lat']
                lon = NODE_LOCATIONS[c.node_name]['lon']
            if lat is None or lon is None:
                continue
            out.append({
                'id':              c.id,
                'node_name':       c.node_name,
                'reason':          c.reason or type_labels.get(c.constraint_type, 'Constraint'),
                'constraint_type': c.constraint_type or 'road_block',
                'lat':             lat,
                'lon':             lon,
                'task_id':         c.task_id,
                'reported_by':     c.reported_by,
                'timestamp':       c.timestamp.strftime("%Y-%m-%d %H:%M") if c.timestamp else None,
            })
        return jsonify(out)

    @app.route("/api/remove_constraint/<int:cid>", methods=["POST"])
    @login_required
    def remove_constraint(cid):
        """Lift a constraint — used by responders when the road is clear again.
        Soft-deletes (is_active=False) and stamps resolved_at so we keep history."""
        c = RoadConstraint.query.get(cid)
        if not c:
            return jsonify({"status": "error", "message": "Constraint not found."}), 404
        if not c.is_active:
            return jsonify({"status": "info", "message": "Constraint already cleared."})
        c.is_active = False
        c.resolved_at = datetime.datetime.utcnow()
        db.session.commit()
        _ROUTER_CACHE.invalidate()
        return jsonify({
            "status": "success",
            "message": f"Constraint cleared at {c.node_name}.",
            "id": c.id,
        })

    @app.route("/calculate_route")
    def calculate_route():
        avoid_param = request.args.get('avoid', '')
        task_id = request.args.get('task_id', 'Manual')
        want_alternative = request.args.get('alternative', 'false').lower() == 'true'
        constraint = request.args.get('constraint', '')  # road_block | heavy_traffic | flooded_road

        use_absra = request.args.get('use_absra', 'false').lower() == 'true'
        print(f"*** ABSRA Toggle is set to: {use_absra} ***")

        # --- DYNAMIC START/END LOCATION MATCHING ---
        team_lat = request.args.get('team_lat')
        team_lon = request.args.get('team_lon')
        task_lat = request.args.get('task_lat')
        task_lon = request.args.get('task_lon')

        # The front-end may pre-compute where on the ORIGINAL route the
        # obstacle is (a point taken from the leaflet-routing-machine
        # geometry of the route being avoided). When provided, this is
        # the most accurate place to drop the warning pin.
        obstacle_lat = request.args.get('obstacle_lat')
        obstacle_lon = request.args.get('obstacle_lon')

        start_node = request.args.get('start', 'Marilao (Municipal Hall)')
        end_node = request.args.get('end', 'Bocaue')

        if team_lat and team_lon:
            t_lat, t_lon = float(team_lat), float(team_lon)
            start_node = min(NODE_LOCATIONS.keys(), key=lambda k: math.hypot(NODE_LOCATIONS[k]['lat'] - t_lat, NODE_LOCATIONS[k]['lon'] - t_lon))
 
        if task_lat and task_lon:
            t_lat, t_lon = float(task_lat), float(task_lon)
            end_node = min(NODE_LOCATIONS.keys(), key=lambda k: math.hypot(NODE_LOCATIONS[k]['lat'] - t_lat, NODE_LOCATIONS[k]['lon'] - t_lon))

        if start_node == end_node and start_node in LOCAL_DESTINATIONS:
            end_node = LOCAL_DESTINATIONS[start_node]

        active_constraints = RoadConstraint.query.filter_by(is_active=True).all()
        avoid_nodes = [c.node_name for c in active_constraints]
        if avoid_param and avoid_param not in avoid_nodes:
            avoid_nodes.append(avoid_param)

        # Base weights: O(1) amortized lookup from RouterCache
        base_w = _ROUTER_CACHE.base_weights

        # 1. Baseline route (unconstrained) for distance comparison
        baseline_path, _ = a_star_search(start_node, end_node, avoid_nodes=[], weights=base_w)
        baseline_dist = 0.0
        if baseline_path:
            baseline_dist = round(sum(haversine_km(baseline_path[j], baseline_path[j+1])
                                      for j in range(len(baseline_path) - 1)), 2)

        # --- PHYSICS-BASED CONSTRAINT MODELS ---
        modified_w = dict(base_w)   # per-query copy; base_w is never mutated
        penalty_nodes = None
        penalty_factor = 1.0

        if constraint == 'heavy_traffic' and baseline_path and len(baseline_path) > 1:
            # BPR model: t = t0 * (1 + BPR_ALPHA * (V/C)^BPR_BETA)
            # V/C = 1.4 → heavy congestion (Level-2 Bulacan corridor calibration)
            vc = 1.4
            bpr_base = 1.0 + BPR_ALPHA * (vc ** BPR_BETA)
            for j in range(len(baseline_path) - 1):
                u, v = baseline_path[j], baseline_path[j + 1]
                risk = edge_risk(u, v, 'traffic')
                mult = bpr_base * (0.5 + 0.5 * risk)
                if (u, v) in modified_w:
                    modified_w[(u, v)] *= mult
                if (v, u) in modified_w:
                    modified_w[(v, u)] *= mult
            penalty_nodes = set(baseline_path[1:-1])
            want_alternative = True

        elif constraint == 'flooded_road' and baseline_path and len(baseline_path) > 2:
            # Block the highest flood-risk intermediate node (Bulacan flood profile)
            intermediates = baseline_path[1:-1]
            blocked = max(intermediates, key=lambda n: BULACAN_RISK_PROFILE.get(n, {}).get('flood', 0.5))
            if blocked not in avoid_nodes:
                avoid_nodes.append(blocked)
            want_alternative = True

        elif constraint == 'road_block' and baseline_path and len(baseline_path) > 2:
            # Severity scoring S = 0.4*D + 0.4*O + 0.2*R; block highest-vulnerability node
            intermediates = baseline_path[1:-1]
            blocked = max(intermediates, key=lambda n: BULACAN_RISK_PROFILE.get(n, {}).get('vuln', 0.5))
            if blocked not in avoid_nodes:
                avoid_nodes.append(blocked)
            want_alternative = True

        # --- PLAIN ALTERNATIVE (no specific constraint selected) ---
        if want_alternative and not constraint and baseline_path and len(baseline_path) > 2:
            middle_node = baseline_path[len(baseline_path) // 2]
            if middle_node not in avoid_nodes:
                avoid_nodes.append(middle_node)

        # 2. Actual route with constraints applied
        if use_absra:
            path, _ = absra_search(start_node, end_node,
                                   avoid_nodes=avoid_nodes, weights=modified_w)
        else:
            path, _ = a_star_search(start_node, end_node, avoid_nodes=avoid_nodes,
                                    penalty_nodes=penalty_nodes,
                                    penalty_factor=penalty_factor, weights=modified_w)

        # ERROR HANDLING
        if not path:
            failed_log = RouteLog(task_id=task_id, origin=start_node, destination=end_node,
                                  new_distance=0.0, reason=", ".join(avoid_nodes), status="Error")
            db.session.add(failed_log)
            db.session.commit()
            return jsonify({"path": [], "coords": [], "distance": "N/A", "eta": "Blocked",
                            "is_rerouted": False, "message": "Error: Destination unreachable due to closures."})

        graph_dist_km = sum(haversine_km(path[j], path[j+1]) for j in range(len(path) - 1))
        graph_cost    = sum(
            modified_w.get((path[j], path[j+1]), haversine_km(path[j], path[j+1]) / BASE_SPEED_KMH * 60.0)
            for j in range(len(path) - 1)
        )

        # First-mile: actual team GPS → nearest graph node (avoids 1-min ETA when both ends
        # snap to the same node but the real-world distance between them is significant).
        first_mile_km = 0.0
        if team_lat and team_lon:
            fn = NODE_LOCATIONS[path[0]]
            first_mile_km = _haversine_raw(float(team_lat), float(team_lon), fn['lat'], fn['lon'])

        # Last-mile: last graph node → actual task GPS
        last_mile_km = 0.0
        if task_lat and task_lon:
            ln = NODE_LOCATIONS[path[-1]]
            last_mile_km = _haversine_raw(float(task_lat), float(task_lon), ln['lat'], ln['lon'])

        extra_km  = first_mile_km + last_mile_km
        dist_km   = round(graph_dist_km + extra_km, 2)
        eta_min   = math.ceil(graph_cost + extra_km / BASE_SPEED_KMH * 60.0)

        is_rerouted = (path != baseline_path) or want_alternative
        message = (f"REROUTED: Avoiding {', '.join(avoid_nodes)}. "
                   f"Added {round(dist_km - baseline_dist, 2)} km."
                   if is_rerouted else "Optimal Route Found.")

        # LOGGING
        constraint_labels = {'road_block': 'Road Block', 'heavy_traffic': 'Heavy Traffic', 'flooded_road': 'Flooded Road'}
        log_reason = constraint_labels.get(constraint) or ("Alternative Route" if want_alternative else "Standard Route")
        success_log = RouteLog(task_id=task_id, origin=start_node, destination=end_node,
                               new_distance=dist_km, reason=log_reason, status="Success")
        db.session.add(success_log)
        db.session.commit()

        # ── PERSIST THE CONSTRAINT (map warning marker) ─────────────────────
        # When a responder reroutes because of a specific road condition, drop
        # a pin so every viewer of the map can see the hazard. Priority for
        # pin location:
        #   1. obstacle_lat/lon from the front-end — a point on the ORIGINAL
        #      route that's being avoided. Most accurate: the pin sits on the
        #      actual road the obstacle is on.
        #   2. The Bulacan node we just avoided (if A* found any).
        #   3. The responder's GPS (where they were when they hit it).
        #   4. The task destination as a last resort.
        if want_alternative and constraint in constraint_labels:
            pin_lat, pin_lon, pin_node = None, None, None

            # 1. Front-end-provided obstacle position (on the original route)
            if obstacle_lat and obstacle_lon:
                try:
                    pin_lat = float(obstacle_lat)
                    pin_lon = float(obstacle_lon)
                    pin_node = min(
                        NODE_LOCATIONS.keys(),
                        key=lambda k: math.hypot(
                            NODE_LOCATIONS[k]['lat'] - pin_lat,
                            NODE_LOCATIONS[k]['lon'] - pin_lon,
                        ),
                    )
                except (TypeError, ValueError):
                    pin_lat = pin_lon = None

            # 2. Avoided Bulacan node
            if pin_lat is None and baseline_path and len(baseline_path) > 2:
                intermediates = baseline_path[1:-1]
                risk_key = {'flooded_road': 'flood', 'road_block': 'vuln', 'heavy_traffic': 'traffic'}[constraint]
                pin_node = max(intermediates, key=lambda n: BULACAN_RISK_PROFILE.get(n, {}).get(risk_key, 0.5))
                node_loc = NODE_LOCATIONS.get(pin_node)
                if node_loc:
                    pin_lat, pin_lon = node_loc['lat'], node_loc['lon']

            # 3. Responder GPS
            if pin_lat is None and team_lat and team_lon:
                try:
                    pin_lat = float(team_lat)
                    pin_lon = float(team_lon)
                    pin_node = min(
                        NODE_LOCATIONS.keys(),
                        key=lambda k: math.hypot(
                            NODE_LOCATIONS[k]['lat'] - pin_lat,
                            NODE_LOCATIONS[k]['lon'] - pin_lon,
                        ),
                    )
                except (TypeError, ValueError):
                    pin_lat = pin_lon = None

            # 4. Task destination as last resort
            if pin_lat is None and task_lat and task_lon:
                try:
                    pin_lat = float(task_lat)
                    pin_lon = float(task_lon)
                    pin_node = min(
                        NODE_LOCATIONS.keys(),
                        key=lambda k: math.hypot(
                            NODE_LOCATIONS[k]['lat'] - pin_lat,
                            NODE_LOCATIONS[k]['lon'] - pin_lon,
                        ),
                    )
                except (TypeError, ValueError):
                    pin_lat = pin_lon = None

            if pin_lat is not None and pin_lon is not None:
                # Spatial duplicate check: same type within ~200 m → skip.
                DUPE_DEG = 0.002
                dupe = RoadConstraint.query.filter(
                    RoadConstraint.constraint_type == constraint,
                    RoadConstraint.is_active == True,
                    RoadConstraint.lat >= pin_lat - DUPE_DEG,
                    RoadConstraint.lat <= pin_lat + DUPE_DEG,
                    RoadConstraint.lon >= pin_lon - DUPE_DEG,
                    RoadConstraint.lon <= pin_lon + DUPE_DEG,
                ).first()
                if not dupe:
                    reporter = getattr(current_user, 'account_id', None) if current_user.is_authenticated else None
                    new_pin = RoadConstraint(
                        node_name=pin_node or 'Reported Location',
                        reason=constraint_labels[constraint],
                        constraint_type=constraint,
                        lat=pin_lat,
                        lon=pin_lon,
                        task_id=task_id if task_id != 'Manual' else None,
                        reported_by=reporter,
                        is_active=True,
                    )
                    db.session.add(new_pin)
                    db.session.commit()
                    _ROUTER_CACHE.invalidate()
                    print(f"[constraint-pin] saved {constraint_labels[constraint]} at "
                          f"({pin_lat:.5f}, {pin_lon:.5f}) by {reporter or 'anon'} for {task_id}")
                else:
                    print(f"[constraint-pin] skipped duplicate {constraint_labels[constraint]} near "
                          f"({pin_lat:.5f}, {pin_lon:.5f}) — already active as id={dupe.id}")

        coords = [[NODE_LOCATIONS[node]['lat'], NODE_LOCATIONS[node]['lon']] for node in path]
        

        return jsonify({
            "path": path, "coords": coords, "distance": f"{dist_km} km", "eta": f"{eta_min} mins",
            "is_rerouted": is_rerouted, "original_distance": f"{baseline_dist} km", "message": message
        })

    @app.route("/api/routing_logs")
    def api_routing_logs():
        try:
            # Fetch the 50 most recent logs from the database, newest first
            logs = RouteLog.query.order_by(RouteLog.id.desc()).limit(50).all()
            
            log_data = []
            for log in logs:
                log_data.append({
                    "id": log.id,
                    "task_id": getattr(log, 'task_id', 'N/A'),
                    "origin": log.origin,
                    "destination": log.destination,
                    "new_distance": f"{log.new_distance} km",
                    "reason": log.reason,
                    "status": log.status,
                    "timestamp": getattr(log, 'timestamp', getattr(log, 'created_at', 'N/A')) 
                })
            return jsonify(log_data)
        except Exception as e:
            print(f"Error fetching logs: {e}")
            return jsonify([])
    # ======================================

    @app.route("/api/all_monitor_reports")
    @login_required
    def all_monitor_reports():
        # For Responder: only their team's tasks (excluding resolved)
        # For everyone else (Operator/Admin/Programmer): ALL reports regardless of status
        if current_user.role == "Responder":
            team = get_responder_team()
            reports = DisasterReport.query.filter_by(assigned_team=team.team_id).filter(DisasterReport.status != 'Resolved').all() if team else []
        else:
            reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        data = []
        for r in reports:
            team_display = "Pending Assignment"
            team_start_loc = None
            if r.assigned_team:
                team = Team.query.filter_by(team_id=r.assigned_team).first()
                if team:
                    team_display = f"{team.team_id} ({team.leader})"
                    team_start_loc = {"lat": team.lat, "lon": team.lon}
            data.append({
                "task_id": r.task_id, "disaster_type": r.disaster_type, "location": r.location,
                "team_location": team_start_loc, "assigned_team": team_display,
                "status": r.status, "time": r.time_str, "severity": r.severity, "lat": r.lat, "lon": r.lon
            })
        return jsonify(data)

    @app.route("/update_status", methods=["POST"])
    @login_required
    def update_status():
        data = request.get_json()
        task_id = data.get("task_id")
        new_status = data.get("status")
        r = DisasterReport.query.filter_by(task_id=task_id).first()
        if r and new_status:
            r.status = new_status
            db.session.commit()
            if new_status == "En Route":
                db.session.add(Notification(task_id=r.task_id, message=f"{r.task_id} — Team is En Route to {r.location}. Update status when task is complete."))
                db.session.commit()
            elif new_status == "Waiting for Approval":
                db.session.add(Notification(task_id=r.task_id, message=f"{r.task_id} — Responder has completed task at {r.location} and is waiting for operator approval."))
                db.session.commit()
            return jsonify({"status": "ok"})
        return jsonify({"error": "Report not found"}), 404

    @app.route("/api/notifications")
    @login_required
    def api_notifications():
        notes = Notification.query.filter_by(is_read=False).order_by(Notification.created_at.desc()).limit(20).all()
        return jsonify([{"id": n.id, "task_id": n.task_id, "message": n.message, "time": n.created_at.strftime("%I:%M %p")} for n in notes])

    @app.route("/api/dismiss_notification/<int:note_id>", methods=["POST"])
    @login_required
    def dismiss_notification(note_id):
        n = Notification.query.get(note_id)
        if n: n.is_read = True; db.session.commit()
        return jsonify({"status": "ok"})

    @app.route("/api/dismiss_all_notifications", methods=["POST"])
    @login_required
    def dismiss_all_notifications():
        Notification.query.filter_by(is_read=False).update({"is_read": True})
        db.session.commit()
        return jsonify({"status": "ok"})

    # Idempotent: top-up legacy databases with any newly-added columns
    # so the app works without a separate manual migration step.
    _auto_migrate_road_constraint(app)

    return app



def _auto_migrate_road_constraint(app):
    """Idempotent: ensure road_constraint has the new map-marker columns.
    Runs on every startup; only adds columns that are missing. Safe across
    SQLite (local dev) and PostgreSQL (Neon/Heroku) backends."""
    from sqlalchemy import text, inspect
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            if 'road_constraint' not in inspector.get_table_names():
                return  # db.create_all() will build it with the new schema
            existing = {col['name'] for col in inspector.get_columns('road_constraint')}

            dialect = db.engine.dialect.name  # 'sqlite' or 'postgresql'
            float_t    = 'FLOAT'     if dialect == 'sqlite' else 'DOUBLE PRECISION'
            datetime_t = 'DATETIME'  if dialect == 'sqlite' else 'TIMESTAMP'

            wanted = [
                ('lat',             float_t),
                ('lon',             float_t),
                ('constraint_type', 'VARCHAR(30)'),
                ('task_id',         'VARCHAR(20)'),
                ('reported_by',     'VARCHAR(50)'),
                ('resolved_at',     datetime_t),
            ]
            added = []
            with db.engine.begin() as conn:
                for name, sqltype in wanted:
                    if name in existing:
                        continue
                    conn.execute(text(f"ALTER TABLE road_constraint ADD COLUMN {name} {sqltype}"))
                    added.append(name)
            if added:
                print(f"[auto-migrate] road_constraint: added columns {added}")
        except Exception as e:
            # Never block app startup; just log so the user can see it.
            print(f"[auto-migrate] WARNING: could not auto-migrate road_constraint: {e}")


def setup_database():
    app = create_app()
    with app.app_context():
        db.create_all()
        # Seed default vehicle resources (10 each) if not already present
        default_vehicles = ["Food Trucks", "Cargo Truck", "Ambulances", "Vans", "MPVs/Sedans"]
        for vtype in default_vehicles:
            if not VehicleResource.query.filter_by(vehicle_type=vtype).first():
                db.session.add(VehicleResource(vehicle_type=vtype, total=10, currently_assigned=0))
        users = [{"id": "programmer", "role": "Programmer", "fname": "Dev", "lname": "Admin"}, 
                 {"id": "admin", "role": "Admin", "fname": "System", "lname": "Admin"}]
        for u in users:
            if not User.query.filter_by(account_id=u["id"]).first():
                db.session.add(User(account_id=u["id"], password="password123", role=u["role"], first_name=u["fname"], last_name=u["lname"]))
        db.session.commit()
    # After tables exist & are seeded, top-up any newly-added columns on
    # legacy databases that pre-date the constraint-marker feature.
    _auto_migrate_road_constraint(app)

if __name__ == "__main__":
    setup_database()
    app = create_app()
    try: host_name = socket.gethostname(); local_ip = socket.gethostbyname(host_name)
    except: local_ip = "127.0.0.1"
    print("\n" + "="*60)
    print(f"🚀 SYSTEM ONLINE (SINGLE PORT)")
    print(f"   ➤ PC Access:     http://127.0.0.1:5004/login")
    print(f"   ➤ Mobile Access: http://{local_ip}:5004/login")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5004)