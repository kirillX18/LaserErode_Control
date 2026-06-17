"""
toolpath.py — загрузка плоской программы обработки (контура) из векторных
форматов и приведение её к рабочему полю станка.

Для лазерно-эрозионной обработки управляющая программа — это не 3D-меш, а
набор плоских контуров (траектории реза/гравировки). Поддерживаются основные
векторные форматы без внешних зависимостей (чистый Python):

    DXF        — LINE, LWPOLYLINE, POLYLINE/VERTEX, CIRCLE, ARC;
    SVG        — line, polyline, polygon, rect, circle, ellipse, path
                 (M/L/H/V/Z, кривые C/Q флэтятся отрезками);
    PLT/HPGL   — перо PU (подъём/переход) и PD (опускание/рез).

Контур описывается списком ломаных (polylines), каждая — список точек (x, y)
в исходных единицах файла. Дальше fit_to_machine() масштабирует контур под
рабочее поле станка с сохранением пропорций и выдаёт:

    • machine_track  — единый упорядоченный список точек (X головки, Y стола)
                       в координатах станка (целые) — по нему движется головка;
    • norm_segments  — те же ломаные в долях [0..1] поля — для 3D-визуализации.

Соответствие осей принятой кинематике: X — горизонталь лазерной головки
(шаговый привод), Y — подача координатного стола; глубина (Z) здесь не
задаётся — контур плоский.
"""

from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET

_CIRCLE_SEG = 64          # на сколько отрезков дробим окружность/дугу
_CURVE_SEG = 24           # сегментов на кривую Безье в SVG-path


class ToolPath:
    """Плоский контур: набор ломаных в исходных единицах файла."""

    def __init__(self, polylines, name="", fmt=""):
        # отбрасываем вырожденные (пустые) ломаные
        self.polylines = [pl for pl in polylines if len(pl) >= 1]
        self.name = name
        self.fmt = fmt

    @property
    def vertex_count(self) -> int:
        return sum(len(pl) for pl in self.polylines)

    def bounds(self):
        xs = [p[0] for pl in self.polylines for p in pl]
        ys = [p[1] for pl in self.polylines for p in pl]
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def is_empty(self) -> bool:
        return not any(len(pl) >= 2 for pl in self.polylines)


# ───────────────────────────── DXF ────────────────────────────────────

