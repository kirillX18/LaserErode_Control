"""
device_card.py — карточка одного узла устройства.

Qt-аналог HTML-карточки модуля (.card): заголовок + бейдж состояния в шапке,
строки параметров (MetricRow), необязательная шкала (MeterBar) и ряд кнопок
управления. Это наследник BasePanel (QGroupBox), поэтому визуально карточки
неотличимы от остальных панелей приложения.

Карточка конфигурируется декларативно (add_metric / add_bar / add_action),
поэтому 9 разных узлов не требуют 9 классов — достаточно одной карточки и
описания на странице. При необходимости узкоспециальный узел можно оформить
наследником DeviceCard.
"""

from typing import Callable

from PyQt5.QtWidgets import QHBoxLayout, QWidget

from ..base import BasePanel
from ..components import (
    StatusBadge, StatusDot, MetricRow, MeterBar,
    PrimaryButton, GrayButton, DangerButton,
)


class DeviceCard(BasePanel):
    """Карточка узла: шапка с бейджем, метрики, шкалы, кнопки."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        self._subtitle = subtitle
        self._metrics: dict[str, MetricRow] = {}
        self._bars: dict[str, MeterBar] = {}
        super().__init__(title, parent)

    def build(self) -> None:
        # Шапка карточки: индикатор-точка + бейдж состояния (справа).
        header = QHBoxLayout()
        self.dot = StatusDot("off")
        self.badge = StatusBadge("—", "off")
        header.addWidget(self.dot)
        header.addStretch()
        header.addWidget(self.badge)
        self.body.addLayout(header)

        # Контейнер строк-метрик.
        self._metrics_box = QWidget()
        from PyQt5.QtWidgets import QVBoxLayout
        self._metrics_layout = QVBoxLayout(self._metrics_box)
        self._metrics_layout.setContentsMargins(0, 2, 0, 2)
        self._metrics_layout.setSpacing(2)
        self.body.addWidget(self._metrics_box)

        # Ряд кнопок (создаётся лениво при первом add_action).
        self._actions_row: QHBoxLayout | None = None

    # ------------------------------------------------------------------
    # Декларативное наполнение
    # ------------------------------------------------------------------
    def add_metric(self, key: str, label: str, value: str = "—") -> MetricRow:
        row = MetricRow(label, value)
        self._metrics[key] = row
        self._metrics_layout.addWidget(row)
        return row

    def add_bar(self, key: str, kind: str = "ok") -> MeterBar:
        bar = MeterBar(kind)
        self._bars[key] = bar
        self.body.addWidget(bar)
        return bar

    def add_action(self, text: str, callback: Callable,
                   role: str = "primary") -> None:
        if self._actions_row is None:
            self._actions_row = QHBoxLayout()
            self.body.addLayout(self._actions_row)
        cls = {"primary": PrimaryButton, "gray": GrayButton,
               "danger": DangerButton}.get(role, PrimaryButton)
        btn = cls(text)
        btn.setMaximumWidth(16777215)  # снять возможный лимит ширины роли
        btn.clicked.connect(callback)
        self._actions_row.addWidget(btn, 1)

    # ------------------------------------------------------------------
    # Обновление состояния
    # ------------------------------------------------------------------
    def set_metric(self, key: str, value, state: str | None = None) -> None:
        if key in self._metrics:
            self._metrics[key].set_value(value, state)

    def set_bar(self, key: str, fraction: float, kind: str | None = None) -> None:
        if key in self._bars:
            if kind is not None:
                self._bars[key].set_kind(kind)
            self._bars[key].set_fraction(fraction)

    def set_state(self, badge_text: str, state: str) -> None:
        self.dot.set_state(state)
        self.badge.set_state(badge_text, state)
