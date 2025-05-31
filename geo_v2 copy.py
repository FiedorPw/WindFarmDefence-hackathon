import os
import math

import pandas as pd

from shapely.geometry import Point

import dash
from dash import dcc, html, Output, Input, State
import plotly.graph_objects as go

# -----------------------------------------------------------------------------------
# --- Configuration / Initial Data --------------------------------------------------
# -----------------------------------------------------------------------------------

# 1) MAP SETTINGS
MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN", "")  # Or replace with your token string
INITIAL_BOUNDS = {
    "min_lon": 18.0,
    "max_lon": 20.0,
    "min_lat": 54.0,
    "max_lat": 55.0,
}

# 2) INITIAL SHIP DEFINITIONS
#    Each ship has: name, initial lon/lat, color, size, highlight flag, show_trace, show_direction, info dict
INITIAL_SHIPS = [
    {
        "name": "Alpha",
        "lon": 18.5,
        "lat": 54.5,
        "color": "orange",
        "size": 12,           # marker size in px
        "highlight": True,
        "show_trace": True,
        "show_direction": True,
        "info": {
            "Type": "Cargo",
            "Speed": "12 kn",
            "Destination": "Gdańsk"
        }
    },
    {
        "name": "Beta",
        "lon": 18.8,
        "lat": 54.4,
        "color": "royalblue",
        "size": 10,
        "highlight": False,
        "show_trace": True,
        "show_direction": True,
        "info": {
            "Type": "Tanker",
            "Speed": "10 kn",
            "Destination": "Szczecin"
        }
    }
]

# 3) TRIANGLES (e.g. camera positions)
INITIAL_TRIANGLES = [
    {
        "name": "Camera 1",
        "lon": 19.0,
        "lat": 54.6,
        "color": "black",
        "size": 10
    }
]

# 4) SIMULATION PARAMETERS
UPDATE_INTERVAL_SEC = 0.5   # how often to update (in seconds)
TOTAL_STEPS = 60


# -----------------------------------------------------------------------------------
# --- “Backend”: Data structures + update logic ------------------------------------
# -----------------------------------------------------------------------------------

class ShipManager:
    """
    Manages ship states: current position, trace (history), direction, highlight, etc.
    Provides a method to simulate a small movement each step.
    """
    def __init__(self, ship_defs):
        # Convert list of dicts into a dict keyed by 'name'
        self.ships = {}
        for sd in ship_defs:
            self.ships[sd["name"]] = {
                "lon": sd["lon"],
                "lat": sd["lat"],
                "color": sd["color"],
                "size": sd["size"],
                "highlight": sd["highlight"],
                "show_trace": sd["show_trace"],
                "show_direction": sd["show_direction"],
                "info": sd["info"],
                # Internals:
                "trace": [(sd["lon"], sd["lat"])],
                "heading": None  # updated each move
            }

    def step_move(self):
        """
        Simulate moving each ship by a small delta.
        - "Alpha": moves NE
        - "Beta": moves E
        """
        for name in list(self.ships.keys()):
            s = self.ships[name]
            lon, lat = s["lon"], s["lat"]

            if name == "Alpha":
                dlon, dlat = 0.01, 0.005
            elif name == "Beta":
                dlon, dlat = 0.015, 0.0
            else:
                dlon, dlat = 0.0, 0.0

            new_lon = lon + dlon
            new_lat = lat + dlat

            # Compute heading if show_direction
            heading = None
            if s["show_direction"]:
                dx = new_lon - lon
                dy = new_lat - lat
                if dx != 0 or dy != 0:
                    heading = math.atan2(dy, dx)  # radians

            # Update
            s["lon"] = new_lon
            s["lat"] = new_lat
            s["heading"] = heading
            s["trace"].append((new_lon, new_lat))

    def get_dataframe(self):
        """
        Returns a pandas DataFrame of current ship positions + metadata for plotting.
        Now includes 'show_direction' so that update_map can check it.
        """
        rows = []
        for name, s in self.ships.items():
            rows.append({
                "name": name,
                "lon": s["lon"],
                "lat": s["lat"],
                "color": s["color"],
                "size": s["size"],
                "highlight": s["highlight"],
                "show_trace": s["show_trace"],
                "show_direction": s["show_direction"],   # <-- added
                "heading": s["heading"],
                "info": s["info"]
            })
        return pd.DataFrame(rows)

    def get_traces(self):
        """
        Returns a dict of traces (list of lon, lat pairs) for each ship that has show_trace=True.
        """
        traces = {}
        for name, s in self.ships.items():
            if s["show_trace"] and len(s["trace"]) > 1:
                traces[name] = s["trace"].copy()
        return traces


