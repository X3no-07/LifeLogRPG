"""Generic smooth vector building rendering.

Big buildings are drawn as one shape with roof, eaves and street-facing
walls instead of cell-by-cell tiles, so they stop reading as a
stack of blocks. Small houses keep the tile look - a FireRed small house
is meant to be tiles.

The shape comes from tracing the building blob's own outline in the grid
(trace_blob_outlines), NOT from the OSM polygons: matching grid blobs to
OSM polygons turned out to lose buildings - a blob merged from several
small houses has no single large OSM polygon, and even matched blobs
were only partly covered (palace: 56% of vector-blob cells had no polygon
over them, so whole complexes vanished into grass). The traced outline
covers exactly the blob's cells, so nothing is erased.

In-repo copy of the FireRed vector-building core (was
map-preview-firered/vector_buildings.py). Generic: every large blob is
drawn from its own traced outline, no per-place hand-tuning, no blob is
excluded by name - the generic drawing covers rotated / merged blobs
(including the old Hengfeng special case) the same way.
"""
import json
import math
from collections import deque

# Roof palettes mirror roof_tile() in the renderers:
# 0 red, 1 brown, 2 slate blue, 3 grey, 4 palace gold
PALETTES = [
    ((198, 86, 48), (236, 128, 78), (140, 56, 32)),
    ((150, 100, 60), (190, 140, 95), (104, 66, 38)),
    ((92, 112, 142), (132, 156, 186), (60, 76, 102)),
    ((96, 96, 108), (132, 132, 146), (62, 62, 72)),
    # palace gold, toned down: the old (232,184,48) read as one flat
    # sheet of neon yellow across a whole palace. Deeper and a touch
    # less saturated, so a roof has some body instead of glaring.
    ((214, 166, 58), (238, 198, 100), (160, 116, 30)),
]
WALL = (238, 216, 168)
WALL_DK = (182, 158, 112)
PALACE_WALL = (196, 48, 40)
PALACE_WALL_DK = (140, 30, 26)
WINDOW = (58, 82, 124)
WINDOW_LT = (140, 180, 220)
GROUND_SHADOW = (132, 125, 109)

# "large" threshold, same as export_buildings.py
AREA_MIN = 30.0
SIDE_MIN = 8.0


def is_large(b):
    return b.get("area", 0) >= AREA_MIN or max(b.get("w", 0), b.get("h", 0)) >= SIDE_MIN


def roof_palette(variant, band, palace):
    """Mirror the tile colour logic: palace gold wins over everything;
    tall buildings go slate; mid-height red buildings go brown."""
    if palace:
        return PALETTES[4]
    base, lt, dk = PALETTES[variant % len(PALETTES)]
    if band >= 5:
        return PALETTES[2]
    if band >= 3 and variant == 0:
        return PALETTES[1]
    return (base, lt, dk)


# ---- geometry helpers (all in float grid coords; y grows downward) ----
def _area_centroid(pts):
    a = 0.0
    cx = 0.0
    cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    return (cx / (6.0 * a), cy / (6.0 * a))


def _pca_axis(pts):
    """Longest axis direction (first principal component of the vertices)."""
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts) / n
    syy = sum((p[1] - my) ** 2 for p in pts) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / n
    tr = sxx + syy
    det = sxx * syy - sxy * sxy
    disc = math.sqrt(max(0.0, (tr / 2.0) ** 2 - det))
    lam1 = tr / 2.0 + disc
    if abs(sxy) > 1e-9:
        dx, dy = sxy, lam1 - sxx
    else:
        dx, dy = (1.0, 0.0) if sxx >= syy else (0.0, 1.0)
    L = math.hypot(dx, dy) or 1.0
    return (dx / L, dy / L)


def _chord(pts, c, d):
    """Parameter range [tmin, tmax] of the line c + t*d inside the polygon."""
    cx, cy = c
    dx, dy = d
    ts = []
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        det = -dx * ey + ex * dy
        if abs(det) < 1e-12:
            continue
        rhsx, rhsy = x1 - cx, y1 - cy
        t = (-rhsx * ey + ex * rhsy) / det
        u = (dx * rhsy - rhsx * dy) / det
        if -1e-9 <= u <= 1 + 1e-9:
            ts.append(t)
    if len(ts) < 2:
        return None
    return (min(ts), max(ts))


