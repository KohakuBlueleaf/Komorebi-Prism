"""A BLAKE2b digest of large byte strings: cut into pieces hashed on several threads, then
the digest of the pieces' digests."""

import concurrent.futures
import hashlib
import os

PIECE = 1 << 24  # bytes of a piece hashed on its own


def threads():
    """The threads that hash: the CPUs this process may use."""
    return max(1, len(os.sched_getaffinity(0)))


class Digest:
    """The bytes given by `update` in order, each update cut into PIECE-byte pieces;
    `hexdigest` hashes the pieces on `threads()` threads."""

    def __init__(self, text=""):
        self.pieces = []
        if text:
            self.update(text.encode())

    def update(self, data):
        """Adds the bytes of `data` (any buffer)."""
        view = memoryview(data).cast("B")
        self.pieces.extend(view[s : s + PIECE] for s in range(0, len(view), PIECE))
        if not len(view):
            self.pieces.append(view)

    def hexdigest(self):
        """The BLAKE2b hex digest of the pieces' BLAKE2b digests, in order."""
        with concurrent.futures.ThreadPoolExecutor(threads()) as pool:
            digests = pool.map(
                lambda piece: hashlib.blake2b(piece).digest(), self.pieces
            )
            top = hashlib.blake2b()
            for one in digests:
                top.update(one)
        return top.hexdigest()
