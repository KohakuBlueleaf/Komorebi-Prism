"""The viewer's server checked without a browser, on one card: the server started, 403
without the token, the state and the catalog read, poses posted and their frames read
from the stream, two sizes (one past the capacity), refusals, then at the view's own
pose each control moved (and moved back) and a frame after it, then each kind's own
checks (prism_viewer.server.check_kinds), then the pose's field of view narrower, wider
and back (prism_viewer.server.check_fov); the server stopped by SIGTERM; then, that
control set and that pose on a loop of the check's own, each frame's JPEG against
the loop's picture through the same encoder (at most SERVED_BOUND apart; another pose's
must be further) and the loop's picture by the preset's JUDGE. One JSON line; exit 1 on
a failure.
python -m prism_viewer.server.check [--pipeline raster --scene sponza --view overview]
"""

import argparse
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import komorebi as km
import numpy as np
from prism_cli.preset import opened

from prism_reference.scene.camera import sized_camera, with_size
from prism_viewer.server import check_fov, encode
from prism_viewer.server.camera import camera_of, pose_of
from prism_viewer.server.check_kinds import checked, moved

OPEN_S = 900.0  # the first load builds the kernels
FOLLOW_S = 120.0  # a request: at most this for the state and a frame to show it
STOP_S = 60.0
POSES, POSE_GAP_S = 20, 0.1
SIZES = ((1280, 720), (1920, 1080))  # within the capacity, then past it (a reload)
SERVED_BOUND = 0.5  # served JPEG vs the loop's picture through the same encoder: mean


def get(url, timeout=10.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read()


def post(url, body, token, timeout=10.0):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Token"] = token
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read()
        return error.code, json.loads(body) if body.startswith(b"{") else body


def status_of(call):
    """The HTTP status of a call, an error's included."""
    try:
        return call()[0]
    except urllib.error.HTTPError as error:
        return error.code


class Reader(threading.Thread):
    """The stream's JPEG parts with their frame and pose numbers, until `stop`."""

    def __init__(self, url):
        super().__init__(daemon=True)
        self.url, self.parts, self.error = url, [], None
        self.stop = threading.Event()

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=FOLLOW_S) as response:
                while not self.stop.is_set():
                    headers = {}
                    line = response.readline()
                    while line in (b"\r\n", b"\n"):
                        line = response.readline()
                    if not line:
                        return
                    while (line := response.readline().strip()) != b"":
                        key, _, value = line.decode().partition(":")
                        headers[key.strip().lower()] = value.strip()
                    data = response.read(int(headers["content-length"]))
                    self.parts.append(
                        (int(headers["x-frame"]), int(headers["x-pose"]), data)
                    )
        except Exception as error:  # noqa: BLE001 - reported in the record
            self.error = f"{type(error).__name__}: {error}"

    def frame_of(self, pose, size, timeout, after=0):
        """The first part of `pose` (its serial) past frame `after` decoding to
        `size`, waited for."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for number, serial, data in list(self.parts):
                if number <= after or serial < pose:
                    continue
                if encode.decoded(data).shape[1::-1] == tuple(size):
                    return data
            time.sleep(0.05)
        return None


def wait_state(base, token, test, timeout):
    """The state once `test(state)` holds, or None after `timeout`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = json.loads(get(f"{base}/api/state?token={token}")[1])
            if test(state):
                return state
            if state["status"] == "error":
                return state
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(0.25)
    return None


def compared(got, want):
    """Mean and largest absolute difference, PSNR in dB, of two uint8 images."""
    error = np.abs(got.astype(np.int32) - want.astype(np.int32))
    mse = float((error.astype(np.float64) ** 2).mean())
    psnr = math.inf if mse == 0 else 10.0 * math.log10(255.0**2 / mse)
    return {
        "mean": round(float(error.mean()), 3),
        "most": int(error.max()),
        "psnr": round(psnr, 2),
    }


def coded(image):
    """`image` through the server's JPEG and back: what the stream would carry."""
    return encode.decoded(encode.jpeg(image))


