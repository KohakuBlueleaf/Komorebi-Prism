"""The frame: its default size, its tiles and the grid of tiles of any size."""

WIDTH = HEIGHT = 1024
TILE = 32


def frame_grid(size):
    """The grid (TX, TY) of a frame of size (W, H): ceil(W / TILE) by ceil(H / TILE)
    tiles; ValueError with the reason unless both are positive."""
    width, height = (int(n) for n in size)
    if width < 1 or height < 1:
        raise ValueError(f"a frame of {width} x {height} pixels: both must be >= 1")
    return -(-width // TILE), -(-height // TILE)


def frame_size(scene):
    """A scene's frame size (W, H): its `size` entry, else (WIDTH, HEIGHT)."""
    width, height = scene.get("size", (WIDTH, HEIGHT))
    return int(width), int(height)
