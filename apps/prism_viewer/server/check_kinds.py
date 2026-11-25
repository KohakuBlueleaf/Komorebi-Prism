"""The viewer check's part for the controls' kinds: another value of each control, then
by kind on the running server: a direction's second angle moved within its limits and
one past them refused with its reason, a choice's labels, a count set to its least (one
with no most also past its value) and back (the host's readings follow: its updates and
passes), the display's gamma moved and back; the display's default table as today's.
Each gives pictures (a label, the controls set, the JPEG) and what they must be.
"""

from functools import partial

from prism.stages.post.show.model.table import show_table
from prism_reference.post.display import GAMMA, to_power8

TURN_DEGREES = 60.0  # a direction control's first angle turned by this
ELEVATION = 50.0  # a direction's second angle moved to this (within its limits)
PAST_DEGREES = 30.0  # a direction's second angle this far past its most: refused
BEYOND = 3  # a count with no most also set this far over its value


def moved(control):
    """Another value of a control, by its kind: a toggle flipped, a range at half as
    much again (or halfway down), a count one more (or one less at its most), the next
    choice, a direction's first angle turned."""
    value, limits = control["value"], control["limits"]
    match control["kind"]:
        case "toggle":
            return not value
        case "range":
            least, most = limits
            return value * 1.5 if least < value * 1.5 <= most else (least + value) / 2
        case "count":
            return value + 1 if limits[1] is None or value < limits[1] else value - 1
        case "choice":
            values = [one for one, _ in control["choices"]]
            return values[(values.index(value) + 1) % len(values)]
        case "direction":
            least, most = limits[0]
            turned = value[0] + TURN_DEGREES
            return [turned if turned <= most else value[0] - TURN_DEGREES, value[1]]
    raise ValueError(f"control {control['name']}: no kind {control['kind']!r}")


def reading_of(state, control, name):
    """The value `name` of the readings of the control's implementation, or None."""
    for given in state.get("readings", []):
        if control["name"].startswith(f"{given['name']}."):
            values = {one["name"]: one["value"] for one in given["values"]}
            return values.get(name)
    return None


def direction(control, shown, post, record):
    """The second angle moved within its limits (a picture) and past its most (refused
    with its reason, the value kept); back."""
    value, (least, most) = control["value"], control["limits"][1]
    target = ELEVATION if least <= ELEVATION <= most else (least + most) / 2
    label = f"{control['name']} elevation {target:g}"
    pictures = [(label, {control["name"]: [value[0], target]})]
    pictures[0] += (shown(control, [value[0], target]),)
    past = [value[0], most + PAST_DEGREES]
    code, body = post(control["name"], past)
    reason = body.get("error", "") if isinstance(body, dict) else str(body)
    record[control["name"]] = {"past": past, "answer": code, "reason": reason}
    if code != 400 or "elevation" not in reason:
        record["failures"].append(f"{control['name']} = {past}: {code} {reason!r}")
    shown(control, value)
    return pictures, {}


def choice(control, shown, post, record):
    """Every choice a (value, label) with a label; the next set by its value (the
    pictures of the controls moved hold it)."""
    labels = {str(value): label for value, label in control["choices"]}
    record[control["name"]] = {"labels": labels}
    if not all(isinstance(label, str) and label for label in labels.values()):
        record["failures"].append(f"{control['name']}: a choice without a label")
    return [], {}


def count(control, shown, post, record, wait):
    """The count at its least, with no most also at BEYOND over its value, then at its
    value again: each time the host's readings give one update more and that many
    passes; the picture after the last must be the one as loaded."""
    name, value, (least, most) = control["name"], control["value"], control["limits"]
    targets = (least, value) if most is not None else (least, value + BEYOND, value)
    pictures, steps = [], []
    for target in targets:
        before = wait(lambda s: True)
        updates = reading_of(before, control, "updates")
        data = shown(control, target)
        after = wait(
            lambda s, u=updates, t=target: reading_of(s, control, "updates") == u + 1
            and reading_of(s, control, "passes") == t
        )
        got = None if after is None else reading_of(after, control, "passes")
        steps.append({"set": target, "updates_before": updates, "passes": got})
        if after is None:
            record["failures"].append(f"{name} = {target}: no update with its passes")
        pictures.append((f"{name} = {target}", {name: target}, data))
    record[name] = steps
    return pictures, {pictures[-1][0]: "same"}


def gamma(control, shown, post, record):
    """The gamma halfway down to its least (the picture must differ) and back (the
    picture must be the one as loaded); when its most is over its value, up to the most
    and back the same."""
    name, value, (least, most) = control["name"], control["value"], control["limits"]
    others = [(least + value) / 2, *([most] if most > value else [])]
    pictures, expect = [], {}
    for other in others:
        there = (f"{name} = {other:g}", {name: other}, shown(control, other))
        back = (f"{name} = {value:g} again from {other:g}", {}, shown(control, value))
        pictures += [there, back]
        expect |= {there[0]: "differs", back[0]: "same"}
    record[name] = {"moved": others, "back": value, "limits": control["limits"]}
    return pictures, expect


def default_table(record):
    """The display's table of the power transfer at GAMMA, word for word today's."""
    same = bool((show_table(partial(to_power8, gamma=GAMMA)) == show_table()).all())
    record["default_table_is_todays"] = same
    if not same:
        record["failures"].append("the default transfer's table is not today's")


def checked(controls, shown, post, wait, record):
    """The kinds' checks over `controls` (the state's): their pictures and what each
    must be against the one as loaded ("same" or "differs")."""
    pictures, expect = [], {}
    default_table(record)
    for control in controls:
        match control["kind"]:
            case "direction":
                got = direction(control, shown, post, record)
            case "choice":
                got = choice(control, shown, post, record)
            case "count":
                got = count(control, shown, post, record, wait)
            case "range" if control["name"].endswith(".gamma"):
                got = gamma(control, shown, post, record)
            case _:
                continue
        pictures += got[0]
        expect |= got[1]
    return pictures, expect
