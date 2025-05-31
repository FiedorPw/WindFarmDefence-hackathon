# app.py ──────────────────────────────────────────────────────────────────────
"""
Dash + Plotly Maplibre demo (Gdańsk viewport).

• Bigger ship markers           (SHIP_DOT_FACTOR)
• Faux-dashed traces            (dashify helper)
• Directional cones             (CONE_ANGLE_DEG, CONE_LENGTH_M)
• Camera triangles/circles      gray → green on proximity
• Marker opacity ∝ # sources    (min 0.2 → max 1.0)
"""

import threading
from math import radians, sin, cos, atan2, sqrt, degrees, atan2 as atan2_
import numpy as np
import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
from flask import Flask

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
SHIP_DOT_FACTOR   = 10       # multiply ship radius for visibility
MAX_SOURCES       = 8       # > this many = fully opaque
MIN_OPACITY       = 0.2     # 1 source ⇒ this opacity
CONE_ANGLE_DEG    = 40      # full fan angle
CONE_LENGTH_M     = 20_000  # 20 km
CAM_RANGE_SEGMENTS = 64
EARTH_R           = 6_371_000
VIEW_CENTER       = {"lon": 18.65, "lat": 54.35}
VIEW_ZOOM         = 10

# ──────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ──────────────────────────────────────────────────────────────────────────────
def haversine_m(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    lat1, lat2 = radians(lat1), radians(lat2)
    h = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2*EARTH_R*atan2(sqrt(h), sqrt(1-h))


def destination(lon, lat, bearing_deg, dist_m):
    br, lat1, lon1 = radians(bearing_deg), radians(lat), radians(lon)
    ang = dist_m / EARTH_R
    sin_lat2 = sin(lat1)*cos(ang) + cos(lat1)*sin(ang)*cos(br)
    lat2 = atan2_(sin_lat2, sqrt(1-sin_lat2**2))
    lon2 = lon1 + atan2_(sin(br)*sin(ang)*cos(lat1),
                         cos(ang)-sin(lat1)*sin(lat2))
    return [(degrees(lon2)+540)%360-180, degrees(lat2)]


def dashify(coords, seg_len=1):
    """Insert None to make dashed poly-line."""
    lons, lats = [], []
    for i, (lo, la) in enumerate(coords):
        lons.append(lo); lats.append(la)
        if i % (seg_len*2) == seg_len*2-1:
            lons.append(None); lats.append(None)
    return lons, lats


# ──────────────────────────────────────────────────────────────────────────────
# Flask + Dash
# ──────────────────────────────────────────────────────────────────────────────
server = Flask(__name__)
app: Dash = Dash(__name__, server=server,
                 external_stylesheets=[dbc.themes.SANDSTONE])
app.title = "MapDisplay (Gdańsk)"

# ──────────────────────────────────────────────────────────────────────────────
# Data stores
# ──────────────────────────────────────────────────────────────────────────────
ships, cameras = {}, {}
_step, STEP_MAX = 0, 80


def add_ship(name, lon, lat, color, info=None):
    ships[name] = {
        "color":  color,
        "radius": 22,
        "coord":  [lon, lat],
        "trace":  [[lon, lat]],
        "info":   info or {},
        "opacity": 1.0,         # will be updated in set_ship_from_sources
    }


def add_camera(name, lon, lat, km_range=15):
    cameras[name] = {"coord": [lon, lat], "range": km_range*1000}


def set_ship_from_sources(name, sources):
    if name not in ships or not sources:
        return
    lon = sum(p[0] for p in sources)/len(sources)
    lat = sum(p[1] for p in sources)/len(sources)
    ship = ships[name]
    ship["coord"] = [lon, lat]
    ship["trace"].append([lon, lat])

    # radius grows slightly with disagreement
    if len(sources) > 1:
        spread = max(haversine_m(a,b)
                     for i,a in enumerate(sources)
                     for b in sources[i+1:])
        ship["radius"] = 22 + spread/1000

    # opacity: linearly from MIN_OPACITY (1 src) → 1.0 (>=MAX_SOURCES)
    n = len(sources)
    frac = min(n-1, MAX_SOURCES-1) / (MAX_SOURCES-1) if MAX_SOURCES>1 else 1
    ship["opacity"] = MIN_OPACITY + (1-MIN_OPACITY)*frac

    ship["info"]["Sources"] = n


# ──────────────────────────────────────────────────────────────────────────────
# Dummy simulation
# ──────────────────────────────────────────────────────────────────────────────
def sim_step():
    global _step
    if _step >= STEP_MAX:
        return
    # Alpha path
    bx, by = 18.5+_step*0.01, 54.5+_step*0.005
    alpha_src = [[bx,by], [bx+0.003,by-0.003], [bx-0.002,by+0.002]]
    set_ship_from_sources("Alpha", alpha_src)
    # Beta path
    bx = 18.8+_step*0.015
    beta_src = ([[bx,54.4],[bx+0.001,54.4]]
                if _step<10 else [[bx,54.7]]+[[bx+0.001,54.8]]*7)
    set_ship_from_sources("Beta", beta_src)

    _step += 1
    threading.Timer(0.3, sim_step).start()


def start_sim():
    add_ship("Alpha", 18.5, 54.5, "#e67e22", {"Type":"Cargo"})
    add_ship("Beta", 18.8, 54.4, "#3498db", {"Type":"Tanker"})
    add_camera("Cam 1", 19.0, 54.6, 15)
    add_camera("Cam 2", 18.7, 54.7, 15)
    sim_step()


# ──────────────────────────────────────────────────────────────────────────────
# Dash layout
# ──────────────────────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    [
        dbc.Row(dbc.Col(html.H2("MapDisplay (Gdańsk)",
                                className="text-center mt-3"))),
        dbc.Row(dbc.Col([
            dcc.Interval(id="tick", interval=1000, n_intervals=0),
            dcc.Graph(id="graph", style={"height":"90vh"}),
        ])),
    ], fluid=True)


