import datetime
import socket
import math
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, DisasterReport, Team, User

app = Flask(__name__)

# --- CONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'disaster.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'thesis_secret_key_123'

db.init_app(app)

# --- LOGIN MANAGER ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- DATABASE SETUP ---
def setup_system():
    with app.app_context():
        db.create_all()

        # Create Default Users
        users_to_create = [
            {"id": "programmer", "role": "Programmer"},
            {"id": "admin",      "role": "Admin"},
            {"id": "operator",   "role": "Operator"},
            {"id": "responder",  "role": "Responder"}
        ]
        for u in users_to_create:
            if not User.query.filter_by(account_id=u["id"]).first():
                new_user = User(account_id=u["id"], password="password123", role=u["role"])
                db.session.add(new_user)
        
        # Create Default Teams
        if not Team.query.first():
            teams_data = [
                {"id": "TM-012", "name": "Alpha Squad", "leader": "Sgt. Perez", "role": "Firefighting", "lat": 14.8437, "lon": 120.8113},
                {"id": "TM-013", "name": "Beta Medical", "leader": "Dr. Cruz", "role": "Medical Aid", "lat": 14.8294, "lon": 120.8872},
                {"id": "TM-014", "name": "Delta Rescue", "leader": "Lt. Santos", "role": "Search & Rescue", "lat": 14.8867, "lon": 120.8576},
                {"id": "TM-015", "name": "Echo Relief", "leader": "Mr. Reyes", "role": "Relief Goods", "lat": 14.9507, "lon": 120.9008},
                {"id": "TM-016", "name": "Zeta Police", "leader": "Capt. Dalisay", "role": "Crowd Control", "lat": 14.7960, "lon": 120.9255},
            ]
            for t in teams_data:
                new_team = Team(team_id=t["id"], name=t["name"], leader=t["leader"], role=t["role"], lat=t["lat"], lon=t["lon"], status="Available")
                db.session.add(new_team)
        
        db.session.commit()

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        acc_id = request.form.get('account_id')
        pwd = request.form.get('password')
        user = User.query.filter_by(account_id=acc_id).first()
        if user and user.password == pwd:
            login_user(user)
            user.last_login = datetime.datetime.now() 
            db.session.commit()
            return redirect(url_for('dashboard_view'))
        else:
            return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- MAIN WEB ROUTES ---
@app.route("/")
def home():
    return redirect(url_for("dashboard_view"))

@app.route("/dashboard")
@login_required
def dashboard_view():
    reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
    active_count = DisasterReport.query.filter(DisasterReport.status != 'Resolved').count()
    pending_count = DisasterReport.query.filter_by(status='Pending').count()
    total_teams = Team.query.count()
    busy_teams = DisasterReport.query.filter(DisasterReport.status != 'Resolved', DisasterReport.assigned_team != None).count()
    resources_available = total_teams - busy_teams
    
    return render_template("dashboard.html", 
                           reports=reports, 
                           active=active_count, 
                           pending=pending_count, 
                           resources=resources_available, 
                           user=current_user)

@app.route("/reports")
@login_required
def reports_list():
    reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
    view_id = request.args.get('view_id', type=int)
    selected_report = reports[view_id] if view_id is not None and 0 <= view_id < len(reports) else None
    return render_template("reports_list.html", reports=reports, selected_report=selected_report, user=current_user)

@app.route("/teams")
@login_required
def teams_view():
    reports = DisasterReport.query.filter(DisasterReport.status != 'Resolved').all()
    teams_db = Team.query.all()
    display_teams = []
    
    for t in teams_db:
        active_assignment = DisasterReport.query.filter_by(assigned_team=t.team_id).filter(DisasterReport.status != 'Resolved').first()
        
        final_status = "Available"
        task_str = "-"
        
        if active_assignment:
            final_status = "Busy"
            task_str = active_assignment.task_id
        
        display_teams.append({
            "id": t.team_id, 
            "name": t.name, 
            "leader": t.leader, 
            "role": t.role, 
            "status": final_status, 
            "task": task_str,
            "last_updated": t.last_updated.strftime('%m-%d-%Y') if t.last_updated else "N/A"
        })
        
    return render_template("teams.html", teams=display_teams, reports=reports, user=current_user)

