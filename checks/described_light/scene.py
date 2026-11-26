"""The written scene: a floor quad, a square occluder above it, one light of each kind
and a uniform world; the floor points looked at and the closed forms of their light."""

import numpy as np

from prism_reference.direct.described.units import LUMENS_PER_WATT
from prism_reference.scene.description.types import Light, Node, Scene, World

FLOOR_HALF = 20.0
OCCLUDER = (0.5, 1.5)  # half side, height
POINT = (np.array([0.0, 3.0, 0.0]), 10.0)  # position, W/sr
SPOT = (np.array([6.0, 3.0, 0.0]), 10.0, 0.25, 0.5)  # position, W/sr, inner, outer
SUN = (np.array([1.0, 2.0, 0.0]) / np.sqrt(5.0), 3.0)  # toward the sun, W/m^2
AREA = (np.array([-6.0, 2.0, 0.0]), 1.0, 100.0)  # centre, side, watts
WORLD = (np.array([0.2, 0.3, 0.4]), 2.0)  # colour, strength
EYE = np.array([0.0, 10.0, 30.0])


def quad(half, height):
    """Positions (4, 3) and two triangles (2, 3) of a square at a height, facing +y."""
    p = np.array(
        [[-half, height, -half], [half, height, -half], [half, height, half]]
        + [[-half, height, half]],
        np.float32,
    )
    return p, np.array([[0, 2, 1], [0, 3, 2]], np.int32)


def geometry():
    """The floor and the occluder as one triangle list {positions, indices}."""
    floor_p, floor_i = quad(FLOOR_HALF, 0.0)
    block_p, block_i = quad(*OCCLUDER)
    return {
        "positions": np.concatenate([floor_p, block_p]),
        "indices": np.concatenate([floor_i, block_i + 4]),
    }


def frame_toward(z):
    """A rotation (3, 3) whose third column is the unit vector z."""
    helper = np.array([1.0, 0.0, 0.0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(helper, z)
    x /= np.linalg.norm(x)
    return np.stack([x, np.cross(z, x), z], axis=1)


def node(name, light, linear, position):
    """A root node holding light `light` at a rotation and position."""
    world = np.eye(4)
    world[:3, :3], world[:3, 3] = linear, position
    return Node(name=name, local=world.copy(), world=world, light=light)


def written_scene():
    """The Scene of the lights and the world (geometry goes to the tree alone)."""
    down = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
    cd = LUMENS_PER_WATT
    lights = [
        Light(kind="point", intensity=POINT[1] * cd),
        Light(
            kind="spot", intensity=SPOT[1] * cd, inner_cone=SPOT[2], outer_cone=SPOT[3]
        ),
        Light(kind="directional", intensity=SUN[1] * cd),
        Light(
            kind="area", intensity=AREA[2], shape="SQUARE", size=np.array([1.0, 1.0])
        ),
    ]
    nodes = [
        node("point", 0, np.eye(3), POINT[0]),
        node("spot", 1, down, SPOT[0]),
        node("sun", 2, frame_toward(SUN[0]), np.zeros(3)),
        node("area", 3, np.eye(3) * AREA[1], AREA[0]),
    ]
    world = World(color=WORLD[0], strength=WORLD[1])
    return Scene(nodes=nodes, lights=lights, world=world)


def corner_factor(x, y):
    """The form factor from a point to a parallel rectangle with one corner above it,
    sides x and y in heights (signed)."""
    a, b = np.sqrt(1 + x * x), np.sqrt(1 + y * y)
    return (x / a * np.arctan(y / a) + y / b * np.arctan(x / b)) / (2 * np.pi)


def area_irradiance(point):
    """pi L F of the area light at a floor point, F by the corner rectangles."""
    centre, side, watts = AREA
    radiance = watts / (np.pi * side * side)
    h = centre[1] - point[1]
    x1, x2 = (centre[0] - side / 2 - point[0]) / h, (
        centre[0] + side / 2 - point[0]
    ) / h
    z1, z2 = (centre[2] - side / 2 - point[2]) / h, (
        centre[2] + side / 2 - point[2]
    ) / h
    f = corner_factor(x2, z2) - corner_factor(x1, z2)
    f += corner_factor(x1, z1) - corner_factor(x2, z1)
    return np.pi * radiance * f


def point_irradiance(position, intensity, point):
    """I cos / d^2 on the floor (normal +y)."""
    d = position - point
    distance = np.linalg.norm(d)
    return intensity * (d[1] / distance) / distance**2


def spot_irradiance(point):
    """I attenuation cos / d^2 with glTF's cone, the spot facing -y."""
    position, intensity, inner, outer = SPOT
    d = position - point
    cosine = d[1] / np.linalg.norm(d)
    t = np.clip((cosine - np.cos(outer)) / (np.cos(inner) - np.cos(outer)), 0, 1)
    return t * t * point_irradiance(position, intensity, point)


def cases():
    """[(kind, name, floor point, closed-form irradiance, tolerance as a share)]."""
    out = []
    for x, z in ((3.0, 2.0), (-4.0, 1.0)):
        p = np.array([x, 0.0, z])
        out.append(
            ("point", f"inverse square at {x, z}", p, point_irradiance(*POINT, p), 1e-5)
        )
    out.append(
        ("point", "in the shadow, 0.05 inside its edge", np.array([0.95, 0, 0]), 0.0, 0)
    )
    p = np.array([1.05, 0.0, 0.0])
    out.append(
        (
            "point",
            "0.05 outside the shadow's edge",
            p,
            point_irradiance(*POINT, p),
            1e-5,
        )
    )
    for angle in (0.1, 0.4, 0.6):
        p = np.array([SPOT[0][0] + 3.0 * np.tan(angle), 0.0, 0.0])
        out.append(("spot", f"cone at {angle} rad", p, spot_irradiance(p), 1e-5))
    sun = SUN[1] * SUN[0][1]
    out.append(("sun", "cosine", np.array([4.0, 0.0, 5.0]), sun, 1e-5))
    out.append(
        ("sun", "in the shadow, 0.05 inside its edge", np.array([-0.3, 0, 0]), 0.0, 0)
    )
    out.append(
        ("sun", "0.05 outside the shadow's edge", np.array([-0.2, 0, 0]), sun, 1e-5)
    )
    for x, z in ((-6.0, 0.0), (-5.5, 0.3), (-7.0, -1.0)):
        p = np.array([x, 0.0, z])
        out.append(("area", f"form factor at {x, z}", p, area_irradiance(p), 1e-2))
    world = np.pi * WORLD[1] * WORLD[0]
    for x, z in ((12.0, 12.0), (-14.0, 10.0)):
        out.append(
            ("world", f"unoccluded at {x, z}", np.array([x, 0.0, z]), world, 1e-5)
        )
    return out


def planes_of(points):
    """Surface planes (1, N, ...) of floor points: white, dielectric, roughness 0.5."""
    count = len(points)
    up = np.tile(np.array([0.0, 1.0, 0.0], np.float32), (1, count, 1))
    return {
        "covered": np.ones((1, count), bool),
        "position": np.asarray(points, np.float32)[None],
        "normal": up,
        "geometric_normal": up.copy(),
        "base_color": np.ones((1, count, 3), np.float32),
        "metallic": np.zeros((1, count), np.float32),
        "roughness": np.full((1, count), 0.5, np.float32),
        "emissive": np.zeros((1, count, 3), np.float32),
    }
