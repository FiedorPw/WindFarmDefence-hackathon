# app.py ───────────────────────────────────────────────────────────────────────
"""
Dash + Plotly Maplibre demo (Gdańsk viewport, dashed traces workaround).

• Ship markers   enlarged  (SHIP_DOT_FACTOR)
• Traces         faux-dashed by inserting None points
• Cameras        gray  ➝ green when ship in range
• Map container  layout.map   (no Mapbox token required)
"""

import threading
from math import radians, sin, cos, atan2, sqrt, degrees, asin, atan2 as atan2_
import numpy as np
import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
from flask import Flask

# ───────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ───────────────────────────────────────────────────────────────────────────────
SHIP_DOT_FACTOR = 8          # multiply base size
CAM_RANGE_SEGMENTS = 64
EARTH_R = 6_371_000  # meters
VIEW_CENTER = {"lon": 18.65, "lat": 54.35}
VIEW_ZOOM = 10

# ───────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ───────────────────────────────────────────────────────────────────────────────
def haversine_m(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    lat1, lat2 = radians(lat1), radians(lat2)
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_R * atan2(sqrt(h), sqrt(1 - h))


def destination(lon, lat, bearing_deg, dist_m):
    br, lat1, lon1 = radians(bearing_deg), radians(lat), radians(lon)
    ang = dist_m / EARTH_R
    sin_lat2 = sin(lat1) * cos(ang) + cos(lat1) * sin(ang) * cos(br)
    lat2 = atan2_(sin_lat2, sqrt(1 - sin_lat2 ** 2))
    lon2 = lon1 + atan2_(sin(br) * sin(ang) * cos(lat1),
                         cos(ang) - sin(lat1) * sin(lat2))
    return [(degrees(lon2) + 540) % 360 - 180, degrees(lat2)]


def dashify(coords, seg_len=1):
    """
    Return lon[], lat[] with None inserted every `seg_len` vertices
    to make a dashed polyline.
    """
    lons, lats = [], []
    for i, (lo, la) in enumerate(coords):
        lons.append(lo)
        lats.append(la)
        if i % (seg_len * 2) == seg_len * 2 - 1:  # end of visible dash
            lons.append(None)
            lats.append(None)
    return lons, lats


# ───────────────────────────────────────────────────────────────────────────────
# Flask + Dash
# ───────────────────────────────────────────────────────────────────────────────
server = Flask(__name__)
app: Dash = Dash(__name__, server=server,
                 external_stylesheets=[dbc.themes.SANDSTONE])
app.title = "MapDisplay (Gdańsk)"

# ───────────────────────────────────────────────────────────────────────────────
# Data stores
# ───────────────────────────────────────────────────────────────────────────────
ships, cameras = {}, {}
_step, STEP_MAX = 0, 80


def add_ship(name, lon, lat, color, info=None):
    ships[name] = {
        "color": color,
        "radius": 12,
        "coord": [lon, lat],
        "trace": [[lon, lat]],
        "info": info or {},
    }


def add_camera(name, lon, lat, km_range=15):
    cameras[name] = {"coord": [lon, lat], "range": km_range * 1000}


def set_ship_from_sources(name, sources):
    if name not in ships or not sources:
        return
    lon = sum(p[0] for p in sources) / len(sources)
    lat = sum(p[1] for p in sources) / len(sources)
    ship = ships[name]
    ship["coord"] = [lon, lat]
    ship["trace"].append([lon, lat])
    if len(sources) > 1:
        spread = max(haversine_m(a, b)
                     for i, a in enumerate(sources)
                     for b in sources[i + 1:])
        ship["radius"] = 12 + spread / 1000
    ship["info"]["Sources"] = len(sources)


def sim_step():
    global _step
    if _step >= STEP_MAX:
        return
    # Alpha
    bx, by = 18.5 + _step * 0.01, 54.5 + _step * 0.005
    alpha_src = [[bx, by], [bx + 0.003, by - 0.003], [bx - 0.002, by + 0.002]]
    set_ship_from_sources("Alpha", alpha_src)
    # Beta
    bx = 18.8 + _step * 0.015
    beta_src = ([[bx, 54.4], [bx + 0.001, 54.4]]
                if _step < 10 else [[bx, 54.7]] + [[bx + 0.001, 54.8]] * 7)
    set_ship_from_sources("Beta", beta_src)
    _step += 1
    threading.Timer(0.3, sim_step).start()


def start_sim():
    add_ship("Alpha", 18.5, 54.5, "#e67e22", {"Type": "Cargo"})
    add_ship("Beta", 18.8, 54.4, "#3498db", {"Type": "Tanker"})
    add_camera("Cam 1", 19.0, 54.6, 15)
    add_camera("Cam 2", 18.7, 54.7, 15)
    sim_step()


# ───────────────────────────────────────────────────────────────────────────────
# Layout
# ───────────────────────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    [
        dbc.Row(dbc.Col(html.H2("MapDisplay (Gdańsk)",
                                className="text-center mt-3"))),
        dbc.Row(
            dbc.Col(
                [
                    dcc.Interval(id="tick", interval=1000, n_intervals=0),
                    dcc.Graph(id="graph", style={"height": "90vh"}),
                ]
            )
        ),
    ],
    fluid=True,
)

