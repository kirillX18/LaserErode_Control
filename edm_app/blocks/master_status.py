import time

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel

from ..components import StatusBadge
from .. import theme


class MasterStatusBar(QWidget):
    """Строка общего состояния: бейджи + часы."""

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 2, 8, 2)

        self.acdc = StatusBadge("AC/DC", "off")
        self.init = StatusBadge("ИНИЦИАЛИЗАЦИЯ", "off")
        self.proc = StatusBadge("ПРОЦЕСС", "off")
        self.alarm = StatusBadge("НЕТ АВАРИЙ", "off")
        for b in (self.acdc, self.init, self.proc, self.alarm):
            h.addWidget(b)
        h.addStretch()

        self.clock = QLabel("--:--:--")
        self.clock.setStyleSheet(f"color:{theme.Palette.ACCENT}; font-weight:bold;")
        h.addWidget(self.clock)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _tick(self) -> None:
        self.clock.setText(time.strftime("%H:%M:%S"))

    def update_from(self, snap: dict, alarms: list) -> None:
        self.acdc.set_state("AC/DC", "ok" if snap["acdc"]["on"] else "off")
        self.init.set_state("ИНИЦИАЛИЗАЦИЯ",
                            "ok" if snap["initialized"] else "off")
        if snap["process_running"]:
            self.proc.set_state("ПРОЦЕСС", "ok")
        elif snap["initialized"]:
            self.proc.set_state("ПРОЦЕСС", "warn")
        else:
            self.proc.set_state("ПРОЦЕСС", "off")
        has_err = any(a[0] == "err" for a in alarms)
        has_warn = any(a[0] == "warn" for a in alarms)
        if has_err:
            self.alarm.set_state("АВАРИЯ", "err")
        elif has_warn:
            self.alarm.set_state("ПРЕДУПРЕЖДЕНИЕ", "warn")
        else:
            self.alarm.set_state("НЕТ АВАРИЙ", "off")
