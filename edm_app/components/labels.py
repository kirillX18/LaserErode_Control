from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from .. import theme


class SectionTitle(QLabel):
    """Синий жирный заголовок секции (например, «Визуализация G-code»)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(theme.title_style())


class ValueLabel(QLabel):
    """Метка для отображения текущего значения (по центру, моноширинно-ровно)."""

    def __init__(self, text: str = "0", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)

    def set_value(self, value) -> None:
        self.setText(str(value))
