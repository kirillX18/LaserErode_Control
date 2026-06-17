"""
Вкладки сервисного управления — приведены в соответствие узлам устройства
из классов-заглушек.

Вкладки «Шаговый привод» и «Координатный стол» объединены в одну —
«Позиционирование» (задание положения лазера по X/Y/Z + 3D над столом).
X/Z — лазерная головка шагового привода, Y — подача координатного стола.
"""

from .positioning_tab import PositioningTab
from .params_tab import ParametersTab
from .laser_tab import LaserControlTab

# Реестр вкладок: (заголовок, класс). Чтобы добавить новую — допишите строку.
SERVICE_TABS = [
    ("Позиционирование", PositioningTab),
    ("Лазером", LaserControlTab),
    ("Параметры устройства", ParametersTab),
]

__all__ = [
    "PositioningTab", "ParametersTab", "LaserControlTab", "SERVICE_TABS",
]