# ──────────────────────────────────────────────────────────────────────────────
# Callback – rebuild figure
# ──────────────────────────────────────────────────────────────────────────────
@app.callback(Output("graph","figure"), Input("tick","n_intervals"))
def redraw(_):
    fig = go.Figure()
    fig.update_layout(
        map=dict(style="open-street-map", center=VIEW_CENTER, zoom=VIEW_ZOOM),
        uirevision="lock",
        margin=dict(l=0,r=0,t=0,b=0),
        showlegend=False,
    )

    # 1️⃣ dashed traces
    for s in ships.values():
        if len(s["trace"])>1:
            lon, lat = dashify(s["trace"], seg_len=1)
            fig.add_trace(go.Scattermap(
                lon=lon, lat=lat, mode="lines",
                line=dict(color=s["color"], width=1),
                hoverinfo="none", showlegend=False))
            
    def hex_to_rgba(hex_col: str, alpha: float) -> str:
        """‘#rrggbb’ → ‘rgba(r,g,b,alpha)’."""
        hex_col = hex_col.lstrip("#")
        r, g, b = (int(hex_col[i:i+2], 16) for i in (0, 2, 4))
        return f"rgba({r},{g},{b},{alpha})"

    # 2️⃣ translucent direction cones
    for s in ships.values():
        if len(s["trace"]) < 2:
            continue
        lon0, lat0   = s["coord"]
        lon_prev, lat_prev = s["trace"][-2]
        dx, dy = lon0 - lon_prev, lat0 - lat_prev
        if dx == dy == 0:
            continue
        heading = degrees(atan2(dy, dx))
        left, right = heading - CONE_ANGLE_DEG/2, heading + CONE_ANGLE_DEG/2
        p1 = destination(lon0, lat0, left,  CONE_LENGTH_M)
        p2 = destination(lon0, lat0, right, CONE_LENGTH_M)
        fig.add_trace(go.Scattermap(
            lon=[lon0, p1[0], p2[0], lon0],
            lat=[lat0, p1[1], p2[1], lat0],
            mode="lines",
            fill="toself",
            fillcolor=hex_to_rgba(s["color"], 0.2),
            line=dict(width=0),
            hoverinfo="none",
            showlegend=False))

    # 3️⃣ cameras (triangles + range circles)
    cam_lon, cam_lat, cam_col, meta = [],[],[],[]
    for cam in cameras.values():
        tri="#7f8c8d"; fill="rgba(127,140,141,0.10)"; line="rgba(127,140,141,0.40)"
        if any(haversine_m(cam["coord"], s["coord"])<=cam["range"]
               for s in ships.values()):
            tri="#2ecc71"; fill="rgba(46,204,113,0.10)"; line="rgba(46,204,113,0.50)"
        cam_lon.append(cam["coord"][0]); cam_lat.append(cam["coord"][1])
        cam_col.append(tri)
        meta.append({"R":cam["range"],"fill":fill,"line":line})

    if cam_lon:
        fig.add_trace(go.Scattermap(
            lon=cam_lon, lat=cam_lat, mode="markers",
            marker=dict(symbol="triangle-up", size=24, color=cam_col),
            hovertemplate="<b>Camera</b><br>Lon:%{lon:.4f}<br>Lat:%{lat:.4f}<extra></extra>"))
        for lon, lat, m in zip(cam_lon,cam_lat,meta):
            lons,lats=[],[]
            for i in range(CAM_RANGE_SEGMENTS+1):
                ang=360*i/CAM_RANGE_SEGMENTS
                x,y = destination(lon,lat,ang,m["R"])
                lons.append(x); lats.append(y)
            fig.add_trace(go.Scattermap(
                lon=lons, lat=lats, mode="lines",
                fill="toself", fillcolor=m["fill"],
                line=dict(color=m["line"], width=1),
                hoverinfo="none", showlegend=False))

    # 4️⃣ ship markers (opacity varies with #sources)
    if ships:
        fig.add_trace(go.Scattermap(
            lon=[s["coord"][0] for s in ships.values()],
            lat=[s["coord"][1] for s in ships.values()],
            mode="markers",
            marker=dict(
                size=[s["radius"]*SHIP_DOT_FACTOR for s in ships.values()],
                color=[s["color"]   for s in ships.values()],
                opacity=[s["opacity"] for s in ships.values()],
                symbol="circle", sizemode="area"),
            text=[ "<br>".join([f"<b>{name}</b>"]+
                                [f"{k}: {v}" for k,v in s["info"].items()])
                   for name,s in ships.items()],
            hoverinfo="text"))

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    start_sim()
    app.run(host="0.0.0.0", port=8050, debug=True)
