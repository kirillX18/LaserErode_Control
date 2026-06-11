from PyQt5.QtWidgets import QWidget, QGroupBox, QVBoxLayout

from .components import SectionTitle


class BasePanel(QGroupBox):
    """Базовая панель-блок.

    Все крупные функциональные блоки (управление осью, суставом, эрозией…)
    наследуются отсюда. Наследник переопределяет build() и наполняет
    self.body — готовый вертикальный layout внутри рамки с заголовком.
    """

    def __init__(self, title: str = "", parent=None):
        super().__init__(title, parent)
        self.body = QVBoxLayout(self)
        self.build()

    def build(self) -> None:  # переопределяется наследниками
        """Наполнение панели. По умолчанию пусто."""
        raise NotImplementedError


class BasePage(QWidget):
    """Базовая страница верхнего уровня.

    Содержит заголовок-секцию и контейнер контента. Наследник переопределяет
    build_content(content_layout), не заботясь о каркасе.
    """

    title: str = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        if self.title:
            self._layout.addWidget(SectionTitle(self.title))
        self.build_content(self._layout)

    def build_content(self, layout: QVBoxLayout) -> None:
        raise NotImplementedError


class BaseServiceTab(QWidget):
    """Базовая вкладка сервисного управления (простой вертикальный контент)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.content = QVBoxLayout(self)
        self.build_content(self.content)

    def build_content(self, layout: QVBoxLayout) -> None:
        raise NotImplementedError
