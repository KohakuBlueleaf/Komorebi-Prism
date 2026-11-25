"""Comparing two sides' results array by array, and recording and printing each case."""

import time

import numpy as np

RESULTS = []


def arrays_of(value, prefix=""):
    """{dotted key: array} of nested dicts, lists and tuples of arrays and numbers."""
    if isinstance(value, list | tuple):
        value = dict(enumerate(value))
    if not isinstance(value, dict):
        return {prefix.rstrip("."): np.asarray(value)}
    out = {}
    for key, item in value.items():
        out |= arrays_of(item, f"{prefix}{key}.")
    return out


def report(name, issues, arrays, seconds):
    """Records and prints one case."""
    equal = not issues
    RESULTS.append({"case": name, "equal": equal, "arrays": arrays, "issues": issues})
    status = "equal" if equal else "DIFFERENT"
    print(f"{status:9s} {name}: {arrays} arrays, {seconds:.1f} s", flush=True)
    for issue in issues[:10]:
        print(f"          {issue}", flush=True)


def compare(name, ours, theirs, seconds):
    """One case: equal when the keys match and every array is np.array_equal."""
    mine, other = arrays_of(ours), arrays_of(theirs)
    issues = []
    if set(mine) != set(other):
        issues.append(f"keys differ: {sorted(set(mine) ^ set(other))[:8]}")
    for key in sorted(set(mine) & set(other)):
        a, b = mine[key], other[key]
        if a.dtype != b.dtype or a.shape != b.shape or not np.array_equal(a, b):
            issues.append(f"{key}: {a.dtype}{a.shape} vs {b.dtype}{b.shape}")
    report(name, issues, len(mine), seconds)


def outcome(function, *args):
    """function's result, or the text of the ValueError it raises."""
    try:
        return function(*args)
    except ValueError as error:
        return f"ValueError: {error}"


def asserted(name, conditions, started):
    """A case of named conditions that must hold: (label, bool) pairs."""
    issues = [label for label, ok in conditions if not ok]
    report(name, issues, len(conditions), time.perf_counter() - started)
