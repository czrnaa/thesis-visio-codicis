class UnitStatus:
    VALID_STATUSES = ["Active", "Standby", "Recovery", "Offline"]

    def __init__(self, unit_name, status="Standby"):
        self.unit_name = unit_name
        self.status = status if status in self.VALID_STATUSES else "Standby"

    def update_status(self, new_status):
        if new_status in self.VALID_STATUSES:
            self.status = new_status
            print(f"[INFO] {self.unit_name} status updated to {self.status}")
        else:
            print(f"[ERROR] Invalid status: {new_status}. Valid: {self.VALID_STATUSES}")

    def display_status(self):
        print(f"Unit: {self.unit_name} | Status: {self.status}")


class StatusManager:
    def __init__(self):
        self.units = {}

    def add_unit(self, unit_name, status="Standby"):
        if unit_name not in self.units:
            self.units[unit_name] = UnitStatus(unit_name, status)

    def update_unit_status(self, unit_name, status):
        if unit_name in self.units:
            self.units[unit_name].update_status(status)
        else:
            print(f"[ERROR] Unit {unit_name} not found.")

    def display_all_statuses(self):
        print("\n--- All Unit Statuses ---")
        if not self.units:
            print("No units registered.")
        for unit in self.units.values():
            unit.display_status()
        print("-------------------------")
