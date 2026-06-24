"""
workzone_tab.py — вкладка «Рабочая зона».

Наладочное управление узлами рабочей зоны, у которых нет своего пульта:
    • система подачи воды — насос/клапан (подача в зону) и слив;
    • крепление детали   — зажим/освобождение заготовки.

Во время процесса подача воды и зажим управляются автоматически
(ProcessController); здесь — ручные наладочные операции. Все действия идут
через DeviceController, результат виден в строке снизу и в показаниях датчиков.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QWIDGETSIZE_MAX,
)

from ..base import BaseServiceTab, BasePanel
from ..components import (
    PrimaryButton, GrayButton, MetricRow, MeterBar, LastMessageBar,
)
from ..hardware import controller


class _WaterPanel(BasePanel):
    """Система подачи воды: подача в зону, слив, показания давления и расхода."""

    def __init__(self, ctl, parent=None):
        self._ctl = ctl
        super().__init__("Система подачи воды", parent)

    def build(self) -> None:
        self.m_state = MetricRow("Состояние:", "—")
        self.m_pump = MetricRow("Насос / клапан:", "—")
        self.m_press = MetricRow("Давление:", "—")
        self.m_flow = MetricRow("Расход:", "—")
        self.bar = MeterBar("ok")
        self.m_drain = MetricRow("Слив:", "—")
        for w in (self.m_state, self.m_pump, self.m_press, self.m_flow,
                  self.bar, self.m_drain):
            self.body.addWidget(w)

        row1 = QHBoxLayout()
        self.supply_on = PrimaryButton("Включить подачу")
        self.supply_off = GrayButton("Остановить подачу")
        # Снимаем компактный лимит ширины GrayButton (90 px) — он рассчитан на
        # короткие подписи и обрезает длинный текст этих кнопок; в строке из
        # двух кнопок они сами делят ширину поровну.
        self.supply_off.setMaximumWidth(QWIDGETSIZE_MAX)
        row1.addWidget(self.supply_on)
        row1.addWidget(self.supply_off)
        self.body.addLayout(row1)

        row2 = QHBoxLayout()
        self.drain_on = GrayButton("Открыть слив")
        self.drain_off = GrayButton("Закрыть слив")
        self.drain_on.setMaximumWidth(QWIDGETSIZE_MAX)
        self.drain_off.setMaximumWidth(QWIDGETSIZE_MAX)
        row2.addWidget(self.drain_on)
        row2.addWidget(self.drain_off)
        self.body.addLayout(row2)

        self.supply_on.clicked.connect(lambda: self._ctl.set_water(True))
        self.supply_off.clicked.connect(lambda: self._ctl.set_water(False))
        self.drain_on.clicked.connect(lambda: self._ctl.set_drain(True))
        self.drain_off.clicked.connect(lambda: self._ctl.set_drain(False))

    def refresh(self, w: dict) -> None:
        flowing = w["flowing"]
        if flowing:
            self.m_state.set_value("подача воды идёт", "ok")
        elif w["pump"] or w["valve"]:
            self.m_state.set_value("нет потока", "warn")
        else:
            self.m_state.set_value("подача выключена", "off")
        self.m_pump.set_value(
            f"{'вкл' if w['pump'] else 'выкл'} / "
            f"{'открыт' if w['valve'] else 'закрыт'}",
            "ok" if flowing else "off")
        self.m_press.set_value(f"{w['pressure']:.1f} бар", "ok" if flowing else "off")
        self.m_flow.set_value(f"{w['flow']:.1f} л/мин",
                              "ok" if flowing else ("warn" if (w["pump"] or w["valve"]) else "off"))
        self.bar.set_kind("ok" if flowing else "warn")
        self.bar.set_fraction(min(1.0, w["flow"] / 5.0))
        self.m_drain.set_value("открыт" if w["drain"] else "закрыт",
                               "warn" if w["drain"] else "off")


class _FixturePanel(BasePanel):
    """Крепление детали: зажим/освобождение заготовки в неподвижном основании."""

    def __init__(self, ctl, parent=None):
        self._ctl = ctl
        super().__init__("Крепление детали", parent)

    def build(self) -> None:
        self.m_state = MetricRow("Фиксация:", "—")
        self.body.addWidget(self.m_state)

        row = QHBoxLayout()
        self.clamp_btn = PrimaryButton("Зажать деталь")
        self.release_btn = GrayButton("Освободить")
        self.release_btn.setMaximumWidth(QWIDGETSIZE_MAX)
        row.addWidget(self.clamp_btn)
        row.addWidget(self.release_btn)
        self.body.addLayout(row)

        self.clamp_btn.clicked.connect(lambda: self._ctl.clamp_fixture(True))
        self.release_btn.clicked.connect(lambda: self._ctl.clamp_fixture(False))

    def refresh(self, fx: dict) -> None:
        clamped = fx["clamped"]
        self.m_state.set_value("деталь зажата" if clamped else "деталь не зажата",
                               "ok" if clamped else "warn")


class WorkZoneTab(BaseServiceTab):
    """Вкладка «Рабочая зона»: подача воды и крепление детали."""

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()

        self.water = _WaterPanel(self.ctl)
        self.fixture = _FixturePanel(self.ctl)
        layout.addWidget(self.water)
        layout.addWidget(self.fixture)
        layout.addStretch()

        self.status_line = LastMessageBar()
        layout.addWidget(self.status_line)

        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        self.water.refresh(s["water"])
        self.fixture.refresh(s["fixture"])
