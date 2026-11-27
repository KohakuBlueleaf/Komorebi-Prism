"""Helpers the export imports inside Blender, and the script one bake job runs: the
passes of the mesh bake written as jobs (a small .blend each), run by several Blender
processes at once, their results kept in a cache folder under a key of what each bake
depends on."""

import hashlib
import json
import os
import subprocess
import sys
import time

import bpy
import numpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bake

VERSION = 1  # of a job's result
CORES_A_BAKE = 1  # cores one bake process keeps busy
SAME = 1e-4
FLAT = (0.5, 0.5, 1.0)  # a flat normal as the bake writes it
CHANNELS = ("Red", "Green", "Blue")
COLOUR = {"Base Color", "Emission Color"}
SCENE = "prism_job"
WIDTHS = {
    "FLOAT": ("value", 1),
    "INT": ("value", 1),
    "INT8": ("value", 1),
    "BOOLEAN": ("value", 1),
    "FLOAT2": ("vector", 2),
    "INT32_2D": ("value", 2),
    "FLOAT_VECTOR": ("vector", 3),
    "FLOAT_COLOR": ("color", 4),
    "BYTE_COLOR": ("color", 4),
    "QUATERNION": ("value", 4),
}
SKIPPED = {"location", "location_absolute", "width", "height", "select", "label"}
SKIPPED |= {"name", "color", "use_custom_color", "show_options", "show_preview"}
SKIPPED |= {"show_texture", "hide", "dimensions", "warning_propagation", "color_tag"}


