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
        self.saved_positions = []  # list of (name, Point)
        self._ship_artists = {}  # artist -> ship_name
        self._annotations = []   # active popup labels

        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.fig.canvas.mpl_connect("pick_event", self._on_pick)
        self.fig.canvas.mpl_connect("button_press_event", self._on_click)
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
        self._ship_artists.clear()
        for ann in self._annotations:
            ann.remove()
        self._annotations.clear()

    def add_ship(self, name, lon, lat, color='red', size=100, label=None,
                 alpha=1.0, show_trace=True, highlight=False, highlight_radius=0.05,
                 show_direction=False, cone_angle=30, cone_length=0.1, info=None):
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
            'cone_length': cone_length,
            'info': info or {}
        }

    def remove_ship(self, name):
        self.ships.pop(name, None)

    def set_ship_position(self, name, lon, lat):
        if name in self.ships:
            point = Point(lon, lat)
            self.ships[name]['geometry'] = point
            self.ships[name]['trace'].append(point)

    def save_ship_position(self, name):
        if name in self.ships:
            self.saved_positions.append((name, self.ships[name]['geometry']))

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

    def _on_pick(self, event):
        artist = event.artist
        if artist in self._ship_artists:
            ship_name = self._ship_artists[artist]
            ship = self.ships[ship_name]
            info = ship.get('info', {})
            point = ship['geometry']

            for ann in self._annotations:
                ann.remove()
            self._annotations.clear()

            text = f"{ship_name}\n" + "\n".join(f"{k}: {v}" for k, v in info.items())
            ann = self.ax.annotate(
                text, xy=(point.x, point.y), xytext=(point.x + 0.03, point.y + 0.03),
                bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.8),
                arrowprops=dict(arrowstyle="->"), fontsize=9
            )
            self._annotations.append(ann)
            plt.draw()

    def _on_click(self, event):
        if not event.inaxes:
            return
        contains = any(artist.contains(event)[0] for artist in self._ship_artists)
        if not contains:
            for ann in self._annotations:
                ann.remove()
            self._annotations.clear()
            plt.draw()

    def draw(self):
        self._init_plot()

        for name, data in self.ships.items():
            p = data['geometry']

            if data.get('highlight'):
                circle = mpatches.Circle(
                    (p.x, p.y), radius=data['highlight_radius'],
                    edgecolor='red', facecolor='none', linewidth=1.5
                )
                self.ax.add_patch(circle)

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

            marker = self.ax.plot(
                p.x, p.y, 'o', color=data['color'],
                markersize=data['size'] / 10, alpha=data['alpha'],
                picker=5
            )[0]
            self._ship_artists[marker] = name

            self.ax.text(p.x + 0.02, p.y + 0.01, data['label'],
                         fontsize=9, fontweight='bold', alpha=data['alpha'])

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

        for name, pt in self.saved_positions:
            self.ax.plot(pt.x, pt.y, 'o', color='gray', markersize=5, alpha=0.6)
            self.ax.text(pt.x + 0.01, pt.y + 0.005, name, fontsize=7, color='gray')

        plt.draw()
        plt.pause(0.01)

    def show(self):
        plt.show()

import time

# Initialize map
map_display = MapDisplay()

# Add ships
map_display.add_ship(
    name="Alpha", lon=18.5, lat=54.5,
    color="orange", size=120,
    highlight=True, show_trace=True, show_direction=True,
    info={"Type": "Cargo", "Speed": "12 kn", "Destination": "Gdańsk"}
)

map_display.add_ship(
    name="Beta", lon=18.8, lat=54.4,
    color="blue", size=100,
    show_trace=True, show_direction=True,
    info={"Type": "Tanker", "Speed": "10 kn", "Destination": "Szczecin"}
)

# Add triangle (camera)
map_display.add_triangle("Camera 1", lon=19.0, lat=54.6)

# Draw initial state
map_display.draw()

# Animate movement + save position halfway
for step in range(30):
    # Move Alpha northeast
    p_alpha = map_display.ships["Alpha"]["geometry"]
    new_alpha_x = p_alpha.x + 0.01
    new_alpha_y = p_alpha.y + 0.005
    new_alpha_y = p_alpha.y + 0.005
    map_display.set_ship_position("Alpha", new_alpha_x, new_alpha_y)

    # Move Beta east
    p_beta = map_display.ships["Beta"]["geometry"]
    new_beta_x = p_beta.x + 0.015
    map_display.set_ship_position("Beta", new_beta_x, p_beta.y)

    # Save position at step 5
    if step == 5:
        map_display.save_ship_position("Alpha")
        map_display.save_ship_position("Beta")

    map_display.draw()
    time.sleep(0.3)

# Final display, interactive
map_display.show()
