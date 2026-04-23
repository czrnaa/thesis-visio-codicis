import datetime
import socket
import math
import heapq
import os
import time  # <--- Added for System Analytics
import requests 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, DisasterReport, Team, User, RouteLog, RoadConstraint

# ==========================================
#  GLOBAL SETTINGS & DATA
# ==========================================
USER_SETTINGS = {}

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
    "San Miguel (Viola St)": ["San Miguel"]
}

LOCAL_DESTINATIONS = {
    "HQ_Malolos": "Malolos (City Hall)",
    "Plaridel":   "Plaridel (Muni Hall)",
    "Calumpit":   "Calumpit (Market)",
    "Guiguinto":  "Guiguinto (Plaza)",
    "Bocaue":     "Bocaue (Crossing)",
    "San Miguel": "San Miguel (Viola St)"
}

def heuristic(node1, node2):
    if node1 not in NODE_LOCATIONS or node2 not in NODE_LOCATIONS: return float('inf')
    x1, y1 = NODE_LOCATIONS[node1]['lat'], NODE_LOCATIONS[node1]['lon']
    x2, y2 = NODE_LOCATIONS[node2]['lat'], NODE_LOCATIONS[node2]['lon']
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

# --- UPDATED A* (Returns Stats) ---
def a_star_search(start, goal, avoid_nodes=[]):
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS: return None, 0
    
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = {node: float('inf') for node in NODE_LOCATIONS}; g_score[start] = 0
    f_score = {node: float('inf') for node in NODE_LOCATIONS}; f_score[start] = heuristic(start, goal)
    
    nodes_explored_count = 0

    while open_set:
        current_cost, current = heapq.heappop(open_set)
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
                if neighbor in avoid_nodes: continue 
                tentative_g_score = g_score[current] + heuristic(current, neighbor)
                if tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = g_score[neighbor] + heuristic(neighbor, goal)
                    if neighbor not in [i[1] for i in open_set]:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
    return None, nodes_explored_count

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
#  APP FACTORY
# ==========================================
def create_app():
    app = Flask(__name__)
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'disaster.db')
    app.config['SECRET_KEY'] = 'thesis_secret_key_123'
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id): return User.query.get(int(user_id))

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
                if user.id not in USER_SETTINGS: USER_SETTINGS[user.id] = {'show_routes': False}
                db.session.commit()
                return redirect(url_for('dashboard_view'))
            return render_template('login.html', error="Invalid Credentials")
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route("/")
    def home(): return redirect(url_for("dashboard_view"))

    @app.route("/dashboard")
    @login_required
    def dashboard_view():
        show_all = USER_SETTINGS.get(current_user.id, {}).get('show_routes', False)
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
        
        return render_template("dashboard.html", reports=reports_display, user=current_user, show_all_routes=show_all)

    @app.route("/reports")
    @login_required
    def reports_list():
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
        reports = DisasterReport.query.filter(DisasterReport.status != 'Resolved').all()
        teams_db = Team.query.all()
        display_teams = []
        for t in teams_db:
            active_assignment = DisasterReport.query.filter_by(assigned_team=t.team_id).filter(DisasterReport.status.in_(['In Progress', 'En Route'])).first()
            final_status = "Busy" if active_assignment else "Available"
            task_str = active_assignment.task_id if active_assignment else "-"
            location_name = get_address_from_coords(t.lat, t.lon)
            display_teams.append({
                "id": t.team_id, "leader": t.leader, "location": location_name,
                "role": t.role, "status": final_status, "task": task_str,
                "last_updated": t.last_updated.strftime('%m-%d-%Y') if t.last_updated else "N/A"
            })
        return render_template("teams.html", teams=display_teams, reports=reports, user=current_user)

    @app.route("/monitor")
    @login_required
    def monitor_view():
        show_all = USER_SETTINGS.get(current_user.id, {}).get('show_routes', False)
        return render_template("monitor.html", user=current_user, show_all_routes=show_all)

    # --- NEW: SYSTEM ANALYTICS VIEW ---
    @app.route("/analytics")
    @login_required
    def analytics_view():
        if current_user.role != "Programmer": return redirect(url_for('dashboard_view'))
        return render_template("analytics.html", user=current_user)

    # --- NEW: SYSTEM ANALYTICS DATA API ---
    @app.route("/analytics_data")
    @login_required
    def analytics_data():
        if current_user.role != "Programmer": return jsonify([])
        reports = DisasterReport.query.filter(DisasterReport.status != 'Resolved').all()
        data = []
        
        for i, r in enumerate(reports):
            # Calculate A* Stats for this specific report's route (HQ -> Incident)
            start_node = "HQ_Malolos"
            end_node = r.location # Assumes location name matches Node name
            
            if end_node not in NODE_LOCATIONS: end_node = "Bocaue" # Fallback

            t_start = time.time()
            path, nodes = a_star_search(start_node, end_node)
            t_end = time.time()
            exec_time = round((t_end - t_start) * 1000, 3) # ms

            # Calculate Distance
            dist = 0
            if path:
                deg_dist = 0
                for j in range(len(path) - 1):
                    deg_dist += heuristic(path[j], path[j+1])
                dist = round(deg_dist * 111, 2) # KM
            
            eta = f"{math.ceil(dist)} mins" if path else "N/A"

            data.append({
                "num": i + 1,
                "task_id": r.task_id,
                "location": r.location,
                "nodes": nodes,
                "time": f"{exec_time} ms",
                "eta": eta,
                "dist": f"{dist} km"
            })
            
        return jsonify(data)

    @app.route("/profile_settings", methods=["GET", "POST"])
    @login_required
    def profile_settings():
        if request.method == "POST":
            current_user.first_name = request.form.get("first_name")
            current_user.last_name = request.form.get("last_name")
            current_user.phone = request.form.get("phone")
            new_password = request.form.get("new_password")
            if new_password and new_password.strip():
                if current_user.password == request.form.get("current_password"):
                    current_user.password = new_password
                    flash("✅ Password changed successfully.", "success")
                else:
                    flash("❌ Incorrect Password.", "error")
            visual_setting = request.form.get("routing_visual") == "on"
            USER_SETTINGS[current_user.id] = {'show_routes': visual_setting}
            if not new_password: flash("✅ Settings updated.", "success")
            db.session.commit()
            return redirect(url_for('profile_settings'))
        current_setting = USER_SETTINGS.get(current_user.id, {}).get('show_routes', False)
        return render_template("profile.html", user=current_user, show_routes=current_setting)

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
            flash(f"✅ User deleted. Active tasks reset.", "success")
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
            prefix = "OPT" if role == "Operator" else "RSP"
            final_id, id_count = get_next_details(prefix)
            auto_pass = f"password{id_count:03d}"
            new_user = User(account_id=final_id, password=auto_pass, role=role, first_name=first_name, last_name=last_name)
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
                            flash(f"✅ Location set: {street}, {municipality}", "success")
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
            new_status = request.form.get("status")
            if new_status == "In Progress" and (not r.assigned_team or r.assigned_team.strip() == ""):
                flash("⚠️ Cannot change status to 'In Progress' without assigning a team first.", "error")
                new_status = "Pending"
            elif new_status == "Pending" or new_status == "Resolved":
                r.assigned_team = None 
            r.status = new_status
            r.notes = request.form.get("notes")
            if request.form.get("disaster_type"): r.disaster_type = request.form.get("disaster_type")
            if request.form.get("severity"): r.severity = request.form.get("severity")
            if request.form.get("response_type"): r.response_type = request.form.get("response_type")
            if request.form.get("affected"): r.affected = request.form.get("affected")
            db.session.commit()
            if new_status == request.form.get("status"):
                flash("✅ Report details updated successfully.", "success")
        return redirect(url_for('reports_list', view_id=request.form.get("view_id")))

    @app.route("/assign_team", methods=["POST"])
    @login_required
    def assign_team():
        if current_user.role == "Responder": return redirect(url_for('dashboard_view'))
        team_id = request.form.get("team_id")
        task_id = request.form.get("task_id")
        if not team_id or team_id.strip() == "": return redirect(url_for("teams_view"))
        r = DisasterReport.query.filter_by(task_id=task_id).first()
        if r: 
            r.assigned_team = team_id
            r.status = "In Progress" 
            db.session.commit()
        return redirect(url_for("teams_view"))

    @app.route("/responder_data")
    @login_required
    def responder_data():
        if current_user.role == "Responder":
            team = get_responder_team()
            reports = DisasterReport.query.filter_by(assigned_team=team.team_id).filter(DisasterReport.status != 'Resolved').all() if team else []
        else:
            reports = DisasterReport.query.filter(DisasterReport.status != 'Resolved').all()
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

    @app.route("/calculate_route")
    def calculate_route():
        avoid_param = request.args.get('avoid', '')
        task_id = request.args.get('task_id', 'Manual') 
        want_alternative = request.args.get('alternative', 'false').lower() == 'true'

        
        use_absra = request.args.get('use_absra', 'false').lower() == 'true'
        print(f"*** ABSRA Toggle is set to: {use_absra} ***") 
   
        
        # --- DYNAMIC START/END LOCATION MATCHING ---
        team_lat = request.args.get('team_lat')
        team_lon = request.args.get('team_lon')
        task_lat = request.args.get('task_lat')
        task_lon = request.args.get('task_lon')

        start_node = request.args.get('start', 'HQ_Malolos')
        end_node = request.args.get('end', 'Bocaue')

        # Find the closest defined Node to the Team's current GPS
        if team_lat and team_lon:
            t_lat, t_lon = float(team_lat), float(team_lon)
            start_node = min(NODE_LOCATIONS.keys(), key=lambda k: math.hypot(NODE_LOCATIONS[k]['lat'] - t_lat, NODE_LOCATIONS[k]['lon'] - t_lon))
            
        # Find the closest defined Node to the Task's GPS
        if task_lat and task_lon:
            t_lat, t_lon = float(task_lat), float(task_lon)
            end_node = min(NODE_LOCATIONS.keys(), key=lambda k: math.hypot(NODE_LOCATIONS[k]['lat'] - t_lat, NODE_LOCATIONS[k]['lon'] - t_lon))
        # ------------------------------------------------
        
        if start_node == end_node and start_node in LOCAL_DESTINATIONS: 
            end_node = LOCAL_DESTINATIONS[start_node]

        active_constraints = RoadConstraint.query.filter_by(is_active=True).all()
        avoid_nodes = [c.node_name for c in active_constraints]
        if avoid_param and avoid_param not in avoid_nodes:
            avoid_nodes.append(avoid_param)

        # 1. Calculate Baseline / Primary Route
        baseline_path, _ = a_star_search(start_node, end_node, avoid_nodes=[])
        baseline_dist = 0.0
        if baseline_path:
            b_deg = sum(heuristic(baseline_path[j], baseline_path[j+1]) for j in range(len(baseline_path) - 1))
            baseline_dist = round(b_deg * 111, 2)

        # --- ALTERNATIVE PATH GENERATOR ---
        if want_alternative and baseline_path and len(baseline_path) > 2:
            middle_node = baseline_path[len(baseline_path) // 2]
            if middle_node not in avoid_nodes:
                avoid_nodes.append(middle_node)
        # ---------------------------------------
            
        # 2. Calculate Actual Route (With constraints / alternative blocks)
        path, nodes_explored = a_star_search(start_node, end_node, avoid_nodes=avoid_nodes)
        
        # ERROR HANDLING
        if not path:
            failed_log = RouteLog(task_id=task_id, origin=start_node, destination=end_node, new_distance=0.0, reason=", ".join(avoid_nodes), status="Error")
            db.session.add(failed_log)
            db.session.commit()
            return jsonify({"path": [], "coords": [], "distance": "N/A", "eta": "Blocked", "is_rerouted": False, "message": "Error: Destination unreachable due to closures."})
        
        deg_dist = sum(heuristic(path[j], path[j+1]) for j in range(len(path) - 1))
        dist_km = round(deg_dist * 111, 2)
        
        is_rerouted = (path != baseline_path) or want_alternative
        message = f"REROUTED (Alternative): Avoiding {', '.join(avoid_nodes)}. Added {round(dist_km - baseline_dist, 2)} km." if is_rerouted else "Optimal Route Found."
        
        # LOGGING
        success_log = RouteLog(task_id=task_id, origin=start_node, destination=end_node, new_distance=dist_km, reason="Alternative Route" if want_alternative else "Standard Route", status="Success")
        db.session.add(success_log)
        db.session.commit()
        
        coords = [[NODE_LOCATIONS[node]['lat'], NODE_LOCATIONS[node]['lon']] for node in path]
        
        # This is the vital return statement that was missing!
        return jsonify({
            "path": path, "coords": coords, "distance": f"{dist_km} km", "eta": f"{math.ceil(dist_km)} mins",
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

    return app



def setup_database():
    app = create_app()
    with app.app_context():
        db.create_all()
        users = [{"id": "programmer", "role": "Programmer", "fname": "Dev", "lname": "Admin"}, 
                 {"id": "admin", "role": "Admin", "fname": "System", "lname": "Admin"}]
        for u in users:
            if not User.query.filter_by(account_id=u["id"]).first():
                db.session.add(User(account_id=u["id"], password="password123", role=u["role"], first_name=u["fname"], last_name=u["lname"]))
        db.session.commit()

if __name__ == "__main__":
    setup_database()
    app = create_app()
    try: host_name = socket.gethostname(); local_ip = socket.gethostbyname(host_name)
    except: local_ip = "127.0.0.1"
    print("\n" + "="*60)
    print(f"🚀 SYSTEM ONLINE (SINGLE PORT)")
    print(f"   ➤ PC Access:     http://127.0.0.1:5000/login")
    print(f"   ➤ Mobile Access: http://{local_ip}:5000/login")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)