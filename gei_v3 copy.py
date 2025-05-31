# app.py

import threading
import numpy as np

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from dash import Dash, dcc, html, Input, Output
from flask import Flask

# ───────────────────────────────────────────────────────────────────────────────
# 1) CONFIGURATION
# ───────────────────────────────────────────────────────────────────────────────

# Hard‐coded Mapbox access token (your token here)
MAPBOX_TOKEN = "pk.eyJ1Ijoib3NhZG5paWsiLCJhIjoiY21iYkg3NHZ0MHV4YjJsc2JhNWYwZm45ZiJ9.tRVy_SOd_eKk4oEaZWTGFA"

# Create Flask server and mount Dash
server = Flask(__name__)
app = Dash(
    __name__,
    server=server,
    external_stylesheets=[dbc.themes.SANDSTONE],
    suppress_callback_exceptions=True,
)
app.title = "MapDisplay (Focused on Gdańsk)"

# ───────────────────────────────────────────────────────────────────────────────
# 2) BACKEND STATE (IN MEMORY)
# ───────────────────────────────────────────────────────────────────────────────

ships = {}
cameras = {}
_simulation_step = 0
_simulation_max_steps = 40

# ships[name] structure:
# {
#   "name": str,
#   "color": "#rrggbb",
#   "base_size": int,         # px
#   "label": str,
#   "custom_info": dict,      # e.g. {"Type": "Cargo"}
#   "sources": list[[lon,lat], ...],
#   "avg_coord": [lon, lat],
#   "spread": float,          # meters
#   "radius": float,          # px
#   "opacity": float,         # 0–1
#   "trace": list[[lon,lat], ...],
#   "show_trace": bool,
#   "highlight": bool,
#   "highlight_radius": float,# meters
#   "show_direction": bool,
#   "cone_angle": float,      # degrees
#   "cone_length": float,     # meters
#   "save_points": list[{ "coord": [lon, lat], "label": str }, ...]
# }

# cameras[name] structure:
# {
#   "name": str,
#   "coord": [lon, lat],
#   "range": float            # meters
# }