def set_shown(base, token, reader, pose, size, record, control, value):
    """`value` posted for `control`, waited for in the state and in a frame after it:
    that frame's JPEG (None when not shown, a failure noted)."""
    name = control["name"]
    want = json.loads(json.dumps(value))
    post(f"{base}/api/control", {"name": name, "value": value}, token, FOLLOW_S)
    shown = wait_state(
        base,
        token,
        lambda s: {c["name"]: c["value"] for c in s["controls"]}.get(name) == want,
        FOLLOW_S,
    )
    if shown is None or shown["status"] != "running":
        record["failures"].append(f"control {name} = {value} not shown")
        return None
    data = reader.frame_of(pose, size, FOLLOW_S, shown["frame"])
    if data is None:
        record["failures"].append(f"no frame after {name} = {value}")
    return data


def served(base, token, args, record):
    """The server's half of the check, on a running server: the pictures served at the
    view's own pose (a label, the controls set, the JPEG), that pose, the last pose of
    the poses posted and the size; None on a failure before them."""
    fail = record["failures"]
    if wait_state(base, token, lambda s: True, OPEN_S) is None:
        fail.append("the server did not answer")
        return None
    no = {
        "GET state": lambda: get(f"{base}/api/state"),
        "GET catalog": lambda: get(f"{base}/api/catalog?token=wrong"),
        "GET stream": lambda: get(f"{base}/api/stream"),
        "POST pose": lambda: post(f"{base}/api/pose", {}, None),
        "POST size": lambda: post(f"{base}/api/size", {}, "wrong"),
        "POST select": lambda: post(f"{base}/api/select", {}, None),
        "POST control": lambda: post(f"{base}/api/control", {}, None),
    }
    record["forbidden"] = {name: status_of(call) for name, call in no.items()}
    fail += [
        f"{name} {code}" for name, code in record["forbidden"].items() if code != 403
    ]
    state = wait_state(base, token, lambda s: s["status"] == "running", OPEN_S)
    if state is None or state["status"] != "running":
        fail.append(f"not running: {state and state['error']}")
        return None
    known = json.loads(get(f"{base}/api/catalog?token={token}")[1])
    record["catalog"] = {
        "pipelines": [one["name"] for one in known["pipelines"]],
        "scenes": len(known["scenes"]),
    }
    if args.pipeline not in record["catalog"]["pipelines"]:
        fail.append(f"catalog lacks {args.pipeline}")
    record["controls"] = {c["name"]: c["value"] for c in state["controls"]}
    reader = Reader(f"{base}/api/stream?token={token}")
    reader.start()
    first, serial = state["first_pose"], state["scene_serial"]
    step = 0.02 * state["diagonal"]
    began = time.monotonic()
    for index in range(POSES):
        pose = dict(first, yaw=first["yaw"] + 0.01 * index)
        ahead = camera_of(np.zeros(16, np.float32), pose)[9:12]
        pose["position"] = [
            float(p + step * index * a) for p, a in zip(first["position"], ahead)
        ]
        _, answer = post(f"{base}/api/pose", pose | {"scene_serial": serial}, token)
        last_pose, last_serial = pose, answer.get("taken")
        time.sleep(POSE_GAP_S)
    size = tuple(state["size"])
    if reader.frame_of(last_serial, size, FOLLOW_S) is None:
        fail.append("no frame of the last pose")
    seconds = time.monotonic() - began
    state = wait_state(base, token, lambda s: True, 5.0)
    record["poses"] = {
        "posted": POSES,
        "frames_read": len(reader.parts),
        "seconds": round(seconds, 2),
        "fps_state": state["fps"],
        "times_ms": state["times"],
    }
    record["sizes"] = []
    for width, height in SIZES:
        asked = time.monotonic()
        post(f"{base}/api/size", {"width": width, "height": height}, token)
        shown = wait_state(
            base, token, lambda s, want=[width, height]: s["size"] == want, FOLLOW_S
        )
        data = reader.frame_of(last_serial, (width, height), FOLLOW_S)
        notes = [n for n in (shown or {}).get("notices", []) if "size" in n["text"]]
        record["sizes"].append(
            {
                "size": [width, height],
                "shown_s": round(time.monotonic() - asked, 2),
                "frame": data is not None,
                "notice": notes[-1] if notes else None,
                "capacity": (shown or {}).get("capacity"),
            }
        )
        if data is None or shown is None:
            fail.append(f"size {width} x {height} not shown")
    first_size = list(state["size"])
    post(f"{base}/api/size", {"width": first_size[0], "height": first_size[1]}, token)
    if wait_state(base, token, lambda s: s["size"] == first_size, FOLLOW_S) is None:
        fail.append(f"size {first_size} not shown again")
    again = wait_state(base, token, lambda s: s["status"] == "running", FOLLOW_S)
    if again is None:
        fail.append("not running after the sizes")
        return None
    view_pose = again["first_pose"]
    _, answer = post(
        f"{base}/api/pose", view_pose | {"scene_serial": again["scene_serial"]}, token
    )
    at_serial = answer.get("taken")
    some = next(iter(record["controls"]), "nothing")
    record["refused"] = {
        "size": post(f"{base}/api/size", {"width": 0, "height": 5}, token),
        "control value": post(
            f"{base}/api/control", {"name": some, "value": "yes"}, token
        ),
        "control name": post(
            f"{base}/api/control", {"name": "nothing", "value": 1}, token
        ),
    }
    fail += [f"refused {k} {v[0]}" for k, v in record["refused"].items() if v[0] != 400]
    shown = wait_state(base, token, lambda s: True, 5.0)
    size = tuple(first_size)
    data = reader.frame_of(at_serial, size, FOLLOW_S, shown["frame"])
    context = (base, token, reader, at_serial, size, record)
    pictures = [("as loaded", {}, data)]
    for control in state["controls"]:
        value = moved(control)
        pictures.append(
            (
                control["name"],
                {control["name"]: value},
                set_shown(*context, control, value),
            )
        )
        set_shown(*context, control, control["value"])
    kinds = {"failures": fail}
    more, expect = checked(
        state["controls"],
        lambda control, value: set_shown(*context, control, value),
        lambda name, value: post(
            f"{base}/api/control", {"name": name, "value": value}, token, FOLLOW_S
        ),
        lambda test: wait_state(base, token, test, FOLLOW_S),
        kinds,
    )
    pictures += more
    record["kinds"] = {k: v for k, v in kinds.items() if k != "failures"}
    posed, expect_fov = check_fov.checked(
        view_pose,
        again["scene_serial"],
        lambda pose: post(f"{base}/api/pose", pose, token)[1].get("taken"),
        lambda test: wait_state(base, token, test, FOLLOW_S),
        lambda serial, after: reader.frame_of(serial, size, FOLLOW_S, after),
        record,
    )
    pictures += posed
    record["expect"] = expect | expect_fov
    final = wait_state(base, token, lambda s: True, 5.0)
    record["after_controls"] = {"frames": len(reader.parts), "times": final["times"]}
    record["card"] = final["card"]
    reader.stop.set()
    if reader.error:
        record["stream_error"] = reader.error
    return pictures, view_pose, last_pose, size


