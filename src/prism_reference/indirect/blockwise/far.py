"""Admissible blocks in low-rank form by adaptive cross approximation: every block
advances one cross a step, all blocks at once over flat rows and columns."""

import numpy as np

from prism_reference.indirect.blockwise.pairs import facing, pair_values

F = np.float32
# Random facing entries of a block that check its residual, and their seed.
SAMPLES, SAMPLE_SEED = 32, 61
GROW = 16  # columns added to the factors when a block's rank reaches their width
ZERO = 1e-12  # a residual row is empty at most this share of the block's largest entry


def segment_first_max(value, owner, count):
    """Per segment (owners 0..count-1, value grouped by owner) the flat index of its
    first largest value, and that value; -1 and -inf for an empty segment."""
    best = np.full(count, -np.inf)
    np.maximum.at(best, owner, value)
    hit = np.nonzero(value == best[owner])[0]
    first = np.full(count, -1)
    seg, at = np.unique(owner[hit], return_index=True)
    first[seg] = hit[at]
    return first, best


class Blocks:
    """The far blocks' flat layout: rows R and columns C of all blocks one after the
    other, each flat row or column naming its element."""

    def __init__(self, r0, r1, c0, c1):
        self.m, self.n = r1 - r0, c1 - c0
        self.ro = np.cumsum(self.m) - self.m
        self.co = np.cumsum(self.n) - self.n
        self.row_owner = np.repeat(np.arange(len(r0)), self.m)
        self.col_owner = np.repeat(np.arange(len(r0)), self.n)
        self.row_elem = (
            r0[self.row_owner] + np.arange(self.m.sum()) - self.ro[self.row_owner]
        )
        self.col_elem = (
            c0[self.col_owner] + np.arange(self.n.sum()) - self.co[self.col_owner]
        )

    def cols_of(self, ids):
        """Flat columns of blocks `ids`, concatenated, and each one's place in ids."""
        n = self.n[ids]
        place = np.repeat(np.arange(len(ids)), n)
        return (
            np.repeat(self.co[ids], n)
            + np.arange(n.sum())
            - np.repeat(np.cumsum(n) - n, n),
            place,
        )

    def rows_of(self, ids):
        """Flat rows of blocks `ids`, concatenated, and each one's place in ids."""
        m = self.m[ids]
        place = np.repeat(np.arange(len(ids)), m)
        return (
            np.repeat(self.ro[ids], m)
            + np.arange(m.sum())
            - np.repeat(np.cumsum(m) - m, m),
            place,
        )


def facing_counts(blocks, p, n, real, rng):
    """Per flat row and column its count of facing real partners in its block, and per
    block SAMPLES random facing entries (flat row, flat column; -1 where fewer)."""
    rows = np.zeros(blocks.m.sum(), np.int64)
    cols = np.zeros(blocks.n.sum(), np.int64)
    sample_r = np.full((len(blocks.m), SAMPLES), -1)
    sample_c = np.full((len(blocks.m), SAMPLES), -1)
    for b in range(len(blocks.m)):
        rs = blocks.row_elem[blocks.ro[b] : blocks.ro[b] + blocks.m[b]]
        cs = blocks.col_elem[blocks.co[b] : blocks.co[b] + blocks.n[b]]
        mask = facing(p, n, rs, cs) & real[rs][:, None] & real[cs][None, :]
        rows[blocks.ro[b] : blocks.ro[b] + blocks.m[b]] = mask.sum(1)
        cols[blocks.co[b] : blocks.co[b] + blocks.n[b]] = mask.sum(0)
        where = np.flatnonzero(mask)
        if len(where):
            pick = rng.choice(where, min(SAMPLES, len(where)), replace=False)
            sample_r[b, : len(pick)] = blocks.ro[b] + pick // blocks.n[b]
            sample_c[b, : len(pick)] = blocks.co[b] + pick % blocks.n[b]
    return rows, cols, sample_r, sample_c


