import datetime
import socket
import math
import heapq
import os
import time  # <--- Added for System Analytics
import random   # <--- For OTP generation
import smtplib  # <--- For sending email OTPs
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, DisasterReport, Team, User, RouteLog, RoadConstraint, Notification

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
def a_star_search(start, goal, avoid_nodes=[], penalty_nodes=None, penalty_factor=1.0):
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
                # Weighted traversal cost for constraint types (e.g. Heavy Traffic)
                edge_cost = heuristic(current, neighbor)
                if penalty_nodes and neighbor in penalty_nodes:
                    edge_cost *= penalty_factor
                tentative_g_score = g_score[current] + edge_cost
                if tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = g_score[neighbor] + heuristic(neighbor, goal)
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
}
REGIONS = ["Central", "Northern", "Southern"]
_ARC_FLAGS = None

def build_arc_flags():
    flags = {}
    for u in GRAPH_CONNECTIONS:
        for v in GRAPH_CONNECTIONS[u]:
            flags[(u, v)] = set()

    for region in REGIONS:
        region_nodes = [n for n, r in NODE_REGIONS.items() if r == region]
        for t in region_nodes:
            d = {n: float('inf') for n in NODE_LOCATIONS}
            d[t] = 0.0
            heap = [(0.0, t)]
            visited = set()
            while heap:
                dd, u = heapq.heappop(heap)
                if u in visited:
                    continue
                visited.add(u)
                for node in GRAPH_CONNECTIONS:
                    if u in GRAPH_CONNECTIONS[node] and node not in visited:
                        cost = heuristic(node, u)
                        new_d = d[u] + cost
                        if new_d < d[node]:
                            d[node] = new_d
                            heapq.heappush(heap, (new_d, node))
            for u in GRAPH_CONNECTIONS:
                for v in GRAPH_CONNECTIONS[u]:
                    if d[u] < float('inf') and d[v] < float('inf'):
                        if abs(d[u] - (heuristic(u, v) + d[v])) < 1e-9:
                            flags[(u, v)].add(region)
    return flags

def get_arc_flags():
    global _ARC_FLAGS
    if _ARC_FLAGS is None:
        _ARC_FLAGS = build_arc_flags()
    return _ARC_FLAGS

