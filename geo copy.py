import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from shapely.geometry import Point, box

class MapDisplay:
    def __init__(self, bounds=(18.0, 54.0, 20.0, 55.0)):
        self.minx, self.miny, self.maxx, self.maxy = bounds
        self.offshore_area = gpd.GeoDataFrame(
            {'geometry': [box(*bounds)]}, crs="EPSG:4326"
        )

        self.ships = {}      # name -> dict
        self.triangles = {}  # name -> Point

        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self._init_plot()

    def _init_plot(self):
        self.ax.clear()
        self.offshore_area.plot(ax=self.ax, color='lightblue', edgecolor='black')
        self.ax.set_xlim(self.minx - 0.1, self.maxx + 0.1)
        self.ax.set_ylim(self.miny - 0.1, self.maxy + 0.1)
        self.ax.set_title("Map Display")
        self.ax.set_xlabel("Longitude")
        self.ax.set_ylabel("Latitude")
        self.ax.grid(True)

    def add_ship(self, name, lon, lat, color='red', size=100, label=None,
                 alpha=1.0, show_trace=True, highlight=False, highlight_radius=0.05,
                 show_direction=False, cone_angle=30, cone_length=0.1):
        point = Point(lon, lat)
        self.ships[name] = {
            'geometry': point,
            'color': color,
            'size': size,
            'label': label or name,
            'alpha': alpha,
            'trace': [point],
            'show_trace': show_trace,
            'highlight': highlight,
            'highlight_radius': highlight_radius,
            'show_direction': show_direction,
            'cone_angle': cone_angle,
            'cone_length': cone_length
        }

    def set_ship_position(self, name, lon, lat):
        if name in self.ships:
            point = Point(lon, lat)
            self.ships[name]['geometry'] = point
            self.ships[name]['trace'].append(point)

    def set_ship_style(self, name, color=None, size=None, label=None, alpha=None):
        if name in self.ships:
            if color: self.ships[name]['color'] = color
            if size: self.ships[name]['size'] = size
            if label: self.ships[name]['label'] = label
            if alpha is not None: self.ships[name]['alpha'] = alpha

    def set_ship_opacity(self, name, alpha):
        if name in self.ships:
            self.ships[name]['alpha'] = alpha

    def set_ship_trace(self, name, show_trace):
        if name in self.ships:
            self.ships[name]['show_trace'] = show_trace

    def set_ship_highlight(self, name, highlight=True, radius=None):
        if name in self.ships:
            self.ships[name]['highlight'] = highlight
            if radius is not None:
                self.ships[name]['highlight_radius'] = radius

    def set_ship_direction_display(self, name, show_direction=True, angle=None, length=None):
        if name in self.ships:
            self.ships[name]['show_direction'] = show_direction
            if angle is not None:
                self.ships[name]['cone_angle'] = angle
            if length is not None:
                self.ships[name]['cone_length'] = length

    def add_triangle(self, name, lon, lat):
        self.triangles[name] = Point(lon, lat)

    def set_triangle_position(self, name, lon, lat):
        if name in self.triangles:
            self.triangles[name] = Point(lon, lat)

    def _draw_direction_cone(self, point, angle_deg, length, heading_rad, color):
        angle_rad = np.radians(angle_deg)
        left = heading_rad - angle_rad / 2
        right = heading_rad + angle_rad / 2

        x0, y0 = point.x, point.y
        x1 = x0 + length * np.cos(left)
        y1 = y0 + length * np.sin(left)
        x2 = x0 + length * np.cos(right)
        y2 = y0 + length * np.sin(right)

        wedge = plt.Polygon([[x0, y0], [x1, y1], [x2, y2]], closed=True, color=color, alpha=0.2)
        self.ax.add_patch(wedge)

    def draw(self):
        self._init_plot()

        for name, data in self.ships.items():
            p = data['geometry']

            # Highlight
            if data.get('highlight'):
                circle = mpatches.Circle(
                    (p.x, p.y), radius=data['highlight_radius'],
                    edgecolor='red', facecolor='none', linewidth=1.5
                )
                self.ax.add_patch(circle)

            # Direction cone
            if data.get('show_direction') and len(data['trace']) >= 2:
                prev = data['trace'][-2]
                dx = p.x - prev.x
                dy = p.y - prev.y
                if dx != 0 or dy != 0:
                    heading = np.arctan2(dy, dx)
                    self._draw_direction_cone(
                        p, angle_deg=data['cone_angle'],
                        length=data['cone_length'],
                        heading_rad=heading,
                        color=data['color']
                    )

            # Marker
            self.ax.plot(p.x, p.y, 'o', color=data['color'],
                         markersize=data['size'] / 10, alpha=data['alpha'])

            # Label
            self.ax.text(p.x + 0.02, p.y + 0.01, data['label'],
                         fontsize=9, fontweight='bold', alpha=data['alpha'])

            # Trace
            if data['show_trace'] and len(data['trace']) > 1:
                xs = [pt.x for pt in data['trace']]
                ys = [pt.y for pt in data['trace']]
                self.ax.plot(xs, ys, linestyle='--', color=data['color'], alpha=0.5)

        for point in self.triangles.values():
            triangle = mpatches.RegularPolygon(
                (point.x, point.y), numVertices=3, radius=0.008,
                orientation=0.5, color='black'
            )
            self.ax.add_patch(triangle)

        plt.draw()
        plt.pause(0.01)

    def show(self):
        plt.show()

import time

map_display = MapDisplay()

map_display.add_ship(
    name="Alpha",
    lon=18.5,
    lat=54.5,
    color='orange',
    size=120,
    highlight=True,
    show_trace=True,
    show_direction=True,
    cone_angle=40,
    cone_length=0.2
)

# Animate Alpha
for _ in range(20):
    p = map_display.ships["Alpha"]["geometry"]
    map_display.set_ship_position("Alpha", p.x + 0.01, p.y + 0.005)
    map_display.draw()
    time.sleep(0.3)

map_display.show()
