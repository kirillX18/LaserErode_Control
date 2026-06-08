from PyQt5.QtWidgets import QVBoxLayout, QTabWidget

from ..base import BasePage
from ..tabs import SERVICE_TABS


class ServiceControlTabs(QTabWidget):
    """Контейнер вкладок сервисного управления (строится из реестра)."""

    def __init__(self, parent=None):
        super().__init__(parent)
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
