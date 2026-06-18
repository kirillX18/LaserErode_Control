"""
machining.py — геометрия и фазовая модель прошивки несквозного отверстия.

Что делает: для уже загруженной 3D-модели детали (список треугольников из
viewer3d.load_mesh) подбирает на плоской стенке место под круглое глухое
(несквозное) отверстие и строит геометрию его постепенного формирования по
ходу процесса. Технология двухфазная — как на реальном станке:

    Фаза 1 «Лазер: рез эмали». Поверхностный слой (эмаль/покрытие) не
        проводит ток, поэтому эрозия по нему невозможна. Сначала лазер
        прожигает эмаль на пятне будущего отверстия — снимается тонкий слой
        (enamel), обнажается металл. В кадре: красный луч, обугленное кольцо
        вокруг пятна, неглубокая лунка.

    Фаза 2 «Эрозия: прошивка отверстия». По обнажённому металлу
        электрод-инструмент электроэрозионно прошивает глухое отверстие на
        полную глубину depth_full (< толщины стенки — остаётся дно). В кадре:
        электрод, искры у дна, разогретое дно лунки, светлая металлическая
        стенка канала.

Модуль не зависит от PyQt/OpenGL — только чистая геометрия (списки точек и
треугольников в мировых координатах) и подбор параметров. Рендерит это любой
из вьюпортов (viewer3d / viewer_gl) через set_overlay()/set_drill_tool().

Главное API:
    site = pick_drill_site(tris)                 # выбрать стенку и параметры
    body = carve_body(tris, site)                # деталь с открытым устьем
    phase, depth, hot = phase_state(progress, site)
    tris2, cols = build_overlay(site, depth, phase, hot)   # лунка/кольцо/дно
    tool = drill_tool(site, depth, phase)        # луч/электрод + искры
"""

from __future__ import annotations

import math

# ── фазы ───────────────────────────────────────────────────────────────
PHASE_IDLE = "idle"
PHASE_LASER = "laser"      # рез эмали лазером
PHASE_EDM = "edm"          # электроэрозионная прошивка

# Доля прогресса (0..1) на лазерную обводку контура. Остальное — эрозия.
_LASER_FRACTION = 0.5
# Сколько оборотов делает лазер по контуру за фазу обводки (>1 — с запасом,
# чтобы контур точно замкнулся).
_LASER_LAPS = 1.2
# Число сегментов окружности отверстия (48 — визуально гладкий круг).
_SEG = 48

# ── палитра материалов канала (RGB 0..1) ───────────────────────────────
_COL_SCORCH = (0.16, 0.17, 0.21)     # обугленная эмаль (кольцо ЗТВ)
_COL_SCORCH_HOT = (0.55, 0.20, 0.10)  # подсветка кольца под лучом
_COL_ENAMEL = (0.34, 0.26, 0.22)     # стенка в зоне эмали (тёмная, обгоревшая)
_COL_METAL = (0.80, 0.84, 0.90)      # стенка канала по металлу (свежий рез)
_COL_BOTTOM = (0.66, 0.72, 0.80)     # дно лунки (металл)
_COL_BOTTOM_HOT = (0.98, 0.55, 0.22)  # дно под эрозией (разогрето, искра)
_COL_GROOVE_PLAN = (0.30, 0.33, 0.39)  # намеченный контур (ещё не прорезан)
_COL_GROOVE_CUT = (0.14, 0.15, 0.18)  # прорезанный контур (обугленная канавка)
_COL_LASER_HOT = (1.0, 0.55, 0.16)   # светящаяся точка реза под лучом


# ── мелкая векторная математика ─────────────────────────────────────────
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v):
    m = math.sqrt(_dot(v, v)) or 1.0
    return (v[0] / m, v[1] / m, v[2] / m)


def _bounds(tris):
    xs = []; ys = []; zs = []
    for t in tris:
        for v in t:
            xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def _ray_tri(o, d, a, b, c):
    """Пересечение луча (o + t·d) с треугольником. Möller–Trumbore.
    Возвращает (t, нормаль) при t>0 или None."""
    e1 = _sub(b, a); e2 = _sub(c, a)
    p = _cross(d, e2); det = _dot(e1, p)
    if abs(det) < 1e-9:
        return None
    inv = 1.0 / det
    tv = _sub(o, a); u = _dot(tv, p) * inv
    if u < -1e-6 or u > 1 + 1e-6:
        return None
    q = _cross(tv, e1); vv = _dot(d, q) * inv
    if vv < -1e-6 or u + vv > 1 + 1e-6:
        return None
    t = _dot(e2, q) * inv
    if t <= 1e-6:
        return None
    return t, _norm(_cross(e1, e2))


