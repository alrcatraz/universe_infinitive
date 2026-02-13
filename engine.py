# engine.py
import math
import json
import os
import xml.etree.ElementTree as ET
from settings import G, COLORS, SCREEN_WIDTH, SCREEN_HEIGHT


def safe_float(node, attr_name, default_value=0.0):
    val = node.attrib.get(attr_name)
    if not val or str(val).strip() == "":
        return default_value
    return float(val)


def get_dominant_body(x, y, bodies):
    best_body, max_g = None, -1
    for b in bodies:
        r2 = max((x - b.x) ** 2 + (y - b.y) ** 2, b.body_radius ** 2)
        g = G * b.mass / r2
        if g > max_g: max_g, best_body = g, b
    return best_body


def compute_gravity(pos_x, pos_y, bodies):
    ax, ay = 0.0, 0.0
    for body in bodies:
        dx, dy = body.x - pos_x, body.y - pos_y
        dist_sq = max(dx ** 2 + dy ** 2, body.body_radius ** 2)
        f = G * body.mass / dist_sq
        dist = math.sqrt(dist_sq)
        ax += f * (dx / dist)
        ay += f * (dy / dist)
    return ax, ay


class CelestialBody:
    def __init__(self, name, parent, orbit_radius, mass, render_size, body_radius, color, offset_x=0, offset_y=0):
        self.name, self.parent = name, parent
        self.orbit_radius, self.mass = orbit_radius, mass
        self.render_size, self.body_radius = render_size, body_radius
        self.color = COLORS.get(color, COLORS["white"])
        self.children, self.x, self.y = [], offset_x, offset_y
        self.theta, self.omega = 0.0, 0.0

        if self.parent and self.orbit_radius > 0:
            self.omega = math.sqrt(G * self.parent.mass / (self.orbit_radius ** 3))
            self.x = self.parent.x + self.orbit_radius
            self.y = self.parent.y

    def set_time(self, current_time):
        """采用绝对时间计算轨道位置，确保读档绝对精准无漂移"""
        if self.parent:
            self.theta = self.omega * current_time
            self.x = self.parent.x + self.orbit_radius * math.cos(self.theta)
            self.y = self.parent.y + self.orbit_radius * math.sin(self.theta)
        for child in self.children:
            child.set_time(current_time)

    def get_velocity(self):
        if not self.parent: return 0.0, 0.0
        v_mag = self.omega * self.orbit_radius
        vx, vy = -v_mag * math.sin(self.theta), v_mag * math.cos(self.theta)
        pvx, pvy = self.parent.get_velocity()
        return pvx + vx, pvy + vy


class Ship:
    def __init__(self, name, x, y, thrust, mass, color):
        self.name, self.x, self.y = name, x, y
        self.vx, self.vy = 0.0, 0.0
        self.thrust, self.mass = thrust, mass
        self.color = COLORS.get(color, COLORS["cyan"])

        self.heading = 0.0
        self.turn_cmd = 0
        self.thrust_percent = 0.0
        self.show_ui = True
        self.autopilot_target = None
        self.ap_state = "IDLE"


class Camera:
    def __init__(self):
        self.target = None
        self.scale = 0.003
        self.offset_x, self.offset_y = 0.0, 0.0
        self.view_level = 3

    def apply(self, x, y):
        tx = (self.target.x if self.target else 0) + self.offset_x
        ty = (self.target.y if self.target else 0) + self.offset_y
        sx = int((x - tx) * self.scale + SCREEN_WIDTH / 2)
        sy = int((y - ty) * self.scale + SCREEN_HEIGHT / 2)
        return sx, sy

    def reset_offset(self):
        self.offset_x, self.offset_y = 0.0, 0.0


# --- 数据与存档管理 ---
def load_universe(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    all_bodies, stars = [], []
    for solar_node in root.findall("Solar"):
        star = CelestialBody(
            name=solar_node.find("Star").attrib["name"], parent=None, orbit_radius=0,
            mass=safe_float(solar_node.find("Star"), "mass", 1.989e27),
            render_size=safe_float(solar_node.find("Star"), "size", 15.0),
            body_radius=safe_float(solar_node.find("Star"), "body_radius", 696340.0),
            color=solar_node.find("Star").attrib["colour"],
            offset_x=safe_float(solar_node.find("Star"), "x", 0.0),
            offset_y=safe_float(solar_node.find("Star"), "y", 0.0)
        )
        stars.append(star);
        all_bodies.append(star)
        for p_node in solar_node.findall("Planet"):
            planet = CelestialBody(
                name=p_node.attrib["name"], parent=star, orbit_radius=safe_float(p_node, "radius"),
                mass=safe_float(p_node, "mass"), render_size=safe_float(p_node, "size"),
                body_radius=safe_float(p_node, "body_radius"), color=p_node.attrib["colour"]
            )
            star.children.append(planet);
            all_bodies.append(planet)
            for m_node in p_node.findall("Moon"):
                moon = CelestialBody(
                    name=m_node.attrib["name"], parent=planet, orbit_radius=safe_float(m_node, "radius"),
                    mass=safe_float(m_node, "mass"), render_size=safe_float(m_node, "size"),
                    body_radius=safe_float(m_node, "body_radius"), color=m_node.attrib["colour"]
                )
                planet.children.append(moon);
                all_bodies.append(moon)
    return stars, all_bodies


def load_ship(filepath):
    tree = ET.parse(filepath)
    s = tree.getroot().find("Ship")
    return Ship(s.attrib["name"], safe_float(s, "x"), safe_float(s, "y"), safe_float(s, "thrust"),
                safe_float(s, "mass"), s.attrib["colour"])


def init_ship_orbit(ship, all_bodies):
    nearest = min(all_bodies, key=lambda b: math.hypot(ship.x - b.x, ship.y - b.y))
    dist = math.hypot(ship.x - nearest.x, ship.y - nearest.y)
    if dist > 0:
        v_circ = math.sqrt(G * nearest.mass / dist)
        rx, ry = ship.x - nearest.x, ship.y - nearest.y
        tx, ty = -ry / dist, rx / dist
        bvx, bvy = nearest.get_velocity()
        ship.vx, ship.vy = bvx + v_circ * tx, bvy + v_circ * ty
        ship.heading = math.atan2(ship.vy - bvy, ship.vx - bvx)
    return nearest


def save_game(filepath, time_elapsed, ship, camera):
    data = {
        "time_elapsed": time_elapsed,
        "ship": {
            "x": ship.x, "y": ship.y, "vx": ship.vx, "vy": ship.vy,
            "heading": ship.heading, "ap_state": ship.ap_state,
            "target": ship.autopilot_target.name if ship.autopilot_target else None
        },
        "camera": {"target": camera.target.name if camera.target else None, "scale": camera.scale}
    }
    with open(filepath, "w") as f: json.dump(data, f)


def load_game(filepath, ship, camera, all_bodies):
    if not os.path.exists(filepath): return None
    with open(filepath, "r") as f: data = json.load(f)
    ship.x, ship.y, ship.vx, ship.vy = data["ship"]["x"], data["ship"]["y"], data["ship"]["vx"], data["ship"]["vy"]
    ship.heading, ship.ap_state = data["ship"]["heading"], data["ship"]["ap_state"]
    tgt = data["ship"]["target"]
    ship.autopilot_target = next((b for b in all_bodies if b.name == tgt), None)
    cam_tgt = data["camera"]["target"]
    camera.target = next((b for b in all_bodies if b.name == cam_tgt), None)
    camera.scale = data["camera"]["scale"]
    return data["time_elapsed"]