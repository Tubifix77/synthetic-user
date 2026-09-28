"""Draw the Synthetic User app icon (the single source for icon.png and icon.ico).

    python -m synthetic_user.ui.make_icon      (needs Pillow: pip install pillow)

A network-brain head in profile with an "S", talking to a speech bubble with
sparkles — the operator stand-in talking to Claude — on a cyan→indigo
rounded-square ("squircle") tile. Drawn with Pillow at 4× and downsampled, so
there is no SVG toolchain to install.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
SS = 4                      # supersampling factor
N = 1024 * SS               # working canvas size
LINE = (232, 253, 255)      # near-white cyan for strokes
GLOW = (120, 235, 255)


def P(x: float, y: float) -> tuple[float, float]:
    """Design coordinates are on a 1024 grid."""
    return x * SS, y * SS


def squircle_mask(size: int, n: float = 5.0) -> Image.Image:
    """Superellipse |x|^n + |y|^n = 1 — the soft rounded square of current app icons."""
    import math
    pts = []
    for i in range(720):
        t = 2 * math.pi * i / 720
        c, s = math.cos(t), math.sin(t)
        x = abs(c) ** (2 / n) * (1 if c >= 0 else -1)
        y = abs(s) ** (2 / n) * (1 if s >= 0 else -1)
        pts.append(((x * 0.5 + 0.5) * (size - 1), (y * 0.5 + 0.5) * (size - 1)))
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def gradient(size: int) -> Image.Image:
    """Diagonal cyan → blue → indigo."""
    stops = [(0.0, (22, 206, 232)), (0.5, (47, 118, 236)), (1.0, (84, 60, 214))]
    small = Image.new("RGB", (256, 256))
    px = small.load()
    for yy in range(256):
        for xx in range(256):
            t = (xx * 0.55 + yy * 0.45) / 255
            for (a, ca), (b, cb) in zip(stops, stops[1:]):
                if a <= t <= b:
                    f = (t - a) / (b - a)
                    px[xx, yy] = tuple(round(ca[k] + (cb[k] - ca[k]) * f) for k in range(3))
                    break
    return small.resize((size, size), Image.BICUBIC)


def catmull_rom(points, steps: int = 24):
    """Smooth curve through the given points."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)
                for k in range(2)))
    out.append(points[-1])
    return out


# Head in profile, facing right: back of neck → crown → brow → nose → lips → chin → neck.
HEAD = [(238, 905), (206, 760), (186, 600), (196, 440), (250, 310), (350, 222), (470, 186),
        (580, 200), (660, 250), (704, 330), (716, 410), (708, 452), (742, 520), (772, 572),
        (768, 590), (730, 602), (740, 628), (720, 648), (734, 672), (712, 700), (718, 738),
        (690, 770), (620, 792), (598, 905)]
NODES = [(290, 330), (410, 250), (540, 238), (640, 318), (250, 470), (420, 360), (650, 470),
         (262, 640), (400, 720), (560, 690), (660, 560), (330, 830), (500, 840)]
EDGES = [(0, 1), (1, 2), (2, 3), (0, 4), (0, 5), (1, 5), (2, 5), (3, 6), (3, 5), (4, 7), (6, 10),
         (7, 8), (8, 9), (9, 10), (7, 11), (8, 11), (8, 12), (9, 12), (4, 5), (6, 9), (5, 6)]
S_CENTER, S_RADIUS = (455, 510), 138
BUBBLE = (738, 188, 984, 472)           # ellipse bbox of the speech bubble


def stroke(draw: ImageDraw.ImageDraw, pts, width: float, fill: int = 255) -> None:
    """Thick polyline with round joins and caps (Pillow's own joins spike on tight curves)."""
    r = width / 2
    draw.line(pts, fill=fill, width=int(width))
    for x, y in pts:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def star4(cx: float, cy: float, r: float, waist: float = 0.28):
    """Four-pointed sparkle."""
    import math
    pts = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * waist
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def _crosses_s(a, b) -> bool:
    """Does segment a-b pass through the disc reserved for the "S"?"""
    (ax, ay), (bx, by), (cx, cy) = a, b, S_CENTER
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / (dx * dx + dy * dy)))
    px, py = ax + t * dx - cx, ay + t * dy - cy
    return (px * px + py * py) ** 0.5 < S_RADIUS