def own_pictures(args, pose, other, size, pictures):
    """Each served picture (a label, the controls set, its JPEG, its pose when not
    `pose`), those controls set on a loop of its own at that pose (else `pose`, the
    view's own) and `size`: the JPEG against the loop's picture through the same
    encoder (it is the loop's picture), the loop's picture by the preset's JUDGE (it is
    right); the first against the pose `other`'s too (must differ). The JPEG against
    the unencoded pictures is reported."""
    preset = opened(args.pipeline, args.scene, args.view, size)
    scene = preset.scene
    own_pose = json.loads(json.dumps(pose_of(scene["camera"])))
    out, base = {}, None
    with km.Session(card=args.card) as session:
        loop = preset.open(session)
        try:
            before = {control.name: control.value for control in loop.controls()}
            for label, setting, data, *posed in pictures:
                for name, value in setting.items():
                    loop.set(name, value)
                at = posed[0] if posed else pose
                camera = (
                    scene["camera"]
                    if at == own_pose
                    else camera_of(scene["camera"], at)
                )
                frame = loop.frame(sized_camera(camera, size), picture=True)
                if frame.code:
                    raise RuntimeError(f"the loop's frame code {frame.code}")
                own = encode.colour(frame.picture, size)
                view = with_size(dict(scene, camera=camera), size)
                judge = preset.judge(loop, view)
                want = encode.colour(preset.reference(loop, view), size)
                got = None if data is None else encode.decoded(data)
                base = got if base is None else base
                out[label] = {"set": setting} | (
                    {"shown": False}
                    if got is None
                    else {
                        "served": compared(got, coded(own)),
                        "judged": None if judge is None else judge(frame.picture),
                        "from_loaded": compared(got, base),
                        "unencoded": {
                            "own": compared(got, own),
                            "reference": compared(got, want),
                        },
                    }
                )
                if label == pictures[0][0] and got is not None:
                    away = loop.frame(
                        sized_camera(camera_of(scene["camera"], other), size), True
                    )
                    if away.code:
                        raise RuntimeError(f"the loop's frame code {away.code}")
                    away = coded(encode.colour(away.picture, size))
                    out[label]["other_pose"] = compared(got, away)
                for name in setting:
                    loop.set(name, before[name])
        finally:
            loop.stop()
    return out


