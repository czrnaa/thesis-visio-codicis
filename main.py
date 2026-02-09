import datetime
import socket
import math
import heapq
import os
import requests 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, DisasterReport, Team, User

# ==========================================
#  GLOBAL SETTINGS STORE
# ==========================================
USER_SETTINGS = {}

# ==========================================
#  GLOBAL MAP DATA
# ==========================================
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

# ==========================================
#  A* ALGORITHM LOGIC
# ==========================================
def heuristic(node1, node2):
    if node1 not in NODE_LOCATIONS or node2 not in NODE_LOCATIONS: return float('inf')
    x1, y1 = NODE_LOCATIONS[node1]['lat'], NODE_LOCATIONS[node1]['lon']
    x2, y2 = NODE_LOCATIONS[node2]['lat'], NODE_LOCATIONS[node2]['lon']
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

def a_star_search(start, goal, avoid_nodes=[]):
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS: return None
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = {node: float('inf') for node in NODE_LOCATIONS}; g_score[start] = 0
    f_score = {node: float('inf') for node in NODE_LOCATIONS}; f_score[start] = heuristic(start, goal)
    
    while open_set:
        current_cost, current = heapq.heappop(open_set)
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            return path[::-1] 
        
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
    return None

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

    # --- HELPER: Identify Responder's Team ---
    def get_responder_team():
        if current_user.role == "Responder":
            full_name = f"{current_user.first_name} {current_user.last_name}"
            return Team.query.filter_by(leader=full_name).first()
        return None

    # --- AUTH ROUTES ---
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

    # --- WEB ROUTES ---
    @app.route("/")
    def home(): return redirect(url_for("dashboard_view"))

    @app.route("/dashboard")
    @login_required
    def dashboard_view():
        show_all = USER_SETTINGS.get(current_user.id, {}).get('show_routes', False)
        
        # --- ROLE BASED FILTERING ---
        if current_user.role == "Responder":
            team = get_responder_team()
            if team:
                # Show ONLY reports assigned to this responder's team
                reports_db = DisasterReport.query.filter_by(assigned_team=team.team_id).order_by(DisasterReport.date_submitted.desc()).all()
            else:
                reports_db = []
        else:
            # Show ALL reports for Admin/Operator/Programmer
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
            active=DisasterReport.query.filter(DisasterReport.status != 'Resolved').count(),
            pending=DisasterReport.query.filter_by(status='Pending').count(),
            resources=Team.query.filter_by(status='Available').count(), 
            user=current_user,
            show_all_routes=show_all)

    @app.route("/reports")
    @login_required
    def reports_list():
        view_id = request.args.get('view_id', type=int)
        
        # --- ROLE BASED FILTERING ---
        if current_user.role == "Responder":
            team = get_responder_team()
            if team:
                reports = DisasterReport.query.filter_by(assigned_team=team.team_id).order_by(DisasterReport.date_submitted.desc()).all()
            else:
                reports = []
        else:
            reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()

        selected = reports[view_id] if view_id is not None and 0 <= view_id < len(reports) else None
        return render_template("reports_list.html", reports=reports, selected_report=selected, user=current_user)

    @app.route("/teams")
    @login_required
    def teams_view():
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

    # --- ADMIN ROUTES ---
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
                if team: db.session.delete(team)
            db.session.delete(u) 
            db.session.commit()
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

    # --- REPORT & API ROUTES ---
    @app.route("/create_report")
    @login_required
    def create_report_view():
        # BLOCK RESPONDERS
        if current_user.role == "Responder": return redirect(url_for('dashboard_view'))
        now = datetime.datetime.now()
        return render_template("user.html", task_id=f"TASK-{DisasterReport.query.count() + 1:03d}", 
            auto_date=now.strftime("%m/%d/%Y"), auto_day=now.strftime("%A"), auto_time=now.strftime("%I:%M %p"), user=current_user)

    @app.route("/submit_report", methods=["POST"])
    @login_required
    def submit_report():
        # BLOCK RESPONDERS
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
            r.disaster_type = request.form.get("disaster_type")
            r.severity = request.form.get("severity")
            r.response_type = request.form.get("response_type")
            r.affected = request.form.get("affected")
            db.session.commit()
            if new_status == request.form.get("status"):
                flash("✅ Report details updated successfully.", "success")
        return redirect(url_for('reports_list', view_id=request.form.get("view_id")))

    @app.route("/assign_team", methods=["POST"])
    @login_required
    def assign_team():
        # BLOCK RESPONDERS
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
            if team: reports = DisasterReport.query.filter_by(assigned_team=team.team_id).filter(DisasterReport.status != 'Resolved').all()
            else: reports = []
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

    @app.route("/calculate_route")
    def calculate_route():
        start_input = request.args.get('start', 'HQ_Malolos')
        end_input = request.args.get('end', 'Bocaue') 
        avoid = request.args.get('avoid', '')
        start_node, end_node = start_input, end_input
        if start_node == end_node and start_node in LOCAL_DESTINATIONS: end_node = LOCAL_DESTINATIONS[start_node]
        path = a_star_search(start_node, end_node, avoid_nodes=[avoid] if avoid else [])
        if not path: return jsonify({"path": [], "coords": [], "distance": "N/A", "eta": "Blocked"})
        coords = [[NODE_LOCATIONS[node]['lat'], NODE_LOCATIONS[node]['lon']] for node in path]
        return jsonify({"path": path, "coords": coords, "distance": "N/A", "eta": "N/A"})

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