def draw_art(small: bool = False) -> Image.Image:
    """small=True is the 16–32 px version: thicker outline, bigger S, no mesh or
    sparkles — detail that turns to noise at that size."""
    lines = Image.new("L", (N, N), 0)       # everything drawn in LINE colour
    d = ImageDraw.Draw(lines)
    w = (54 if small else 26) * SS

    # Network inside the head (drawn first; the "S" disc covers what's behind it).
    for a, b in ([] if small else EDGES):
        if _crosses_s(NODES[a], NODES[b]):
            continue  # a clipped line would leave a stub beside the letter
        d.line([P(*NODES[a]), P(*NODES[b])], fill=255, width=11 * SS)
    for x, y in ([] if small else NODES):
        r = 22 * SS
        d.ellipse([x * SS - r, y * SS - r, x * SS + r, y * SS + r], fill=255)

    # Clear a disc for the "S", then the letter itself.
    cx, cy = P(*S_CENTER)
    r = S_RADIUS * SS
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    font = None
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, (400 if small else 290) * SS)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    d.text((cx, cy + 6 * SS), "S", font=font, fill=255, anchor="mm")

    # Head outline.
    stroke(d, [P(*p) for p in catmull_rom(HEAD)], w)

    # Speech bubble (filled, with a tail toward the mouth) — its own layer so it
    # can be separated from the face by a gap.
    bubble = Image.new("L", (N, N), 0)
    b = ImageDraw.Draw(bubble)
    x0, y0, x1, y1 = BUBBLE
    b.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=255)
    b.polygon([P(770, 400), P(850, 455), P(752, 540)], fill=255)   # tail toward the mouth
    # Gap between face and bubble: erase a fat copy of the head stroke.
    gap = Image.new("L", (N, N), 0)
    stroke(ImageDraw.Draw(gap), [P(*p) for p in catmull_rom(HEAD)], w + 44 * SS)
    bubble = ImageChops.subtract(bubble, gap)

    # Sparkles + dot inside the bubble are cut out of it (they show the blue below).
    cut = Image.new("L", (N, N), 0)
    c = ImageDraw.Draw(cut)
    bx, by = (x0 + x1) / 2, (y0 + y1) / 2
    if small:
        c.ellipse([P(bx - 34, by - 34), P(bx + 34, by + 34)], fill=255)
    else:
        for dx, dy, rr in ((-58, 0, 32), (58, 0, 32), (0, -62, 30), (0, 62, 30)):
            c.polygon([P(*q) for q in star4(bx + dx, by + dy, rr)], fill=255)
        c.ellipse([P(bx - 15, by - 15), P(bx + 15, by + 15)], fill=255)
    bubble = ImageChops.subtract(bubble, cut)

    # Glint in the top-right corner.
    glint = Image.new("L", (N, N), 0)
    if not small:
        ImageDraw.Draw(glint).polygon([P(*q) for q in star4(930, 150, 40, 0.18)], fill=255)

    # Compose: gradient tile, soft glow, then crisp shapes.
    tile = gradient(N).convert("RGBA")
    shapes = ImageChops.lighter(ImageChops.lighter(lines, glint), bubble)
    glow = shapes.filter(ImageFilter.GaussianBlur(28 * SS))
    tile.paste(Image.new("RGBA", (N, N), GLOW + (255,)), (0, 0), glow.point(lambda v: v * 0.75))
    tile.paste(Image.new("RGBA", (N, N), (214, 247, 255, 255)), (0, 0), bubble)
    tile.paste(Image.new("RGBA", (N, N), LINE + (255,)), (0, 0), ImageChops.lighter(lines, glint))

    # Soft top highlight for depth.
    hl = Image.new("L", (N, N), 0)
    ImageDraw.Draw(hl).ellipse([-N * 0.2, -N * 0.9, N * 1.2, N * 0.42], fill=40)
    tile.paste(Image.new("RGBA", (N, N), (255, 255, 255, 255)), (0, 0), hl.filter(ImageFilter.GaussianBlur(60 * SS)))

    mask = squircle_mask(N)
    tile.putalpha(mask)
    return tile.resize((1024, 1024), Image.LANCZOS)


def main() -> None:
    art, simple = draw_art(), draw_art(small=True)
    art.resize((512, 512), Image.LANCZOS).save(HERE / "icon.png")
    frames = [(simple if size <= 32 else art).resize((size, size), Image.LANCZOS)
              for size in (16, 24, 32, 48, 64, 128, 256)]
    frames[-1].save(HERE / "icon.ico", sizes=[f.size for f in frames], append_images=frames[:-1])
    print(f"wrote {HERE / 'icon.png'} and {HERE / 'icon.ico'}")


if __name__ == "__main__":
    main()
