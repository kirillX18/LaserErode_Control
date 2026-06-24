"""
positioning_tab.py — вкладка «Позиционирование».

Управление положением рабочей головки роботизированным 8-суставным манипулятором
(заменяет прежние «Шаговый привод» и «Координатный стол»).

    слева  — задание положения инструмента (TCP) по X / Y / Z и пульт суставов
             J1…J8 (текущий угол + задание угла, в пределах ограничений);
    справа — 3D-визуализация положения инструмента и луча над зоной обработки.

Соответствие узлам устройства из заглушек:
    X, Y, Z — оси инструмента манипулятора (move_tool, snapshot["arm"]);
    J1…J8   — суставы манипулятора (move_joint), у каждого своё ограничение угла.

Все действия идут через DeviceController; перемещение до инициализации и во
время процесса блокируется логикой стабов, результат виден в строке снизу.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QWidget, QSplitter, QGroupBox, QGridLayout, QHBoxLayout,
    QLabel, QSpinBox, QScrollArea,
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
    JOINTS = ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8")

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()
        self.joint_spins: dict[str, QSpinBox] = {}
        self.joint_rows: dict[str, MetricRow] = {}

        splitter = QSplitter(Qt.Horizontal)

        # ── левая колонка: TCP + суставы + скорость ──
        left_inner = QWidget()
        lv = QVBoxLayout(left_inner)
        lv.addWidget(self._build_tcp_box())
        lv.addWidget(self._build_joints_box())
        lv.addWidget(self._build_speed_box())
        lv.addLayout(self._build_buttons())
        lv.addStretch()
        self.status_line = LastMessageBar()
        lv.addWidget(self.status_line)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_inner)

        # ── правая колонка: 3D над зоной ──
        right = QWidget()
        rv = QVBoxLayout(right)
        view_box = QGroupBox("Положение инструмента над зоной (3D)")
        vb = QVBoxLayout(view_box)
        self.view = PositionView()
        self.view.setToolTip(
            "Вращение — перетаскивание мышью · Зум — колесо · "
            "Двойной клик — сброс ракурса")
        vb.addWidget(self.view)
        rv.addWidget(view_box)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right)
        splitter.setSizes([520, 540])
        layout.addWidget(splitter)

        # сигналы
        self.move_btn.clicked.connect(self._move_tcp)
        self.home_btn.clicked.connect(self.ctl.home_arm)
        self.stop_btn.clicked.connect(self.ctl.stop_arm)
        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    # ---- построение блоков --------------------------------------------
    def _build_tcp_box(self) -> QGroupBox:
        box = QGroupBox("Положение инструмента (TCP X / Y / Z)")
        g = QGridLayout(box)

        self.x_row = MetricRow("Текущая X:", "0"); g.addWidget(self.x_row, 0, 0, 1, 3)
        self.x_bar = MeterBar("ok");               g.addWidget(self.x_bar, 1, 0, 1, 3)
        self.y_row = MetricRow("Текущая Y:", "0"); g.addWidget(self.y_row, 2, 0, 1, 3)
        self.y_bar = MeterBar("ok");               g.addWidget(self.y_bar, 3, 0, 1, 3)
        self.z_row = MetricRow("Текущая Z:", "0"); g.addWidget(self.z_row, 4, 0, 1, 3)
        self.z_bar = MeterBar("ok");               g.addWidget(self.z_bar, 5, 0, 1, 3)

        g.addWidget(QLabel("Задать X:"), 6, 0)
        self.target_x = QSpinBox(); self.target_x.setRange(0, 1000)
        g.addWidget(self.target_x, 6, 1)
        g.addWidget(QLabel("Задать Y:"), 7, 0)
        self.target_y = QSpinBox(); self.target_y.setRange(0, 500)
        g.addWidget(self.target_y, 7, 1)
        g.addWidget(QLabel("Задать Z:"), 8, 0)
        self.target_z = QSpinBox(); self.target_z.setRange(0, 400)
        g.addWidget(self.target_z, 8, 1)
        self.move_btn = PrimaryButton("Переместить")
        g.addWidget(self.move_btn, 6, 2, 3, 1)

        g.addWidget(QLabel("Смещение X:"), 9, 0)
        g.addWidget(StepControl(self.JOG_STEPS, self._jog_x, label_fmt="{:g}",
                                label_first=True, minus_red=False), 9, 1, 1, 2)
        g.addWidget(QLabel("Смещение Y:"), 10, 0)
        g.addWidget(StepControl(self.JOG_STEPS, self._jog_y, label_fmt="{:g}",
                                label_first=True, minus_red=False), 10, 1, 1, 2)
        g.addWidget(QLabel("Смещение Z:"), 11, 0)
        g.addWidget(StepControl(self.JOG_STEPS, self._jog_z, label_fmt="{:g}",
                                label_first=True, minus_red=False), 11, 1, 1, 2)
        g.setColumnStretch(1, 1)
        return box

    def _build_joints_box(self) -> QGroupBox:
        box = QGroupBox("Суставы манипулятора (J1…J8)")
        g = QGridLayout(box)
        g.addWidget(QLabel("Сустав"), 0, 0)
        g.addWidget(QLabel("Текущий угол"), 0, 1)
        g.addWidget(QLabel("Задать, °"), 0, 2)
        for i, j in enumerate(self.JOINTS, start=1):
            g.addWidget(QLabel(j + ":"), i, 0)
            row = MetricRow("", "0°")
            self.joint_rows[j] = row
            g.addWidget(row, i, 1)
            spin = QSpinBox(); spin.setRange(-360, 360); spin.setSuffix(" °")
            self.joint_spins[j] = spin
            g.addWidget(spin, i, 2)
            btn = PrimaryButton("Задать"); btn.setMaximumWidth(90)
            btn.clicked.connect(lambda _=False, jj=j: self._move_joint(jj))
            g.addWidget(btn, i, 3)
        g.setColumnStretch(1, 1)
        return box

    def _build_speed_box(self) -> QGroupBox:
        box = QGroupBox("Скорость (задаётся на «Параметрах устройства»)")
        g = QGridLayout(box)
        self.speed_row = MetricRow("Скорость манипулятора:", "—")
        g.addWidget(self.speed_row, 0, 0, 1, 3)
        g.setColumnStretch(1, 1)
        return box

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.home_btn = GrayButton("В исходную позу"); self.home_btn.setMaximumWidth(190)
        self.stop_btn = GrayButton("Стоп"); self.stop_btn.setMaximumWidth(130)
        row.addWidget(self.home_btn)
        row.addWidget(self.stop_btn)
        row.addStretch()
        return row

    # ---- действия ------------------------------------------------------
    def _move_tcp(self) -> None:
        self.ctl.move_tool(self.target_x.value(),
                           self.target_y.value(),
                           self.target_z.value())

    def _move_joint(self, joint: str) -> None:
        self.ctl.move_joint(joint, self.joint_spins[joint].value())

    def _jog_x(self, d: float) -> None:
        self.ctl.move_tool(x=int(self.ctl.snapshot()["arm"]["x"] + d))

    def _jog_y(self, d: float) -> None:
        self.ctl.move_tool(y=int(self.ctl.snapshot()["arm"]["y"] + d))

    def _jog_z(self, d: float) -> None:
        self.ctl.move_tool(z=int(self.ctl.snapshot()["arm"]["z"] + d))

    # ---- обновление ----------------------------------------------------
    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        arm, rc = s["arm"], s["robot"]
        rx, ry, rz = arm["ranges"]["x"], arm["ranges"]["y"], arm["ranges"]["z"]
        xspan = max(1, rx[1] - rx[0])
        yspan = max(1, ry[1] - ry[0])
        zspan = max(1, rz[1] - rz[0])
        moving = arm["moving"]
        kind = "warn" if moving else "ok"

        self.x_row.set_value(f"{arm['x']:.0f}", kind)
        self.x_bar.set_kind(kind); self.x_bar.set_fraction((arm["x"] - rx[0]) / xspan)
        self.y_row.set_value(f"{arm['y']:.0f}", kind)
        self.y_bar.set_kind(kind); self.y_bar.set_fraction((arm["y"] - ry[0]) / yspan)
        self.z_row.set_value(f"{arm['z']:.0f}", kind)
        self.z_bar.set_kind(kind); self.z_bar.set_fraction((arm["z"] - rz[0]) / zspan)

        self.target_x.setRange(rx[0], rx[1])
        self.target_y.setRange(ry[0], ry[1])
        self.target_z.setRange(rz[0], rz[1])

        # суставы: текущий угол + диапазон полей по ограничениям
        for j in self.JOINTS:
            angle = arm["joints"][j]
            self.joint_rows[j].set_value(f"{angle:.0f}°", kind)
            lo, hi = arm["limits"][j]
            spin = self.joint_spins[j]
            spin.setRange(int(lo), int(hi))
            if not spin.hasFocus():
                spin.blockSignals(True)
                spin.setValue(int(round(angle)))
                spin.blockSignals(False)

        self.speed_row.set_value(
            f"{rc['speed']}" if rc["online"] else "нет связи",
            "ok" if rc["online"] else "warn")

        # 3D-вид: горизонталь зоны = X/Y инструмента, высота = Z
        self.view.set_position(
            (arm["x"] - rx[0]) / xspan,
            (arm["y"] - ry[0]) / yspan,
            (arm["z"] - rz[0]) / zspan,
            moving=moving,
            labels=(f"X {arm['x']:.0f}", f"Y {arm['y']:.0f}", f"Z {arm['z']:.0f}"))
