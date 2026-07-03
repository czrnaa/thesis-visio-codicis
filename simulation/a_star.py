import csv
import heapq
import math
import os
import time  # compute execution times

# --- REPORTLAB IMPORTS FOR PDF GENERATION ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


# --- CUSTOM PSEUDO-RANDOM NUMBER GENERATOR (LCG) ---
class LinearCongruentialGenerator:
    """Implements the GLIBC/GCC standard LCG algorithm to replace the random module."""

    def __init__(self, seed=42):
        self.state = seed
        # GLIBC / GCC specification standards
        self.m = 2**31        # Modulus
        self.a = 1103515245   # Multiplier
        self.c = 12345        # Increment

    def next_state(self):
        """Computes and updates the next linear congruential pseudo-random state."""
        self.state = (self.a * self.state + self.c) % self.m
        return self.state

    def choice(self, sequence):
        """Custom equivalent to random.choice using the LCG state to resolve indices."""
        if not sequence:
            raise IndexError("Cannot select an item from an empty sequence.")
        # Scale the pseudo-random integer state to fit within sequence boundaries
        random_index = self.next_state() % len(sequence)
        return sequence[random_index]


class GraphAStarPathfinder:

    def __init__(self, csv_filename="bulacan_dataset.csv"):
        self.locations = {}
        self.connections = {}
        self._load_dataset_from_csv(csv_filename)

    def _load_dataset_from_csv(self, csv_filename):
        """Parses a node-list CSV file with embedded connections to construct the network graph."""
        try:
            with open(csv_filename, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                reader.fieldnames = (
                    [field.strip().lower() for field in reader.fieldnames]
                    if reader.fieldnames
                    else []
                )
                raw_connections = {}

                for row in reader:
                    node_name = row["node name"].strip()
                    self.locations[node_name] = {
                        "lat": float(row["latitude"]),
                        "lon": float(row["longitude"]),
                    }
                    raw_connections[node_name] = row.get(
                        "graph connections", ""
                    ).strip()

                for node_name, connection_str in raw_connections.items():
                    if not connection_str:
                        continue
                    cleaned_str = (
                        connection_str.replace("[", "")
                        .replace("]", "")
                        .replace("'", "")
                        .replace('"', "")
                    )
                    delimiter = ";" if ";" in cleaned_str else ","
                    neighbors = [
                        n.strip()
                        for n in cleaned_str.split(delimiter)
                        if n.strip()
                    ]

                    if node_name not in self.connections:
                        self.connections[node_name] = []

                    for neighbor in neighbors:
                        if neighbor in self.locations:
                            if neighbor not in self.connections[node_name]:
                                self.connections[node_name].append(neighbor)
                            if neighbor not in self.connections:
                                self.connections[neighbor] = []
                            if node_name not in self.connections[neighbor]:
                                self.connections[neighbor].append(node_name)
            print(
                f"Successfully mapped {len(self.locations)} nodes and edges from your node list layout.\n"
            )
        except FileNotFoundError:
            raise FileNotFoundError(f"Error: '{csv_filename}' not found.")
        except KeyError as e:
            raise KeyError(
                f"Missing expected column header in CSV layout: {e}\n"
                f"Make sure headers match: ['node name', 'latitude', 'longitude', 'graph connections']"
            )

    def _haversine_distance(self, node_a, node_b):
        """Calculates the great-circle distance between two GPS points in kilometers."""
        lat1, lon1 = (
            self.locations[node_a]["lat"],
            self.locations[node_a]["lon"],
        )
        lat2, lon2 = (
            self.locations[node_b]["lat"],
            self.locations[node_b]["lon"],
        )
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(
            math.radians(lat1)
        ) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

    def find_path(self, start, goal):
        """Executes A* on the network graph using GPS-based heuristics."""
        if start not in self.locations or goal not in self.locations:
            return None, 0, 0.0

        open_set = []
        heapq.heappush(open_set, (0.0, start))
        came_from = {}
        g_score = {node: float("inf") for node in self.locations}
        g_score[start] = 0.0
        f_score = {node: float("inf") for node in self.locations}
        f_score[start] = self._haversine_distance(start, goal)

        open_set_hash = {start}
        nodes_expanded = 0

        while open_set:
            _, current = heapq.heappop(open_set)
            if current in open_set_hash:
                open_set_hash.remove(current)

            nodes_expanded += 1

            if current == goal:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.append(start)
                return path[::-1], nodes_expanded, g_score[goal]

            for neighbor in self.connections.get(current, []):
                move_cost = self._haversine_distance(current, neighbor)
                tentative_g = g_score[current] + move_cost

                if tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = (
                        tentative_g + self._haversine_distance(neighbor, goal)
                    )

                    if neighbor not in open_set_hash:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
                        open_set_hash.add(neighbor)

        return None, nodes_expanded, 0.0

    def find_dijkstra_cost(self, start, goal):
        """Standard Dijkstra algorithm deployment to establish absolute ground-truth shortest paths."""
        if start not in self.locations or goal not in self.locations:
            return float("inf")
        pq = [(0.0, start)]
        distances = {node: float("inf") for node in self.locations}
        distances[start] = 0.0
        while pq:
            current_dist, current_node = heapq.heappop(pq)
            if current_node == goal:
                return current_dist
            if current_dist > distances[current_node]:
                continue
            for neighbor in self.connections.get(current_node, []):
                cost = self._haversine_distance(current_node, neighbor)
                if distances[current_node] + cost < distances[neighbor]:
                    distances[neighbor] = distances[current_node] + cost
                    heapq.heappush(pq, (distances[neighbor], neighbor))
        return distances[goal]


def generate_results_pdf(
    output_filename="astar_performance_report.pdf", total_scenarios=30
):
    """Runs route simulations via LCG environment generation and exports performance data to a styled PDF."""
    DATASET_FILE = "bulacan_dataset.csv"
    pathfinder = GraphAStarPathfinder(csv_filename=DATASET_FILE)
    all_nodes = list(pathfinder.locations.keys())

    # int seed
    lcg = LinearCongruentialGenerator(seed=int(time.time()))

    total_time_ms = 0.0
    total_nodes_expanded = 0
    optimal_paths_count = 0
    successful_runs = 0

    # Data collection arrays for ReportLab tables
    table_data = [
        ["No.", "Start Node", "Goal Node", "Cost", "Expanded", "Time", "Status"]
    ]

    for i in range(1, total_scenarios + 1):
        # Utilizes custom LCG algorithm to programmatically generate pseudo-random coordinate pairings
        start = lcg.choice(all_nodes)
        goal = lcg.choice(all_nodes)

        while start == goal:
            goal = lcg.choice(all_nodes)

        start_time = time.perf_counter()
        path, expanded, total_cost = pathfinder.find_path(start, goal)
        execution_time_ms = (time.perf_counter() - start_time) * 1000.0

        if path:
            status = f"Found ({len(path)} moves)"
            cost_str = f"{total_cost:.2f} km"

            dijkstra_cost = pathfinder.find_dijkstra_cost(start, goal)
            if abs(total_cost - dijkstra_cost) < 1e-5:
                optimal_paths_count += 1

            successful_runs += 1
            total_time_ms += execution_time_ms
            total_nodes_expanded += expanded
            time_str = f"{execution_time_ms:.3f} ms"
        else:
            status = "No Path Found"
            cost_str = "N/A"
            time_str = "N/A"

        # Append row to the main simulation list
        table_data.append(
            [str(i), start, goal, cost_str, str(expanded), time_str, status]
        )

    # Compute aggregate metrics
    avg_time = total_time_ms / successful_runs if successful_runs > 0 else 0.0
    avg_nodes = (
        total_nodes_expanded / successful_runs if successful_runs > 0 else 0.0
    )
    optimality_rate = (
        (optimal_paths_count / successful_runs * 100.0)
        if successful_runs > 0
        else 0.0
    )

    # --- PDF GENERATION ASSEMBLY ---
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#2C5282"),
        spaceBefore=15,
        spaceAfter=8,
    )
    normal_style = styles["Normal"]

    # Document Header
    story.append(Paragraph("A* Routing Engine Performance Report", title_style))
    story.append(
        Paragraph(
            f"Dataset Analyzed: {DATASET_FILE} | Total Simulated Iterations: {total_scenarios} (LCG Generated)",
            normal_style,
        )
    )
    story.append(Spacer(1, 15))

    # Summary Metrics Table
    story.append(Paragraph("System Performance Metrics Summary", section_style))
    summary_data = [
        ["Metric Category", "Evaluated System Average"],
        ["Computational Time", f"{avg_time:.3f} ms"],
        ["Nodes Explored (Expanded)", f"{avg_nodes:.1f} nodes"],
        ["Path Optimality Rate", f"{optimality_rate:.1f}%"],
        ["Successful Resolutions", f"{successful_runs} / {total_scenarios}"],
    ]
    summary_table = Table(summary_data, colWidths=[200, 200])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#2C5282")),
                ("TEXTCOLOR", (0, 0), (1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.HexColor("#F7FAFC"), colors.white],
                ),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Detailed Scenario Log Breakdown", section_style))
    log_table = Table(table_data, colWidths=[30, 115, 115, 65, 55, 65, 95])
    log_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5568")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (1, 1), (2,-1), "LEFT"),  # Keep strings left-aligned
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.HexColor("#F7FAFC"), colors.white],
                ),
            ]
        )
    )
    story.append(log_table)

    # Build PDF
    doc.build(story)
    print(
        f"\n[PDF Generated Successfully] Results written cleanly to '{output_filename}'!"
    )


if __name__ == "__main__":
    generate_results_pdf("astar_performance_report.pdf", total_scenarios=30)