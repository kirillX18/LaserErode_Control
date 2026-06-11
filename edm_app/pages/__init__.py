"""Страницы верхнего уровня и контейнер вкладок сервисного управления."""

from .process_page import ProcessPage
from .service_page import ServiceControlPage, ServiceControlTabs
from .hardware_page import HardwarePage

__all__ = [
    "ProcessPage", "ServiceControlPage", "ServiceControlTabs", "HardwarePage",
]
