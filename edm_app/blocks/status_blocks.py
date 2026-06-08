from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
)
from PyQt5.QtGui import QColor

from ..base import BasePanel
from ..components import PrimaryButton
from .. import theme


class AlarmPanel(BasePanel):
    """Список активных аварий и предупреждений."""

    def build(self) -> None:
        self.list = QListWidget()
        self.list.setMaximumHeight(150)
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

        self.clear_button = PrimaryButton("Очистить журнал")
        self.clear_button.clicked.connect(self.view.clear)
        self.body.addWidget(self.clear_button)

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
