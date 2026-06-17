"""
service_page.py — страница «Сервисное управление» и контейнер её вкладок.

ServiceControlTabs автоматически собирает все вкладки из реестра SERVICE_TABS,
поэтому добавление новой вкладки не требует правок здесь.
"""

from PyQt5.QtWidgets import QVBoxLayout, QTabWidget

from ..base import BasePage
from ..components import AnimatedTabBar
from ..tabs import SERVICE_TABS


class ServiceControlTabs(QTabWidget):
    """Контейнер вкладок сервисного управления (строится из реестра)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(AnimatedTabBar())   # плавная подсветка при наведении
        self.tabs = {}
        for title, tab_cls in SERVICE_TABS:
            tab = tab_cls()
            self.tabs[title] = tab
            self.addTab(tab, title)


class ServiceControlPage(BasePage):
    title = ""

    def build_content(self, layout: QVBoxLayout) -> None:
        self.tabs_widget = ServiceControlTabs()
        layout.addWidget(self.tabs_widget)
