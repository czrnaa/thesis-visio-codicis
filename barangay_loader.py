import csv
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_BARANGAY_CSV = Path(__file__).resolve().parent / "data" / "bulacan_barangays_with_lat_lon.csv"


@dataclass(frozen=True)
class Barangay:
    barangay_id: str
    psgc_barangay_code: str
    municipality_code: str
    psgc_municipality_code: str
    municipality: str
    barangay: str
    lat: float
    lon: float
    region: str
    flood_risk: float
    traffic_risk: float
    vuln_risk: float
    source_url: str

    @property
    def label(self):
        return f"{self.barangay}, {self.municipality}"

    def to_dict(self):
        data = asdict(self)
        data["label"] = self.label
        return data


def _float_field(row, field_name):
    value = (row.get(field_name) or "").strip()
    if value == "":
        raise ValueError(f"Missing required numeric field '{field_name}' for {row.get('barangay_id')}")
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid numeric field '{field_name}'={value!r} for {row.get('barangay_id')}"
        ) from exc


def _text_field(row, field_name):
    value = (row.get(field_name) or "").strip()
    if value == "":
        raise ValueError(f"Missing required field '{field_name}'")
    return value


@lru_cache(maxsize=4)
def load_barangays(csv_path=str(DEFAULT_BARANGAY_CSV)):
    """Load and validate the Bulacan barangay CSV.

    Returns an immutable tuple of Barangay rows. The result is cached so Flask
    can call this repeatedly without rereading the CSV on every request.
    """
    path = Path(csv_path)
    barangays = []
    seen_ids = set()

    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for line_number, row in enumerate(reader, start=2):
            barangay_id = _text_field(row, "barangay_id")
            if barangay_id in seen_ids:
                raise ValueError(f"Duplicate barangay_id {barangay_id!r} on line {line_number}")
            seen_ids.add(barangay_id)

            lat = _float_field(row, "lat")
            lon = _float_field(row, "lon")
            if not (14.4 <= lat <= 15.4 and 120.4 <= lon <= 121.3):
                raise ValueError(
                    f"Coordinate outside expected Bulacan bounds for {barangay_id}: {lat}, {lon}"
                )

            barangays.append(
                Barangay(
                    barangay_id=barangay_id,
                    psgc_barangay_code=(row.get("psgc_barangay_code") or "").strip(),
                    municipality_code=_text_field(row, "municipality_code"),
                    psgc_municipality_code=(row.get("psgc_municipality_code") or "").strip(),
                    municipality=_text_field(row, "municipality"),
                    barangay=_text_field(row, "barangay"),
                    lat=lat,
                    lon=lon,
                    region=_text_field(row, "region"),
                    flood_risk=_float_field(row, "flood_risk"),
                    traffic_risk=_float_field(row, "traffic_risk"),
                    vuln_risk=_float_field(row, "vuln_risk"),
                    source_url=(row.get("source_url") or "").strip(),
                )
            )

    return tuple(barangays)


def clear_barangay_cache():
    """Clear cached CSV rows after editing the file during a running process."""
    load_barangays.cache_clear()


def get_municipalities(csv_path=str(DEFAULT_BARANGAY_CSV)):
    municipalities = {}
    for item in load_barangays(csv_path):
        entry = municipalities.setdefault(
            item.municipality_code,
            {"municipality_code": item.municipality_code, "municipality": item.municipality, "count": 0},
        )
        entry["count"] += 1
    return sorted(municipalities.values(), key=lambda item: item["municipality_code"])


def get_barangays_by_municipality(municipality_code, csv_path=str(DEFAULT_BARANGAY_CSV)):
    return [
        item
        for item in load_barangays(csv_path)
        if item.municipality_code == municipality_code
    ]


def find_barangay(barangay_id, csv_path=str(DEFAULT_BARANGAY_CSV)):
    for item in load_barangays(csv_path):
        if item.barangay_id == barangay_id:
            return item
    return None


def _haversine_km(lat1, lon1, lat2, lon2):
    radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(h))