def absra_search(start, goal, avoid_nodes=[]):
    if start not in NODE_LOCATIONS or goal not in NODE_LOCATIONS:
        return None, 0
    if start == goal:
        return [start], 0

    flags = get_arc_flags()
    goal_region = NODE_REGIONS.get(goal)
    start_region = NODE_REGIONS.get(start)

    rev_adj = {n: [] for n in NODE_LOCATIONS}
    for u in GRAPH_CONNECTIONS:
        for v in GRAPH_CONNECTIONS[u]:
            rev_adj[v].append(u)

    fwd_g = {n: float('inf') for n in NODE_LOCATIONS}
    fwd_g[start] = 0.0
    fwd_par = {start: None}
    fwd_open = [(heuristic(start, goal), start)]
    fwd_closed = set()

    bwd_g = {n: float('inf') for n in NODE_LOCATIONS}
    bwd_g[goal] = 0.0
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
                if goal_region and v != goal and (u, v) in flags:
                    if goal_region not in flags[(u, v)]:
                        continue
                new_g = fwd_g[u] + heuristic(u, v)
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
                if start_region and v != start and (v, u) in flags:
                    if start_region not in flags[(v, u)]:
                        continue
                new_g = bwd_g[u] + heuristic(u, v)
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

    # ==========================================
    #  OTP / EMAIL AUTHENTICATION
    # ==========================================
    # 🔧 GMAIL SMTP CONFIG — SET THESE TO ENABLE REAL EMAIL DELIVERY
    # 1. Enable 2-Step Verification on your Gmail: https://myaccount.google.com/security
    # 2. Generate an App Password: https://myaccount.google.com/apppasswords
    # 3. Paste the 16-char password below (no spaces).
    # If left blank, OTPs print to console (demo fallback).
    GMAIL_USER     = 'onikabutosan@gmail.com'   # ← your Gmail address
    GMAIL_APP_PASS = 'enipenxonecarhes'        # ← the NEW 16 chars, no spaces
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
    def home(): return redirect(url_for("dashboard_view"))

    @app.route("/dashboard")
    @login_required
    def dashboard_view():
        show_all = USER_SETTINGS.get(current_user.id, {}).get('show_routes', False)
        
        # --- NEW LOGIC: Calculate Dashboard Stats ---
        # 1. Active Reports (Tasks that are currently being handled)
        active_count = DisasterReport.query.filter(DisasterReport.status.in_(['In Progress', 'En Route'])).count()
        
        # 2. Pending Tasks (Tasks waiting for assignment)
        pending_count = DisasterReport.query.filter_by(status='Pending').count()
        
        # 3. Resources Available (Teams without an active task)
        all_teams = Team.query.all()
        available_teams = 0
        for t in all_teams:
            has_active_task = DisasterReport.query.filter_by(assigned_team=t.team_id).filter(DisasterReport.status.in_(['In Progress', 'En Route'])).first()
            if not has_active_task:
                available_teams += 1
        # --------------------------------------------

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
        
        # Pass the calculated stats into the HTML template
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
            
        return render_template("teams.html", teams=display_teams, reports=reports, user=current_user)

    @app.route("/monitor")
    @login_required
    def monitor_view():
        show_all = USER_SETTINGS.get(current_user.id, {}).get('show_routes', False)
        can_reroute = current_user.role == "Responder"
        return render_template("monitor.html", user=current_user, show_all_routes=show_all, can_reroute=can_reroute)

    # --- NEW: SYSTEM ANALYTICS VIEW ---
    @app.route("/analytics")
    @login_required
    def analytics_view():
        if current_user.role != "Programmer": return redirect(url_for('dashboard_view'))
        return render_template("analytics.html", user=current_user)

    # --- UPDATED: SYSTEM ANALYTICS DATA API ---
    @app.route("/analytics_data")
    @login_required
    def analytics_data():
        if current_user.role != "Programmer": return jsonify([])
        
        # REMOVED the != 'Resolved' filter so it retains ALL tasks in the analytics
        reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        data = []
        
        for i, r in enumerate(reports):
            start_node = "HQ_Malolos"
            end_node = r.location 
            if end_node not in NODE_LOCATIONS: end_node = "Bocaue" 

            t_start = time.time()
            path, nodes = a_star_search(start_node, end_node)
            exec_time = round((time.time() - t_start) * 1000, 3)

            dist = 0.0
            if path and len(path) > 1:
                dist = round(sum(heuristic(path[j], path[j+1]) for j in range(len(path)-1)) * 111, 2)
            eta = f"{math.ceil(dist)} mins" if path else "N/A"

            t_start = time.time()
            absra_path, absra_nodes = absra_search(start_node, end_node)
            absra_exec_time = round((time.time() - t_start) * 1000, 3)

            if absra_path and len(absra_path) > 1:
                absra_dist = round(sum(heuristic(absra_path[j], absra_path[j+1]) for j in range(len(absra_path)-1)) * 111, 2)
                absra_eta = f"{math.ceil(absra_dist)} mins"
            else:
                absra_path, absra_nodes, absra_exec_time, absra_dist, absra_eta = path, nodes, exec_time, dist, eta

            data.append({
                "num": i + 1,
                "task_id": r.task_id,
                "location": r.location,
                "nodes": nodes,
                "time": f"{exec_time} ms",
                "absra_nodes": absra_nodes,
                "absra_time": f"{absra_exec_time} ms",
                "eta": eta,
                "dist": f"{dist} km",
                "absra_eta": absra_eta,
                "absra_dist": f"{absra_dist} km"
            })
            
        return jsonify(data)

    @app.route("/profile_settings", methods=["GET", "POST"])
    @login_required
    def profile_settings():
        if request.method == "POST":
            current_user.first_name = request.form.get("first_name")
            current_user.last_name = request.form.get("last_name")
            current_user.phone = request.form.get("phone")
            visual_setting = request.form.get("routing_visual") == "on"
            USER_SETTINGS[current_user.id] = {'show_routes': visual_setting}

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

    # --- UPDATED: RESPONDER DATA API ---
    @app.route("/responder_data")
    @login_required
    def responder_data():
        if current_user.role == "Responder":
            team = get_responder_team()
            reports = DisasterReport.query.filter_by(assigned_team=team.team_id).filter(DisasterReport.status != 'Resolved').all() if team else []
        else:
            reports = DisasterReport.query.order_by(DisasterReport.date_submitted.desc()).all()
        
        data = []
        for i, r in enumerate(reports): # <--- Added enumerate(reports) to get the index
            team_display = "Pending Assignment"
            team_start_loc = None
            if r.assigned_team:
                team = Team.query.filter_by(team_id=r.assigned_team).first()
                if team:
                    team_display = f"{team.team_id} ({team.leader})"
                    team_start_loc = {"lat": team.lat, "lon": team.lon}
            data.append({
                "index": i, # <--- Passing the index for the 'View' button redirect
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
        constraint = request.args.get('constraint', '')  # road_block | heavy_traffic | flooded_road

        use_absra = request.args.get('use_absra', 'false').lower() == 'true'
        print(f"*** ABSRA Toggle is set to: {use_absra} ***")

        # --- DYNAMIC START/END LOCATION MATCHING ---
        team_lat = request.args.get('team_lat')
        team_lon = request.args.get('team_lon')
        task_lat = request.args.get('task_lat')
        task_lon = request.args.get('task_lon')

        start_node = request.args.get('start', 'HQ_Malolos')
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

        # 1. Calculate Baseline / Primary Route
        baseline_path, _ = a_star_search(start_node, end_node, avoid_nodes=[])
        baseline_dist = 0.0
        if baseline_path:
            b_deg = sum(heuristic(baseline_path[j], baseline_path[j+1]) for j in range(len(baseline_path) - 1))
            baseline_dist = round(b_deg * 111, 2)

        # --- CONSTRAINT-BASED REROUTE ---
        # Road Block / Flooded Road: physically block the congested intermediate node
        # Heavy Traffic: apply a 2.5x traversal cost penalty on intermediate nodes (weighted A*)
        penalty_nodes = None
        penalty_factor = 1.0
        if constraint in ('road_block', 'flooded_road') and baseline_path and len(baseline_path) > 2:
            blocked = baseline_path[len(baseline_path) // 2]
            if blocked not in avoid_nodes:
                avoid_nodes.append(blocked)
            want_alternative = True
        elif constraint == 'heavy_traffic' and baseline_path and len(baseline_path) > 1:
            penalty_nodes = set(baseline_path[1:-1])
            penalty_factor = 2.5
            want_alternative = True

        # --- ALTERNATIVE PATH GENERATOR (no constraint selected) ---
        if want_alternative and not constraint and baseline_path and len(baseline_path) > 2:
            middle_node = baseline_path[len(baseline_path) // 2]
            if middle_node not in avoid_nodes:
                avoid_nodes.append(middle_node)

        # 2. Calculate Actual Route (with constraints / alternative blocks)
        path, nodes_explored = a_star_search(start_node, end_node, avoid_nodes=avoid_nodes,
                                              penalty_nodes=penalty_nodes, penalty_factor=penalty_factor)
        
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
        constraint_labels = {'road_block': 'Road Block', 'heavy_traffic': 'Heavy Traffic', 'flooded_road': 'Flooded Road'}
        log_reason = constraint_labels.get(constraint) or ("Alternative Route" if want_alternative else "Standard Route")
        success_log = RouteLog(task_id=task_id, origin=start_node, destination=end_node, new_distance=dist_km, reason=log_reason, status="Success")
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
            elif new_status == "Awaiting Confirmation":
                db.session.add(Notification(task_id=r.task_id, message=f"{r.task_id} — Responder has ended task at {r.location}. Please update the report status."))
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
    print(f"   ➤ PC Access:     http://127.0.0.1:5004/login")
    print(f"   ➤ Mobile Access: http://{local_ip}:5004/login")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5004)