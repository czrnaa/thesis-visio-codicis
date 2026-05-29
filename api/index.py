import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import create_app
from models import db, User, VehicleResource

app = create_app()

with app.app_context():
    db.create_all()
    # Seed default users
    seed_users = [
        {"id": "programmer", "role": "Programmer", "fname": "Dev",    "lname": "Admin"},
        {"id": "admin",      "role": "Admin",       "fname": "System", "lname": "Admin"},
    ]
    for u in seed_users:
        if not User.query.filter_by(account_id=u["id"]).first():
            db.session.add(User(
                account_id=u["id"], password="password123",
                role=u["role"], first_name=u["fname"], last_name=u["lname"]
            ))
    # Seed default vehicle resources (10 each)
    default_vehicles = ["Food Trucks", "Cargo Truck", "Ambulances", "Vans", "MPVs/Sedans"]
    for vtype in default_vehicles:
        if not VehicleResource.query.filter_by(vehicle_type=vtype).first():
            db.session.add(VehicleResource(vehicle_type=vtype, total=10, currently_assigned=0))
    db.session.commit()
