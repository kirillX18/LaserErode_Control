"""
params_tab.py — вкладка «Параметры устройства».

Заменяет прежнюю «Параметры робота». Здесь собраны изменяемые параметры,
которые есть в заглушках устройства: лимит тока источника 48 В, порог
перегрева, скорость шагового привода и скорость координатного стола. Слева —
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
        self.m_limit = MetricRow("Лимит тока (48 В):", "—")
        self.m_temp = MetricRow("Порог перегрева:", "—")
        self.m_speed = MetricRow("Скорость привода:", "—")
        self.m_tspeed = MetricRow("Скорость стола:", "—")
        for m in (self.m_limit, self.m_temp, self.m_speed, self.m_tspeed):
            self.body.addWidget(m)


class ParametersTab(BaseServiceTab):
    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()

        self.values = _CurrentValues("Текущие параметры")
        layout.addWidget(self.values)

        self.form = ParameterForm("Задать параметры")
        self.form.add_row("limit", "Лимит тока, А", lo=0.1, hi=10, value=8.0,
                          step=0.1, decimals=1,
                          callback=self.ctl.set_current_limit)
        self.form.add_row("maxtemp", "Порог перегрева, °C", lo=1, hi=200,
                          value=80, step=1, decimals=0,
                          callback=self.ctl.set_max_temp)
        self.form.add_row("speed", "Скорость привода, шаг/с", lo=1, hi=5000,
                          value=150, step=10, decimals=0,
                          callback=lambda v: self.ctl.set_speed(int(v)))
        self.form.add_row("tspeed", "Скорость стола, шаг/с", lo=1, hi=5000,
                          value=100, step=10, decimals=0,
                          callback=lambda v: self.ctl.set_table_speed(int(v)))
        layout.addWidget(self.form)
        layout.addStretch()

        self.status_line = LastMessageBar()
        layout.addWidget(self.status_line)

        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        self.values.m_limit.set_value(f"{s['psu']['limit']:.1f} А", "ok")
        over = s["temp"]["over"]
        self.values.m_temp.set_value(f"{s['temp']['max']:.0f} °C",
                                     "err" if over else "ok")
        self.values.m_speed.set_value(f"{s['driver']['speed']} шаг/с", "ok")
        self.values.m_tspeed.set_value(f"{s['table']['speed']} шаг/с", "ok")

        # Поля ввода подтягиваются к реальным значениям (если не редактируются).
        self.form.sync("limit", s["psu"]["limit"])
        self.form.sync("maxtemp", s["temp"]["max"])
        self.form.sync("speed", s["driver"]["speed"])
        self.form.sync("tspeed", s["table"]["speed"])