def main():
    parser = argparse.ArgumentParser(prog="prism_viewer.server.check")
    parser.add_argument("--pipeline", default="raster")
    parser.add_argument("--scene", default="sponza")
    parser.add_argument("--view", default="overview")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--card", type=int, default=0)
    parser.add_argument("--log", default=None, help="the server's output file")
    args = parser.parse_args()
    token, base = secrets.token_hex(16), f"http://127.0.0.1:{args.port}"
    command = [sys.executable, "-m", "prism_viewer.server", "--host", "127.0.0.1"]
    command += ["--port", str(args.port), "--token", token, "--card", str(args.card)]
    command += ["--pipeline", args.pipeline, "--scene", args.scene]
    command += ["--view", args.view] if args.view else []
    record = {"failures": [], "server_pid": None}
    with open(args.log or os.devnull, "w") as out:
        process = subprocess.Popen(
            command, stdout=out, stderr=subprocess.STDOUT, env=os.environ
        )
    record["server_pid"] = process.pid
    try:
        result = served(base, token, args, record)
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            record["server_exit"] = process.wait(timeout=STOP_S)
        except subprocess.TimeoutExpired:
            process.kill()
            record["server_exit"] = "killed"
            record["failures"].append("the server did not stop on SIGTERM")
    if record["server_exit"] != 0:
        record["failures"].append(f"server exit {record['server_exit']}")
    if result is not None:
        pictures, pose, other, size = result
        judged = own_pictures(args, pose, other, size, pictures)
        record["pictures"] = {"size": list(size), "by_setting": judged}
        record["pictures"]["bound"] = {"served_mean": SERVED_BOUND}
        fail = record["failures"]
        for label, numbers in judged.items():
            if not numbers.get("shown", True):
                fail.append(f"{label}: no picture")
                continue
            if numbers["served"]["mean"] > SERVED_BOUND:
                fail.append(f"{label}: the served picture is not the loop's")
            if numbers.get("other_pose", {"mean": math.inf})["mean"] <= SERVED_BOUND:
                fail.append("the bound does not tell another pose apart")
            want = record.get("expect", {}).get(label)
            near = numbers["from_loaded"]["mean"] <= SERVED_BOUND
            if want is not None and near != (want == "same"):
                fail.append(f"{label}: not {want} as loaded")
    record["ok"] = not record["failures"]
    print(json.dumps(record, default=str), flush=True)
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
