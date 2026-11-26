"""The threads of the BLAS library numpy loaded (OpenBLAS), read and set through its own
calls; nothing where the library or the calls are not found."""

import ctypes
import os
from contextlib import contextmanager

MAPS = "/proc/self/maps"
PREFIXES = ("scipy_openblas", "openblas")
SUFFIXES = ("64_", "")


def openblas():
    """(get, set) of the loaded OpenBLAS' thread count, or None."""
    if not os.path.exists(MAPS):
        return None
    with open(MAPS) as f:
        paths = {line.split()[-1] for line in f if "openblas" in line.lower()}
    for path in sorted(p for p in paths if p.startswith("/")):
        lib = ctypes.CDLL(path)
        for prefix in PREFIXES:
            for suffix in SUFFIXES:
                get = getattr(lib, f"{prefix}_get_num_threads{suffix}", None)
                put = getattr(lib, f"{prefix}_set_num_threads{suffix}", None)
                if get is not None and put is not None:
                    put.argtypes = [ctypes.c_int]
                    return get, put
    return None


@contextmanager
def blas_threads(count):
    """Runs the block with the BLAS library on `count` threads, then as it was."""
    calls = openblas()
    if calls is None:
        yield
        return
    get, put = calls
    before = get()
    put(count)
    try:
        yield
    finally:
        put(before)