def nearest_barangay(lat, lon, csv_path=str(DEFAULT_BARANGAY_CSV)):
    """Return (Barangay, distance_km) for the closest barangay coordinate."""
    target_lat = float(lat)
    target_lon = float(lon)
    best = None
    best_distance = float("inf")

    for item in load_barangays(csv_path):
        distance = _haversine_km(target_lat, target_lon, item.lat, item.lon)
        if distance < best_distance:
            best = item
            best_distance = distance

    return best, best_distance


def build_node_locations(csv_path=str(DEFAULT_BARANGAY_CSV)):
    """Build a NODE_LOCATIONS-style mapping keyed by barangay_id."""
    return {
        item.barangay_id: {
            "lat": item.lat,
            "lon": item.lon,
            "label": item.label,
            "municipality_code": item.municipality_code,
            "municipality": item.municipality,
            "barangay": item.barangay,
        }
        for item in load_barangays(csv_path)
    }


def build_risk_profile(csv_path=str(DEFAULT_BARANGAY_CSV)):
    """Build a BULACAN_RISK_PROFILE-style mapping keyed by barangay_id."""
    return {
        item.barangay_id: {
            "flood": item.flood_risk,
            "traffic": item.traffic_risk,
            "vuln": item.vuln_risk,
        }
        for item in load_barangays(csv_path)
    }


def build_node_regions(csv_path=str(DEFAULT_BARANGAY_CSV)):
    """Build a NODE_REGIONS-style mapping keyed by barangay_id."""
    return {item.barangay_id: item.region for item in load_barangays(csv_path)}


def build_graph_connections(csv_path=str(DEFAULT_BARANGAY_CSV), k_neighbors=5):
    """Build a synthetic barangay adjacency graph from nearest coordinates.

    This is a lightweight demo graph: every barangay is connected to its nearest
    k barangay centroids, then any disconnected components are stitched together
    by their closest cross-component pair. It is suitable for ABSRA/A* demos over
    the barangay dataset, but it is not a substitute for OSM road edges.
    """
    rows = load_barangays(csv_path)
    if not rows:
        return {}

    k = max(1, int(k_neighbors))
    adjacency = {item.barangay_id: set() for item in rows}

    distance_cache = {}

    def distance(a, b):
        key = tuple(sorted((a.barangay_id, b.barangay_id)))
        if key not in distance_cache:
            distance_cache[key] = _haversine_km(a.lat, a.lon, b.lat, b.lon)
        return distance_cache[key]

    for item in rows:
        nearest = sorted(
            (other for other in rows if other.barangay_id != item.barangay_id),
            key=lambda other: distance(item, other),
        )[:k]
        for other in nearest:
            adjacency[item.barangay_id].add(other.barangay_id)
            adjacency[other.barangay_id].add(item.barangay_id)

    def components():
        unseen = set(adjacency)
        groups = []
        while unseen:
            start = unseen.pop()
            stack = [start]
            group = {start}
            while stack:
                current = stack.pop()
                for neighbor in adjacency[current]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        group.add(neighbor)
                        stack.append(neighbor)
            groups.append(group)
        return groups

    row_by_id = {item.barangay_id: item for item in rows}
    groups = components()
    while len(groups) > 1:
        base = groups[0]
        best_pair = None
        best_distance = float("inf")
        best_group_index = None
        for group_index, group in enumerate(groups[1:], start=1):
            for left_id in base:
                left = row_by_id[left_id]
                for right_id in group:
                    right = row_by_id[right_id]
                    candidate_distance = distance(left, right)
                    if candidate_distance < best_distance:
                        best_distance = candidate_distance
                        best_pair = (left_id, right_id)
                        best_group_index = group_index
        left_id, right_id = best_pair
        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)
        groups[0] = groups[0] | groups[best_group_index]
        del groups[best_group_index]

    return {node: sorted(neighbors) for node, neighbors in adjacency.items()}


if __name__ == "__main__":
    rows = load_barangays()
    municipalities = get_municipalities()
    graph = build_graph_connections()
    print(f"Loaded {len(rows)} barangays across {len(municipalities)} municipalities/cities.")
    print(f"Generated {sum(len(v) for v in graph.values())} directed graph edges.")
    print(f"First: {rows[0].barangay_id} - {rows[0].label} ({rows[0].lat}, {rows[0].lon})")
    print(f"Last : {rows[-1].barangay_id} - {rows[-1].label} ({rows[-1].lat}, {rows[-1].lon})")
