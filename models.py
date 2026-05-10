from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import datetime

db = SQLAlchemy()

# --- TABLE 1: DISASTER REPORTS ---
class DisasterReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(20), unique=True, nullable=False)
    disaster_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    full_address = db.Column(db.String(200), nullable=False)
    resources = db.Column(db.String(200))
    constraints = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Pending")
    priority = db.Column(db.Integer, default=1)
    date_submitted = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    assigned_team = db.Column(db.String(50), nullable=True)
    
    # Display Fields
    date_str = db.Column(db.String(20))
    day_str = db.Column(db.String(20))
    time_str = db.Column(db.String(20))
    affected = db.Column(db.String(50))
    response_type = db.Column(db.String(50))
    notes = db.Column(db.Text)

# --- TABLE 2: TEAMS ---
class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    leader = db.Column(db.String(50))
    role = db.Column(db.String(50))
    status = db.Column(db.String(20), default="Available")
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'team_id': self.team_id,
            'name': self.name,
            'role': self.role,
            'status': self.status,
            'lat': self.lat,
            'lon': self.lon,
            'last_updated': self.last_updated.strftime("%H:%M:%S") if self.last_updated else "Never"
        }

# --- TABLE 3: USERS (Updated for Profile) ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default="Operator")
    
    # NEW PROFILE FIELDS
    first_name = db.Column(db.String(50), default="Jane Doe")
    last_name = db.Column(db.String(50), default="Yamada")
    phone = db.Column(db.String(20), default="09XX XXX XXXX")
    email = db.Column(db.String(120), default="")
    status = db.Column(db.String(20), default="Active")
    last_login = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    show_routes = db.Column(db.Boolean, default=False)

class RoadConstraint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(100), nullable=False)  # e.g., "Plaridel"
    reason = db.Column(db.String(255)) # e.g., "Heavy Flooding"
    is_active = db.Column(db.Boolean, default=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(20), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# --- TABLE 5: ROUTE & REROUTE LOGS ---
class RouteLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(20), nullable=True)      # The task this route belongs to
    origin = db.Column(db.String(100), nullable=False)     # 'From' destination
    destination = db.Column(db.String(100), nullable=False)# 'To' destination
    new_distance = db.Column(db.Float, nullable=True)      # New distance length
    reason = db.Column(db.String(255), nullable=True)      # Reason/Type of Constraint
    status = db.Column(db.String(50), nullable=False)      # "Success" or "Error"
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow) # Time triggered