class TriangleManager:
    """
    Manages fixed triangle points (e.g. camera locations).
    In this demo, they never move.
    """
    def __init__(self, tri_defs):
        self.triangles = []
        for td in tri_defs:
            self.triangles.append({
                "name": td["name"],
                "lon": td["lon"],
                "lat": td["lat"],
                "color": td["color"],
                "size": td["size"]
            })


# Instantiate managers:
ship_mgr = ShipManager(INITIAL_SHIPS)
tri_mgr = TriangleManager(INITIAL_TRIANGLES)


# -----------------------------------------------------------------------------------
# --- “Frontend” (Dash app) ---------------------------------------------------------
# -----------------------------------------------------------------------------------

external_stylesheets = [
    "https://cdnjs.cloudflare.com/ajax/libs/normalize/8.0.1/normalize.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/skeleton/2.0.4/skeleton.min.css"
]

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server  # for deploying (e.g. to Heroku)


# Helper: build empty figure with correct map style and bounds
def create_base_figure():
    fig = go.Figure()

    # Set the map style & bounding box
    fig.update_layout(
        mapbox=dict(
            accesstoken=MAPBOX_TOKEN or None,
            style="carto-positron" if not MAPBOX_TOKEN else "mapbox://styles/mapbox/light-v10",
            center=dict(
                lon=(INITIAL_BOUNDS["min_lon"] + INITIAL_BOUNDS["max_lon"]) / 2,
                lat=(INITIAL_BOUNDS["min_lat"] + INITIAL_BOUNDS["max_lat"]) / 2
            ),
            zoom=8
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        hovermode="closest"
    )
    return fig


# Layout: Graph + Controls
app.layout = html.Div(
    style={"height": "100vh", "display": "flex", "flexDirection": "column"},
    children=[
        html.H3("📡 Ship Tracker Dashboard", style={"textAlign": "center", "marginTop": "10px"}),
        dcc.Graph(
            id="map-graph",
            figure=create_base_figure(),
            style={"flex": "1 1 auto"}
        ),
        html.Div(
            style={"padding": "10px", "textAlign": "center"},
            children=[
                html.Button("Start Animation", id="start-btn", n_clicks=0),
                html.Button("Stop Animation", id="stop-btn", n_clicks=0, style={"marginLeft": "10px"}),
            ]
        ),
        # Hidden Interval component for triggering updates
        dcc.Interval(id="interval-component", interval=UPDATE_INTERVAL_SEC * 1000, n_intervals=0, disabled=True),
        # Store current step count in dcc.Store
        dcc.Store(id="step-count", data=0)
    ]
)


@app.callback(
    Output("interval-component", "disabled"),
    Input("start-btn", "n_clicks"),
    Input("stop-btn", "n_clicks"),
    State("interval-component", "disabled"),
    prevent_initial_call=True
)
def toggle_interval(start_clicks, stop_clicks, is_disabled):
    """
    Enable the Interval when “Start” is clicked, disable when “Stop” is clicked.
    """
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_disabled
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if button_id == "start-btn":
        return False  # enable interval
    elif button_id == "stop-btn":
        return True   # disable interval
    return is_disabled


@app.callback(
    Output("step-count", "data"),
    Input("interval-component", "n_intervals"),
    State("step-count", "data")
)
def update_step(n_intervals, current_step):
    """
    Increment step count until TOTAL_STEPS; after that, keep it constant.
    """
    if current_step >= TOTAL_STEPS:
        return current_step
    return current_step + 1


@app.callback(
    Output("map-graph", "figure"),
    Input("step-count", "data")
)
def update_map(step):
    """
    Rebuilds the map figure each time step increases:
    - Move ships
    - Plot markers, highlights, traces, direction cones, triangles
    - Attach hover/click data
    """
    # 1) Simulate one step of movement (unless we've reached TOTAL_STEPS)
    if 0 < step <= TOTAL_STEPS:
        ship_mgr.step_move()

    # 2) Build the figure
    fig = create_base_figure()

    # 3) Plot each ship as a Scattermapbox trace
    ship_df = ship_mgr.get_dataframe()
    for idx, row in ship_df.iterrows():
        name = row["name"]
        lon = row["lon"]
        lat = row["lat"]
        color = row["color"]
        size = row["size"]
        highlight = row["highlight"]
        heading = row["heading"]
        info = row["info"]

        # 3a) If highlight=True, draw a semi‐transparent circle (Scattermapbox with bigger marker)
        if highlight:
            fig.add_trace(
                go.Scattermapbox(
                    lon=[lon],
                    lat=[lat],
                    mode="markers",
                    marker=dict(
                        size=size * 2,           # a bigger “halo”
                        color="rgba(255,0,0,0.2)",  # redish translucent
                        allowoverlap=True
                    ),
                    hoverinfo="none",
                    showlegend=False
                )
            )

        # 3b) Main ship marker
        hover_text = [f"<b>{name}</b><br>" + "<br>".join(f"{k}: {v}" for k, v in info.items())]
        fig.add_trace(
            go.Scattermapbox(
                lon=[lon],
                lat=[lat],
                mode="markers",
                marker=dict(
                    size=size,
                    color=color,
                    opacity=0.9,
                    symbol="circle"
                ),
                hoverinfo="text",
                hovertext=hover_text,
                name=name,
                customdata=[name],  # for potential click events later
            )
        )

        # 3c) Direction cone: draw as a filled triangle polygon if heading is available
        if row["show_direction"] and heading is not None:
            # create small triangle polygon points
            cone_length = 0.1  # degrees ~ approx 10km; tweak as needed
            cone_angle_deg = 30
            half_ang = math.radians(cone_angle_deg / 2)

            # apex at (lon, lat)
            x0, y0 = lon, lat
            left_ang = heading - half_ang
            right_ang = heading + half_ang

            x1 = x0 + cone_length * math.cos(left_ang)
            y1 = y0 + cone_length * math.sin(left_ang)
            x2 = x0 + cone_length * math.cos(right_ang)
            y2 = y0 + cone_length * math.sin(right_ang)

            # A polygon with three vertices (apex, left, right)
            fig.add_trace(
                go.Scattermapbox(
                    lon=[x0, x1, x2, x0],
                    lat=[y0, y1, y2, y0],
                    mode="lines",
                    fill="toself",
                    fillcolor=f"rgba({int(color_to_rgb(color)[0])},"
                              f"{int(color_to_rgb(color)[1])},"
                              f"{int(color_to_rgb(color)[2])}, 0.2)",
                    line=dict(width=0),
                    hoverinfo="none",
                    showlegend=False
                )
            )

    # 4) Plot traces (past routes) for each ship
    traces = ship_mgr.get_traces()
    for ship_name, pts in traces.items():
        lons = [pt[0] for pt in pts]
        lats = [pt[1] for pt in pts]
        fig.add_trace(
            go.Scattermapbox(
                lon=lons,
                lat=lats,
                mode="lines",
                line=dict(
                    width=2,
                    color=ship_mgr.ships[ship_name]["color"]
                ),
                hoverinfo="none",
                showlegend=False
            )
        )

    # 5) Plot triangles (camera positions) as small black triangles
    for tri in tri_mgr.triangles:
        fig.add_trace(
            go.Scattermapbox(
                lon=[tri["lon"]],
                lat=[tri["lat"]],
                mode="markers",
                marker=dict(
                    size=tri["size"],
                    color=tri["color"],
                    symbol="triangle"
                ),
                hoverinfo="text",
                hovertext=[f"{tri['name']}"],
                showlegend=False
            )
        )

    # 6) Adjust layout title to show current step
    fig.update_layout(
        title_text=f"Step {step} / {TOTAL_STEPS}",
        title_x=0.5
    )
    return fig


# -----------------------------------------------------------------------------------
# --- Utility: Convert a CSS‐style color name (e.g. "orange") to RGB tuple ------------
# -----------------------------------------------------------------------------------
# Plotly’s Polygon “fillcolor” requires RGBA format; to preserve your original “color” strings,
# we’ll do a quick mapping. For more robust handling, consider installing `webcolors`.
COLOR_NAME_TO_RGB = {
    "orange": (255, 165, 0),
    "royalblue": (65, 105, 225),
    "red": (255, 0, 0),
    "blue": (0, 0, 255),
    "black": (0, 0, 0),
    # add more as needed…
}

def color_to_rgb(name):
    """
    Returns an (R,G,B) tuple for a CSS‐style color.
    Defaults to black if unknown.
    """
    return COLOR_NAME_TO_RGB.get(name.lower(), (0, 0, 0))


# -----------------------------------------------------------------------------------
# --- Run the app -------------------------------------------------------------------
# -----------------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