# ───────────────────────────────────────────────────────────────────────────────
# Callback
# ───────────────────────────────────────────────────────────────────────────────
@app.callback(Output("graph", "figure"), Input("tick", "n_intervals"))
def redraw(n):
    fig = go.Figure()
    fig.update_layout(
        map=dict(style="open-street-map",
                 center=VIEW_CENTER, zoom=VIEW_ZOOM),
        uirevision="lock",
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )

    # ── dashed traces
    for s in ships.values():
        if len(s["trace"]) > 1:
            dash_lon, dash_lat = dashify(s["trace"], seg_len=1)
            fig.add_trace(
                go.Scattermap(lon=dash_lon, lat=dash_lat,
                              mode="lines",
                              line=dict(color=s["color"], width=1),
                              hoverinfo="none", showlegend=False)
            )

    # ── camera symbols + range
    cam_lon, cam_lat, cam_color, meta = [], [], [], []
    for c in cameras.values():
        tri = "#7f8c8d"
        fill = "rgba(127,140,141,0.10)"
        line = "rgba(127,140,141,0.40)"
        if any(haversine_m(c["coord"], s["coord"]) <= c["range"]
               for s in ships.values()):
            tri = "#2ecc71"
            fill = "rgba(46,204,113,0.10)"
            line = "rgba(46,204,113,0.50)"
        cam_lon.append(c["coord"][0])
        cam_lat.append(c["coord"][1])
        cam_color.append(tri)
        meta.append({"R": c["range"], "fill": fill, "line": line})

    if cam_lon:
        fig.add_trace(
            go.Scattermap(lon=cam_lon, lat=cam_lat, mode="markers",
                          marker=dict(symbol="triangle-up",
                                      size=24, color=cam_color),
                          hovertemplate="<b>Camera</b><br>Lon:%{lon:.4f}<br>"
                                        "Lat:%{lat:.4f}<extra></extra>"))
        for lon, lat, m in zip(cam_lon, cam_lat, meta):
            lons, lats = [], []
            for i in range(CAM_RANGE_SEGMENTS + 1):
                ang = 360 * i / CAM_RANGE_SEGMENTS
                x, y = destination(lon, lat, ang, m["R"])
                lons.append(x); lats.append(y)
            fig.add_trace(
                go.Scattermap(lon=lons, lat=lats, mode="lines",
                              fill="toself", fillcolor=m["fill"],
                              line=dict(color=m["line"], width=1),
                              hoverinfo="none", showlegend=False)
            )

    # ── ship markers
    if ships:
        fig.add_trace(
            go.Scattermap(
                lon=[s["coord"][0] for s in ships.values()],
                lat=[s["coord"][1] for s in ships.values()],
                mode="markers",
                marker=dict(
                    size=[s["radius"] * SHIP_DOT_FACTOR for s in ships.values()],
                    color=[s["color"] for s in ships.values()],
                    opacity=0.9,
                    symbol="circle",
                    sizemode="area",
                ),
                text=[
                    "<br>".join([f"<b>{name}</b>"]
                                 + [f"{k}: {v}" for k, v in s["info"].items()])
                    for name, s in ships.items()
                ],
                hoverinfo="text",
            )
        )
    return fig


# ───────────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    start_sim()
    app.run(host="0.0.0.0", port=8050, debug=True)
