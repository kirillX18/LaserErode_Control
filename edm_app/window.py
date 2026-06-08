from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel,
)
from PyQt5.QtCore import Qt, QTimer

from . import theme
from .pages import ProcessPage, ServiceControlPage, HardwarePage
from .blocks import MasterStatusBar
from .hardware import controller

APP_TITLE = "Управление лазерно-эрозионным роботом"

# Реестр страниц верхнего уровня: (заголовок вкладки, класс страницы).
PAGES = [
    ("Процесс", ProcessPage),
    ("Узлы оборудования", HardwarePage),
    ("Сервисное управление", ServiceControlPage),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1450, 820)
        self.pages = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        header = QLabel(APP_TITLE)
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(theme.header_style())
        layout.addWidget(header)

        # Строка общего состояния устройства (видна на всех страницах).
        self.status_bar = MasterStatusBar()
        layout.addWidget(self.status_bar)

        self.tabs = QTabWidget()
        for title, page_cls in PAGES:
            page = page_cls()
            self.pages[title] = page
            self.tabs.addTab(page, title)
        layout.addWidget(self.tabs)

        # Общий контроллер: строка состояния + единый мониторинг безопасности.
        self._ctl = controller()
        self._ctl.stateChanged.connect(self._update_status_bar)
        self._update_status_bar()

        self._monitor = QTimer(self)
        self._monitor.timeout.connect(self._ctl.poll)
        self._monitor.start(500)

    def _update_status_bar(self) -> None:
        self.status_bar.update_from(self._ctl.snapshot(), self._ctl.alarms())

    def show_page(self, title: str) -> None:
        """Переключиться на страницу по её заголовку."""
        index = self.tabs.indexOf(self.pages[title])
        if index >= 0:
            self.tabs.setCurrentIndex(index)
