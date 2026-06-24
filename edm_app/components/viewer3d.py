"""
viewer3d.py — программный 3D-вьюпорт детали на координатном столе.

Зачем «свой» рендер, а не OpenGL: всё приложение держится на одном PyQt5
(см. requirements.txt) и запускается батником на Windows. Чтобы не тащить
PyOpenGL/numpy ради одного окна, 3D рисуется средствами QPainter:

    * парсер STL (binary + ASCII) и OBJ — чистый Python (struct);
    * камера-орбита (поворот ЛКМ, зум колесом, панорама СКМ/ПКМ);
    * ось Z — вверх, плоскость XY — стол; деталь «ставится» на стол;
    * плоское затенение (face normal · направление света);
    * сортировка граней по глубине (алгоритм художника) + отсечение задних.

Это не CAD-движок: для деталей демонстрационного размера (до ~30 тыс.
треугольников) скорость приемлема. Очень крупные сетки прорежаются.

Публичный API:
    view = MeshViewer()
    view.load_file(path)   # .stl / .obj — бросает ValueError при ошибке
    view.clear()           # вернуть пустую сцену (только стол)
    view.mesh_info()       # dict: name, tris, size — для подписи в UI

Хук под «вариант 2» (привязка к процессу): метод set_head_marker(x, y, on)
уже есть — достаточно вызывать его из страницы по stateChanged.
"""

from __future__ import annotations

import math
import os
import struct

from PyQt5.QtCore import Qt, QPointF, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont
from PyQt5.QtWidgets import QWidget, QSizePolicy

from ..theme import Palette

# Потолок треугольников для статичного («чёткого») кадра: выше — равномерно
# прореживаем. Для предпросмотра формы детали этого достаточно, а QPainter
# не «ложится» на одном кадре.
_MAX_TRIS = 15000
# Сколько граней рисуем во время вращения/зума (LOD). Гарантирует плавность
# независимо от размера исходного STL; полная детализация — когда мышь отпущена.
# ~4500 граней держат ~30 кадр/с в софт-рендере и читаются как сплошная деталь.
_FAST_TRIS = 4500


# ───────────────────────── парсеры геометрии ──────────────────────────

def _parse_stl(path: str) -> list[tuple[tuple, tuple, tuple]]:
    """Читает STL (binary или ASCII). Возвращает список треугольников,
    каждый — кортеж из трёх вершин (x, y, z)."""
    with open(path, "rb") as f:
        head = f.read(5)
        f.seek(0)
        data = f.read()

    is_ascii = head[:5].lower() == b"solid"
    # У binary-STL заголовок тоже может начинаться со «solid»; проверяем по
    # длине файла относительно объявленного числа треугольников.
    if is_ascii and len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + n * 50 == len(data):
            is_ascii = False

    if is_ascii:
        return _parse_stl_ascii(data.decode("ascii", "replace"))
    return _parse_stl_binary(data)


def _parse_stl_binary(data: bytes) -> list:
    if len(data) < 84:
        raise ValueError("STL: файл слишком короткий")
    n = struct.unpack_from("<I", data, 80)[0]
    tris = []
    off = 84
    for _ in range(n):
        if off + 50 > len(data):
            break
        # 12 float: нормаль(3) + v1(3) + v2(3) + v3(3); затем 2 байта атрибут
        vals = struct.unpack_from("<12f", data, off)
        v1 = (vals[3], vals[4], vals[5])
        v2 = (vals[6], vals[7], vals[8])
        v3 = (vals[9], vals[10], vals[11])
        tris.append((v1, v2, v3))
        off += 50
    if not tris:
        raise ValueError("STL: не найдено ни одного треугольника")
    return tris