# ── подбор места под отверстие ──────────────────────────────────────────
# Горизонтальное направление «на зрителя» при стартовом ракурсе камеры
# (yaw≈35°, pitch≈58°): на эту сторону пользователь и смотрит, туда и сажаем
# отверстие, если стенок-кандидатов несколько (как нарисованный круг на пере).
_FRONT_DIR = (-0.57, -0.82)


def pick_drill_site(tris) -> dict | None:
    """Подобрать место и параметры глухого отверстия.

    Приоритет — вертикальная стенка на средней высоте детали (стенка пера/
    корпуса), обращённая к зрителю: именно туда обычно ведут рез. Если такой
    стенки нет, берётся запасной вариант — плоская толстая полка/основание."""
    if not tris:
        return None
    site = _pick_wall_site(tris)
    if site is not None:
        return site
    return _pick_flat_site(tris)


def _pick_wall_site(tris) -> dict | None:
    """Вертикальная стенка на средней высоте, обращённая к зрителю.

    Стенка может быть изогнутой (оболочка пера), поэтому компланарность не
    требуется: место берётся как площадно-взвешенный центр граней выбранной
    «передней» стороны, нормаль — локальная (средняя по кластеру). Глубина
    строго меньше толщины стенки (отверстие несквозное)."""
    (xlo, xhi), (ylo, yhi), (zlo, zhi) = _bounds(tris)
    Hx, Hy, Hz = xhi - xlo, yhi - ylo, zhi - zlo
    if Hz <= 1e-6:
        return None
    diag = math.sqrt(Hx * Hx + Hy * Hy + Hz * Hz)
    axis_x = 0.5 * (xlo + xhi)        # вертикальная ось детали (центр XY)
    axis_y = 0.5 * (ylo + yhi)
    zb_lo = zlo + 0.32 * Hz           # полоса средней высоты (где рисуют круг)
    zb_hi = zlo + 0.60 * Hz

    # грани-кандидаты: на средней высоте, почти вертикальные, наружу от оси
    cand = []
    for a, b, c in tris:
        n = _cross(_sub(b, a), _sub(c, a))
        area = 0.5 * math.sqrt(_dot(n, n))
        if area <= 1e-9:
            continue
        nn = _norm(n)
        if abs(nn[2]) > 0.5:                       # не вертикальная
            continue
        cz = (a[2] + b[2] + c[2]) / 3.0
        if not (zb_lo <= cz <= zb_hi):
            continue
        cx = (a[0] + b[0] + c[0]) / 3.0
        cy = (a[1] + b[1] + c[1]) / 3.0
        radial = (cx - axis_x, cy - axis_y)        # наружу от оси детали
        if nn[0] * radial[0] + nn[1] * radial[1] <= 0:
            continue
        cand.append((nn, area, (cx, cy, cz)))
    if not cand:
        return None

    # выбрать «переднюю» сторону: бинируем по азимуту нормали, для каждого бина
    # копим площадь со взвешиванием на обращённость к зрителю (_FRONT_DIR)
    bins = {}
    for nn, area, ctr in cand:
        az = int((math.atan2(nn[1], nn[0]) + math.pi) / (math.pi / 12)) % 24
        facing = 0.5 + 0.5 * (nn[0] * _FRONT_DIR[0] + nn[1] * _FRONT_DIR[1])
        slot = bins.setdefault(az, [0.0, 0.0, []])
        slot[0] += area                         # суммарная площадь
        slot[1] += area * facing                # вклад с учётом обращённости
        slot[2].append((nn, area, ctr))
    # лучший бин — по взвешенному вкладу, но с минимальной реальной площадью
    best_az = max(bins, key=lambda k: bins[k][1])
    group = bins[best_az][2]
    tot = sum(a for _, a, _ in group)
    if tot <= 1e-9:
        return None

    # площадно-взвешенные центр и нормаль выбранной стороны
    cx = sum(a * c[0] for _, a, c in group) / tot
    cy = sum(a * c[1] for _, a, c in group) / tot
    cz = sum(a * c[2] for _, a, c in group) / tot
    nx = sum(a * n[0] for n, a, _ in group) / tot
    ny = sum(a * n[1] for n, a, _ in group) / tot
    nz = sum(a * n[2] for n, a, _ in group) / tot
    out = _norm((nx, ny, nz))
    axis = _mul(out, -1.0)

    # базис стенки: v — вертикаль (вдоль прямой образующей оболочки, там стенка
    # не кривится → кольцо ложится точнее), u — горизонталь (хорда, кривизна).
    v = _norm(_sub((0.0, 0.0, 1.0),
                   _mul(out, _dot((0.0, 0.0, 1.0), out))))
    u = _norm(_cross(out, v))

    # центр устья = геометрический центр выбранной грани (середина габаритов
    # кластера в плоскости стенки), а не площадно-взвешенный центр — так круг
    # садится аккуратно по центру заготовки, не сползая к краю/ряду отверстий.
    origin = (cx, cy, cz)
    us = [_dot(_sub(g[2], origin), u) for g in group]
    vs = [_dot(_sub(g[2], origin), v) for g in group]
    cu = 0.5 * (min(us) + max(us))
    cv = 0.5 * (min(vs) + max(vs))
    centred = _add(origin, _add(_mul(u, cu), _mul(v, cv)))
    surf, thickness = _thickness_at(tris, centred, out, axis, diag)

    # несквозное: глубина < толщины тонкой стенки оболочки
    depth_full = min(0.7 * thickness, 0.10 * diag)
    radius = min(1.6, 0.12 * diag, 0.45 * Hz)
    radius = max(radius, 0.8)
    enamel = min(0.3 * depth_full, 0.4)

    return {
        "p0": surf, "out": out, "axis": axis, "u": u, "v": v,
        "R": radius, "depth_full": depth_full, "enamel": enamel,
        "thickness": thickness,
    }


