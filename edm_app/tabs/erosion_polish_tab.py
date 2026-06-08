from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QDoubleSpinBox, QMessageBox,
)

from ..base import BaseServiceTab, BasePanel
from ..components import PrimaryButton, GrayButton, MetricRow, LastMessageBar
from ..hardware import controller


class _TankPanel(BasePanel):
    def build(self) -> None:
        row = QHBoxLayout()
        self.fill = PrimaryButton("Наполнить")
        self.drain = GrayButton("Слить")
        self.drain.setMaximumWidth(200)
        self.connect = PrimaryButton("Подключить электроды")
        self.disconnect = GrayButton("Отключить электроды")
        self.disconnect.setMaximumWidth(200)
        for b in (self.fill, self.drain, self.connect, self.disconnect):
            row.addWidget(b)
        self.body.addLayout(row)

        self.m_filled = MetricRow("Рабочая жидкость:", "—")
        self.m_elec = MetricRow("Анод / катод:", "—")
        self.m_ready = MetricRow("Готовность:", "—")
        self.m_volt = MetricRow("Напряжение процесса:", "—")
        for m in (self.m_filled, self.m_elec, self.m_ready, self.m_volt):
            self.body.addWidget(m)


class _SourcePanel(BasePanel):
    def build(self) -> None:
        self.m_v = MetricRow("Напряжение:", "—")
        self.m_i = MetricRow("Ток:", "—")
        self.m_lim = MetricRow("Лимит тока:", "—")
        for m in (self.m_v, self.m_i, self.m_lim):
            self.body.addWidget(m)

        grid = QGridLayout()
        grid.addWidget(QLabel("Задать лимит тока, А:"), 0, 0)
        self.limit = QDoubleSpinBox()
        self.limit.setRange(0.1, 10.0)
        self.limit.setSingleStep(0.1)
        self.limit.setValue(5.0)
        grid.addWidget(self.limit, 0, 1)
        self.set_limit = PrimaryButton("Задать")
        self.set_limit.setMaximumWidth(120)
        grid.addWidget(self.set_limit, 0, 2)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)


class _StatePanel(BasePanel):
    def build(self) -> None:
        self.m_proc = MetricRow("Процесс:", "—")
        self.m_vibro = MetricRow("Вибростол:", "—")
        for m in (self.m_proc, self.m_vibro):
            self.body.addWidget(m)


class ErosionPolishTab(BaseServiceTab):
    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()

        self.tank = _TankPanel("Ёмкость для полировки")
        self.source = _SourcePanel("Источник напряжения 48 В")
        self.state = _StatePanel("Состояние")
        for p in (self.tank, self.source, self.state):
            layout.addWidget(p)
        layout.addStretch()

        self.status_line = LastMessageBar()
        layout.addWidget(self.status_line)

        # подключение действий
        self.tank.fill.clicked.connect(self.ctl.fill_tank)
        self.tank.drain.clicked.connect(self._confirm_drain)
        self.tank.connect.clicked.connect(self.ctl.connect_electrodes)
        self.tank.disconnect.clicked.connect(self._confirm_disconnect)
        self.source.set_limit.clicked.connect(
            lambda: self.ctl.set_current_limit(self.source.limit.value()))

        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    def _confirm_drain(self) -> None:
        if self.ctl.snapshot()["process_running"]:
            self.ctl.drain_tank()  # стаб сам отклонит во время процесса
            return
        if QMessageBox.question(
                self, "Слить рабочую жидкость",
                "Слить жидкость? Ёмкость перестанет быть готовой к процессу.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctl.drain_tank()

    def _confirm_disconnect(self) -> None:
        if self.ctl.snapshot()["process_running"]:
            self.ctl.disconnect_electrodes()
            return
        if QMessageBox.question(
                self, "Отключить электроды",
                "Отключить электроды? Ёмкость перестанет быть готовой к процессу.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctl.disconnect_electrodes()

    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        k, p, v = s["tank"], s["psu"], s["vibro"]
        on = lambda b: "ok" if b else "off"

        self.tank.m_filled.set_value("есть" if k["filled"] else "нет", on(k["filled"]))
        elec = f"{'+' if k['anode'] else '−'} / {'+' if k['cathode'] else '−'}"
        self.tank.m_elec.set_value(elec, on(k["anode"] and k["cathode"]))
        self.tank.m_ready.set_value("готова" if k["ready"] else "не готова",
                                    "ok" if k["ready"] else "warn")
        self.tank.m_volt.set_value(f"{k['volt']:.1f} В", "ok")

        self.source.m_v.set_value(f"{p['v']:.0f} В", on(p["on"]))
        over = p["on"] and p["i"] > p["limit"]
        self.source.m_i.set_value(f"{p['i']:.1f} А", "err" if over else on(p["on"]))
        self.source.m_lim.set_value(f"{p['limit']:.1f} А")
        if not self.source.limit.hasFocus():
            self.source.limit.blockSignals(True)
            self.source.limit.setValue(p["limit"])
            self.source.limit.blockSignals(False)

        self.state.m_proc.set_value("запущен" if s["process_running"] else "остановлен",
                                    "ok" if s["process_running"] else "off")
        self.state.m_vibro.set_value("вибрирует" if v["on"] else "остановлен", on(v["on"]))
