from PyQt5.QtWidgets import (
    QVBoxLayout, QGroupBox, QGridLayout, QHBoxLayout, QLabel, QSpinBox,
)

from ..base import BaseServiceTab
from ..components import (
    PrimaryButton, GrayButton, StepControl, MetricRow, MeterBar, LastMessageBar,
)
from ..hardware import controller


class MotorControlTab(BaseServiceTab):
    JOG_STEPS = (1, 10, 100)

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()

        # --- положение ---
        pos_box = QGroupBox("Положение")
        pg = QGridLayout(pos_box)
        self.current_row = MetricRow("Текущая позиция:", "0")
        pg.addWidget(self.current_row, 0, 0, 1, 3)

        self.pos_bar = MeterBar("ok")
        pg.addWidget(self.pos_bar, 1, 0, 1, 3)
        self.range_row = MetricRow("Диапазон:", "0 … 1000")
        pg.addWidget(self.range_row, 2, 0, 1, 3)

        pg.addWidget(QLabel("Задать позицию:"), 3, 0)
        self.target = QSpinBox()
        self.target.setRange(0, 1000)
        pg.addWidget(self.target, 3, 1)
        self.move_btn = PrimaryButton("Переместить")
        self.move_btn.clicked.connect(lambda: self.ctl.move_to(self.target.value()))
        pg.addWidget(self.move_btn, 3, 2)

        pg.addWidget(QLabel("Толчком (шагов):"), 4, 0)
        pg.addWidget(StepControl(self.JOG_STEPS, self._jog, label_fmt="{:g}",
                                 label_first=True, minus_red=False), 4, 1, 1, 2)
        pg.setColumnStretch(1, 1)
        layout.addWidget(pos_box)

        # --- скорость ---
        sp_box = QGroupBox("Скорость")
        sg = QGridLayout(sp_box)
        self.speed_row = MetricRow("Текущая скорость:", "—")
        sg.addWidget(self.speed_row, 0, 0, 1, 3)
        sg.addWidget(QLabel("Задать скорость:"), 1, 0)
        self.speed = QSpinBox()
        self.speed.setRange(1, 5000)
        self.speed.setSuffix(" шаг/с")
        sg.addWidget(self.speed, 1, 1)
        self.set_speed_btn = PrimaryButton("Задать")
        self.set_speed_btn.clicked.connect(lambda: self.ctl.set_speed(self.speed.value()))
        sg.addWidget(self.set_speed_btn, 1, 2)
        sg.setColumnStretch(1, 1)
        layout.addWidget(sp_box)

        # --- состояние + кнопки ---
        self.state_row = MetricRow("Состояние привода:", "—")
        layout.addWidget(self.state_row)
        row = QHBoxLayout()
        self.reset_btn = GrayButton("Сброс позиции")
        self.reset_btn.setMaximumWidth(160)
        self.stop_btn = GrayButton("Стоп")
        self.stop_btn.setMaximumWidth(160)
        self.reset_btn.clicked.connect(self.ctl.reset_motor)
        self.stop_btn.clicked.connect(self.ctl.stop_motor)
        row.addWidget(self.reset_btn)
        row.addWidget(self.stop_btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

        # строка последнего сообщения/результата (локальная обратная связь)
        self.status_line = LastMessageBar()
        layout.addWidget(self.status_line)

        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    def _jog(self, delta: float) -> None:
        s = self.ctl.snapshot()["motor"]
        self.ctl.move_to(int(s["pos"] + delta))

    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        m, d = s["motor"], s["driver"]
        span = max(1, m["max"] - m["min"])

        self.current_row.set_value(str(m["pos"]), "ok")
        self.pos_bar.set_kind("warn" if m["moving"] else "ok")
        self.pos_bar.set_fraction((m["pos"] - m["min"]) / span)
        self.range_row.set_value(f"{m['min']} … {m['max']}")
        self.target.setRange(m["min"], m["max"])

        self.speed_row.set_value(f"{d['speed']} шаг/с", "ok")
        if not self.speed.hasFocus():
            self.speed.blockSignals(True)
            self.speed.setValue(d["speed"])
            self.speed.blockSignals(False)

        if d["enabled"]:
            self.state_row.set_value("движется" if d["moving"] else "включен, готов",
                                     "warn" if d["moving"] else "ok")
        else:
            self.state_row.set_value("выключен", "off")