def _parse_stl_ascii(text: str) -> list:
    tris, verts = [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("vertex"):
            p = s.split()
            verts.append((float(p[1]), float(p[2]), float(p[3])))
            if len(verts) == 3:
                tris.append((verts[0], verts[1], verts[2]))
                verts = []
    if not tris:
        raise ValueError("STL(ASCII): не найдено вершин")
    return tris


def _parse_obj(path: str) -> list:
    """Минимальный парсер OBJ: вершины v + грани f (полигоны триангулируются
    веером). Индексы, текстуры и нормали в f игнорируются, кроме номера v."""
    verts, tris = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("v "):
                p = s.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif s.startswith("f "):
                idx = []
                for tok in s.split()[1:]:
                    vi = tok.split("/")[0]
                    if vi:
                        i = int(vi)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):  # веер
                    tris.append((verts[idx[0]], verts[idx[k]], verts[idx[k + 1]]))
    if not tris:
        raise ValueError("OBJ: не найдено граней")
    return tris


def load_mesh(path: str) -> list:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".stl":
        return _parse_stl(path)
    if ext == ".obj":
        return _parse_obj(path)
    raise ValueError(f"Формат {ext} не поддерживается вьюпортом (нужен STL/OBJ)")


# ───────────────────────── мелкая 3D-математика ───────────────────────

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(v):
    m = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / m, v[1] / m, v[2] / m)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# ───────────────────────────── виджет ─────────────────────────────────