def _pick_flat_site(tris) -> dict | None:
    """Запасной выбор: плоская толстая стенка (основание/полка)."""
    if not tris:
        return None
    (xlo, xhi), (ylo, yhi), (zlo, zhi) = _bounds(tris)
    diag = math.sqrt((xhi - xlo) ** 2 + (yhi - ylo) ** 2 + (zhi - zlo) ** 2)

    # предрасчёт нормалей/площадей/центров граней
    faces = []
    for a, b, c in tris:
        n = _cross(_sub(b, a), _sub(c, a))
        area = 0.5 * math.sqrt(_dot(n, n))
        if area <= 1e-9:
            continue
        nn = _norm(n)
        ctr = ((a[0] + b[0] + c[0]) / 3.0,
               (a[1] + b[1] + c[1]) / 3.0,
               (a[2] + b[2] + c[2]) / 3.0)
        faces.append((nn, area, ctr))

    # кандидатные наружные направления (низ -Z исключён: деталь стоит на столе)
    candidates = [
        ((1.0, 0.0, 0.0), xhi, 0), ((-1.0, 0.0, 0.0), xlo, 0),
        ((0.0, 1.0, 0.0), yhi, 1), ((0.0, -1.0, 0.0), ylo, 1),
        ((0.0, 0.0, 1.0), zhi, 2),
    ]
    span = (xhi - xlo, yhi - ylo, zhi - zlo)

    best = None
    for out, edge, axis_i in candidates:
        sgn = 1.0 if out[axis_i] > 0 else -1.0
        near = edge - sgn * 0.12 * span[axis_i]   # «у внешней границы»
        cluster = []
        for nn, area, ctr in faces:
            if _dot(nn, out) < 0.92:               # грань почти строго наружу
                continue
            if sgn * (ctr[axis_i] - near) < 0:     # и лежит у внешней грани
                continue
            cluster.append((area, ctr))
        if not cluster:
            continue
        tot = sum(a for a, _ in cluster)
        # центр кластера и толщина стенки под ним (луч вдоль оси внутрь)
        cx = sum(a * c[0] for a, c in cluster) / tot
        cy = sum(a * c[1] for a, c in cluster) / tot
        cz = sum(a * c[2] for a, c in cluster) / tot
        centroid = (cx, cy, cz)
        surf, thick = _thickness_at(tris, centroid, out, _mul(out, -1.0), diag)
        # ключевой критерий — толщина: глухое отверстие нужно в массивной
        # стенке (основание/полка), а не в тонкой оболочке пера. Площадь —
        # вторичный множитель. Верхнюю грань слегка штрафуем (бок > верх).
        # Разброс кластера вдоль оси наказываем: настоящая плоская стенка
        # лежит в одной плоскости (нулевой разброс по `out`).
        offs = [c[axis_i] for _, c in cluster]
        flat = max(offs) - min(offs)
        coplanar = 1.0 / (1.0 + (flat / max(diag * 0.02, 1e-6)))
        sidewt = 0.6 if out == (0.0, 0.0, 1.0) else 1.0
        score = tot * (thick ** 2) * sidewt * coplanar
        if best is None or score > best[0]:
            best = (score, out, cluster, tot, centroid, surf, thick)

    if best is None:
        return None
    _, out, cluster, tot, centroid, surf, thickness = best
    out = _norm(out)
    axis = _mul(out, -1.0)                          # ось сверления — внутрь

    # локальный базис стенки (u, v ⟂ оси)
    up = (0.0, 0.0, 1.0) if abs(out[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _norm(_cross(up, out))
    v = _norm(_cross(out, u))

    # габариты плоского участка в плоскости стенки
    us = [_dot(_sub(c, centroid), u) for _, c in cluster]
    vs = [_dot(_sub(c, centroid), v) for _, c in cluster]
    ext_u = (max(us) - min(us)) or diag * 0.1
    ext_v = (max(vs) - min(vs)) or diag * 0.1

    # Глубина — строго меньше толщины стенки (отверстие несквозное) и не
    # больше доли габарита детали (чтобы канал был «отверстием», а не шахтой).
    depth_full = min(0.55 * thickness, 0.20 * diag)
    # Радиус — по размеру плоского участка, но не глубже половины глубины
    # «на ширину» (канал должен читаться как отверстие, а не как блюдце).
    radius = 0.15 * min(ext_u, ext_v)
    radius = min(radius, 0.9 * depth_full, 0.42 * min(ext_u, ext_v), 0.07 * diag)
    radius = max(radius, min(0.6, 0.35 * depth_full))
    enamel = min(0.22 * depth_full, 0.7)

    # удержать отверстие+кольцо внутри плоского участка (зажать центр по u,v)
    cu = _dot(_sub(surf, centroid), u)
    cv = _dot(_sub(surf, centroid), v)
    lim_u = max(0.0, 0.5 * ext_u - radius * 1.6)
    lim_v = max(0.0, 0.5 * ext_v - radius * 1.6)
    cu = max(-lim_u, min(lim_u, cu))
    cv = max(-lim_v, min(lim_v, cv))
    centred = _add(centroid, _add(_mul(u, cu), _mul(v, cv)))
    p0, thickness = _thickness_at(tris, centred, out, axis, diag)
    # пересчитать глубину под фактической толщиной в точке устья
    depth_full = min(depth_full, 0.55 * thickness)
    radius = min(radius, 0.9 * depth_full)
    enamel = min(enamel, 0.22 * depth_full)

    return {
        "p0": p0, "out": out, "axis": axis, "u": u, "v": v,
        "R": radius, "depth_full": depth_full, "enamel": enamel,
        "thickness": thickness,
    }


def _thickness_at(tris, point, out, axis, diag):
    """Поверхностная точка и толщина стенки под `point` вдоль оси сверления.
    Луч пускаем снаружи внутрь; первый удар — поверхность, разница до второго
    удара — толщина стенки. Без второго удара толщину оцениваем грубо."""
    o = _add(point, _mul(out, diag))
    hits = []
    for a, b, c in tris:
        r = _ray_tri(o, axis, a, b, c)
        if r:
            hits.append(r[0])
    if not hits:
        return point, diag * 0.2
    hits.sort()
    surf = _add(o, _mul(axis, hits[0]))
    thick = (hits[1] - hits[0]) if len(hits) >= 2 else diag * 0.2
    return surf, thick


# ── вырезание устья отверстия в детали ──────────────────────────────────
def carve_body(tris, site) -> list:
    """Вернуть копию детали с физически открытым устьем отверстия.

    Стенка детали тесселирована грубо: один-два треугольника стенки крупнее
    самого отверстия (рёбра ~6 мм при Ø ~3 мм), поэтому «удаление по центру»
    ничего не вскрывает. Здесь те треугольники наружной стенки, что перекрывают
    пятно устья, субдивидятся барицентрической сеткой на мелкие, и из них
    выбрасываются попавшие внутрь круга. Границы исходных треугольников
    сохраняются (узлы сетки лежат на рёбрах) — стыков-щелей с соседями нет;
    «ступеньки» кромки прячутся под кольцом ЗТВ (build_overlay). Несквозное:
    снимается только наружный слой граней — дно стенки остаётся целым."""
    p0 = site["p0"]; out = site["out"]; axis = site["axis"]
    u = site["u"]; v = site["v"]; R = site["R"]
    drop = (R * 1.15) ** 2          # радиус² «съедаемого» пятна тела
    touch = (R * 1.6) ** 2          # радиус² «затронутого» (под субдивизию)

    def _ruv(pt):                    # координаты точки в плоскости устья
        rel = (pt[0] - p0[0], pt[1] - p0[1], pt[2] - p0[2])
        return _dot(rel, u), _dot(rel, v), _dot(rel, axis)

    result = []
    for tri in tris:
        a, b, c = tri
        # грань наружной стенки устья: нормаль наружу и лежит у поверхности
        n = _cross(_sub(b, a), _sub(c, a))
        nm = math.sqrt(_dot(n, n)) or 1.0
        outward = (n[0] / nm) * out[0] + (n[1] / nm) * out[1] + (n[2] / nm) * out[2]
        au, av, aw = _ruv(a); bu, bv, bw = _ruv(b); cu, cv, cw = _ruv(c)
        depth_avg = (aw + bw + cw) / 3.0
        # верхний слой стенки (aw≈0..) и грань смотрит наружу
        is_face = outward > 0.85 and -0.3 * R <= depth_avg <= 0.6 * R
        # перекрывает ли треугольник пятно устья (вершина близко к оси
        # или центр круга внутри треугольника в плоскости (u,v))
        rv2 = [au * au + av * av, bu * bu + bv * bv, cu * cu + cv * cv]
        near = min(rv2) <= touch or _point_in_tri2d(
            (au, av), (bu, bv), (cu, cv))
        if not (is_face and near):
            result.append(tri)
            continue
        # субдивизия под размер отверстия: ребро ≈ 0.4·R
        emax = max(_dist2((au, av), (bu, bv)),
                   _dist2((bu, bv), (cu, cv)),
                   _dist2((cu, cv), (au, av))) ** 0.5
        k = max(5, min(16, int(math.ceil(emax / (R * 0.4)))))
        for sub in _subdivide_tri(a, b, c, k):
            su = _ruv(sub[0]); sv = _ruv(sub[1]); sw = _ruv(sub[2])
            mu = (su[0] + sv[0] + sw[0]) / 3.0
            mv = (su[1] + sv[1] + sw[1]) / 3.0
            if mu * mu + mv * mv < drop:
                continue                 # под-треугольник внутри устья — убрать
            result.append(sub)
    return result


def _point_in_tri2d(a, b, c, p=(0.0, 0.0)):
    """Лежит ли точка p (по умолчанию начало = ось устья) внутри 2D-треуг."""
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _subdivide_tri(a, b, c, k):
    """Барицентрическая сетка k×k → k² мелких треугольников, точно
    закрывающих исходный (узлы на рёбрах → стыки с соседями без щелей)."""
    def P(i, j):
        s = i / k; t = j / k
        return (a[0] + (b[0] - a[0]) * s + (c[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * s + (c[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * s + (c[2] - a[2]) * t)
    out = []
    for i in range(k):
        for j in range(k - i):
            out.append((P(i, j), P(i + 1, j), P(i, j + 1)))
            if i + j < k - 1:
                out.append((P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)))
    return out


# ── фазовая модель: прогресс → фаза, глубина, обводка ───────────────────
def phase_state(progress: float, site: dict):
    """progress (0..100) → (phase, depth, hot, sweep).

    Фаза 1 (лазер) — обводка контура: sweep растёт 0→_LASER_LAPS (доля оборота
    лазера по окружности), depth держится у эмали. Фаза 2 (эрозия) — заглубление
    лунки: depth идёт от эмали до полной, sweep=полный круг, hot — накал дна."""
    p = max(0.0, min(100.0, progress)) / 100.0
    enamel = site["enamel"]; full = site["depth_full"]
    if p <= _LASER_FRACTION:
        frac = p / _LASER_FRACTION if _LASER_FRACTION > 0 else 1.0
        sweep = frac * _LASER_LAPS
        return PHASE_LASER, enamel * min(1.0, sweep), 0.0, sweep
    frac = (p - _LASER_FRACTION) / (1.0 - _LASER_FRACTION)
    depth = enamel + (full - enamel) * frac
    hot = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(p * 34.0))   # мерцание искры
    return PHASE_EDM, depth, hot, _LASER_LAPS


# ── геометрия лунки/кольца/дна (overlay) ────────────────────────────────
def _ring(site, t):
    """Кольцо из _SEG точек на окружности отверстия на глубине t."""
    p0 = site["p0"]; u = site["u"]; v = site["v"]; axis = site["axis"]
    R = site["R"]
    base = _add(p0, _mul(axis, t))
    pts = []
    for i in range(_SEG):
        a = 2.0 * math.pi * i / _SEG
        pts.append(_add(base, _add(_mul(u, R * math.cos(a)),
                                   _mul(v, R * math.sin(a)))))
    return pts


def build_overlay(site, depth, phase, hot, sweep=0.0):
    """Геометрия + цвета визуализации.

    Фаза 1 (лазер): прогрессивная канавка-контур на поверхности — лазер
    обводит окружность, прорезанная часть тёмная/обугленная, перед лучом —
    светящаяся точка реза, остаток — намеченный контур. Деталь ещё цела.
    Фаза 2 (эрозия): открытая лунка — стенка канала (эмаль/металл), дно и
    обугленное кольцо ЗТВ вокруг устья."""
    p0 = site["p0"]; u = site["u"]; v = site["v"]; axis = site["axis"]
    out = site["out"]; R = site["R"]; enamel = site["enamel"]

    if phase == PHASE_LASER:
        return _overlay_contour(site, sweep)

    tris = []
    cols = []
    # 1) обугленное кольцо ЗТВ на поверхности (чуть приподнято над стенкой)
    lift = _mul(out, R * 0.05)
    inner = [_add(p, lift) for p in _ring(site, 0.0)]
    R_out = R * 1.34
    outer = []
    base = _add(p0, lift)
    for i in range(_SEG):
        a = 2.0 * math.pi * i / _SEG
        outer.append(_add(base, _add(_mul(u, R_out * math.cos(a)),
                                     _mul(v, R_out * math.sin(a)))))
    ring_col = _COL_SCORCH
    for i in range(_SEG):
        j = (i + 1) % _SEG
        tris.append((inner[i], outer[i], outer[j])); cols.append(ring_col)
        tris.append((inner[i], outer[j], inner[j])); cols.append(ring_col)

    # 2) стенка канала: кольца на нескольких уровнях; цвет зависит от того,
    #    эмаль это (тёмная зона) или металл (светлая зона).
    levels = [0.0]
    if depth > enamel:
        levels += [enamel, depth]
    else:
        levels += [depth]
    rings = [_ring(site, t) for t in levels]
    for k in range(len(levels) - 1):
        t_mid = 0.5 * (levels[k] + levels[k + 1])
        col = _COL_ENAMEL if t_mid <= enamel + 1e-6 else _COL_METAL
        lo = rings[k]; hi = rings[k + 1]
        for i in range(_SEG):
            j = (i + 1) % _SEG
            tris.append((lo[i], hi[i], hi[j])); cols.append(col)
            tris.append((lo[i], hi[j], lo[j])); cols.append(col)

    # 3) дно лунки — пологий конус (вид «прошитого» дна), вершина чуть глубже
    bottom = _ring(site, depth)
    apex = _add(p0, _mul(axis, depth + R * 0.12))
    h = max(0.0, min(1.0, hot))
    bcol = tuple(_COL_BOTTOM[i] + (_COL_BOTTOM_HOT[i] - _COL_BOTTOM[i]) * h
                 for i in range(3))
    for i in range(_SEG):
        j = (i + 1) % _SEG
        tris.append((bottom[i], bottom[j], apex)); cols.append(bcol)

    return tris, cols


def _overlay_contour(site, sweep):
    """Канавка-контур на поверхности: плоское кольцо-полоса вокруг окружности
    отверстия. Прорезанная (по ходу луча) часть тёмная, перед лучом —
    светящаяся точка, ещё не пройденная — намеченный (бледный) контур."""
    tris = []; cols = []
    p0 = site["p0"]; u = site["u"]; v = site["v"]; out = site["out"]; R = site["R"]
    base = _add(p0, _mul(out, R * 0.08))      # приподнять над изогнутой стенкой
    r0 = R * 0.84; r1 = R * 1.16              # ширина канавки вокруг радиуса R
    cut = min(1.0, sweep)
    lead_i = cut * _SEG                        # индекс «головы» луча

    def pt(r, a):
        return _add(base, _add(_mul(u, r * math.cos(a)),
                               _mul(v, r * math.sin(a))))
    for i in range(_SEG):
        a0 = 2.0 * math.pi * i / _SEG
        a1 = 2.0 * math.pi * (i + 1) / _SEG
        seg = (i + 0.5) / _SEG
        if seg <= cut:
            # прорезано; у самой «головы» луча — горячая точка
            if sweep < 1.0 and 0 <= (lead_i - i) <= 2:
                col = _COL_LASER_HOT
            else:
                col = _COL_GROOVE_CUT
        else:
            col = _COL_GROOVE_PLAN
        in0 = pt(r0, a0); in1 = pt(r0, a1)
        ou0 = pt(r1, a0); ou1 = pt(r1, a1)
        tris.append((in0, ou0, ou1)); cols.append(col)
        tris.append((in0, ou1, in1)); cols.append(col)
    return tris, cols


# ── инструмент над отверстием (луч/электрод + искры) ────────────────────
def drill_tool(site, depth, phase, sweep=0.0):
    """Положение инструмента. Лазер (фаза 1): луч идёт сверху в точку на
    контуре, которая движется по окружности (обводка). Электрод (фаза 2):
    стоит над центром, наконечник у дна лунки, вокруг — искры."""
    p0 = site["p0"]; out = site["out"]; axis = site["axis"]
    u = site["u"]; v = site["v"]; R = site["R"]
    if phase == PHASE_LASER:
        a = sweep * 2.0 * math.pi                  # текущий угол реза по контуру
        spot = _add(p0, _add(_mul(u, R * math.cos(a)), _mul(v, R * math.sin(a))))
        top = _add(spot, _mul(out, R * 4.0))
        return {"top": top, "tip": spot, "phase": phase, "sparks": []}
    top = _add(p0, _mul(out, R * 4.0))
    tip = _add(p0, _mul(axis, depth))
    sparks = []
    for i in range(6):
        a = 2.0 * math.pi * (i / 6.0) + depth * 7.0
        rr = R * (0.25 + 0.6 * ((i * 37) % 10) / 10.0)
        sp = _add(tip, _add(_mul(u, rr * math.cos(a)),
                            _mul(v, rr * math.sin(a))))
        sparks.append(_add(sp, _mul(out, R * 0.05)))
    return {"top": top, "tip": tip, "phase": phase, "sparks": sparks}


def phase_label(phase, depth, site, sweep=0.0):
    """Подпись для UI: фаза + Ø и прогресс/глубина."""
    d = site["R"] * 2.0
    if phase == PHASE_LASER:
        done = min(100.0, sweep / _LASER_LAPS * 100.0)
        return f"Лазер: обводка контура Ø{d:.1f} мм · {done:.0f} %"
    if phase == PHASE_EDM:
        return (f"Эрозия: прошивка Ø{d:.1f} мм · "
                f"глубина {depth:.1f}/{site['depth_full']:.1f} мм")
    return "—"
