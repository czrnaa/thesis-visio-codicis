class DisasterReport:
    # Constructor updated to accept 'status' to prevent TypeError
    def __init__(self, disaster_type, location, value, lat, lon, priority, status="Pending"):
        self.disaster_type = disaster_type
        self.location = location
        self.value = value
        self.lat = lat
        self.lon = lon
        self.priority = priority
        self.status = status