def cross_blocks(tree, elements, real, eps, r0, r1, c0, c1, tolerance):
    """Low-rank factors U (m, k), V (n, k) float64 of each block of M = pi F with
    M ~ U V^T, by cross approximation to `tolerance`; None for a block left to be
    computed whole (its rank reached m n / (m + n)). Factors, rays, steps."""
    p = elements["position"].astype(np.float64)
    nrm = elements["normal"].astype(np.float64)
    blocks = Blocks(r0, r1, c0, c1)
    count = len(r0)
    rng = np.random.default_rng(SAMPLE_SEED)
    row_count, _, sample_r, sample_c = facing_counts(blocks, p, nrm, real, rng)
    rays = 0
    has = sample_r >= 0
    sample_v = np.zeros(sample_r.shape)
    if has.any():
        value, traced = pair_values(
            tree,
            elements,
            blocks.row_elem[sample_r[has]],
            blocks.col_elem[sample_c[has]],
            eps,
        )
        sample_v[has] = value * np.pi
        rays += traced
    facing_total = np.zeros(count)
    np.add.at(facing_total, blocks.row_owner, row_count)
    width = GROW
    u = np.zeros((blocks.m.sum(), width))
    v = np.zeros((blocks.n.sum(), width))
    rank = np.zeros(count, np.int64)
    s2 = np.zeros(count)
    largest = np.zeros(count)
    used_row = row_count == 0
    used_col = np.zeros(blocks.n.sum(), dtype=bool)
    cap = (blocks.m * blocks.n) // (blocks.m + blocks.n)
    whole = np.zeros(count, dtype=bool)
    pivot, _ = segment_first_max(
        np.where(used_row, -1, row_count), blocks.row_owner, count
    )
    done = (facing_total == 0) | (pivot < 0) | ~has.any(1)
    pivot[done] = -1
    steps = 0
    while not done.all():
        steps += 1
        act = np.nonzero(~done)[0]
        if rank[act].max() >= width:
            u = np.concatenate([u, np.zeros((len(u), GROW))], 1)
            v = np.concatenate([v, np.zeros((len(v), GROW))], 1)
            width += GROW
        k = int(rank[act].max())
        prow = pivot[act]
        cols, place = blocks.cols_of(act)
        value, traced = pair_values(
            tree, elements, blocks.row_elem[prow[place]], blocks.col_elem[cols], eps
        )
        rays += traced
        value = value * np.pi * real[blocks.col_elem[cols]]
        res = value - np.einsum("ek,ek->e", u[prow[place], :k], v[cols, :k])
        np.maximum.at(largest, act[place], np.abs(value))
        score = np.where(used_col[cols], -1.0, np.abs(res))
        jat, jbest = segment_first_max(score, place, len(act))
        used_row[prow] = True
        live = jbest > ZERO * largest[act]
        term = np.zeros(len(act))
        if live.any():
            la = act[live]
            jcol = cols[jat[live]]
            delta = res[jat[live]]
            keep = live[place]
            v_new = np.zeros(len(v))
            v_new[cols[keep]] = res[keep] / delta[np.cumsum(live)[place[keep]] - 1]
            rows, rplace = blocks.rows_of(la)
            cvalue, traced = pair_values(
                tree,
                elements,
                blocks.row_elem[rows],
                blocks.col_elem[jcol[rplace]],
                eps,
            )
            rays += traced
            cvalue = cvalue * np.pi * real[blocks.row_elem[rows]]
            u_new = cvalue - np.einsum("ek,ek->e", u[rows, :k], v[jcol[rplace], :k])
            used_col[jcol] = True
            kk = rank[la]
            cross_uu = np.zeros((len(la), k))
            np.add.at(cross_uu, rplace, u[rows, :k] * u_new[:, None])
            vcols, vplace = blocks.cols_of(la)
            cross_vv = np.zeros((len(la), k))
            np.add.at(cross_vv, vplace, v[vcols, :k] * v_new[vcols][:, None])
            uu = np.bincount(rplace, u_new * u_new, len(la))
            vv = np.bincount(vplace, v_new[vcols] ** 2, len(la))
            s2[la] += 2 * (cross_uu * cross_vv).sum(1) + uu * vv
            u[rows, kk[rplace]] = u_new
            v[vcols, kk[vplace]] = v_new[vcols]
            rank[la] += 1
            term[live] = np.sqrt(uu * vv)
            urow_score = np.where(used_row[rows], -1.0, np.abs(u_new))
            nat, nbest = segment_first_max(urow_score, rplace, len(la))
            next_live = np.where(nbest > 0, rows[np.maximum(nat, 0)], -1)
        kq = int(rank[act].max())
        sr, sc, sh = sample_r[act], sample_c[act], has[act]
        approx = np.einsum(
            "bsk,bsk->bs", u[np.maximum(sr, 0), :kq], v[np.maximum(sc, 0), :kq]
        )
        sres = np.where(sh, sample_v[act] - approx, 0.0)
        rms = np.sqrt((sres**2).sum(1) / np.maximum(sh.sum(1), 1))
        scale = np.sqrt(s2[act] / np.maximum(facing_total[act], 1))
        ok_norm = term <= tolerance * np.sqrt(s2[act])
        ok_sample = rms <= tolerance * scale
        finished = ok_norm & ok_sample
        worst = np.argmax(np.abs(sres), 1)
        worst_row = sr[np.arange(len(act)), worst]
        nxt = np.full(len(act), -1)
        if live.any():
            nxt[live] = next_live
        fallback, _ = segment_first_max(
            np.where(used_row, -1, row_count), blocks.row_owner, count
        )
        retry = ok_norm & ~ok_sample & ~used_row[np.maximum(worst_row, 0)]
        nxt = np.where(retry, worst_row, nxt)
        bad = nxt < 0
        nxt[bad] = fallback[act[bad]]
        nxt = np.where((nxt >= 0) & used_row[np.maximum(nxt, 0)], fallback[act], nxt)
        pivot[act] = nxt
        over = rank[act] >= cap[act]
        whole[act[over & ~finished]] = True
        done[act[finished | over | (nxt < 0)]] = True
    factors = []
    for b in range(count):
        if whole[b]:
            factors.append(None)
            continue
        k = rank[b]
        factors.append(
            (
                u[blocks.ro[b] : blocks.ro[b] + blocks.m[b], :k],
                v[blocks.co[b] : blocks.co[b] + blocks.n[b], :k],
            )
        )
    return factors, rays, steps


def recompress(u, v, tolerance):
    """U (m, k), V (n, k) reduced to the singular values above `tolerance` times the
    largest: (U', V') with sigma^(1/2) each, or None when the block is zero."""
    if u.shape[1] == 0:
        return None
    qu, ru = np.linalg.qr(u)
    qv, rv = np.linalg.qr(v)
    a, sigma, bt = np.linalg.svd(ru @ rv.T)
    if sigma[0] <= 0:
        return None
    k = int((sigma > tolerance * sigma[0]).sum())
    root = np.sqrt(sigma[:k])
    return qu @ (a[:, :k] * root), qv @ (bt[:k].T * root)