def default_processes():
    """The bake processes run at once: the cores this process may use over the cores
    one bake keeps busy."""
    return max(1, len(os.sched_getaffinity(0)) // CORES_A_BAKE)


def image_digest(image, digest):
    """Adds what an image's values depend on to `digest`."""
    path = bpy.path.abspath(image.filepath_raw, library=image.library)
    found = os.stat(path) if image.filepath_raw and os.path.exists(path) else None
    packed = image.packed_file.size if image.packed_file else None
    stamp = (found.st_size, int(found.st_mtime)) if found else None
    tiles = [t.number for t in image.tiles] if image.source == "TILED" else []
    entry = (image.name_full, image.source, image.filepath_raw, tuple(image.size))
    entry += (image.colorspace_settings.name, image.alpha_mode, stamp, packed, tiles)
    digest.update(repr(entry).encode())


def value_of(owner, prop, digest, seen):
    """A property's value as text (pointers to trees and images digested)."""
    value = getattr(owner, prop.identifier)
    if prop.type == "POINTER":
        if isinstance(value, bpy.types.NodeTree) and value.as_pointer() not in seen:
            seen.add(value.as_pointer())
            tree_digest(value, digest, seen)
        elif isinstance(value, bpy.types.Image):
            image_digest(value, digest)
        return getattr(value, "name_full", None)
    if hasattr(value, "__len__") and not isinstance(value, str):
        return tuple(value)
    return value


def tree_digest(tree, digest, seen):
    """Adds a node tree as resolved (nodes, values, links, groups, images) to
    `digest`."""
    for node in sorted(tree.nodes, key=lambda n: n.name):
        entry = [node.bl_idname, node.name, node.mute]
        for prop in node.bl_rna.properties:
            if prop.identifier in SKIPPED or prop.identifier.startswith("bl_"):
                continue
            if prop.type in ("BOOLEAN", "INT", "FLOAT", "STRING", "ENUM", "POINTER"):
                entry.append((prop.identifier, value_of(node, prop, digest, seen)))
        ramp = getattr(node, "color_ramp", None)
        if ramp is not None:
            entry.append([(e.position, tuple(e.color)) for e in ramp.elements])
            entry.append((ramp.interpolation, ramp.color_mode))
        mapping = getattr(node, "mapping", None)
        if mapping is not None and hasattr(mapping, "curves"):
            entry.append(
                [
                    [(tuple(p.location), p.handle_type) for p in c.points]
                    for c in mapping.curves
                ]
            )
        for socket in node.inputs:
            value = getattr(socket, "default_value", None)
            if hasattr(value, "__len__") and not isinstance(value, str):
                value = tuple(value)
            entry.append((socket.identifier, socket.is_linked, repr(value)))
        digest.update(repr(entry).encode())
    links = sorted(
        (
            link.from_node.name,
            link.from_socket.identifier,
            link.to_node.name,
            link.to_socket.identifier,
            link.is_muted,
        )
        for link in tree.links
    )
    digest.update(repr(links).encode())


def mesh_digest(mesh, digest):
    """Adds a mesh's faces and every attribute's values to `digest`."""
    for attribute in sorted(mesh.attributes, key=lambda a: a.name):
        if attribute.data_type not in WIDTHS:
            continue
        field, width = WIDTHS[attribute.data_type]
        kind = (
            numpy.float32
            if attribute.data_type.startswith(("FLOAT", "QUAT", "BYTE"))
            else numpy.int32
        )
        if attribute.data_type == "BOOLEAN":
            kind = bool
        values = numpy.empty(len(attribute.data) * width, kind)
        attribute.data.foreach_get(field, values)
        digest.update(repr((attribute.name, attribute.domain)).encode())
        digest.update(values.tobytes())
    for owner, field in ((mesh.polygons, "loop_start"), (mesh.loops, "vertex_index")):
        values = numpy.empty(len(owner), numpy.int32)
        owner.foreach_get(field, values)
        digest.update(values.tobytes())


def fingerprint(material, targets, kind, holder, side):
    """The key of one pass: the material's tree, the outputs baked, the holder's mesh,
    the side and the bake's settings."""
    digest = hashlib.sha256()
    entry = (VERSION, tuple(bpy.app.version), kind, side, bake.MESH_MARGIN, targets)
    digest.update(repr((entry, holder.name)).encode())
    tree_digest(material.node_tree, digest, set())
    mesh_digest(holder.data, digest)
    return digest.hexdigest()[:32]


def passes(names):
    """The sockets of an atlas grouped into passes: a colour or the normal alone, the
    scalars three to a pass; [(kind, [names])]."""
    found, scalars = [], []
    for name in names:
        if name == "Normal":
            found.append(("NORMAL", [name]))
        elif name in COLOUR:
            found.append(("EMIT", [name]))
        else:
            scalars.append(name)
    found += [("EMIT", scalars[i : i + 3]) for i in range(0, len(scalars), 3)]
    return found


class Jobs:
    """The passes of the mesh bake: cached, or written as jobs and run in parallel."""

    def __init__(self, folder, processes):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.processes = processes or default_processes()
        self.queue, self.running, self.atlases = [], {}, {}
        self.first, self.left, self.owner = {}, {}, {}
        self.ran = self.cached = self.failed = 0
        self.process_seconds = 0.0
        self.devices = set()

    def path(self, key, suffix):
        """A file of a pass in the cache folder."""
        return os.path.join(self.folder, f"{key}{suffix}")

    def add(self, baker, material, atlas, holder, uv_layer, side, kind, sockets):
        """One pass of `sockets` [(name, target, one_minus)] of an atlas: its key,
        written as a job unless its result is cached."""
        targets = [(target, one_minus) for _, target, one_minus in sockets]
        names = [name for name, _, _ in sockets]
        key = fingerprint(material, (names, targets), kind, holder, side)
        self.atlases.setdefault(atlas, []).append(key)
        self.left.setdefault(atlas, set())
        known = key in self.owner
        self.owner.setdefault(key, atlas)
        if os.path.exists(self.path(key, ".json")) or known:
            self.cached += int(not known)
            return key
        self.left[atlas].add(key)
        work, image = baker.work(material, targets, (side, side), kind)
        scene = bpy.data.scenes.new(SCENE)
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        scene.cycles.use_denoising = False
        mesh = holder.data
        mesh.materials.clear()
        mesh.materials.append(work)
        job = bpy.data.objects.new(SCENE, mesh)
        scene.collection.objects.link(job)
        spec = {"kind": kind, "names": names, "uv_layer": uv_layer, "side": side}
        with open(self.path(key, ".job.json"), "w") as out:
            json.dump(spec, out)
        bpy.data.libraries.write(
            self.path(key, ".blend"), {scene}, path_remap="ABSOLUTE"
        )
        bpy.data.objects.remove(job)
        bpy.data.scenes.remove(scene)
        mesh.materials.clear()
        bpy.data.images.remove(image)
        self.queue.append(key)
        return key

    def launch(self, key):
        """Starts the Blender process of one job."""
        command = [
            bpy.app.binary_path,
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            self.path(key, ".blend"),
            "--python",
            os.path.abspath(__file__),
            "--",
            self.folder,
            key,
        ]
        with open(self.path(key, ".log"), "w") as log:
            return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)

    def close(self, atlas):
        """Ends the passes of one atlas: its line now when none waits for a job."""
        if not self.left.get(atlas):
            self.progress(atlas, {"seconds": 0.0, "cached": True})

    def pump(self):
        """Starts queued jobs up to `processes` running and collects the finished; a
        line an atlas when its passes are done (name, side, seconds)."""
        while self.queue and len(self.running) < self.processes:
            key = self.queue.pop(0)
            self.first.setdefault(self.owner[key], time.perf_counter())
            self.running[key] = (self.launch(key), time.perf_counter())
        for key in [k for k, (p, _) in self.running.items() if p.poll() is not None]:
            _, started = self.running.pop(key)
            self.process_seconds += time.perf_counter() - started
            self.ran += 1
            done = os.path.exists(self.path(key, ".json"))
            self.failed += int(not done)
            for suffix in (".blend", ".job.json") + ((".log",) if done else ()):
                if os.path.exists(self.path(key, suffix)):
                    os.remove(self.path(key, suffix))
            atlas = self.owner[key]
            self.left[atlas].discard(key)
            if not self.left[atlas]:
                seconds = round(time.perf_counter() - self.first[atlas], 1)
                self.progress(atlas, {"seconds": seconds})

    def run(self):
        """Runs every queued job to its end."""
        while self.queue or self.running:
            self.pump()
            time.sleep(0.1)

    def summary(self):
        """The jobs' counts for the export's summary line."""
        return {
            "processes": self.processes,
            "ran": self.ran,
            "cached": self.cached,
            "failed": self.failed,
            "process_seconds": round(self.process_seconds, 1),
            "devices": sorted(d for d in self.devices if d),
        }

    def progress(self, atlas, entry):
        """Prints the line of one atlas."""
        line = {"material": atlas[0], "side": atlas[1]} | entry
        print("PRISM atlas", json.dumps(line), flush=True)

    def result(self, key, material):
        """{socket: choice} of a finished pass; lost "bake job failed" without one."""
        path = self.path(key, ".json")
        if not os.path.exists(path):
            return None
        with open(path) as found:
            done = json.load(found)
        self.devices.add(done.get("device"))
        entries = done["names"]
        out = {}
        for name, entry in entries.items():
            if "lost" in entry:
                out[name] = {"done": "lost", "node": entry["lost"]}
            elif "value" in entry:
                value = entry["value"]
                out[name] = {"done": "mesh_baked", "value": value}
            else:
                image = bpy.data.images.load(
                    self.path(key, ".png"), check_existing=True
                )
                image.name = f"{material.name}_{name}_mesh"
                image.colorspace_settings.name = (
                    "sRGB" if entry["colour"] else "Non-Color"
                )
                if not image.packed_file:
                    image.pack()
                spec = {"image": image, "output": "Color", "channel": entry["channel"]}
                spec |= {"coord": ("", None), "extension": "EXTEND"}
                spec["interpolation"] = "Linear"
                out[name] = {"done": "mesh_baked", "spec": spec}
                out[name] |= {"strength": 1.0} if name == "Normal" else {}
        return out