# ───────────────────────────────────────────────────────────────────────────────
# 2.1) UTILITY FUNCTIONS
# ───────────────────────────────────────────────────────────────────────────────
def haversine_distance_m(coord1, coord2):
    """
    Haversine distance (in meters) between two (lon, lat) pairs.
    """
    lon1, lat1 = coord1
    lon2, lat2 = coord2
    φ1, φ2 = np.radians(lat1), np.radians(lat2)
    Δφ = np.radians(lat2 - lat1)
    Δλ = np.radians(lon2 - lon1)
    a = np.sin(Δφ / 2) ** 2 + np.cos(φ1) * np.cos(φ2) * np.sin(Δλ / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    R = 6371000  # Earth radius in meters
    return R * c


def destination_point(lon, lat, bearing_deg, distance_m):
    """
    Compute destination (lon, lat) from a start point, bearing (deg), and distance (m).
    """
    R = 6371000
    δ = distance_m / R
    θ = np.radians(bearing_deg)
    φ1 = np.radians(lat)
    λ1 = np.radians(lon)

    sinφ2 = np.sin(φ1) * np.cos(δ) + np.cos(φ1) * np.sin(δ) * np.cos(θ)
    φ2 = np.arcsin(sinφ2)

    y = np.sin(θ) * np.sin(δ) * np.cos(φ1)
    x = np.cos(δ) - np.sin(φ1) * np.sin(φ2)
    λ2 = λ1 + np.arctan2(y, x)

    newLat = np.degrees(φ2)
    newLon = (np.degrees(λ2) + 540) % 360 - 180
    return [newLon, newLat]


# ───────────────────────────────────────────────────────────────────────────────
# 2.2) SHIP MANAGEMENT FUNCTIONS
# ───────────────────────────────────────────────────────────────────────────────
def add_ship(
    name: str,
    color: str = "#e74c3c",
    base_size: int = 12,
    label: str = None,
    initial_coord: list[float] = None,
    custom_info: dict = None,
):
    """
    Create a new ship entry. Raises ValueError if `name` already exists.
    """
    if name in ships:
        raise ValueError(f"Ship '{name}' already exists.")
    if initial_coord is None:
        initial_coord = [0.0, 0.0]
    if custom_info is None:
        custom_info = {}

    ships[name] = {
        "name": name,
        "color": color,
        "base_size": base_size,
        "label": label or name,
        "custom_info": custom_info.copy(),
        "sources": [],
        "avg_coord": initial_coord[:],
        "spread": 0.0,
        "radius": base_size,
        "opacity": 1.0,
        "trace": [initial_coord[:]],
        "show_trace": True,
        "highlight": False,
        "highlight_radius": 5000.0,  # meters
        "show_direction": False,
        "cone_angle": 30.0,          # degrees
        "cone_length": 20000.0,      # meters
        "save_points": [],
    }


def remove_ship(name: str):
    """
    Remove a ship by name (if it exists).
    """
    ships.pop(name, None)


def update_ship_position_from_sources(name: str, source_coords: list[list[float]]):
    """
    Given multiple [lon, lat] sources, compute:
      - average position
      - compute spread (max pairwise Haversine)
      - new radius px (based on spread)
      - new opacity (based on number of sources)
      - append to trace
      - update custom_info["Sources"]
    """
    if name not in ships or not source_coords:
        return

    ship = ships[name]
    lons = [pt[0] for pt in source_coords]
    lats = [pt[1] for pt in source_coords]
    avg_lon = sum(lons) / len(lons)
    avg_lat = sum(lats) / len(lats)
    ship["avg_coord"] = [avg_lon, avg_lat]

    # Compute spread (max pairwise distance)
    if len(source_coords) > 1:
        max_d = 0.0
        for i in range(len(source_coords)):
            for j in range(i + 1, len(source_coords)):
                d = haversine_distance_m(source_coords[i], source_coords[j])
                if d > max_d:
                    max_d = d
        ship["spread"] = max_d
    else:
        ship["spread"] = 0.0

    # Compute new radius px (cap at 20 km)
    max_spread = 20000.0
    spread_factor = min(ship["spread"] / max_spread, 1.0)
    ship["radius"] = ship["base_size"] * (1 + spread_factor)

    # Compute opacity (fewer sources → more opaque)
    max_sources = 10
    ship["opacity"] = max(
        0.2, min(1.0, 1.0 - (len(source_coords) / max_sources))
    )

    # Append to trace
    ship["trace"].append([avg_lon, avg_lat])

    # Update source count
    ship["sources"] = [pt[:] for pt in source_coords]
    ship["custom_info"]["Sources"] = len(source_coords)


def toggle_ship_trace(name: str, show: bool):
    if name in ships:
        ships[name]["show_trace"] = show


def toggle_ship_highlight(name: str, highlight: bool, radius_m: float = None):
    if name in ships:
        ships[name]["highlight"] = highlight
        if radius_m is not None:
            ships[name]["highlight_radius"] = radius_m


def toggle_ship_direction(
    name: str, show: bool, angle_deg: float = None, length_m: float = None
):
    if name in ships:
        ships[name]["show_direction"] = show
        if angle_deg is not None:
            ships[name]["cone_angle"] = angle_deg
        if length_m is not None:
            ships[name]["cone_length"] = length_m


def save_ship_position(name: str):
    """
    Manually save a ship’s current avg_coord as a “save point.”
    """
    if name not in ships:
        return
    ship = ships[name]
    coord = ship["avg_coord"][:]
    label = f"{name}—Pt{len(ship['save_points'])+1}"
    ship["save_points"].append({"coord": coord, "label": label})


# ───────────────────────────────────────────────────────────────────────────────
# 2.3) CAMERA MANAGEMENT FUNCTIONS
# ───────────────────────────────────────────────────────────────────────────────
def add_camera(name: str, coord: list[float], range_km: float = 10.0):
    """
    Create a new camera with detection range in kilometers.
    """
    if name in cameras:
        raise ValueError(f"Camera '{name}' already exists.")
    cameras[name] = {"name": name, "coord": coord[:], "range": range_km * 1000.0}


def remove_camera(name: str):
    cameras.pop(name, None)


def update_camera(name: str, coord: list[float] = None, range_km: float = None):
    if name not in cameras:
        return
    if coord is not None:
        cameras[name]["coord"] = coord[:]
    if range_km is not None:
        cameras[name]["range"] = range_km * 1000.0


# ───────────────────────────────────────────────────────────────────────────────
# 2.4) SIMULATION LOOP (BACKGROUND)
# ───────────────────────────────────────────────────────────────────────────────
def _simulate_movement():
    """
    Every 0.3 seconds, move “Alpha” and “Beta” exactly as in your original loop.
    """
    global _simulation_step

    if _simulation_step >= _simulation_max_steps:
        return

    # Move “Alpha”
    if "Alpha" in ships:
        base_x = 18.5 + _simulation_step * 0.01
        base_y = 54.5 + _simulation_step * 0.005
        sources_alpha = [
            [base_x, base_y],
            [base_x + 0.003, base_y - 0.003],
            [base_x - 0.002, base_y + 0.002],
        ]
        update_ship_position_from_sources("Alpha", sources_alpha)

    # Move “Beta”
    if "Beta" in ships:
        if _simulation_step < 10:
            base_x_b = 18.8 + _simulation_step * 0.015
            sources_beta = [[base_x_b, 54.4], [base_x_b + 0.001, 54.4]]
        else:
            base_x_b = 18.8 + _simulation_step * 0.015
            sources_beta = [
                [base_x_b, 54.7],
                [base_x_b + 0.001, 54.8],
                [base_x_b + 0.001, 54.8],
                [base_x_b + 0.001, 54.8],
                [base_x_b + 0.001, 54.8],
                [base_x_b + 0.001, 54.8],
                [base_x_b + 0.001, 54.8],
                [base_x_b + 0.001, 54.8],
            ]
        update_ship_position_from_sources("Beta", sources_beta)

    # At step 5, save each ship’s position
    if _simulation_step == 5:
        save_ship_position("Alpha")
        save_ship_position("Beta")

    _simulation_step += 1
    threading.Timer(0.3, _simulate_movement).start()


def start_simulation():
    """
    Pre-add “Alpha,” “Beta,” and two cameras, then start the 0.3 s loop.
    """
    add_ship(
        name="Alpha",
        color="#e67e22",
        base_size=14,
        label="Alpha",
        initial_coord=[18.5, 54.5],
        custom_info={"Type": "Cargo"},
    )
    add_ship(
        name="Beta",
        color="#3498db",
        base_size=14,
        label="Beta",
        initial_coord=[18.8, 54.4],
        custom_info={"Type": "Tanker"},
    )
    add_camera(name="Camera 1", coord=[19.0, 54.6], range_km=7.0)
    add_camera(name="Camera 2", coord=[18.7, 54.7], range_km=5.0)

    threading.Timer(0.3, _simulate_movement).start()


# ───────────────────────────────────────────────────────────────────────────────
# 3) DASH LAYOUT (MAP ONLY)
# ───────────────────────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H2(
                    "MapDisplay (Focused on Gdańsk)",
                    className="text-center mt-3 mb-2",
                ),
                width=12,
            )
        ),
        dbc.Row(
            dbc.Col(
                [
                    # Interval triggers map refresh once per second
                    dcc.Interval(id="interval-simulate", interval=1000, n_intervals=0),
                    # Graph that holds our Mapbox figure
                    # The callback will immediately set its layout to Gdańsk+zoom+bounds.
                    dcc.Graph(
                        id="map-graph",
                        style={"width": "100%", "height": "90vh"},
                    ),
                ],
                width=12,
            )
        ),
    ],
    fluid=True,
)


