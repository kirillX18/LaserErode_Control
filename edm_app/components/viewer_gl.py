"""
viewer_gl.py — аппаратный 3D-вьюпорт детали на координатном столе (OpenGL).

Зачем OpenGL, а не QPainter: реальные STL содержат сотни тысяч граней.
Программный растеризатор на QPainter их не тянет и, главное, без буфера
глубины («алгоритм художника») неправильно рисует сложную/вогнутую деталь —
поверхность рассыпается на треугольники. GPU с честным z-буфером рисует
деталь сплошной и плавно, без прорежения.

Подход — фиксированный конвейер совместимого профиля (есть везде на десктопе):
    * геометрия грузится в VBO один раз (interleaved N3F_V3F);
    * освещение GL_LIGHT0 + GL_COLOR_MATERIAL, двусторонняя подсветка;
    * ортографическая проекция, орбита/зум/панорама мышью;
    * z-буфер (GL_DEPTH_TEST) убирает любые артефакты перекрытия.

API совпадает с программным MeshViewer (load_file/clear/mesh_info/
set_head_marker), поэтому панель может использовать любой из них.
"""

from __future__ import annotations

import array
import math
import os

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import QOpenGLWidget, QSizePolicy

from .viewer3d import load_mesh   # переиспользуем парсеры STL/OBJ
from ..theme import Palette


