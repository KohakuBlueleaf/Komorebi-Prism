"""The scene description as dataclasses of numpy arrays. Conventions: metres, +Y up,
right-handed, counter-clockwise front faces, linear colour factors, matrices row-major on
column vectors (`world @ [x, y, z, 1]`), UV origin at the image's top left, -1 for none.
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Note:
    """What happened to one kind of thing: used, carried, computed, refused or dropped."""

    kind: str
    what: str
    count: int = 1
    detail: str = ""


@dataclass
class TextureUse:
    """A material's reference to a texture, with its UV set and texture transform."""

    texture: int
    uv: int = 0
    offset: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0]))
    rotation: float = 0.0
    scale: np.ndarray = field(default_factory=lambda: np.array([1.0, 1.0]))


@dataclass
class Texture:
    """An image with a sampler (-1: the default sampler)."""

    image: int = -1
    sampler: int = -1


@dataclass
class Sampler:
    """Wrap modes ("REPEAT", "CLAMP", "MIRROR") and filters by glTF's names (None: unset)."""

    wrap_s: str = "REPEAT"
    wrap_t: str = "REPEAT"
    mag: str | None = None
    min: str | None = None


@dataclass
class Image:
    """An image never decoded here: its header's size and a path or a view of its bytes."""

    name: str = ""
    mime: str = ""
    width: int = 0
    height: int = 0
    uri: str | None = None
    data: memoryview | None = None


@dataclass
class Material:
    """A metallic-roughness material with glTF's defaults; other extensions carried."""

    name: str = ""
    base_color: np.ndarray = field(
        default_factory=lambda: np.array([1.0, 1.0, 1.0, 1.0])
    )
    base_color_texture: TextureUse | None = None
    metallic: float = 1.0
    roughness: float = 1.0
    metallic_roughness_texture: TextureUse | None = None
    normal_texture: TextureUse | None = None
    normal_scale: float = 1.0
    occlusion_texture: TextureUse | None = None
    occlusion_strength: float = 1.0
    emissive: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0]))
    emissive_strength: float = 1.0
    emissive_texture: TextureUse | None = None
    alpha_mode: str = "OPAQUE"
    alpha_cutoff: float = 0.5
    double_sided: bool = False
    unlit: bool = False
    carried: dict = field(default_factory=dict)


@dataclass
class Primitive:
    """Triangles with their vertex attributes; joints, weights and morph targets carried."""

    positions: np.ndarray
    indices: np.ndarray
    normals: np.ndarray | None = None
    tangents: np.ndarray | None = None
    uv0: np.ndarray | None = None
    uv1: np.ndarray | None = None
    colors: np.ndarray | None = None
    material: int = -1
    carried: dict = field(default_factory=dict)


@dataclass
class Mesh:
    """A named list of primitives."""

    name: str = ""
    primitives: list = field(default_factory=list)


@dataclass
class Node:
    """A node of the hierarchy: its local and world matrices and what it holds."""

    name: str = ""
    parent: int = -1
    local: np.ndarray = field(default_factory=lambda: np.eye(4))
    world: np.ndarray = field(default_factory=lambda: np.eye(4))
    mesh: int = -1
    camera: int = -1
    light: int = -1
    instances: np.ndarray | None = None
    moving: bool = False


@dataclass
class Light:
    """A light: lux (directional), candela (point, spot) or watts (area)."""

    kind: str = "point"
    color: np.ndarray = field(default_factory=lambda: np.array([1.0, 1.0, 1.0]))
    intensity: float = 1.0
    range: float | None = None
    inner_cone: float = 0.0
    outer_cone: float = np.pi / 4
    shape: str | None = None
    size: np.ndarray | None = None


@dataclass
class Camera:
    """A perspective or orthographic camera; a lens shift in units of the fitted side,
    the side whose field of view is kept at another aspect ("" or "VERTICAL": yfov;
    "AUTO": the longer side)."""

    kind: str = "perspective"
    yfov: float = 0.0
    aspect: float | None = None
    znear: float = 0.0
    zfar: float | None = None
    xmag: float = 0.0
    ymag: float = 0.0
    shift_x: float = 0.0
    shift_y: float = 0.0
    sensor_fit: str = ""


@dataclass
class World:
    """The background: a colour and strength, or an environment image and its rotation."""

    color: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0]))
    strength: float = 1.0
    environment: str | None = None
    rotation: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0]))


@dataclass
class Render:
    """The render settings: size, camera node, exposure and view transform."""

    size: np.ndarray = field(default_factory=lambda: np.array([0, 0], dtype=np.int64))
    camera: int = -1
    exposure: float = 0.0
    view_transform: str = ""
    look: str = ""
    gamma: float = 1.0


@dataclass
class Scene:
    """A whole scene; `source`: "path", "format", "bytes", "file" (whole-file counts)."""

    nodes: list = field(default_factory=list)
    meshes: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    textures: list = field(default_factory=list)
    images: list = field(default_factory=list)
    samplers: list = field(default_factory=list)
    lights: list = field(default_factory=list)
    cameras: list = field(default_factory=list)
    world: World | None = None
    render: Render | None = None
    animations: list = field(default_factory=list)
    skins: list = field(default_factory=list)
    source: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