# ───────────────────────────────────────────────────────────────────────────────
# 4) DASH CALLBACK (RENDER MAP)
# ───────────────────────────────────────────────────────────────────────────────
@app.callback(
    Output("map-graph", "figure"),
    Input("interval-simulate", "n_intervals"),
)
def update_map(n_intervals):
    """
    Rebuilds and returns a Plotly Figure (Mapbox via Maplibre) using current `ships` and `cameras`.
    Fired once per second by the Interval.
    """

    # 1) Start with a brand‐new Figure and immediately set:
    #    - mapbox.bounds to lock the view over Gdańsk (18.0–19.5 E, 54.0–55.0 N)
    #    - uirevision="lock" so Plotly never auto‐zoom/center on data.
    fig = go.Figure()
    fig.update_layout(
        map=dict(
    style="open-street-map",                # or any Maplibre style URL
    center={"lon": 18.65, "lat": 54.35},
    zoom=10,
),
        uirevision="lock",
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )

    local_ships = ships
    local_cameras = cameras

    # 2) Prepare ship marker data
    ship_lons, ship_lats = [], []
    ship_colors, ship_sizes, ship_opacities, ship_texts = [], [], [], []

    # 3) Ship traces (lines)
    trace_data = []

    # 4) Save points
    save_lons, save_lats, save_texts = [], [], []

    # 5) Direction cones
    cone_polygons = []

    # 6) Highlight circles
    highlight_polygons = []

    # 7) Cameras
    cam_lons, cam_lats, cam_colors, cam_ranges = [], [], [], []

    # — Process each ship
    for name, s in local_ships.items():
        lon, lat = s["avg_coord"]
        ship_lons.append(lon)
        ship_lats.append(lat)
        ship_colors.append(s["color"])
        ship_sizes.append(s["radius"])
        ship_opacities.append(s["opacity"])

        # Build hover text
        info_lines = [f"<b>{s['label']}</b>"]
        for k, v in s["custom_info"].items():
            info_lines.append(f"{k}: {v}")
        info_lines.append(f"Sources: {len(s['sources'])}")
        ship_texts.append("<br>".join(info_lines))

        # (a) Trace (line)
        if s["show_trace"] and len(s["trace"]) > 1:
            coords = np.array(s["trace"])
            trace_data.append(
                go.Scattermap(
                    lon=coords[:, 0],
                    lat=coords[:, 1],
                    mode="lines",
                    line={"color": s["color"], "width": 2},
                    hoverinfo="none",
                    showlegend=False,
                )
            )

        # (b) Save points
        for sp in s["save_points"]:
            save_lons.append(sp["coord"][0])
            save_lats.append(sp["coord"][1])
            save_texts.append(sp["label"])

        # (c) Direction cones
        if s["show_direction"] and len(s["trace"]) >= 2:
            prev_pt = s["trace"][-2]
            curr_pt = s["avg_coord"]
            dx = curr_pt[0] - prev_pt[0]
            dy = curr_pt[1] - prev_pt[1]
            if dx != 0 or dy != 0:
                heading = np.degrees(np.arctan2(dy, dx))
                half_angle = s["cone_angle"] / 2.0
                left_bearing = heading - half_angle
                right_bearing = heading + half_angle
                p1 = destination_point(lon, lat, left_bearing, s["cone_length"])
                p2 = destination_point(lon, lat, right_bearing, s["cone_length"])
                cone_polygons.append(
                    {
                        "lons": [lon, p1[0], p2[0], lon],
                        "lats": [lat, p1[1], p2[1], lat],
                        "color": s["color"],
                    }
                )

        # (d) Highlight circle
        if s["highlight"]:
            R = s["highlight_radius"]
            circle_pts = []
            num_segments = 64
            for i in range(num_segments):
                θ = (i / num_segments) * 360.0
                px, py = destination_point(lon, lat, θ, R)
                circle_pts.append([px, py])
            circle_pts.append(circle_pts[0])
            circle_lons = [pt[0] for pt in circle_pts]
            circle_lats = [pt[1] for pt in circle_pts]
            highlight_polygons.append(
                {"lons": circle_lons, "lats": circle_lats, "color": s["color"]}
            )

    # — Process each camera
    for cname, cam in local_cameras.items():
        lonc, latc = cam["coord"]
        status = "ok"
        for s in local_ships.values():
            d = haversine_distance_m(cam["coord"], s["avg_coord"])
            if d <= cam["range"]:
                status = "alert"
                break
        cam_lons.append(lonc)
        cam_lats.append(latc)
        cam_colors.append("#2ecc71" if status == "alert" else "#000000")
        cam_ranges.append(cam["range"])

    # 1) Add ship traces
    for trace in trace_data:
        fig.add_trace(trace)

    # 2) Add direction cones
    for cone in cone_polygons:
        fig.add_trace(
            go.Scattermap(
                lon=cone["lons"],
                lat=cone["lats"],
                mode="lines",
                fill="toself",
                fillcolor=cone["color"],
                line={"width": 0},
                opacity=0.2,
                hoverinfo="none",
                showlegend=False,
            )
        )

    # 3) Add highlight circles
    for circ in highlight_polygons:
        fig.add_trace(
            go.Scattermap(
                lon=circ["lons"],
                lat=circ["lats"],
                mode="lines",
                fill="toself",
                fillcolor=circ["color"],
                line={"width": 0},
                opacity=0.1,
                hoverinfo="none",
                showlegend=False,
            )
        )

    # 4) Add save points (gray markers + text)
    if save_lons:
        fig.add_trace(
            go.Scattermap(
                lon=save_lons,
                lat=save_lats,
                mode="markers+text",
                marker={"color": "#7f8c8d", "size": 6},
                text=save_texts,
                textposition="top center",
                textfont={"size": 10, "color": "#7f8c8d"},
                hoverinfo="none",
                showlegend=False,
            )
        )

    # 5) Add cameras (triangle symbols)
    if cam_lons:
        fig.add_trace(
            go.Scattermap(
                lon=cam_lons,
                lat=cam_lats,
                mode="markers",
                marker={
                    "size": 24,
                    "color": cam_colors,
                    "symbol": "triangle-up",
                    "opacity": 1.0,
                },
                hovertemplate="<b>Camera</b><br>Lon: %{lon:.4f}<br>Lat: %{lat:.4f}<extra></extra>",
                name="Cameras",
            )
        )
        # 5a) Add camera‐range circles
        for idx, crange in enumerate(cam_ranges):
            center = [cam_lons[idx], cam_lats[idx]]
            pts = []
            for i in range(64):
                θ = (i / 64) * 360.0
                px, py = destination_point(center[0], center[1], θ, crange)
                pts.append([px, py])
            pts.append(pts[0])
            lons = [p[0] for p in pts]
            lats = [p[1] for p in pts]
            fig.add_trace(
                go.Scattermap(
                    lon=lons,
                    lat=lats,
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(46, 204, 113, 0.1)",
                    line={"width": 1, "color": "rgba(46, 204, 113, 0.5)"},
                    hoverinfo="none",
                    showlegend=False,
                )
            )

    # 6) Finally, add ship markers on top
    if ship_lons:
        fig.add_trace(
            go.Scattermap(
                lon=ship_lons,
                lat=ship_lats,
                mode="markers",
                marker={
                    "size": ship_sizes,
                    "color": ship_colors,
                    "opacity": ship_opacities,
                    "symbol": "circle",
                    "sizemode": "area",
                    "sizeref": 1,
                },
                text=ship_texts,
                hoverinfo="text",
                name="Ships",
            )
        )

    return fig


# ───────────────────────────────────────────────────────────────────────────────
# 5) MAIN ENTRYPOINT
# ───────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Kick off simulation (adds “Alpha,” “Beta,” “Camera 1,” “Camera 2”)
    start_simulation()

    # Run the Dash server (use app.run, not app.run_server)
    app.run(host="0.0.0.0", port=8050, debug=True)