class GLMeshViewer(QOpenGLWidget):
    """Аппаратный просмотр меша. Данные — через load_file()/set_mesh()."""

    _LIGHT = (-0.35, -0.45, 0.82)   # направленный свет (мировые коорд., Z вверх)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._name = ""
        self._center = (0.0, 0.0, 0.0)
        self._vc = (0.0, 0.0, 0.0)   # центр кадрирования (середина высоты детали)
        self._extent = 13.0
        self._size = (0.0, 0.0, 0.0)
        self._ntris = 0

        # буфер геометрии
        self._cpu = None            # array('f') до загрузки в GPU
        self._vbo = None            # id VBO
        self._nverts = 0
        self._dirty = False         # требуется (пере)загрузка в GPU

        # камера
        self._yaw = math.radians(35)
        self._pitch = math.radians(58)
        self._zoom = 1.0
        self._pan = [0.0, 0.0]      # в долях полувысоты вьюпорта
        self._last = None
        self._mode = None

        self._marker = None         # (x, y) — хук «варианта 2»
        self._toolpath = None       # список ломаных в мировых координатах
        self._head = None           # (x, y) головки над полем
        self._WORK = 100.0          # сторона рабочего поля в координатах сцены

        # машинная обработка (прошивка отверстия по ходу процесса)
        self._overlay = None        # (tris, cols) — геометрия лунки или None
        self._drill = None          # инструмент: dict {top, tip, phase, sparks}

    # ---- данные --------------------------------------------------------
    def load_file(self, path: str) -> None:
        self.set_mesh(load_mesh(path), os.path.basename(path))

    def set_mesh(self, tris: list, name: str = "", keep_view: bool = False) -> None:
        """keep_view=True — сохранить камеру (горячая подмена меша на карвленый
        во время процесса, ракурс на стенку не сбрасывается)."""
        self._toolpath = None
        self._head = None
        self._name = name
        self._ntris = len(tris)
        self._build_buffer(tris)
        self._recompute_bounds(tris)
        if not keep_view:
            self._reset_view()
        self._dirty = True
        self.update()

    def set_toolpath(self, segments, name: str = "") -> None:
        """Показать плоский контур (доли [0..1]) на рабочем поле станка."""
        w = self._WORK
        self._toolpath = [[((xf - 0.5) * w, (yf - 0.5) * w, 0.0)
                           for xf, yf in seg] for seg in segments]
        self._name = name
        self._ntris = 0
        self._cpu = None
        self._nverts = 0
        self._dirty = True
        self._center = (0.0, 0.0, 0.0)
        self._vc = (0.0, 0.0, 0.0)
        self._extent = (w / 2) / 0.9
        self._size = (w, w, 0.0)
        self._reset_view()
        self.update()

    def set_head_norm(self, xf: float, yf: float, on: bool) -> None:
        w = self._WORK
        self._head = ((xf - 0.5) * w, (yf - 0.5) * w) if on else None
        self.update()

    def clear(self) -> None:
        self._name = ""
        self._ntris = 0
        self._cpu = None
        self._nverts = 0
        self._dirty = True
        self._center = (0.0, 0.0, 0.0)
        self._vc = (0.0, 0.0, 0.0)
        self._extent = 13.0
        self._size = (0.0, 0.0, 0.0)
        self._marker = None
        self._toolpath = None
        self._head = None
        self._overlay = None
        self._drill = None
        self.update()

    def mesh_info(self) -> dict:
        return {"name": self._name, "tris": self._ntris, "size": self._size}

    def set_head_marker(self, x: float, y: float, on: bool) -> None:
        self._marker = (x, y) if on else None
        self.update()

    # ---- машинная обработка (прошивка отверстия) ----------------------
    def set_overlay(self, tris: list, cols: list) -> None:
        """Геометрия лунки: треугольники + цвет каждого (r,g,b в 0..1).
        Рисуется немедленным режимом поверх детали с честным z-буфером."""
        self._overlay = (tris or [], cols or []) if tris else None
        self.update()

    def clear_overlay(self) -> None:
        self._overlay = None
        self.update()

    def set_drill_tool(self, top, tip, phase: str, sparks=()) -> None:
        self._drill = {"top": top, "tip": tip,
                       "phase": phase, "sparks": list(sparks)}
        self.update()

    def clear_drill(self) -> None:
        self._drill = None
        self.update()

    def reset_view(self) -> None:
        self._reset_view()
        self.update()

    def aim_at_normal(self, nx: float, ny: float, nz: float) -> None:
        """Камера «лицом» к стенке с внешней нормалью (nx,ny,nz): для боковых
        стенок почти горизонтально (анфас), для верхней грани — сверху."""
        self._yaw = math.atan2(-nx, -ny) - math.radians(22)
        pitch_deg = 82.0 - 30.0 * min(1.0, abs(nz))
        self._pitch = max(0.05, min(math.pi - 0.05, math.radians(pitch_deg)))
        self._zoom = 1.3
        self._pan = [0.0, 0.0]
        self.update()

    # ---- подготовка геометрии -----------------------------------------
    def _build_buffer(self, tris: list) -> None:
        """Interleaved N3F_V3F: на каждую вершину нормаль грани + позиция."""
        data = array.array('f')
        ext = data.extend
        sqrt = math.sqrt
        for a, b, c in tris:
            ux = b[0] - a[0]; uy = b[1] - a[1]; uz = b[2] - a[2]
            vx = c[0] - a[0]; vy = c[1] - a[1]; vz = c[2] - a[2]
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            m = sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx /= m; ny /= m; nz /= m
            ext((nx, ny, nz, a[0], a[1], a[2],
                 nx, ny, nz, b[0], b[1], b[2],
                 nx, ny, nz, c[0], c[1], c[2]))
        self._cpu = data
        self._nverts = len(tris) * 3

    def _recompute_bounds(self, tris: list) -> None:
        if not tris:
            return
        xs = []; ys = []; zs = []
        for t in tris:
            for v in t:
                xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        zmin = min(zs)
        self._center = (cx, cy, zmin)         # дно детали = плоскость стола
        self._size = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        self._vc = (cx, cy, zmin + self._size[2] / 2.0)   # центр для кадрирования
        self._extent = max(self._size[0], self._size[1], self._size[2], 1e-6)

    def _reset_view(self) -> None:
        self._yaw = math.radians(35)
        self._pitch = math.radians(58)
        self._zoom = 1.0
        self._pan = [0.0, 0.0]

    # ---- OpenGL --------------------------------------------------------
    def initializeGL(self):
        from OpenGL.GL import (
            glClearColor, glEnable, glLightModeli, glShadeModel,
            GL_DEPTH_TEST, GL_LIGHTING, GL_LIGHT0, GL_COLOR_MATERIAL,
            GL_LIGHT_MODEL_TWO_SIDE, GL_NORMALIZE, GL_FLAT,
        )
        glClearColor(0.118, 0.129, 0.153, 1.0)   # #1e2127
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_NORMALIZE)
        glLightModeli(GL_LIGHT_MODEL_TWO_SIDE, 1)
        glShadeModel(GL_FLAT)

    def _upload(self):
        from OpenGL.GL import (
            glGenBuffers, glBindBuffer, glBufferData,
            GL_ARRAY_BUFFER, GL_STATIC_DRAW,
        )
        if self._vbo is None:
            self._vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        if self._cpu is not None and self._nverts:
            glBufferData(GL_ARRAY_BUFFER, self._cpu.tobytes(), GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        self._dirty = False

    def resizeGL(self, w, h):
        from OpenGL.GL import glViewport
        glViewport(0, 0, w, max(1, h))

    def paintGL(self):
        from OpenGL.GL import (
            glClear, glMatrixMode, glLoadIdentity, glOrtho, glRotatef,
            glTranslatef, glLightfv, glColor3f, glColorMaterial,
            glEnableClientState, glDisableClientState, glInterleavedArrays,
            glDrawArrays, glBindBuffer, glEnable, glDisable,
            GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_PROJECTION,
            GL_MODELVIEW, GL_LIGHT0, GL_POSITION, GL_FRONT_AND_BACK,
            GL_AMBIENT_AND_DIFFUSE, GL_VERTEX_ARRAY, GL_NORMAL_ARRAY,
            GL_N3F_V3F, GL_TRIANGLES, GL_ARRAY_BUFFER, GL_LIGHTING,
        )
        if self._dirty:
            self._upload()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # ── проекция: ортографическая, авто-фит по габаритам ──
        w = self.width() or 1
        h = self.height() or 1
        asp = w / h
        r = (self._extent * 0.65) / self._zoom
        px = self._pan[0] * r * asp
        py = self._pan[1] * r
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        far = self._extent * 20 + 10
        glOrtho(-r * asp - px, r * asp - px, -r - py, r - py, -far, far)

        # ── вид: орбита вокруг центра детали (Z — вверх) ──
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glRotatef(math.degrees(self._pitch) - 90.0, 1, 0, 0)  # наклон камеры
        glRotatef(math.degrees(self._yaw), 0, 0, 1)           # азимут вокруг Z
        glTranslatef(-self._vc[0], -self._vc[1], -self._vc[2])

        # свет привязан к сцене (направленный, w=0)
        lx, ly, lz = self._LIGHT
        glLightfv(GL_LIGHT0, GL_POSITION, (lx, ly, lz, 0.0))

        # ── деталь ──
        if self._nverts and self._vbo is not None:
            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            glColor3f(0.62, 0.70, 0.82)          # сталь/голубой
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
            glInterleavedArrays(GL_N3F_V3F, 0, None)
            glDrawArrays(GL_TRIANGLES, 0, self._nverts)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)

        # ── динамическая лунка (overlay) — освещается как деталь ──
        if self._overlay is not None:
            self._draw_overlay()

        # ── стол и оси рисуются без освещения ──
        glDisable(GL_LIGHTING)
        self._draw_grid()
        self._draw_axes()
        self._draw_marker()
        self._draw_toolpath()
        self._draw_head()
        self._draw_drill()
        glEnable(GL_LIGHTING)

    def _draw_overlay(self):
        """Стенки/дно/кольцо лунки немедленным режимом: на каждый треугольник
        своя нормаль (для затенения) и свой цвет материала."""
        from OpenGL.GL import (
            glColorMaterial, glColor3f, glNormal3f, glBegin, glEnd, glVertex3f,
            GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, GL_TRIANGLES,
        )
        tris, cols = self._overlay
        if not tris:
            return
        sqrt = math.sqrt
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glBegin(GL_TRIANGLES)
        for i in range(len(tris)):
            a, b, c = tris[i]
            ux = b[0] - a[0]; uy = b[1] - a[1]; uz = b[2] - a[2]
            vx = c[0] - a[0]; vy = c[1] - a[1]; vz = c[2] - a[2]
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            m = sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            col = cols[i] if i < len(cols) else (0.7, 0.7, 0.75)
            glColor3f(col[0], col[1], col[2])
            glNormal3f(nx / m, ny / m, nz / m)
            glVertex3f(a[0], a[1], a[2])
            glVertex3f(b[0], b[1], b[2])
            glVertex3f(c[0], c[1], c[2])
        glEnd()

    def _draw_drill(self):
        """Луч лазера / электрод с искрами. Без z-теста — всегда поверх,
        «входит» в открытое устье отверстия."""
        d = self._drill
        if not d:
            return
        from OpenGL.GL import (
            glColor3f, glLineWidth, glPointSize, glBegin, glEnd, glVertex3f,
            glEnable, glDisable, GL_LINES, GL_POINTS, GL_DEPTH_TEST,
        )
        top = d["top"]; tip = d["tip"]
        if d["phase"] == "laser":
            beam = (1.0, 0.31, 0.22); spot = (1.0, 0.92, 0.75)
        else:
            beam = (0.47, 0.80, 1.0); spot = (0.92, 0.96, 1.0)
        glDisable(GL_DEPTH_TEST)
        glColor3f(*beam); glLineWidth(2.6)
        glBegin(GL_LINES)
        glVertex3f(top[0], top[1], top[2])
        glVertex3f(tip[0], tip[1], tip[2])
        glEnd()
        glLineWidth(1.0)
        # пятно контакта
        glColor3f(*spot); glPointSize(9.0)
        glBegin(GL_POINTS); glVertex3f(tip[0], tip[1], tip[2]); glEnd()
        # искры
        sparks = d.get("sparks") or []
        if sparks:
            glColor3f(1.0, 0.84, 0.51); glPointSize(4.0)
            glBegin(GL_POINTS)
            for s in sparks:
                glVertex3f(s[0], s[1], s[2])
            glEnd()
        glPointSize(1.0)
        glEnable(GL_DEPTH_TEST)

    def _draw_grid(self):
        from OpenGL.GL import glColor3f, glBegin, glEnd, glVertex3f, GL_LINES
        half = self._extent * 0.9 if (self._nverts or self._toolpath) else 6.0
        z = self._center[2]
        step = (half * 2) / 10.0
        cx, cy = self._center[0], self._center[1]
        glColor3f(0.35, 0.39, 0.45)
        glBegin(GL_LINES)
        i = -half
        while i <= half + 1e-6:
            glVertex3f(cx + i, cy - half, z); glVertex3f(cx + i, cy + half, z)
            glVertex3f(cx - half, cy + i, z); glVertex3f(cx + half, cy + i, z)
            i += step
        glEnd()

    def _draw_axes(self):
        from OpenGL.GL import glColor3f, glBegin, glEnd, glVertex3f, glLineWidth, GL_LINES
        has_content = bool(self._nverts or self._toolpath)
        half = self._extent * 0.9 if has_content else 6.0
        L = (self._extent if has_content else 6.0) * 0.55
        # Начало координат — в ближнем углу стола (деталь остаётся в центре).
        ox = self._center[0] - half
        oy = self._center[1] - half
        oz = self._center[2]
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glColor3f(0.89, 0.33, 0.33); glVertex3f(ox, oy, oz); glVertex3f(ox + L, oy, oz)
        glColor3f(0.33, 0.80, 0.33); glVertex3f(ox, oy, oz); glVertex3f(ox, oy + L, oz)
        glColor3f(0.33, 0.60, 0.93); glVertex3f(ox, oy, oz); glVertex3f(ox, oy, oz + L)
        glEnd()
        glLineWidth(1.0)

    def _draw_toolpath(self):
        if not self._toolpath:
            return
        from OpenGL.GL import (glColor3f, glLineWidth, glBegin, glEnd,
                               glVertex3f, GL_LINE_STRIP)
        glColor3f(0.21, 0.76, 1.0)
        glLineWidth(2.0)
        for seg in self._toolpath:
            glBegin(GL_LINE_STRIP)
            for x, y, z in seg:
                glVertex3f(x, y, z)
            glEnd()
        glLineWidth(1.0)

    def _draw_head(self):
        if self._head is None:
            return
        from OpenGL.GL import (glColor3f, glLineWidth, glBegin, glEnd,
                               glVertex3f, glPointSize, GL_LINES, GL_POINTS)
        hx, hy = self._head
        hz = self._WORK * 0.12
        glColor3f(1.0, 0.27, 0.27); glLineWidth(2.0)
        glBegin(GL_LINES); glVertex3f(hx, hy, hz); glVertex3f(hx, hy, 0.0); glEnd()
        glLineWidth(1.0)
        glColor3f(0.82, 0.85, 0.90); glPointSize(10.0)
        glBegin(GL_POINTS); glVertex3f(hx, hy, hz); glEnd()
        glPointSize(1.0)

    def _draw_marker(self):
        if self._marker is None:
            return
        from OpenGL.GL import glColor3f, glPointSize, glBegin, glEnd, glVertex3f, GL_POINTS
        mx, my = self._marker
        top = self._center[2] + self._size[2] + self._extent * 0.06
        glColor3f(0.84, 0.13, 0.13)
        glPointSize(8.0)
        glBegin(GL_POINTS)
        glVertex3f(mx, my, top)
        glEnd()
        glPointSize(1.0)

    # ---- мышь ----------------------------------------------------------
    def mousePressEvent(self, e):
        self._last = e.pos()
        if e.button() == Qt.LeftButton:
            self._mode = "orbit"
        elif e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._mode = "pan"

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
            self._pan[0] += d.x() * 2.0 / max(1, self.height())
            self._pan[1] -= d.y() * 2.0 / max(1, self.height())
        self.update()

    def mouseReleaseEvent(self, e):
        self._last = None
        self._mode = None

    def wheelEvent(self, e):
        self._zoom *= 1.0015 ** e.angleDelta().y()
        self._zoom = max(0.15, min(40.0, self._zoom))
        self.update()

    def mouseDoubleClickEvent(self, e):
        self._reset_view()
        self.update()
