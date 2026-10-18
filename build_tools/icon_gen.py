# -*- coding: utf-8 -*-
"""Wallpaper Peel 图标 v9（定稿）：三叶结实心笔画 + 末端翘起的蓝色剥口"""
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFilter

SS = 4
S = 256 * SS
INK_TOP = (13, 16, 23)
INK_BOT = (35, 42, 60)
WHITE = (242, 246, 252)
ACCENT = (99, 141, 255)


def trefoil(t):
    return math.sin(t) + 2 * math.sin(2 * t), math.cos(t) - 2 * math.cos(2 * t)


def bg(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    g = Image.new('RGB', (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x / size) * 0.22 + (y / size) * 0.78
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(INK_TOP, INK_BOT))
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(size * 0.235), fill=255)
    img.paste(g, (0, 0), mask)
    return img


def stroke(dr, pts, color, w, cap=True):
    w = max(1, int(round(w)))
    dr.line(pts, fill=color, width=w, joint='curve')
    if cap:
        r = w / 2.0
        for p in (pts[0], pts[-1]):
            dr.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def build(scale, w_ratio, tip_ratio, lift_ratio, twist, size=S, accent=True):
    cx = cy = size / 2.0
    N = 200
    raw = [trefoil(2 * math.pi * i / N) for i in range(N)]
    xs = [x for x, y in raw]
    ys = [y for x, y in raw]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    k = size * scale / span
    ox = (max(xs) + min(xs)) / 2
    oy = (max(ys) + min(ys)) / 2
    pts = [(cx + (x - ox) * k, cy + (y - oy) * k) for x, y in raw]
    w = size * w_ratio

    # 结画在独立图层上，方便"挖掉"一小段
    knot = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    stroke(ImageDraw.Draw(knot), pts, WHITE + (255,), w)

    if not accent:
        img = bg(size)
        img.alpha_composite(knot)
        return img

    m = max(5, int(N * tip_ratio))
    tail = pts[N - m:]
    ex, ey = pts[-1]
    bx, by = pts[-2]
    tx, ty = ex - bx, ey - by
    L = math.hypot(tx, ty) or 1
    tx, ty = tx / L, ty / L
    lift = size * lift_ratio
    ang = math.radians(twist)

    # 逐点渐增的"翘起"位移：越靠末端翘得越高
    moved = []
    for i, (x, y) in enumerate(tail):
        s = ((i + 1) / len(tail)) ** 1.35
        dx, dy = x + tx * lift * s, y + ty * lift * s - lift * 0.85 * s
        moved.append((cx + (dx - cx) * math.cos(ang) - (dy - cy) * math.sin(ang),
                      cy + (dx - cx) * math.sin(ang) + (dy - cy) * math.cos(ang)))

    # 在结上挖掉这一段
    hole = Image.new('L', (size, size), 0)
    hd = ImageDraw.Draw(hole)
    hd.line(tail, fill=255, width=int(w * 1.12), joint='curve')
    for p in tail:
        r = w * 0.56
        hd.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=255)
    knot.paste((0, 0, 0, 0), (0, 0), hole)

    img = bg(size)
    img.alpha_composite(knot)

    sh = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    stroke(ImageDraw.Draw(sh), [(x + w * 0.16, y + w * 0.30) for x, y in moved],
           (0, 0, 0, 165), w)
    sh = sh.filter(ImageFilter.GaussianBlur(w * 0.55))
    img.alpha_composite(sh)

    dr = ImageDraw.Draw(img)
    stroke(dr, moved, ACCENT + (255,), w)
    return img


VARIANTS = [
    ('A 素结', (0.76, 0.062, 0, 0, 0)),
    ('B 剥口·短', (0.76, 0.062, 0.05, 0.085, 12)),
    ('C 剥口·中', (0.76, 0.062, 0.085, 0.095, 16)),
    ('D 剥口·长', (0.74, 0.064, 0.12, 0.10, 18)),
]


def sheet():
    imgs = []
    for name, p in VARIANTS:
        im = build(*p, accent=(name != 'A 素结'))
        imgs.append(im.resize((256, 256), Image.LANCZOS))
    pad = 16
    W = 256 * 2 + pad * 3
    H = 256 * 2 + pad * 3 + 28
    out = Image.new('RGB', (W, H), (30, 32, 38))
    d = ImageDraw.Draw(out)
    for i, (im, (name, _)) in enumerate(zip(imgs, VARIANTS)):
        x = pad + (i % 2) * (256 + pad)
        y = pad + (i // 2) * (256 + pad + 14)
        out.paste(im, (x, y), im)
        d.text((x + 2, y + 258), name, fill=(220, 224, 232))
    out.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'variants.png'))
    print('variants ok')


def export(idx):
    name, p = VARIANTS[idx]
    im = build(*p, accent=(name != 'A 素结'))
    big = im.resize((256, 256), Image.LANCZOS)
    here = os.path.dirname(os.path.abspath(__file__))
    big.save(os.path.abspath(os.path.join(here, '..', 'app_preview.png')))
    big.save(os.path.abspath(os.path.join(here, '..', 'app.ico')), format='ICO',
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    print('exported', name)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        export(int(sys.argv[1]))
    else:
        sheet()
