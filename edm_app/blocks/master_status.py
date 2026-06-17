"""
master_status.py — общая строка состояния системы под шапкой окна.

Qt-аналог верхней панели статусов из HTML (.status-pills): четыре бейджа
(AC/DC, Инициализация, Процесс, Авария). Видна на всех страницах, чтобы
оператор всегда сразу видел общее состояние устройства.
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout

from ..components import StatusBadge


class MasterStatusBar(QWidget):
    """Строка общего состояния: бейджи состояний устройства."""

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 2, 8, 2)

        # AC/DC намеренно убран из этой строки: он всегда «включён» и
        # программно не управляется (физический тумблер), поэтому неуправляемый
        # вечно-зелёный бейдж только дублировал пункт чек-листа «Условия
        # запуска». Предусловие AC/DC осталось там, где оно действует.
        self.init = StatusBadge("ИНИЦИАЛИЗАЦИЯ", "off")
        self.proc = StatusBadge("ПРОЦЕСС", "off")
        self.alarm = StatusBadge("НЕТ АВАРИЙ", "off")
        for b in (self.init, self.proc, self.alarm):
            h.addWidget(b)
        h.addStretch()

    def update_from(self, snap: dict, alarms: list) -> None:
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