def _point_in_poly(px, py, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            xin = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < xin:
                inside = not inside
    return inside


# ---- polygon -> blob matching ----
def match_buildings(buildings, blob_id, grid, W, H):
    """Map each large OSM polygon to the grid blob containing most of its
    cells. Returns (vector_blobs, blob_polys) where vector_blobs is the set
    of blob ids to render as vectors and blob_polys maps each such blob to
    a list of (pts, levels) polygons. A blob can collect several polygons
    (merged row houses); a polygon that matches no blob is ignored."""
    vector_blobs = set()
    blob_polys = {}
    for b in buildings:
        if not is_large(b):
            continue
        pts = [tuple(p) for p in b["pts"]]
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0 = max(0, int(min(xs)) - 1)
        x1 = min(W - 1, int(max(xs)) + 1)
        y0 = max(0, int(min(ys)) - 1)
        y1 = min(H - 1, int(max(ys)) + 1)
        counts = {}
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                bid = blob_id[y][x]
                if bid >= 0 and _point_in_poly(x + 0.5, y + 0.5, pts):
                    counts[bid] = counts.get(bid, 0) + 1
        bid = None
        if counts:
            bid = max(counts.items(), key=lambda kv: kv[1])[0]
        else:
            # fallback: centroid neighbourhood, like the Hengfeng code
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            for _dy in range(-3, 4):
                for _dx in range(-3, 4):
                    gx, gy = int(cx) + _dx, int(cy) + _dy
                    if 0 <= gx < W and 0 <= gy < H and blob_id[gy][gx] >= 0:
                        bid = blob_id[gy][gx]
                        break
                if bid is not None:
                    break
        if bid is None:
            continue
        vector_blobs.add(bid)
        blob_polys.setdefault(bid, []).append((pts, b.get("levels", 1)))
    return vector_blobs, blob_polys


# ---- drawing one vector building ----
def _draw_facade(dr, a, b, depth, wall, trim, palace):
    """Extrude one roof edge toward the viewer and shade the ground below it."""
    ax, ay = a
    bx, by = b
    dr.polygon([a, b, (bx, by + depth), (ax, ay + depth)], fill=wall)
    dr.line([(ax, ay + depth + 2), (bx, by + depth + 2)],
            fill=GROUND_SHADOW, width=3)
    dr.line([(ax, ay + depth), (bx, by + depth)], fill=trim, width=2)

    # These are decorative windows, not entrances on the real map.
    if depth < 7:
        return
    bays = int(math.hypot(bx - ax, by - ay) // 18)
    for index in range(bays):
        t = (index + 0.5) / bays
        x = ax + (bx - ax) * t
        y = ay + (by - ay) * t + depth * 0.55
        dr.rectangle((x - 3, y - 2, x + 3, y + 2),
                     fill=trim if palace else WINDOW)
        if not palace:
            dr.line([(x - 2, y - 1), (x + 2, y - 1)], fill=WINDOW_LT)


def draw_building(dr, pts, palette, palace, is_building, T, ridge=True):
    """Draw one building as a single smooth shape on a 1x base image.
    pts: polygon in float grid coords. palette: (base, lt, dk) roof colours.
    is_building: callable(gx, gy) -> True if that grid cell is a building
    cell (used to skip wall segments on edges shared with a neighbouring
    polygon of the same blob). T: pixels per cell (16). ridge: False
    skips the ridge line - used when the blob's own halls are drawn as
    separate roof pieces below (one long ridge across the whole blob
    would cut straight through them)."""
    base, lt, dk = palette
    wall = PALACE_WALL if palace else WALL
    trim = PALACE_WALL_DK if palace else WALL_DK
    px = [(x * T, y * T) for x, y in pts]
    centre = _area_centroid(pts)
    edges = list(zip(pts, pts[1:] + pts[:1]))
    signed_area = sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)
    winding = 1 if signed_area >= 0 else -1
    # Project only exposed edges facing the viewer, including concave façades.
    for a, b in edges:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 0.2:
            continue
        nx, ny = winding * dy / length, -winding * dx / length
        if ny <= 0.2:
            continue
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        ox, oy = math.floor(mx + nx * 0.7), math.floor(my + ny * 0.7)
        if is_building(ox, oy):
            continue
        pa = (a[0] * T, a[1] * T)
        pb = (b[0] * T, b[1] * T)
        depth = max(3, round(T * 0.7 * ny))
        _draw_facade(dr, pa, pb, depth, wall, trim, palace)
    # roof: one flat polygon, no shingle grid, no seams
    dr.polygon(px, fill=base)
    # ridge: longest axis through the centroid, endpoints inside the roof.
    # Skipped when the caller draws the blob's halls as separate roof
    # pieces (see roof_pieces): one ridge across a whole palace would
    # run straight through the halls the pieces are meant to separate.
    if ridge:
        d = _pca_axis(pts)
        chord = _chord(pts, centre, d)
        if chord is not None:
            t0, t1 = chord
            span = t1 - t0
            if span > 2.0:
                m = max(0.4, 0.04 * span)
                r0 = (centre[0] + d[0] * (t0 + m), centre[1] + d[1] * (t0 + m))
                r1 = (centre[0] + d[0] * (t1 - m), centre[1] + d[1] * (t1 - m))
                dr.line([(r0[0] * T, r0[1] * T), (r1[0] * T, r1[1] * T)],
                        fill=lt, width=5)
    # outline
    dr.line(px + [px[0]], fill=dk, width=3, joint="curve")


# ---- one roof piece per building (the blob fix) ----
# A blob is a connected clump of building cells, so a palace reads as
# one outline filled with one flat colour - the three great halls
# (太和殿/中和殿/保和殿） melt into a single yellow sheet. The fix is
# to draw each hall's own OSM polygon as a separate roof on top of
# the blob fill: its own shade, its own outline, its own ridge. The
# blob outline stays underneath so nothing is lost where no polygon
# covers the blob; the pieces only add the seams between halls.
PIECE_SHADES = [-15, -10, -5, 0, 5, 10, 15]


def draw_roof_piece(dr, pts, base, lt, dk, T):
    """Draw one roof piece (one OSM polygon) inside a larger blob:
    flat fill in the piece's own shade, outline, and a ridge line if
    the piece is big enough. No walls, doors or windows - the piece
    is part of a larger roof, not a freestanding house."""
    px = [(x * T, y * T) for x, y in pts]
    centre = _area_centroid(pts)
    dr.polygon(px, fill=base)
    d = _pca_axis(pts)
    chord = _chord(pts, centre, d)
    if chord is not None:
        t0, t1 = chord
        span = t1 - t0
        if span > 2.0:
            m = max(0.4, 0.04 * span)
            r0 = (centre[0] + d[0] * (t0 + m), centre[1] + d[1] * (t0 + m))
            r1 = (centre[0] + d[0] * (t1 - m), centre[1] + d[1] * (t1 - m))
            dr.line([(r0[0] * T, r0[1] * T), (r1[0] * T, r1[1] * T)],
                    fill=lt, width=5)
    dr.line(px + [px[0]], fill=dk, width=3, joint="curve")


def _is_hall_like(b):
    """An OSM polygon that reads as its own roofed building (a hall,
    not a wall or a fragment): big enough to see, and not a long thin
    strip. Uses the exported area/w/h fields. This is why 保和殿
    (area 29.6, just under the old 'large' line of 30) and 中和殿
    (area 10.2) were invisible to the old blob-only drawing - they
    are halls, just small ones."""
    a = b.get("area", 0)
    w = b.get("w", 0)
    h = b.get("h", 0)
    if a < 8:
        return False
    mn = min(w, h)
    mx = max(w, h)
    return mn >= 2 and (mx / mn if mn > 0 else 99) <= 4


def _is_piece_like(b):
    """An OSM polygon worth drawing as its own roof piece: a compact
    building, not a wall or a sliver. Looser than _is_hall_like so
    dense rows of small houses get seams too - the palace east wing
    is hundreds of 1-8 cell red roofs touching each other, and the
    hall-only line left them as one flat red sheet (a blob of 3187
    cells with only 16% covered by hall-like pieces). Long thin
    strips (aspect > 4, e.g. wall fragments) and sub-cell slivers
    (area < 1.5) stay out. A piece too small for a ridge just gets
    fill + outline (draw_roof_piece already skips the ridge when
    the span is under 2 cells)."""
    a = b.get("area", 0)
    w = b.get("w", 0)
    h = b.get("h", 0)
    if a < 1.5:
        return False
    mn = min(w, h)
    mx = max(w, h)
    return mn >= 1.0 and (mx / mn if mn > 0 else 99) <= 4


def roof_pieces(buildings, blob_id, grid, W, H, traced_blobs):
    """OSM polygons to draw as separate roof pieces, grouped by blob.
    A polygon becomes a piece when it is piece-like (see
    _is_piece_like) and either (a) its blob is a traced blob holding
    more than one piece (the blob is a merged row of buildings, e.g.
    the central palace or the east wing's dense red roofs), or (b)
    its blob is not traced at all (a small standalone hall like
    中和殿， which would otherwise stay a tiled roof and blend into
    the big blob next to it). A traced blob holding a single piece
    needs no piece: its outline already draws that one building.
    The pieces are what keep a merged blob from reading as one flat
    sheet: each gets its own shade, outline and ridge, so the seam
    between neighbours is visible. The hall-only line used to leave
    dense small-roof areas solid - the east wing's red blob had 500
    polygons but only 33 hall-like ones, so 84% of it stayed flat.
    Returns {bid: [(pts, levels, shade), ...]} with the pieces of
    each blob sorted top-to-bottom, left-to-right, shades cycling
    so neighbours in that order - usually neighbours on the map -
    get different shades. A hash of the centroid cannot do this: the
    three great halls sit at almost the same x, so every hash tried
    gave two of them the same shade."""
    by_blob = {}
    for b in buildings:
        if not _is_piece_like(b):
            continue
        pts = [tuple(p) for p in b.get("pts", [])]
        if len(pts) < 3:
            continue
        # terrace / platform outlines are NOT roofs: OSM maps the
        # palace's marble terraces as unnamed building=yes outlines
        # with dozens of nodes tracing the balustrade (area >= 25,
        # >= 30 points). Drawing one gold would paint a giant slab
        # over the plaza between the halls. Same guard as
        # recovered_buildings / completion_buildings (which use 35
        # points); pieces are more sensitive, so 30 here. A real hall
        # is either named or a simple outline, so it is kept.
        if (not b.get("name") and b.get("area", 0) >= 25
                and len(pts) >= 30):
            continue
        from collections import Counter
        cnt = Counter()
        _cells = polygon_grid_cells(pts, W, H)
        for (cx, cy) in _cells:
            if grid[cy][cx] == 2 and blob_id[cy][cx] >= 0:
                cnt[blob_id[cy][cx]] += 1
        bid = None
        if cnt:
            bid = cnt.most_common(1)[0][0]
        else:
            ccx, ccy = _area_centroid(pts)
            for _dy in range(-3, 4):
                for _dx in range(-3, 4):
                    gx, gy = int(ccx) + _dx, int(ccy) + _dy
                    if 0 <= gx < W and 0 <= gy < H and blob_id[gy][gx] >= 0:
                        bid = blob_id[gy][gx]
                        break
                if bid is not None:
                    break
        if bid is None:
            continue
        by_blob.setdefault(bid, []).append(
            (pts, b.get("levels", 1), set(_cells)))
    out = {}
    for bid, polys in by_blob.items():
        # dedup: the export now carries building:part fragments next
        # to their building=yes outline, so one hall can arrive as
        # several overlapping polygons (e.g. 保和殿 as five). A piece
        # more than 70% inside a larger kept piece is a duplicate
        # fragment, not a separate roof - drop it, or the hall gets
        # concentric outlines. Adjacent pieces (a wing sticking out)
        # survive: they overlap little.
        _kept = []
        for _pts, _levels, _cells in sorted(
                polys, key=lambda t: -len(t[2])):
            _dup = False
            for _kpts, _klevels, _kcells in _kept:
                if _cells and len(_cells & _kcells) / len(_cells) > 0.7:
                    _dup = True
                    break
            if not _dup:
                _kept.append((_pts, _levels, _cells))
        if bid in traced_blobs and len(_kept) <= 1:
            continue
        keyed = sorted(_kept, key=lambda t: (_area_centroid(t[0])[1],
                                             _area_centroid(t[0])[0]))
        out[bid] = [(pts, levels, PIECE_SHADES[i % len(PIECE_SHADES)])
                    for i, (pts, levels, _cells) in enumerate(keyed)]
    return out


# ---- recovered buildings (problem 3) ----
# OSM polygons the grid bake lost: the baker draws roads AFTER buildings,
# so a gatehouse threaded with footways (tunnel=building_passage),
# steps and pedestrian-area rings comes out of the bake as road cells,
# and its grid blob is only fragments (palace: 太和门 9/38 cells,
# 熙和门 7/33, 左翼门 2/18, 坤宁宫 6/21, ...). The renderer can put
# them back from the exported OSM polygons, which the bake never had
# a chance to shred - but only the badly shredded ones (frac < 0.6):
# a mostly-intact building is already drawn from its blob, and
# redrawing its OSM outline on top would double its outline.
# Terrace/platform outlines are NOT halls and are skipped: OSM maps
# the palace's marble terraces as unnamed building=yes outlines with
# dozens of nodes tracing the balustrade (area >= 25, >= 35 points).
# Drawing one gold would paint a giant slab over the plaza between
# the halls (e.g. the 134-153, 67-78 apron south of 太和殿, or the
# 135-148, 11-21 platform under 坤宁宫/交泰殿/乾清宫). A real hall
# either has a name or a simple outline, so the rule keeps it out.
# 中和殿 cannot be recovered this way at all: it has no building=yes
# way in OSM (only building:part fragments), so it is in neither the
# grid nor the exported polygons - that needs a re-export, not a
# renderer change.

def _poly_cells(pts, grid, W, H):
    """(total, building) cell-centre counts inside a polygon."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    tot = 0
    bld = 0
    for y in range(max(0, int(min(ys))), min(H, int(max(ys)) + 1)):
        for x in range(max(0, int(min(xs))), min(W, int(max(xs)) + 1)):
            if _point_in_poly(x + 0.5, y + 0.5, pts):
                tot += 1
                if grid[y][x] == 2:
                    bld += 1
    return tot, bld


def recovered_buildings(buildings, grid, W, H, min_cells=8, max_frac=0.60):
    """OSM polygons to draw back over the map because the bake lost
    them to roads. Returns a list of (pts, levels, name), smallest
    first so small gates draw on top of the big halls next to them."""
    out = []
    for b in buildings:
        pts = [tuple(p) for p in b.get("pts", [])]
        if len(pts) < 3:
            continue
        name = b.get("name", "")
        area = abs(_signed_area(pts))
        if not name and area >= 25 and len(pts) >= 35:
            continue  # terrace / platform outline, not a hall
        tot, bld = _poly_cells(pts, grid, W, H)
        if tot >= min_cells and bld / tot < max_frac:
            out.append((pts, b.get("levels", 1), name))
    out.sort(key=lambda t: abs(_signed_area(t[0])))
    return out


def completion_buildings(buildings, grid, W, H, min_cells=8,
                         min_frac=0.60, max_frac=0.90):
    """The middle band: buildings the bake only partly lost (a road
    stripe through one face - 午门 0.78, 乾清宫 0.64, 保和殿 0.89,
    第三/第五教学区 0.80). Their grid blob already draws most of the
    hall, so they are NOT redrawn as vector shapes (a second outline
    a fraction of a cell off the first would double the edge) - they
    only get their missing cells flat-filled (see fill_missing_cells).
    Same terrace skip as recovered_buildings."""
    out = []
    for b in buildings:
        pts = [tuple(p) for p in b.get("pts", [])]
        if len(pts) < 3:
            continue
        name = b.get("name", "")
        area = abs(_signed_area(pts))
        if not name and area >= 25 and len(pts) >= 35:
            continue  # terrace / platform outline, not a hall
        tot, bld = _poly_cells(pts, grid, W, H)
        if tot >= min_cells and min_frac <= bld / tot < max_frac:
            out.append((pts, b.get("levels", 1), name))
    out.sort(key=lambda t: abs(_signed_area(t[0])))
    return out


def polygon_grid_cells(pts, W, H):
    """Grid cells whose centre falls inside a polygon."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [(x, y)
            for y in range(max(0, int(min(ys))), min(H, int(max(ys)) + 1))
            for x in range(max(0, int(min(xs))), min(W, int(max(xs)) + 1))
            if _point_in_poly(x + 0.5, y + 0.5, pts)]