def finish(values, kind, names):
    """A pass's values as entries a socket, and the 8-bit image's (H, W, 3) values in
    [0, 1] when one is needed (unwritten texels the written mean, a normal flat)."""
    covered = values[..., 3] > 0.5
    rgb = values[..., :3].astype(numpy.float64)
    if not covered.any():
        return {n: {"lost": "bake wrote no texel"} for n in names}, None
    seen = rgb[covered]
    if kind == "NORMAL":
        rgb[~covered] = FLAT
        return {names[0]: {"channel": None, "colour": False}}, rgb
    entries, image = {}, False
    colour = names[0] in COLOUR
    for channel, name in enumerate(names):
        part = seen if colour else seen[:, channel : channel + 1]
        if numpy.all(part.max(axis=0) - part.min(axis=0) <= SAME):
            mean = part.mean(axis=0)
            entries[name] = {
                "value": [*mean.tolist(), 1.0] if colour else float(mean[0])
            }
        else:
            image = True
            entries[name] = {"channel": None if colour else CHANNELS[channel]}
            entries[name]["colour"] = colour
    rgb[~covered] = seen.mean(axis=0)
    return entries, (bake.encode_srgb(rgb) if colour else rgb) if image else None


def job_main(folder, key):
    """Runs one job in the opened job file: bakes its object and writes the result
    (a .png when needed, then the .json)."""
    with open(os.path.join(folder, f"{key}.job.json")) as found:
        spec = json.load(found)
    scene = bpy.data.scenes[SCENE]
    device, devices = bake.select_devices(scene)
    target = scene.objects[0]
    window = bpy.context.window
    if window is not None:
        window.scene = scene
    layer = scene.view_layers[0]
    target.select_set(True)
    layer.objects.active = target
    started = time.perf_counter()
    with bpy.context.temp_override(
        scene=scene,
        view_layer=layer,
        active_object=target,
        selected_objects=[target],
        selected_editable_objects=[target],
    ):
        bpy.ops.object.bake(
            type=spec["kind"],
            margin=bake.MESH_MARGIN,
            margin_type="EXTEND",
            use_clear=False,
            uv_layer=spec["uv_layer"],
            normal_space="TANGENT",
        )
    seconds = time.perf_counter() - started
    image = target.active_material.node_tree.nodes.active.image
    side = spec["side"]
    values = numpy.empty(side * side * 4, numpy.float32)
    image.pixels.foreach_get(values)
    entries, rgb = finish(values.reshape(side, side, 4), spec["kind"], spec["names"])
    if rgb is not None:
        made = bpy.data.images.new(key, side, side, alpha=False)
        made.colorspace_settings.name = "Non-Color"
        rgba = numpy.ones((side, side, 4), numpy.float32)
        rgba[..., :3] = numpy.rint(numpy.clip(rgb, 0, 1) * 255) / 255
        made.pixels.foreach_set(rgba.ravel())
        made.filepath_raw = os.path.join(folder, f"{key}.part.png")
        made.file_format = "PNG"
        made.save()
        os.replace(made.filepath_raw, os.path.join(folder, f"{key}.png"))
    record = {"names": entries, "device": device, "seconds": round(seconds, 2)}
    record["devices"] = devices
    with open(os.path.join(folder, f"{key}.part.json"), "w") as out:
        json.dump(record, out)
    os.replace(
        os.path.join(folder, f"{key}.part.json"), os.path.join(folder, f"{key}.json")
    )


if __name__ == "__main__":
    job_main(*sys.argv[sys.argv.index("--") + 1 :][:2])
