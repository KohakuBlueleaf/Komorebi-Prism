"""Loading the compiled helpers as libraries: the batch ray routine."""

import ctypes

from prism_reference.native.build import TRACE, build

_LIBRARY = {}


def library():
    """The batch ray routine (trace/trace_batch.cpp), built once as a library."""
    if "lib" not in _LIBRARY:
        source = TRACE / "trace_batch.cpp"
        path = build(str(source), "libtrace_batch.so", (), True)
        if path is None:
            raise RuntimeError("indirect light traces rays in C++: no compiler found")
        lib = ctypes.CDLL(str(path))
        pointer = ctypes.c_void_p
        lib.trace_batch.argtypes = [pointer] * 6 + [ctypes.c_long, ctypes.c_int]
        lib.trace_batch.argtypes += [pointer] * 4 + [ctypes.c_int]
        _LIBRARY["lib"] = lib
    return _LIBRARY["lib"]