def _read_dxf_pairs(path):
    """DXF — поток пар (код, значение). Возвращает список (int_code, str_val)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = [ln.strip() for ln in f]
    pairs = []
    for i in range(0, len(lines) - 1, 2):
        try:
            code = int(lines[i])
        except ValueError:
            continue
        pairs.append((code, lines[i + 1]))
    return pairs


def _arc_points(cx, cy, r, a0_deg, a1_deg):
    a0 = math.radians(a0_deg)
    a1 = math.radians(a1_deg)
    if a1 <= a0:
        a1 += 2 * math.pi
    n = max(2, int(_CIRCLE_SEG * (a1 - a0) / (2 * math.pi)))
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n),
             cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def _parse_dxf(path):
    pairs = _read_dxf_pairs(path)
    polylines = []
    i = 0
    n = len(pairs)
    # перейти к секции ENTITIES
    while i < n and not (pairs[i][0] == 2 and pairs[i][1] == "ENTITIES"):
        i += 1
    i += 1

    def entity_block(start):
        """Собрать пары одной сущности до следующего кода 0."""
        j = start + 1
        block = []
        while j < n and pairs[j][0] != 0:
            block.append(pairs[j])
            j += 1
        return block, j

    while i < n:
        code, val = pairs[i]
        if code != 0:
            i += 1
            continue
        etype = val
        if etype in ("ENDSEC", "EOF"):
            break
        block, nxt = entity_block(i)
        d = {}
        xs, ys = [], []
        closed = False
        for c, v in block:
            if c == 10:
                xs.append(float(v))
            elif c == 20:
                ys.append(float(v))
            elif c == 70:
                closed = bool(int(float(v)) & 1)
            else:
                d.setdefault(c, v)

        if etype == "LINE":
            if len(xs) >= 1 and len(ys) >= 1:
                x0, y0 = xs[0], ys[0]
                x1 = float(d.get(11, x0)); y1 = float(d.get(21, y0))
                polylines.append([(x0, y0), (x1, y1)])
        elif etype in ("LWPOLYLINE", "POLYLINE"):
            pts = list(zip(xs, ys))
            if closed and len(pts) >= 2:
                pts = pts + [pts[0]]
            if pts:
                polylines.append(pts)
        elif etype == "CIRCLE":
            if xs and ys and 40 in d:
                cx, cy, r = xs[0], ys[0], float(d[40])
                polylines.append(_arc_points(cx, cy, r, 0, 360))
        elif etype == "ARC":
            if xs and ys and 40 in d and 50 in d and 51 in d:
                polylines.append(_arc_points(
                    xs[0], ys[0], float(d[40]), float(d[50]), float(d[51])))
        # VERTEX/SEQEND/прочее — пропускаем (вершины LWPOLYLINE уже собраны)
        i = nxt

    return ToolPath(polylines, name=os.path.basename(path), fmt="DXF")


# ───────────────────────────── SVG ────────────────────────────────────

def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def _flatten_path(d):
    """Минимальный флэттенинг SVG-path: M/L/H/V/Z + кривые C/Q (отрезками).

    A/S/T и прочее аппроксимируются прямой до конечной точки. Y инвертируется
    выше по стеку (на уровне элемента), здесь — как в исходных координатах.
    """
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    polylines, cur = [], []
    x = y = 0.0
    sx = sy = 0.0
    cmd = None
    idx = 0

    def num():
        nonlocal idx
        v = float(tokens[idx]); idx += 1
        return v

    while idx < len(tokens):
        t = tokens[idx]
        if t.isalpha():
            cmd = t; idx += 1
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            if cur:
                polylines.append(cur)
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            sx, sy = x, y
            cur = [(x, y)]
            cmd = "l" if rel else "L"     # последующие пары M трактуются как L
        elif c == "L":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            cur.append((x, y))
        elif c == "H":
            nx = num(); x = x + nx if rel else nx
            cur.append((x, y))
        elif c == "V":
            ny = num(); y = y + ny if rel else ny
            cur.append((x, y))
        elif c in ("C", "Q"):
            pts = []
            if c == "C":
                x1, y1, x2, y2, ex, ey = (num(), num(), num(), num(), num(), num())
                if rel:
                    x1 += x; y1 += y; x2 += x; y2 += y; ex += x; ey += y
                p0, p1, p2, p3 = (x, y), (x1, y1), (x2, y2), (ex, ey)
                for k in range(1, _CURVE_SEG + 1):
                    u = k / _CURVE_SEG; m = 1 - u
                    bx = (m**3 * p0[0] + 3 * m * m * u * p1[0]
                          + 3 * m * u * u * p2[0] + u**3 * p3[0])
                    by = (m**3 * p0[1] + 3 * m * m * u * p1[1]
                          + 3 * m * u * u * p2[1] + u**3 * p3[1])
                    pts.append((bx, by))
                x, y = ex, ey
            else:  # Q
                x1, y1, ex, ey = (num(), num(), num(), num())
                if rel:
                    x1 += x; y1 += y; ex += x; ey += y
                p0, p1, p2 = (x, y), (x1, y1), (ex, ey)
                for k in range(1, _CURVE_SEG + 1):
                    u = k / _CURVE_SEG; m = 1 - u
                    bx = m * m * p0[0] + 2 * m * u * p1[0] + u * u * p2[0]
                    by = m * m * p0[1] + 2 * m * u * p1[1] + u * u * p2[1]
                    pts.append((bx, by))
                x, y = ex, ey
            cur.extend(pts)
        elif c in ("S", "T", "A"):
            # аппроксимация: берём только конечную точку команды
            need = {"S": 4, "T": 2, "A": 7}[c]
            vals = [num() for _ in range(need)]
            ex, ey = vals[-2], vals[-1]
            x, y = (x + ex, y + ey) if rel else (ex, ey)
            cur.append((x, y))
        elif c == "Z":
            if cur:
                cur.append((sx, sy))
                polylines.append(cur)
                cur = []
            x, y = sx, sy
        else:
            idx += 1
    if cur:
        polylines.append(cur)
    return polylines


def _parse_svg(path):
    tree = ET.parse(path)
    root = tree.getroot()
    polylines = []

    def add(pts):
        if len(pts) >= 1:
            polylines.append(pts)

    for el in root.iter():
        tag = _strip_ns(el.tag)
        a = el.attrib
        try:
            if tag == "line":
                add([(float(a["x1"]), float(a["y1"])),
                     (float(a["x2"]), float(a["y2"]))])
            elif tag in ("polyline", "polygon"):
                nums = [float(v) for v in re.findall(
                    r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", a.get("points", ""))]
                pts = list(zip(nums[0::2], nums[1::2]))
                if tag == "polygon" and len(pts) >= 2:
                    pts = pts + [pts[0]]
                add(pts)
            elif tag == "rect":
                x, y = float(a.get("x", 0)), float(a.get("y", 0))
                w, h = float(a["width"]), float(a["height"])
                add([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
            elif tag == "circle":
                cx, cy, r = float(a["cx"]), float(a["cy"]), float(a["r"])
                add(_arc_points(cx, cy, r, 0, 360))
            elif tag == "ellipse":
                cx, cy = float(a["cx"]), float(a["cy"])
                rx, ry = float(a["rx"]), float(a["ry"])
                add([(cx + rx * math.cos(2 * math.pi * k / _CIRCLE_SEG),
                      cy + ry * math.sin(2 * math.pi * k / _CIRCLE_SEG))
                     for k in range(_CIRCLE_SEG + 1)])
            elif tag == "path" and a.get("d"):
                for pl in _flatten_path(a["d"]):
                    add(pl)
        except (KeyError, ValueError):
            continue

    # SVG: ось Y вниз — инвертируем, чтобы контур выглядел естественно (Y вверх)
    polylines = [[(x, -y) for x, y in pl] for pl in polylines]
    return ToolPath(polylines, name=os.path.basename(path), fmt="SVG")


# ────────────────────────── PLT / HPGL ────────────────────────────────

def _parse_plt(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    polylines = []
    cur = []
    pen_down = False
    pos = (0.0, 0.0)

    for cmd in text.replace("\n", "").split(";"):
        cmd = cmd.strip()
        if len(cmd) < 2:
            continue
        op = cmd[:2].upper()
        nums = [float(v) for v in re.findall(
            r"-?\d*\.?\d+", cmd[2:])]
        coords = list(zip(nums[0::2], nums[1::2]))
        if op == "PU":
            if pen_down and len(cur) >= 2:
                polylines.append(cur)
            pen_down = False
            cur = []
            if coords:
                pos = coords[-1]
        elif op == "PD":
            if not pen_down:
                cur = [pos]
                pen_down = True
            for c in coords:
                cur.append(c)
                pos = c
        elif op in ("PA", "PR"):
            for c in coords:
                if pen_down:
                    cur.append(c)
                pos = c
        # IN/SP/прочее — игнорируем
    if pen_down and len(cur) >= 2:
        polylines.append(cur)
    return ToolPath(polylines, name=os.path.basename(path), fmt="HPGL")


# ─────────────────────────── диспетчер ────────────────────────────────

_PARSERS = {
    ".dxf": _parse_dxf,
    ".svg": _parse_svg,
    ".plt": _parse_plt,
    ".hpgl": _parse_plt,
    ".hpg": _parse_plt,
}

SUPPORTED_EXTS = tuple(_PARSERS.keys())


def is_toolpath_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _PARSERS


def load_toolpath(path: str) -> ToolPath:
    """Загрузить контур из векторного файла. Бросает ValueError при ошибке."""
    ext = os.path.splitext(path)[1].lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        raise ValueError(f"Формат {ext} не поддерживается "
                         f"(нужен DXF/SVG/PLT/HPGL)")
    tp = parser(path)
    if tp.is_empty():
        raise ValueError("В файле не найдено ни одного контура")
    return tp


# ───────────────────── приведение к полю станка ───────────────────────

def fit_to_machine(tp: ToolPath, x_range, y_range, margin: float = 0.12):
    """Масштабировать контур под поле станка с сохранением пропорций.

    x_range, y_range — (min, max) хода головки (X) и стола (Y) в шагах.
    Возвращает (machine_track, norm_segments, machine_segments):
        machine_track   — [(X, Y), …] целые координаты станка (для движения);
        norm_segments   — [[(xf, yf), …], …] доли [0..1] (для 3D-вида);
        machine_segments— [[(X, Y), …], …] координаты станка по ломаным.
    """
    minx, miny, maxx, maxy = tp.bounds()
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    ax = (x_range[1] - x_range[0])
    ay = (y_range[1] - y_range[0])
    scale = min(ax * (1 - 2 * margin) / w, ay * (1 - 2 * margin) / h)

    cx_src, cy_src = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    cx_dst = (x_range[0] + x_range[1]) / 2.0
    cy_dst = (y_range[0] + y_range[1]) / 2.0

    def to_m(p):
        X = cx_dst + (p[0] - cx_src) * scale
        Y = cy_dst + (p[1] - cy_src) * scale
        X = int(round(min(x_range[1], max(x_range[0], X))))
        Y = int(round(min(y_range[1], max(y_range[0], Y))))
        return (X, Y)

    machine_segments = [[to_m(p) for p in pl] for pl in tp.polylines]

    def norm(P):
        return ((P[0] - x_range[0]) / (ax or 1),
                (P[1] - y_range[0]) / (ay or 1))

    norm_segments = [[norm(P) for P in seg] for seg in machine_segments]
    machine_track = [P for seg in machine_segments for P in seg]
    return machine_track, norm_segments, machine_segments
