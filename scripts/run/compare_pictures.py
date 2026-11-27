"""The numbers and pictures of `compare.py`: a picture against its truth (mean ratio,
PSNR, the share of pixels past a bound), the difference heat map, labelled cells, strips
and crops."""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FAR = 0.1  # a display value's difference (0 to 1) counted far off
HEAT = 0.3  # the difference shown at full heat
CROP_HEIGHT = 360  # a crop's cell is scaled up (nearest) to about this height
LABEL_HEIGHT = 30
FONT = ImageFont.load_default(size=20)


def srgb_linear(picture):
    """Display bytes (H, W, 3) to linear values by the standard sRGB transfer."""
    x = picture.astype(np.float64) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def ratio_of_means(ours, truth):
    """The mean of ours over the mean of the truth (channel mean), None when the
    truth's mean is not positive."""
    t = float(np.mean(truth))
    return None if t <= 0 else round(float(np.mean(ours)) / t, 4)


def display_numbers(ours, truth, mask=None):
    """PSNR (peak 1) and the share of pixels whose largest channel differs past FAR,
    of two display pictures (bytes) over `mask` (every pixel when None)."""
    a = ours[..., :3].astype(np.float64) / 255.0
    b = truth[..., :3].astype(np.float64) / 255.0
    if mask is not None:
        a, b = a[mask], b[mask]
    if not a.size:
        return {"psnr": None, "far": None, "pixels": 0}
    mse = float(np.mean((a - b) ** 2))
    psnr = round(10 * np.log10(1.0 / mse), 2) if mse > 0 else None
    far = float(np.mean(np.abs(a - b).max(axis=-1) > FAR))
    return {"psnr": psnr, "far": round(far, 4), "pixels": int(a.size // 3)}


def pass_numbers(ours, truth, ours_shown, truth_shown, mask):
    """A pass of linear values against its truth over `mask`: the ratio of the means,
    and PSNR and the far share of their display pictures."""
    o = ours[mask].astype(np.float64).mean(axis=-1)
    t = truth[mask].astype(np.float64).mean(axis=-1)
    out = {"ratio": ratio_of_means(o, t) if len(t) else None}
    return out | display_numbers(ours_shown, truth_shown, mask)


def whole_numbers(ours_shown, truth_shown, box=None):
    """A displayed picture against the displayed truth, inside `box` (x0, y0, x1, y1
    in pixels) or over every pixel: the ratio of the linear means, PSNR, far."""
    if box is not None:
        x0, y0, x1, y1 = box
        ours_shown, truth_shown = ours_shown[y0:y1, x0:x1], truth_shown[y0:y1, x0:x1]
    ratio = ratio_of_means(srgb_linear(ours_shown), srgb_linear(truth_shown))
    return {"ratio": ratio} | display_numbers(ours_shown, truth_shown)


def heat(ours, truth, mask=None):
    """The largest channel difference of two display pictures as a heat map (bytes):
    blue none, red HEAT or more; black outside `mask`."""
    d = np.abs(ours[..., :3].astype(np.float64) - truth[..., :3]).max(axis=-1) / 255.0
    h = np.clip(d / HEAT, 0.0, 1.0)
    rgb = np.stack([h, h * 0.3, 1.0 - h], axis=-1)
    if mask is not None:
        rgb = np.where(mask[..., None], rgb, 0.0)
    return np.rint(rgb * 255).astype(np.uint8)


def labelled(picture, text):
    """A cell: the picture (bytes) with a label strip above it."""
    h, w = picture.shape[:2]
    cell = Image.new("RGB", (w, h + LABEL_HEIGHT))
    cell.paste(
        Image.fromarray(np.ascontiguousarray(picture[..., :3])), (0, LABEL_HEIGHT)
    )
    ImageDraw.Draw(cell).text((6, 4), text, fill=(255, 255, 0), font=FONT)
    return cell


def strip(cells):
    """[(label, picture)] side by side as one image."""
    shown = [labelled(p, label) for label, p in cells]
    out = Image.new("RGB", (sum(c.width for c in shown), max(c.height for c in shown)))
    x = 0
    for c in shown:
        out.paste(c, (x, 0))
        x += c.width
    return out


def sheet(rows):
    """Rows of [(label, picture)] cells, each row a strip, stacked top to bottom."""
    strips = [strip(cells) for cells in rows if cells]
    out = Image.new(
        "RGB", (max(s.width for s in strips), sum(s.height for s in strips))
    )
    y = 0
    for one in strips:
        out.paste(one, (0, y))
        y += one.height
    return out


def crop_box(fractions, size):
    """A crop's pixel box (x0, y0, x1, y1) from its fractions of the picture."""
    w, h = size
    x0, y0, x1, y1 = fractions
    box = (round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f"crop {fractions} is empty at {w} x {h}")
    return box


def cropped(picture, box):
    """The box of a picture scaled up by a whole factor (nearest) to about
    CROP_HEIGHT rows."""
    x0, y0, x1, y1 = box
    part = picture[y0:y1, x0:x1]
    factor = max(1, CROP_HEIGHT // max(1, y1 - y0))
    return np.repeat(np.repeat(part, factor, axis=0), factor, axis=1)
