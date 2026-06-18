"""
Вкладки сервисного управления — приведены в соответствие узлам устройства
из классов-заглушек.

Прежние «Шаговый привод» и «Координатный стол» заменены вкладкой
«Позиционирование»: управление рабочей головкой 8-суставной рукой —
инструмент по X/Y/Z и суставы J1…J8 + 3D над зоной обработки.
"""

from .positioning_tab import PositioningTab
from .params_tab import ParametersTab
from .laser_tab import LaserControlTab
from .workzone_tab import WorkZoneTab

# Реестр вкладок: (заголовок, класс). Чтобы добавить новую — допишите строку.
SERVICE_TABS = [
    ("Позиционирование", PositioningTab),
    ("Лазером", LaserControlTab),
    ("Рабочая зона", WorkZoneTab),
    ("Параметры устройства", ParametersTab),
]

__all__ = [
    "PositioningTab", "ParametersTab", "LaserControlTab",
    "WorkZoneTab", "SERVICE_TABS",
]