def fill_missing_cells(dr, pts, grid, W, H, base, T):
    """Flat-fill the polygon cells the grid does NOT have as building
    with the roof colour. Two uses: (1) before draw_building for a
    recovered polygon - PIL's fill can miss the tip cells of a narrow
    or self-touching outline (东华门's north tip stayed plaza), and
    the ray-cast cell list does not; (2) on its own for a completion
    polygon, where it extends the already-drawn roof over the road
    cells that bit into it. Only non-building cells are touched, so
    no ridge, wall, door or outline drawn for the blob is painted
    over - the fill just completes the roof to its true edge."""
    for (x, y) in polygon_grid_cells(pts, W, H):
        if grid[y][x] != 2:
            dr.rectangle([x * T, y * T, (x + 1) * T - 1, (y + 1) * T - 1],
                         fill=base)


def draw_under_patches(dr, cells, blob_cells, base, wall, dk, T):
    """Fill the blob cells the simplified outline cut off (the tip
    cell of each step on a diagonal edge: DP tolerance 0.8 drops a
    protruding corner whose centre is ~0.7 cells off the chord, so
    the roof gets a 1-cell paved notch at every step). A patch is one
    flat roof-coloured cell with a dark edge only where it borders
    open ground - the stepped edge this leaves is exactly how a
    FireRed diagonal roof reads. South-edge patches get the wall
    colour on their lower half, matching the wall band's inner half."""
    for (x, y) in cells:
        x0, y0 = x * T, y * T
        dr.rectangle([x0, y0, x0 + T - 1, y0 + T - 1], fill=base)
        if (x, y + 1) not in blob_cells:
            # wall band's inner half is 0.75 cell deep (see draw_building)
            dr.rectangle([x0, y0 + T // 4, x0 + T - 1, y0 + T - 1], fill=wall)
        if (x, y - 1) not in blob_cells:
            dr.line([(x0, y0), (x0 + T - 1, y0)], fill=dk, width=3)
        if (x, y + 1) not in blob_cells:
            dr.line([(x0, y0 + T - 1), (x0 + T - 1, y0 + T - 1)], fill=dk, width=3)
        if (x - 1, y) not in blob_cells:
            dr.line([(x0, y0), (x0, y0 + T - 1)], fill=dk, width=3)
        if (x + 1, y) not in blob_cells:
            dr.line([(x0 + T - 1, y0), (x0 + T - 1, y0 + T - 1)], fill=dk, width=3)


# ---- blob outline tracing (problem 2) ----
# A large blob's own outline, traced from its grid cells and simplified
# into a smooth polygon. Used for every large blob, matched or not:
# it covers exactly the blob's cells, so no building is lost to a
# missing or partial OSM polygon.

def _dp_simplify_open(pts, tol):
    """Ramer-Douglas-Peucker on an open polyline (endpoints kept)."""
    if len(pts) <= 2:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        x1, y1 = pts[a]
        x2, y2 = pts[b]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        far = -1.0
        far_i = -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if L < 1e-9:
                dist = math.hypot(px - x1, py - y1)
            else:
                dist = abs((px - x1) * dy - (py - y1) * dx) / L
            if dist > far:
                far = dist
                far_i = i
        if far > tol:
            keep[far_i] = True
            stack.append((a, far_i))
            stack.append((far_i, b))
    return [p for p, k in zip(pts, keep) if k]


def _simplify_closed(loop, tol):
    """Simplify a closed loop (list of vertices, no duplicate end).
    Splits at the vertex farthest from vertex 0 so the ends are fixed."""
    n = len(loop)
    if n <= 4:
        return list(loop)
    x0, y0 = loop[0]
    k = max(range(n), key=lambda i: (loop[i][0] - x0) ** 2 + (loop[i][1] - y0) ** 2)
    if k == 0:
        return list(loop)
    half1 = _dp_simplify_open(loop[:k + 1], tol)
    half2 = _dp_simplify_open(loop[k:] + [loop[0]], tol)
    # half1 ends at loop[k], half2 starts at loop[k] and ends at loop[0];
    # join without duplicating either endpoint (the loop closes implicitly)
    return half1 + half2[1:-1]


def _signed_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a * 0.5


def trace_blob_outline(cells):
    """Trace the outer boundary of one blob (set of (x, y) cells).
    Returns a list of outer loops, each a list of (x, y) float grid
    coords (cell corners). Holes are NOT returned as loops - they are
    handled separately by trace_blob_holes (cell lists).
    Boundary edges are walked with the building on the left (left-hand
    wall follower), so pinch points split into separate loops instead
    of one figure-eight. In y-down grid coords outer loops have
    negative signed area; hole loops (positive) are dropped here."""
    cellset = set(cells)
    # directed boundary edges: (start -> end), building on the left
    outgoing = {}
    for (x, y) in cellset:
        if (x, y - 1) not in cellset:  # north edge, walk west
            outgoing.setdefault((x + 1, y), []).append((x, y))
        if (x, y + 1) not in cellset:  # south edge, walk east
            outgoing.setdefault((x, y + 1), []).append((x + 1, y + 1))
        if (x - 1, y) not in cellset:  # west edge, walk south
            outgoing.setdefault((x, y), []).append((x, y + 1))
        if (x + 1, y) not in cellset:  # east edge, walk north
            outgoing.setdefault((x + 1, y + 1), []).append((x + 1, y))
    # left-hand rule: at each vertex prefer the sharpest left turn
    # (left, straight, right, back) relative to the heading
    def _turns(dx, dy):
        return [(dy, -dx), (dx, dy), (-dy, dx), (-dx, -dy)]
    visited = set()
    loops = []
    total_edges = sum(len(v) for v in outgoing.values())
    for start in list(outgoing):
        for first in outgoing[start]:
            if (start, first) in visited:
                continue
            loop = [start]
            visited.add((start, first))
            prev, cur = start, first
            guard = 0
            while cur != start and guard <= total_edges + 2:
                guard += 1
                loop.append(cur)
                dx, dy = cur[0] - prev[0], cur[1] - prev[1]
                nxt = None
                for tdx, tdy in _turns(dx, dy):
                    cand = (cur[0] + tdx, cur[1] + tdy)
                    if cand in outgoing.get(cur, []) and (cur, cand) not in visited:
                        nxt = cand
                        break
                if nxt is None:
                    break
                visited.add((cur, nxt))
                prev, cur = cur, nxt
            if cur == start and len(loop) >= 4:
                loops.append(loop)
    outer = []
    for loop in loops:
        if _signed_area(loop) < 0:  # outer boundary (y-down coords)
            outer.append([(float(x), float(y)) for x, y in loop])
    return outer


def trace_blob_holes(blobs, blob_id, grid, W, H):
    """Enclosed non-building cells (courtyards) per blob id, found by
    flood-filling the non-building cells from the map border. Returns
    {bid: [(x, y), ...]}. Enclosed cells form connected regions; a
    region is attributed to the blob with the most building cells
    adjacent to it (per-cell attribution would drop the interior
    cells of a wide courtyard, which touch no building cell)."""
    reach = [[False] * W for _ in range(H)]
    q = deque()
    for x in range(W):
        for y in (0, H - 1):
            if grid[y][x] != 2 and not reach[y][x]:
                reach[y][x] = True
                q.append((x, y))
    for y in range(H):
        for x in (0, W - 1):
            if grid[y][x] != 2 and not reach[y][x]:
                reach[y][x] = True
                q.append((x, y))
    while q:
        cx, cy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < W and 0 <= ny < H and grid[ny][nx] != 2 and not reach[ny][nx]:
                reach[ny][nx] = True
                q.append((nx, ny))
    from collections import Counter
    seen = [[False] * W for _ in range(H)]
    holes = {}
    for y in range(H):
        for x in range(W):
            if grid[y][x] != 2 and not reach[y][x] and not seen[y][x]:
                comp = []
                q = deque([(x, y)])
                seen[y][x] = True
                while q:
                    cx, cy = q.popleft()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < W and 0 <= ny < H and grid[ny][nx] != 2
                                and not reach[ny][nx] and not seen[ny][nx]):
                            seen[ny][nx] = True
                            q.append((nx, ny))
                cnt = Counter()
                for (cx, cy) in comp:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < W and 0 <= ny < H and grid[ny][nx] == 2:
                            cnt[blob_id[ny][nx]] += 1
                if cnt:
                    holes.setdefault(cnt.most_common(1)[0][0], []).extend(comp)
    return holes


def trace_large_blobs(blobs, blob_id, grid, W, H, exclude=()):
    """Trace every large blob (area >= 30 cells or side >= 8 cells)
    except the excluded ones (e.g. Hengfeng, which keeps its own block).
    Returns (traced, holes, under) where traced maps bid -> list of simplified
    outer polygons (float grid coords), holes maps bid -> hole cells, and
    under maps bid -> blob cells the simplification cut off (the tip cell
    of each step on a diagonal edge - see draw_under_patches).
    Blobs whose outline simplifies to nothing usable are skipped.
    Staircase diagonals collapse into straight lines (tolerance 0.8
    cells > the 0.71-cell zigzag of a unit staircase)."""
    traced = {}
    for bid, cells in enumerate(blobs):
        if bid in exclude:
            continue
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        w = max(xs) - min(xs) + 1
        h = max(ys) - min(ys) + 1
        if len(cells) < AREA_MIN and max(w, h) < SIDE_MIN:
            continue
        loops = trace_blob_outline(cells)
        polys = []
        for loop in loops:
            simp = _simplify_closed(loop, 0.8)
            if len(simp) >= 4 and abs(_signed_area(simp)) >= 2.0:
                polys.append(simp)
        if polys:
            traced[bid] = polys
    under = {}
    for bid, polys in traced.items():
        cut = [(x, y) for (x, y) in blobs[bid]
               if not any(_point_in_poly(x + 0.5, y + 0.5, p) for p in polys)]
        if cut:
            under[bid] = cut
    holes = trace_blob_holes(blobs, blob_id, grid, W, H)
    holes = {b: cells for b, cells in holes.items() if b in traced}
    # only re-expose hole regions of >= 6 cells (real courtyards). A 1-5
    # cell gap is a light well or alley too small to read as a courtyard -
    # re-exposing it speckles the roof like damage, so it stays roofed.
    _all = set()
    for _cells in holes.values():
        _all.update(_cells)
    _seen = set()
    _keep = set()
    for (_x, _y) in _all:
        if (_x, _y) in _seen:
            continue
        _comp = []
        _q = deque([(_x, _y)])
        _seen.add((_x, _y))
        while _q:
            _cx, _cy = _q.popleft()
            _comp.append((_cx, _cy))
            for _dx, _dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                _nb = (_cx + _dx, _cy + _dy)
                if _nb in _all and _nb not in _seen:
                    _seen.add(_nb)
                    _q.append(_nb)
        if len(_comp) >= 6:
            _keep.update(_comp)
    holes = {b: [c for c in cells if c in _keep] for b, cells in holes.items()}
    holes = {b: cells for b, cells in holes.items() if cells}
    return traced, holes, under
