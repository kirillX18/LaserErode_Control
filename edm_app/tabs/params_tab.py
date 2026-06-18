"""
params_tab.py — вкладка «Параметры устройства».

Изменяемые параметры узлов лазерно-эрозионного робота: лимит тока источника
эрозии, порог перегрева, темп отработки траектории контроллером робота. Слева —
текущие значения, в форме — задание новых. Всё идёт через DeviceController.
"""

from PyQt5.QtWidgets import QVBoxLayout

from ..base import BaseServiceTab, BasePanel
from ..components import MetricRow, LastMessageBar
from ..blocks import ParameterForm
from ..hardware import controller


class _CurrentValues(BasePanel):
    """Сводка текущих значений параметров (только чтение)."""

    def build(self) -> None:
        self.m_limit = MetricRow("Лимит тока (эрозия):", "—")
        self.m_temp = MetricRow("Порог перегрева:", "—")
        self.m_speed = MetricRow("Темп траектории:", "—")
        for m in (self.m_limit, self.m_temp, self.m_speed):
            self.body.addWidget(m)


class ParametersTab(BaseServiceTab):
    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()

        self.values = _CurrentValues("Текущие параметры")
        layout.addWidget(self.values)

        self.form = ParameterForm("Задать параметры")
        self.form.add_row("limit", "Лимит тока эрозии, А", lo=0.1, hi=10, value=8.0,
                          step=0.1, decimals=1,
                          callback=self.ctl.set_current_limit)
        self.form.add_row("maxtemp", "Порог перегрева, °C", lo=1, hi=200,
                          value=80, step=1, decimals=0,
                          callback=self.ctl.set_max_temp)
        self.form.add_row("speed", "Темп траектории робота", lo=1, hi=5000,
                          value=150, step=10, decimals=0,
                          callback=lambda v: self.ctl.set_arm_speed(int(v)))
        layout.addWidget(self.form)
        layout.addStretch()

        self.status_line = LastMessageBar()
        layout.addWidget(self.status_line)

        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        self.values.m_limit.set_value(f"{s['edm']['limit']:.1f} А", "ok")
        over = s["temp"]["over"]
        self.values.m_temp.set_value(f"{s['temp']['max']:.0f} °C",
                                     "err" if over else "ok")
        self.values.m_speed.set_value(f"{s['robot']['speed']}", "ok")

        self.form.sync("limit", s["edm"]["limit"])
        self.form.sync("maxtemp", s["temp"]["max"])
        self.form.sync("speed", s["robot"]["speed"])
