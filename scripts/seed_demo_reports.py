from pathlib import Path
import datetime as dt
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from barangay_loader import find_barangay
from main import create_app
from models import DisasterReport, db


DEMO_MARKER = "[demo-analytics-seed]"

DEMO_REPORTS = [
    ("TASK-008", "BRGY-018", "Relief Goods Distribution", "Medium", "Pending", None, "Food Trucks x2, Cargo Truck x1", ""),
    ("TASK-009", "BRGY-035", "Emergency Logistics Prepositioning", "High", "In Progress", "TM-001", "Cargo Truck x2, Vans x1", "Heavy Traffic"),
    ("TASK-010", "BRGY-058", "Relief Goods Distribution", "Low", "Resolved", "TM-002", "Food Trucks x1", ""),
    ("TASK-011", "BRGY-074", "Mobile Financial Assistance Payouts", "Medium", "Pending", None, "MPVs/Sedans x2", ""),
    ("TASK-012", "BRGY-088", "Relief Goods Distribution", "High", "In Progress", "TM-002", "Food Trucks x2, Vans x1", "Flooded Road"),
    ("TASK-013", "BRGY-109", "Relief Goods Distribution", "Critical", "Pending", None, "Food Trucks x3, Cargo Truck x2", "Flooded Road"),
    ("TASK-014", "BRGY-131", "Emergency Logistics Prepositioning", "Medium", "Resolved", "TM-001", "Cargo Truck x1, MPVs/Sedans x1", ""),
    ("TASK-015", "BRGY-150", "Relief Goods Distribution", "Critical", "In Progress", "TM-001", "Food Trucks x3, Ambulances x1", "Flooded Road"),
    ("TASK-016", "BRGY-187", "Mobile Financial Assistance Payouts", "Low", "Pending", None, "MPVs/Sedans x1", ""),
    ("TASK-017", "BRGY-240", "Relief Goods Distribution", "High", "Resolved", "TM-002", "Food Trucks x2, Cargo Truck x1", "Road Blocked"),
    ("TASK-018", "BRGY-259", "Emergency Logistics Prepositioning", "High", "Pending", None, "Cargo Truck x2, Vans x2", "Road Blocked"),
    ("TASK-019", "BRGY-271", "Relief Goods Distribution", "Medium", "In Progress", "TM-002", "Food Trucks x1, Ambulances x1", ""),
    ("TASK-020", "BRGY-305", "Relief Goods Distribution", "High", "Pending", None, "Food Trucks x2, Cargo Truck x1", "Flooded Road"),
    ("TASK-021", "BRGY-321", "Emergency Logistics Prepositioning", "Medium", "Resolved", "TM-001", "Cargo Truck x1, Vans x1", ""),
    ("TASK-022", "BRGY-340", "Mobile Financial Assistance Payouts", "Low", "Pending", None, "MPVs/Sedans x2", ""),
    ("TASK-023", "BRGY-368", "Relief Goods Distribution", "High", "In Progress", "TM-001", "Food Trucks x2, Cargo Truck x1", "Heavy Traffic"),
    ("TASK-024", "BRGY-415", "Emergency Logistics Prepositioning", "Critical", "Pending", None, "Cargo Truck x3, Ambulances x1", "Road Blocked"),
    ("TASK-025", "BRGY-468", "Relief Goods Distribution", "High", "Resolved", "TM-002", "Food Trucks x3, Vans x1", ""),
    ("TASK-026", "BRGY-508", "Relief Goods Distribution", "Medium", "In Progress", "TM-001", "Food Trucks x2", "Heavy Traffic"),
    ("TASK-027", "BRGY-552", "Emergency Logistics Prepositioning", "Critical", "Pending", None, "Cargo Truck x3, Vans x2", "Road Blocked"),
]

SEVERITY_PRIORITY = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Critical": 4,
}

RESPONSE_TYPES = {
    "Relief Goods Distribution": "Food Items (FFPs & RTEF)",
    "Emergency Logistics Prepositioning": "Prepositioning of Emergency Supplies",
    "Mobile Financial Assistance Payouts": "Assistance to Individuals in Crisis Situation (AICS) Cash Aid",
}

AFFECTED_BY_SEVERITY = {
    "Low": "1-10",
    "Medium": "11-50",
    "High": "50-100",
    "Critical": "100+",
}


def upsert_demo_report(index, spec, now):
    task_id, barangay_id, disaster_type, severity, status, team, resources, constraints = spec
    barangay = find_barangay(barangay_id)
    if not barangay:
        raise ValueError(f"{task_id}: barangay {barangay_id} was not found in the CSV")

    existing = DisasterReport.query.filter_by(task_id=task_id).first()
    if existing and DEMO_MARKER not in (existing.notes or ""):
        return "skipped", task_id, f"existing non-demo task at {existing.location}"

    report = existing or DisasterReport(task_id=task_id)
    submitted_at = now - dt.timedelta(minutes=(len(DEMO_REPORTS) - index) * 9)
    assigned_team = None if status == "Pending" else team

    report.disaster_type = disaster_type
    report.severity = severity
    report.lat = barangay.lat
    report.lon = barangay.lon
    report.location = barangay.label
    report.municipality_code = barangay.municipality_code
    report.barangay_id = barangay.barangay_id
    report.barangay_name = barangay.barangay
    report.full_address = barangay.label
    report.resources = resources
    report.constraints = constraints
    report.status = status
    report.priority = SEVERITY_PRIORITY[severity]
    report.date_submitted = submitted_at
    report.assigned_team = assigned_team
    report.date_str = submitted_at.strftime("%m/%d/%Y")
    report.day_str = submitted_at.strftime("%A")
    report.time_str = submitted_at.strftime("%I:%M %p")
    report.affected = AFFECTED_BY_SEVERITY[severity]
    report.response_type = RESPONSE_TYPES[disaster_type]
    report.notes = (
        f"{DEMO_MARKER}\n"
        f"Seeded demo case for analytics coverage: {barangay.label}."
    )

    if not existing:
        db.session.add(report)
        return "inserted", task_id, barangay.label
    return "updated", task_id, barangay.label


def main():
    app = create_app()
    now = dt.datetime.utcnow()
    results = []
    with app.app_context():
        for index, spec in enumerate(DEMO_REPORTS):
            results.append(upsert_demo_report(index, spec, now))
        db.session.commit()

        total = DisasterReport.query.count()

    for status, task_id, detail in results:
        print(f"{status:8} {task_id} - {detail}")
    print(f"\nReports in database: {total}")


if __name__ == "__main__":
    main()
