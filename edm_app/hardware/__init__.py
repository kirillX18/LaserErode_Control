"""
hardware — связь UI с оборудованием.

    laser_erosion_stubs — классы-заглушки устройства (как есть, без правок);
    controller          — адаптер DeviceController + общий доступ controller().

UI работает только с DeviceController. При подключении реального железа
достаточно переписать методы DeviceController, не трогая виджеты.
"""

from .controller import DeviceController, controller, process_readiness
from .laser_erosion_stubs import TransistorChannel

__all__ = ["DeviceController", "controller", "process_readiness",
           "TransistorChannel"]