class MeshViewer(QWidget):
    """Виджет программного 3D-просмотра. Самодостаточен: данные кладутся
    через load_file()/set_mesh(), всё остальное он делает сам."""

    # Свет: сверху-спереди-сбоку (в мировых координатах, Z — вверх).
    _LIGHT = _norm((-0.35, -0.45, 0.82))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(False)
        self.setAutoFillBackground(True)

        self._tris: list = []          # треугольники в исходных координатах
        self._fast: list = []          # прорежённый набор для интерактива (LOD)
        self._name = ""
        self._center = (0.0, 0.0, 0.0)  # центр габаритов по XY, дно по Z
        self._extent = 13.0            # максимальный габарит (для авто-масштаба)
        self._size = (0.0, 0.0, 0.0)   # габариты dx, dy, dz

        # камера-орбита
        self._yaw = math.radians(35)
        self._pitch = math.radians(58)
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._last = None
        self._mode = None

        # интерактив: во время вращения/зума показываем LOD без сглаживания,
        # после паузы возвращаем полную детализацию (чёткий кадр).
        self._interacting = False
        self._lod_timer = QTimer(self)
        self._lod_timer.setSingleShot(True)
        self._lod_timer.setInterval(180)
        self._lod_timer.timeout.connect(self._end_interaction)

        # кэш тригонометрии и масштаба (заполняется раз на кадр)
        self._tf = None

        # хук под «вариант 2»: маркер головки на столе
        self._marker = None            # (x, y) в координатах меша или None

        # машинная обработка (прошивка отверстия по ходу процесса):
        #   _overlay_tris/_cols — динамическая геометрия лунки (стенки/дно/кольцо)
        #   _drill — инструмент над устьем: dict {top, tip, phase, sparks}
        self._overlay_tris: list = []
        self._overlay_cols: list = []
        self._drill = None

        # программа обработки (контур) и положение головки над полем:
        #   _toolpath — список ломаных в мировых координатах (доли → поле);
        #   _head     — текущее положение головки (мировые X, Y) или None.
        self._toolpath = None
        self._head = None
        self._WORK = 100.0             # сторона рабочего поля в координатах сцены

    # ---- данные --------------------------------------------------------
    def load_file(self, path: str) -> None:
        self.set_mesh(load_mesh(path), os.path.basename(path))

    def set_mesh(self, tris: list, name: str = "", keep_view: bool = False) -> None:
        """keep_view=True — не сбрасывать камеру (для «горячей» подмены меша
        на карвленый во время процесса: ракурс на стенку сохраняется)."""
        self._toolpath = None
        self._head = None
        if len(tris) > _MAX_TRIS:                       # равномерное прореживание
            step = math.ceil(len(tris) / _MAX_TRIS)
            tris = tris[::step]
        self._tris = tris
        # прорежённый набор для плавного вращения больших моделей
        if len(tris) > _FAST_TRIS:
            step = math.ceil(len(tris) / _FAST_TRIS)
            self._fast = tris[::step]
        else:
            self._fast = tris
        self._name = name
        self._recompute_bounds()
        if not keep_view:
            self._reset_view()
        self.update()

    def set_toolpath(self, segments, name: str = "") -> None:
        """Показать плоскую программу обработки (контур) на рабочем поле.

        segments — список ломаных с точками (xf, yf) в долях [0..1] поля.
        Сцена кадрируется под рабочее поле; меш сбрасывается.
        """
        self._tris = []
        self._fast = []
        w = self._WORK
        self._toolpath = [[((xf - 0.5) * w, (yf - 0.5) * w, 0.0)
                           for xf, yf in seg] for seg in segments]
        self._name = name
        self._center = (0.0, 0.0, 0.0)
        self._extent = (w / 2) / 0.9     # так половина сетки = w/2 (точно по полю)
        self._size = (w, w, 0.0)
        self._reset_view()
        self.update()

    def set_head_norm(self, xf: float, yf: float, on: bool) -> None:
        """Положение головки над полем в долях [0..1] (для анимации процесса)."""
        w = self._WORK
        self._head = ((xf - 0.5) * w, (yf - 0.5) * w) if on else None
        self.update()

    def clear(self) -> None:
        self._tris = []
        self._fast = []
        self._name = ""
        self._center = (0.0, 0.0, 0.0)
        self._extent = 13.0
        self._size = (0.0, 0.0, 0.0)
        self._marker = None
        self._toolpath = None
        self._head = None
        self._overlay_tris = []
        self._overlay_cols = []
        self._drill = None
        self.update()

    def mesh_info(self) -> dict:
        return {"name": self._name, "tris": len(self._tris), "size": self._size}

    def set_head_marker(self, x: float, y: float, on: bool) -> None:
        """Хук «варианта 2»: положение головки над столом (в коорд. меша)."""
        self._marker = (x, y) if on else None
        self.update()

    # ---- машинная обработка (прошивка отверстия) ----------------------
    def set_overlay(self, tris: list, cols: list) -> None:
        """Динамическая геометрия лунки: треугольники + цвет каждого (r,g,b
        в 0..1). Рисуется поверх детали с той же сортировкой по глубине."""
        self._overlay_tris = tris or []
        self._overlay_cols = cols or []
        self.update()

    def clear_overlay(self) -> None:
        self._overlay_tris = []
        self._overlay_cols = []
        self.update()

    def set_drill_tool(self, top, tip, phase: str, sparks=()) -> None:
        """Инструмент над устьем: top/tip — мировые точки луча (лазер) или
        электрода (эрозия); sparks — точки искр у дна."""
        self._drill = {"top": top, "tip": tip,
                       "phase": phase, "sparks": list(sparks)}
        self.update()

    def clear_drill(self) -> None:
        self._drill = None
        self.update()

    def reset_view(self) -> None:
        """Публичный сброс камеры (для возврата ракурса после процесса)."""
        self._reset_view()
        self.update()

    def aim_at_normal(self, nx: float, ny: float, nz: float) -> None:
        """Развернуть камеру «лицом» к стенке с внешней нормалью (nx,ny,nz)
        — чтобы устье отверстия смотрело на зрителя. Для вертикальных стенок
        камера почти горизонтальна (стенка видна анфас), для верхней грани —
        наклонена сверху. Лёгкий доворот по азимуту даёт объём лунке."""
        self._yaw = math.atan2(-nx, -ny) - math.radians(22)
        pitch_deg = 82.0 - 30.0 * min(1.0, abs(nz))
        self._pitch = max(0.05, min(math.pi - 0.05, math.radians(pitch_deg)))
        self._zoom = 1.3
        self._pan = QPointF(0, 0)
        self.update()

    # ---- геометрия сцены ----------------------------------------------
    def _recompute_bounds(self) -> None:
        xs, ys, zs = [], [], []
        for t in self._tris:
            for v in t:
                xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
        if not xs:
            return
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        zmin = min(zs)
        self._center = (cx, cy, zmin)              # дно детали = плоскость стола
        self._size = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        self._extent = max(self._size[0], self._size[1], self._size[2], 1e-6)

    def _reset_view(self) -> None:
        self._yaw = math.radians(35)
        self._pitch = math.radians(58)
        self._zoom = 1.0
        self._pan = QPointF(0, 0)

    # ---- камера: подготовка трансформа раз на кадр --------------------
    def _prepare_transform(self) -> None:
        """Считает cos/sin поворота и масштаб ОДИН раз за paintEvent.
        Раньше это считалось на каждую вершину — главный источник лагов."""
        w, h = self.width(), self.height()
        self._tf = {
            "cy": math.cos(self._yaw), "sy": math.sin(self._yaw),
            "cp": math.cos(self._pitch), "sp": math.sin(self._pitch),
            "scale": (min(w, h) * 0.62 / self._extent) * self._zoom,
            "ox": w / 2 + self._pan.x(), "oy": h / 2 + self._pan.y(),
            "cx": self._center[0], "cyc": self._center[1], "cz": self._center[2],
        }

    def _project(self, p):
        """world -> (экранная точка, глубина). Использует кэш self._tf."""
        tf = self._tf
        x = p[0] - tf["cx"]; y = p[1] - tf["cyc"]; z = p[2] - tf["cz"]
        x1 = x * tf["cy"] - y * tf["sy"]
        y1 = x * tf["sy"] + y * tf["cy"]
        y2 = y1 * tf["cp"] - z * tf["sp"]
        z2 = y1 * tf["sp"] + z * tf["cp"]
        return QPointF(tf["ox"] + x1 * tf["scale"],
                       tf["oy"] - z2 * tf["scale"]), y2

    # ---- мышь ----------------------------------------------------------
    def mousePressEvent(self, e):
        self._last = e.pos()
        if e.button() == Qt.LeftButton:
            self._mode = "orbit"
            self._interacting = True
        elif e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._mode = "pan"
            self._interacting = True

    def mouseMoveEvent(self, e):
        if self._last is None:
            return
        d = e.pos() - self._last
        self._last = e.pos()
        if self._mode == "orbit":
            self._yaw += d.x() * 0.01
            self._pitch += d.y() * 0.01
            self._pitch = max(0.05, min(math.pi - 0.05, self._pitch))
        elif self._mode == "pan":
            self._pan += QPointF(d.x(), d.y())
        self.update()

    def mouseReleaseEvent(self, e):
        self._last = None
        self._mode = None
        self._end_interaction()           # вернуть полную детализацию

    def wheelEvent(self, e):
        self._zoom *= 1.0015 ** e.angleDelta().y()
        self._zoom = max(0.15, min(12.0, self._zoom))
        self._interacting = True          # на время зума — LOD
        self._lod_timer.start()           # вернуть чёткий кадр после паузы
        self.update()

    def mouseDoubleClickEvent(self, e):
        self._reset_view()
        self.update()

    def _end_interaction(self) -> None:
        self._lod_timer.stop()
        if self._interacting:
            self._interacting = False
            self.update()

    # ---- отрисовка -----------------------------------------------------
    def paintEvent(self, _):
        qp = QPainter(self)
        # сглаживание только для статичного кадра: при вращении оно даёт
        # основную просадку. Во время интерактива — без AA.
        qp.setRenderHint(QPainter.Antialiasing, not self._interacting)
        qp.fillRect(self.rect(), QColor("#1e2127"))   # тёмный фон вьюпорта

        self._prepare_transform()
        self._draw_table_grid(qp)
        if self._tris:
            self._draw_mesh(qp)
            self._draw_marker(qp)
            self._draw_drill(qp)
        elif self._toolpath is not None:
            self._draw_toolpath(qp)
            self._draw_head(qp)
        else:
            self._draw_hint(qp)
        self._draw_axes(qp)
        qp.end()

    def _draw_table_grid(self, qp: QPainter) -> None:
        """Сетка координатного стола в плоскости XY (z = низ детали)."""
        half = self._extent * 0.9 if (self._tris or self._toolpath is not None) else 6.0
        z0 = 0.0
        step = (half * 2) / 10.0
        pen = QPen(QColor(90, 100, 115), 1)
        qp.setPen(pen)
        i = -half
        while i <= half + 1e-6:
            a, _ = self._project((self._center[0] + i, self._center[1] - half, self._center[2] + z0))
            b, _ = self._project((self._center[0] + i, self._center[1] + half, self._center[2] + z0))
            qp.drawLine(a, b)
            c, _ = self._project((self._center[0] - half, self._center[1] + i, self._center[2] + z0))
            d, _ = self._project((self._center[0] + half, self._center[1] + i, self._center[2] + z0))
            qp.drawLine(c, d)
            i += step
        # рамка стола ярче
        qp.setPen(QPen(QColor(120, 135, 155), 2))
        corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
        poly = QPolygonF([self._project(
            (self._center[0] + cx, self._center[1] + cy, self._center[2]))[0]
            for cx, cy in corners])
        qp.drawPolygon(poly)

    def _draw_mesh(self, qp: QPainter) -> None:
        # во время вращения/зума — прорежённый набор (плавность);
        # в статике — полный (чёткость).
        tris = self._fast if self._interacting else self._tris

        tf = self._tf
        c_y, s_y, c_p, s_p = tf["cy"], tf["sy"], tf["cp"], tf["sp"]
        scale, ox, oy = tf["scale"], tf["ox"], tf["oy"]
        cx0, cy0, cz0 = tf["cx"], tf["cyc"], tf["cz"]
        lx, ly, lz = self._LIGHT
        sqrt = math.sqrt

        faces = []
        for t in tris:
            a, b, c = t
            # --- нормаль грани (для затенения и отсечения задних) ---
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            nm = sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx /= nm; ny /= nm; nz /= nm

            # --- проекция трёх вершин (инлайн, без вызовов/QPointF в цикле) ---
            ax, ay, az = a[0] - cx0, a[1] - cy0, a[2] - cz0
            bx, by, bz = b[0] - cx0, b[1] - cy0, b[2] - cz0
            cx_, cy_, cz_ = c[0] - cx0, c[1] - cy0, c[2] - cz0

            ax1 = ax * c_y - ay * s_y; ay1 = ax * s_y + ay * c_y
            bx1 = bx * c_y - by * s_y; by1 = bx * s_y + by * c_y
            cx1 = cx_ * c_y - cy_ * s_y; cy1 = cx_ * s_y + cy_ * c_y

            ad = ay1 * c_p - az * s_p; az2 = ay1 * s_p + az * c_p
            bd = by1 * c_p - bz * s_p; bz2 = by1 * s_p + bz * c_p
            cd = cy1 * c_p - cz_ * s_p; cz2 = cy1 * s_p + cz_ * c_p

            sax = ox + ax1 * scale; say = oy - az2 * scale
            sbx = ox + bx1 * scale; sby = oy - bz2 * scale
            scx = ox + cx1 * scale; scy = oy - cz2 * scale

            depth = (ad + bd + cd)        # без /3 — для сортировки не важно
            shade = abs(nx * lx + ny * ly + nz * lz)
            faces.append((depth, shade, sax, say, sbx, sby, scx, scy, None))

        # --- динамическая геометрия лунки (overlay) с собственными цветами ---
        # набор маленький (~300 граней), считаем всегда полностью; сортируется
        # вместе с деталью по той же глубине (единый алгоритм художника).
        ov = self._overlay_tris
        if ov:
            ocols = self._overlay_cols
            for ti in range(len(ov)):
                a, b, c = ov[ti]
                ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
                nx = uy * vz - uz * vy
                ny = uz * vx - ux * vz
                nz = ux * vy - uy * vx
                nm = sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                nx /= nm; ny /= nm; nz /= nm

                ax, ay, az = a[0] - cx0, a[1] - cy0, a[2] - cz0
                bx, by, bz = b[0] - cx0, b[1] - cy0, b[2] - cz0
                cx_, cy_, cz_ = c[0] - cx0, c[1] - cy0, c[2] - cz0

                ax1 = ax * c_y - ay * s_y; ay1 = ax * s_y + ay * c_y
                bx1 = bx * c_y - by * s_y; by1 = bx * s_y + by * c_y
                cx1 = cx_ * c_y - cy_ * s_y; cy1 = cx_ * s_y + cy_ * c_y

                ad = ay1 * c_p - az * s_p; az2 = ay1 * s_p + az * c_p
                bd = by1 * c_p - bz * s_p; bz2 = by1 * s_p + bz * c_p
                cd = cy1 * c_p - cz_ * s_p; cz2 = cy1 * s_p + cz_ * c_p

                sax = ox + ax1 * scale; say = oy - az2 * scale
                sbx = ox + bx1 * scale; sby = oy - bz2 * scale
                scx = ox + cx1 * scale; scy = oy - cz2 * scale

                depth = (ad + bd + cd)
                shade = abs(nx * lx + ny * ly + nz * lz)
                col = ocols[ti] if ti < len(ocols) else (0.7, 0.7, 0.75)
                # лёгкий «подъём» к зрителю, чтобы лунка не конкурировала по
                # глубине со стенкой детали на одном уровне (без z-буфера).
                faces.append((depth - self._extent * 0.012, shade,
                              sax, say, sbx, sby, scx, scy, col))

        # алгоритм художника: дальние (большая глубина) — первыми
        faces.sort(key=lambda f: f[0], reverse=True)

        edge = self._interacting        # при интерактиве не рисуем контур граней
        for f in faces:
            shade = f[1]
            sax, say, sbx, sby, scx, scy = f[2], f[3], f[4], f[5], f[6], f[7]
            col = f[8]
            if col is None:                    # сталь детали — штатное затенение
                k = 0.30 + 0.70 * shade
                qc = QColor(int(70 + 150 * k), int(95 + 150 * k),
                            int(120 + 135 * k))
                qp.setBrush(qc)
                qp.setPen(Qt.NoPen if edge else QPen(qc.darker(140), 1))
            else:                              # материал лунки — заданный цвет
                k = 0.55 + 0.45 * shade
                qc = QColor(max(0, min(255, int(col[0] * 255 * k))),
                            max(0, min(255, int(col[1] * 255 * k))),
                            max(0, min(255, int(col[2] * 255 * k))))
                qp.setBrush(qc)
                qp.setPen(Qt.NoPen)
            qp.drawPolygon(QPolygonF([QPointF(sax, say), QPointF(sbx, sby),
                                      QPointF(scx, scy)]))

    def _draw_drill(self, qp: QPainter) -> None:
        """Инструмент в устье: луч лазера (фаза 1) или электрод с искрами
        (фаза 2). Рисуется поверх детали — «входит» в открытое устье."""
        d = self._drill
        if not d:
            return
        top, _ = self._project(d["top"])
        tip, _ = self._project(d["tip"])
        if d["phase"] == "laser":
            beam = QColor(255, 80, 55)
            glow = QColor(255, 120, 60, 140)
            core = QColor(255, 235, 190)
        else:
            beam = QColor(120, 205, 255)
            glow = QColor(150, 220, 255, 130)
            core = QColor(235, 245, 255)
        # луч/электрод
        qp.setPen(QPen(beam, 2.6))
        qp.drawLine(top, tip)
        # ореол и ядро пятна контакта на дне
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(glow))
        qp.drawEllipse(tip, 8, 8)
        qp.setBrush(QBrush(core))
        qp.drawEllipse(tip, 3, 3)
        # искры (только эрозия)
        sparks = d.get("sparks") or []
        if sparks:
            qp.setBrush(QBrush(QColor(255, 215, 130)))
            for s in sparks:
                p, _ = self._project(s)
                qp.drawEllipse(p, 1.7, 1.7)

    def _draw_marker(self, qp: QPainter) -> None:
        if self._marker is None:
            return
        mx, my = self._marker
        top = self._center[2] + self._size[2] + self._extent * 0.06
        p, _ = self._project((mx, my, top))
        qp.setPen(QPen(QColor(Palette.RED), 2))
        qp.setBrush(QBrush(QColor(Palette.RED)))
        qp.drawEllipse(p, 5, 5)

    def _draw_axes(self, qp: QPainter) -> None:
        has_content = bool(self._tris) or self._toolpath is not None
        half = self._extent * 0.9 if has_content else 6.0
        L = (self._extent if has_content else 6.0) * 0.55
        # Начало координат выносим в ближний угол стола, а не в центр:
        # деталь по-прежнему загружается по середине, оси ей не мешают.
        o = (self._center[0] - half, self._center[1] - half, self._center[2])
        origin, _ = self._project(o)
        axes = [((o[0] + L, o[1], o[2]), QColor("#e25555"), "X"),
                ((o[0], o[1] + L, o[2]), QColor("#55cc55"), "Y"),
                ((o[0], o[1], o[2] + L), QColor("#5599ee"), "Z")]
        f = QFont("Sans Serif", 8, QFont.Bold)
        qp.setFont(f)
        for tip, col, name in axes:
            p, _ = self._project(tip)
            qp.setPen(QPen(col, 2))
            qp.drawLine(origin, p)
            qp.drawText(p + QPointF(3, 3), name)

    def _draw_toolpath(self, qp: QPainter) -> None:
        """Контур программы обработки на плоскости стола (z = 0)."""
        qp.setPen(QPen(QColor("#36c2ff"), 2))
        qp.setBrush(Qt.NoBrush)
        for seg in self._toolpath:
            if len(seg) >= 2:
                qp.drawPolyline(QPolygonF([self._project(v)[0] for v in seg]))
            elif seg:
                p, _ = self._project(seg[0])
                qp.drawEllipse(p, 2, 2)

    def _draw_head(self, qp: QPainter) -> None:
        """Головка над полем + «опускной» луч до точки реза на столе."""
        if self._head is None:
            return
        hx, hy = self._head
        hz = self._WORK * 0.12                     # высота головки над столом
        head, _ = self._project((hx, hy, hz))
        foot, _ = self._project((hx, hy, 0.0))

        beam = QColor(255, 70, 70)
        qp.setPen(QPen(beam, 2, Qt.DashLine))
        qp.drawLine(head, foot)
        qp.setPen(QPen(beam, 1))
        qp.setBrush(QBrush(QColor(255, 70, 70, 90)))
        qp.drawEllipse(foot, 6, 3)

        size = 7
        diamond = QPolygonF([
            head + QPointF(0, -size), head + QPointF(size, 0),
            head + QPointF(0, size), head + QPointF(-size, 0)])
        qp.setPen(QPen(QColor("#202428"), 1))
        qp.setBrush(QBrush(QColor("#d0d8e6")))
        qp.drawPolygon(diamond)

    def _draw_hint(self, qp: QPainter) -> None:
        qp.setPen(QColor(170, 180, 195))
        qp.setFont(QFont("Sans Serif", 11))
        qp.drawText(self.rect(), Qt.AlignCenter,
                    "Программа обработки не загружена\n"
                    "Выберите контур (DXF/SVG/PLT/HPGL) или модель (STL/OBJ)")
