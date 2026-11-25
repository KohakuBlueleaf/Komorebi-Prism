"""The textures as pages: every level of every texture in 32 x 32 blocks of texels."""

import numpy as np

from prism.stages.material.texture.model.numbers import PAGE


def texture_pages(materials):
    """Every level of every texture in 32 x 32 blocks of texels (a page each, blocks row
    by row, edge blocks padded by repeating), and per (texture, level) its first page,
    width and height: ((pages, 1024) uint32, (N, 11, 3))."""
    mip, levels, texels = materials["mip"], materials["levels"], materials["texels"]
    entries = np.zeros((len(levels), mip.shape[1], 3), dtype=np.int64)
    blocks = []
    first = 0
    for texture in range(len(levels)):
        for level in range(levels[texture]):
            offset, width, height = (int(v) for v in mip[texture, level])
            words = (
                texels[offset : offset + 4 * width * height]
                .view(np.uint32)
                .reshape(height, width)
            )
            across, down = -(-width // PAGE), -(-height // PAGE)
            padded = np.pad(
                words, ((0, down * PAGE - height), (0, across * PAGE - width)), "edge"
            )
            page_words = padded.reshape(down, PAGE, across, PAGE).transpose(0, 2, 1, 3)
            blocks.append(page_words.reshape(-1, PAGE * PAGE))
            entries[texture, level] = first, width, height
            first += across * down
    return np.concatenate(blocks), entries