@app.route("/monitor")
@login_required
def monitor_view():
    return render_template("monitor.html", user=current_user)

@app.route("/profile_settings", methods=["GET", "POST"])
@login_required
def profile_settings():
    if request.method == "POST":
        current_user.first_name = request.form.get("first_name")
        current_user.last_name = request.form.get("last_name")
        current_user.phone = request.form.get("phone")
        db.session.commit()
        return redirect(url_for('profile_settings'))
    return render_template("profile.html", user=current_user)

# --- REPORT CREATION LOGIC ---
@app.route("/create_report")
@login_required
def create_report_view():
    count = DisasterReport.query.count()
    new_task_id = f"TASK-{count + 1:03d}"
    now = datetime.datetime.now()
    return render_template("user.html", 
                           task_id=new_task_id, 
                           auto_date=now.strftime("%m/%d/%Y"), 
                           auto_day=now.strftime("%A"), 
                           auto_time=now.strftime("%I:%M %p"), 
                           user=current_user)

@app.route("/submit_report", methods=["POST"])
@login_required
def submit_report():
    try:
        lat = float(request.form.get("lat"))
        lon = float(request.form.get("lon"))
    except:
        return "Invalid Coordinates", 400

    municipality = request.form.get("municipality")
    street = request.form.get("address")
    landmark = request.form.get("landmark")
    
    full_address_str = f"{street}"
    if municipality: full_address_str += f", {municipality}"
    if landmark: full_address_str += f" ({landmark})"

    resources_list = request.form.getlist("resources")
    constraints_list = request.form.getlist("constraints")

    sev_map = {"Low": 1, "Medium": 3, "High": 5, "Critical": 10}

    new_report = DisasterReport(
        task_id=request.form.get("task_id"),
        disaster_type=request.form.get("disaster_type"),
        severity=request.form.get("severity"),
        lat=lat,
        lon=lon,
        location=municipality,          
        full_address=full_address_str,  
        resources=", ".join(resources_list),      
        constraints=", ".join(constraints_list),  
        status="Pending",
        priority=sev_map.get(request.form.get("severity"), 1),
        date_str=request.form.get("date"),
        day_str=request.form.get("day"), 
        time_str=request.form.get("time"),
        affected=request.form.get("affected"),
        response_type=request.form.get("response_type"),
        notes=request.form.get("notes")
    )

    db.session.add(new_report)
    db.session.commit()
    return redirect(url_for("reports_list"))

# --- ACTION ROUTES ---
@app.route("/save_report_changes", methods=["POST"])
@login_required
def save_report_changes():
    report = DisasterReport.query.get(request.form.get("report_id"))
    if report:
        report.status = request.form.get("status")
        if report.status == "Pending": 
            report.assigned_team = None 
        report.notes = request.form.get("notes")
        db.session.commit()
    return redirect(url_for('reports_list', view_id=request.form.get("view_id")))

@app.route("/assign_team", methods=["POST"])
@login_required
def assign_team():
    report = DisasterReport.query.filter_by(task_id=request.form.get("task_id")).first()
    team_id = request.form.get("team_id")
    
    if report and team_id:
        report.assigned_team = team_id
        report.status = "In Progress"
        db.session.commit()
        
    return redirect(url_for("teams_view"))

# --- API ROUTES ---
@app.route("/responder_data")
@login_required
def responder_data():
    active_reports = DisasterReport.query.filter(DisasterReport.status != 'Resolved').all()
    data = []
    for r in active_reports:
        data.append({ 
            "task_id": r.task_id, 
            "disaster_type": r.disaster_type, 
            "location": r.full_address or r.location, 
            "lat": r.lat, 
            "lon": r.lon, 
            "severity": r.severity, 
            "status": r.status,
            "time": r.time_str if r.time_str else "N/A" # <--- THIS LINE IS THE STATUS MONITORING FIX
        })
    return jsonify(data)

@app.route("/get_locations")
def get_locations():
    return jsonify({"Malolos": [14.8437, 120.8113], "Hagonoy": [14.8322, 120.7380]}) 

if __name__ == "__main__":
    setup_system()
    print("\n" + "="*50)
    print(f"✅ SYSTEM ONLINE")
    print(f"🔐 Login: http://127.0.0.1:5000/login")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0')