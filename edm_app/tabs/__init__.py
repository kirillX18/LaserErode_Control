from .motor_tab import MotorControlTab
from .erosion_polish_tab import ErosionPolishTab
from .params_tab import ParametersTab
from .laser_tab import LaserControlTab

# Реестр вкладок: (заголовок, класс). Чтобы добавить новую — допишите строку.
SERVICE_TABS = [
    ("Шаговый привод", MotorControlTab),
    ("Эрозия и полировка", ErosionPolishTab),
    ("Лазером", LaserControlTab),
    ("Параметры устройства", ParametersTab),
]

__all__ = [
    "MotorControlTab", "ErosionPolishTab", "ParametersTab", "LaserControlTab",
    "SERVICE_TABS",
]
