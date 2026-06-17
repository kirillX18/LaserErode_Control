"""
positioning_tab.py — вкладка «Позиционирование».

Заменяет прежние вкладки «Шаговый привод» и «Координатный стол»: объединяет
управление положением лазерной головки в один пульт.

    слева  — задание положения по X / Y / Z и текущие координаты;
    справа — 3D-визуализация положения головки и луча над столом.

Соответствие осей узлам устройства из заглушек:
    X, Z — лазерная головка шагового привода (move_to: горизонталь X и высота Z,
            диапазон каждой оси из snapshot["motor"]);
    Y     — подача заготовки координатным столом (move_table, snapshot["table"]).

Все действия идут через DeviceController; перемещение до инициализации и во
время процесса блокируется логикой стабов, результат виден в строке снизу.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QWidget, QSplitter, QGroupBox, QGridLayout, QHBoxLayout,
    QLabel, QSpinBox,
)
from PyQt5.QtCore import Qt

from ..base import BaseServiceTab
from ..components import (
    PrimaryButton, GrayButton, StepControl, MetricRow, MeterBar,
    LastMessageBar, PositionView,
)
from ..hardware import controller


class PositioningTab(BaseServiceTab):
    JOG_STEPS = (1, 10, 100)

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()

        splitter = QSplitter(Qt.Horizontal)

        # ── левая колонка: задание положения ──
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(self._build_position_box())
        lv.addWidget(self._build_speed_box())
        lv.addLayout(self._build_buttons())
        lv.addStretch()
        self.status_line = LastMessageBar()
        lv.addWidget(self.status_line)

        # ── правая колонка: 3D над столом ──
        right = QWidget()
        rv = QVBoxLayout(right)
        view_box = QGroupBox("Положение лазера над столом (3D)")
        vb = QVBoxLayout(view_box)
        self.view = PositionView()
        self.view.setToolTip(
            "Вращение — перетаскивание мышью · Зум — колесо · "
            "Двойной клик — сброс ракурса")
        vb.addWidget(self.view)
        rv.addWidget(view_box)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([480, 560])
        layout.addWidget(splitter)

        # сигналы
        self.move_btn.clicked.connect(self._move_all)
        self.reset_btn.clicked.connect(self._reset_all)
        self.stop_btn.clicked.connect(self._stop_all)
        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    # ---- построение блоков --------------------------------------------
    def _build_position_box(self) -> QGroupBox:
        box = QGroupBox("Положение лазера (X / Z — головка, Y — стол)")
        g = QGridLayout(box)

        # текущие координаты + шкалы
        self.x_row = MetricRow("Текущая X:", "0"); g.addWidget(self.x_row, 0, 0, 1, 3)
        self.x_bar = MeterBar("ok");               g.addWidget(self.x_bar, 1, 0, 1, 3)
        self.y_row = MetricRow("Текущая Y:", "0"); g.addWidget(self.y_row, 2, 0, 1, 3)
        self.y_bar = MeterBar("ok");               g.addWidget(self.y_bar, 3, 0, 1, 3)
        self.z_row = MetricRow("Текущая Z:", "0"); g.addWidget(self.z_row, 4, 0, 1, 3)
        self.z_bar = MeterBar("ok");               g.addWidget(self.z_bar, 5, 0, 1, 3)

        # задание целевой точки
        g.addWidget(QLabel("Задать X:"), 6, 0)
        self.target_x = QSpinBox(); self.target_x.setRange(0, 1000)
        g.addWidget(self.target_x, 6, 1)
        g.addWidget(QLabel("Задать Y:"), 7, 0)
        self.target_y = QSpinBox(); self.target_y.setRange(0, 500)
        g.addWidget(self.target_y, 7, 1)
        g.addWidget(QLabel("Задать Z:"), 8, 0)
        self.target_z = QSpinBox(); self.target_z.setRange(0, 1000)
        g.addWidget(self.target_z, 8, 1)
        self.move_btn = PrimaryButton("Переместить")
        g.addWidget(self.move_btn, 6, 2, 3, 1)

        # толчки по осям
        g.addWidget(QLabel("Толчком X:"), 9, 0)
        g.addWidget(StepControl(self.JOG_STEPS, self._jog_x, label_fmt="{:g}",
                                label_first=True, minus_red=False), 9, 1, 1, 2)
        g.addWidget(QLabel("Толчком Y:"), 10, 0)
        g.addWidget(StepControl((1, 10, 50), self._jog_y, label_fmt="{:g}",
                                label_first=True, minus_red=False), 10, 1, 1, 2)
        g.addWidget(QLabel("Толчком Z:"), 11, 0)
        g.addWidget(StepControl(self.JOG_STEPS, self._jog_z, label_fmt="{:g}",
                                label_first=True, minus_red=False), 11, 1, 1, 2)
        g.setColumnStretch(1, 1)
        return box

    def _build_speed_box(self) -> QGroupBox:
        box = QGroupBox("Скорость (задаётся на вкладке «Параметры устройства»)")
        g = QGridLayout(box)
        self.speed_row = MetricRow("Скорость привода (X/Z):", "—")
        g.addWidget(self.speed_row, 0, 0, 1, 3)
        self.table_speed_row = MetricRow("Скорость стола (Y):", "—")
        g.addWidget(self.table_speed_row, 1, 0, 1, 3)
        g.setColumnStretch(1, 1)
        return box

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.reset_btn = GrayButton("Сброс позиции"); self.reset_btn.setMaximumWidth(170)
        self.stop_btn = GrayButton("Стоп"); self.stop_btn.setMaximumWidth(130)
        row.addWidget(self.reset_btn)
        row.addWidget(self.stop_btn)
        row.addStretch()
        return row

    # ---- действия ------------------------------------------------------
    def _move_all(self) -> None:
        self.ctl.move_to(self.target_x.value(), self.target_z.value())  # головка X/Z
        self.ctl.move_table(self.target_y.value())                      # стол Y

    def _reset_all(self) -> None:
        self.ctl.reset_motor()
        self.ctl.reset_table()

    def _stop_all(self) -> None:
        self.ctl.stop_motor()
        self.ctl.stop_table()

    def _jog_x(self, d: float) -> None:
        self.ctl.move_to(int(self.ctl.snapshot()["motor"]["x"] + d), None)

    def _jog_y(self, d: float) -> None:
        self.ctl.move_table(int(self.ctl.snapshot()["table"]["pos"] + d))

    def _jog_z(self, d: float) -> None:
        self.ctl.move_to(None, int(self.ctl.snapshot()["motor"]["z"] + d))

    # ---- обновление ----------------------------------------------------
    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        m, d, tb = s["motor"], s["driver"], s["table"]
        mspan = max(1, m["max"] - m["min"])
        tspan = max(1, tb["max"] - tb["min"])
        kind = "warn" if (m["moving"] or tb["moving"]) else "ok"

        # X — головка
        self.x_row.set_value(str(m["x"]), kind)
        self.x_bar.set_kind(kind); self.x_bar.set_fraction((m["x"] - m["min"]) / mspan)
        # Y — стол
        self.y_row.set_value(str(tb["pos"]), kind)
        self.y_bar.set_kind(kind); self.y_bar.set_fraction((tb["pos"] - tb["min"]) / tspan)
        # Z — головка
        self.z_row.set_value(str(m["z"]), kind)
        self.z_bar.set_kind(kind); self.z_bar.set_fraction((m["z"] - m["min"]) / mspan)

        self.target_x.setRange(m["min"], m["max"])
        self.target_y.setRange(tb["min"], tb["max"])
        self.target_z.setRange(m["min"], m["max"])

        self.speed_row.set_value(f"{d['speed']} шаг/с", "ok")
        self.table_speed_row.set_value(
            f"{tb['speed']} шаг/с" if tb["online"] else "нет связи",
            "ok" if tb["online"] else "warn")

        # 3D-вид: горизонталь стола = X (головка) и Y (стол), высота = Z (головка)
        self.view.set_position(
            (m["x"] - m["min"]) / mspan,
            (tb["pos"] - tb["min"]) / tspan,
            (m["z"] - m["min"]) / mspan,
            moving=(m["moving"] or tb["moving"]),
            labels=(f"X {m['x']}", f"Y {tb['pos']}", f"Z {m['z']}"))
