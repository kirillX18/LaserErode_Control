"""
status_blocks.py — крупные панели «состояние/диагностика»:

    AlarmPanel       — блок активных ошибок и предупреждений (.alarm-list);
    EventLogPanel    — журнал событий логгера «hardware» (.log);
    DiagnosticsPanel — текстовый дамп get_system_status() (.diag).

Все три — наследники BasePanel, поэтому выглядят как обычные панели приложения.
"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from ..base import BasePanel
from ..components import PrimaryButton
from .. import theme


class AlarmPanel(BasePanel):
    """Список активных аварий и предупреждений."""

    def build(self) -> None:
        self.list = QListWidget()
        self.list.setMaximumHeight(150)
        # Панель только для чтения — не должна попадать в обход фокуса по Tab.
        self.list.setFocusPolicy(Qt.NoFocus)
        self.body.addWidget(self.list)
        self.set_alarms([])

    def set_alarms(self, alarms: list) -> None:
        self.list.clear()
        if not alarms:
            item = QListWidgetItem("● Активных аварий нет")
            item.setForeground(QColor(theme.Palette.OK))
            self.list.addItem(item)
            return
        for severity, text, source in alarms:
            mark = "⛔" if severity == "err" else "⚠"
            item = QListWidgetItem(f"{mark}  {text}\n      {source}")
            fg, _ = theme.state_colors(severity)
            item.setForeground(QColor(fg))
            self.list.addItem(item)


class EventLogPanel(BasePanel):
    """Журнал событий (подписан на логгер «hardware» через контроллер)."""

    LEVEL_COLORS = {"info": theme.Palette.ACCENT,
                    "warning": theme.Palette.WARN,
                    "error": theme.Palette.ERR}

    def build(self) -> None:
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(400)
        self.body.addWidget(self.view)

        self.save_button = PrimaryButton("Сохранить журнал событий")
        self.save_button.clicked.connect(self.save_log)
        self.body.addWidget(self.save_button)

    def save_log(self) -> None:
        """Сохранить содержимое журнала событий в текстовый файл."""
        default_name = "Журнал_событий_{:%Y-%m-%d_%H-%M-%S}.txt".format(
            datetime.now())
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить журнал событий", default_name,
            "Текстовые файлы (*.txt);;Все файлы (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.view.toPlainText())
        except OSError as exc:
            QMessageBox.warning(
                self, "Ошибка сохранения",
                "Не удалось сохранить журнал событий:\n{}".format(exc))

    def append(self, level: str, text: str) -> None:
        color = self.LEVEL_COLORS.get(level, theme.Palette.ACCENT)
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        tag = level.upper().ljust(7).replace(" ", "&nbsp;")
        self.view.appendHtml(
            f'<span style="color:{color};font-weight:bold;">{tag}</span>'
            f'&nbsp;<span>{safe}</span>')


class DiagnosticsPanel(BasePanel):
    """Полный текстовый статус системы (get_system_status())."""

    def build(self) -> None:
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlainText("Нажмите «Обновить статус» для опроса системы…")
        self.body.addWidget(self.view)

        self.refresh_button = PrimaryButton("Обновить статус")
        self.body.addWidget(self.refresh_button)

    def set_status(self, text: str) -> None:
        self.view.setPlainText(text)
