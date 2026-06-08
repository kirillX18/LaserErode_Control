"""
controller.py — адаптер между классами-заглушками и UI.

Это единственное место, где UI «знает» о железе. Страницы и виджеты не
обращаются к стабам напрямую — они вызывают методы DeviceController и читают
плоский снимок состояния snapshot(). Так UI остаётся независимым от внутренней
структуры стабов: при замене заглушек на реальную прошивку меняется только
этот файл.

Связь идёт через сигналы Qt:
    logMessage(level, text) — сообщения логгера «hardware» (для окна журнала);
    stateChanged()         — что-то изменилось, UI должен перерисоваться.
"""

from __future__ import annotations

import logging

from PyQt5.QtCore import QObject, pyqtSignal

from .laser_erosion_stubs import (
    HardwareRegistry, ProcessController, TestHarness, TransistorChannel,
)


class _SignalLogHandler(logging.Handler):
    """Перенаправляет записи логгера «hardware» в сигнал Qt."""

    def __init__(self, controller: "DeviceController"):
        super().__init__()
        self._controller = controller

    def emit(self, record: logging.LogRecord) -> None:
        self._controller.logMessage.emit(record.levelname.lower(),
                                         record.getMessage())


class DeviceController(QObject):
    """Фасад над HardwareRegistry + ProcessController + TestHarness."""

    logMessage = pyqtSignal(str, str)   # (level, text)
    stateChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hw = HardwareRegistry()
        self.process = ProcessController(self.hw)
        self.test = TestHarness(self.hw, self.process)

        # Асинхронное (фоновое) движение ШД: позиция меняется в фоне, поток UI
        # не блокируется, а индикатор «движется» виден до завершения хода.
        # scale подобран так, чтобы ход был заметен, но не раздражал
        # (≈ steps/speed * scale секунд; полный ход 1000/100*0.4 ≈ 4 c).
        self.hw.stepper_motor.set_async_motion(True, scale=0.4)

        # Подписываемся на логгер «hardware», как и предполагали стабы.
        self._handler = _SignalLogHandler(self)
        self._handler.setLevel(logging.INFO)
        log = logging.getLogger("hardware")
        log.setLevel(logging.INFO)
        log.addHandler(self._handler)
        log.propagate = False

    # ------------------------------------------------------------------
    # Команды процесса
    # ------------------------------------------------------------------
    def initialize(self):      return self._do(self.process.initialize)
    def start_process(self):   return self._do(self.process.start_process)
    def stop_process(self):    return self._do(self.process.stop_process)
    def emergency_stop(self):  return self._do(self.process.emergency_stop)

    # ------------------------------------------------------------------
    # Параметры
    # ------------------------------------------------------------------
    def set_current_limit(self, v): return self._do(self.hw.power_supply_48v.set_current_limit, v)
    def set_speed(self, v):         return self._do(self.process.set_motor_speed, v)
    def move_to(self, v):           return self._do(self.process.move_motor_to, v)
    def set_max_temp(self, v):      return self._do(self.hw.temperature_sensor.set_max_temperature, v)
    def set_load_power(self, on):   return self._do(self.hw.transistors.set_load_power, on)
    def reset_motor(self):          return self._do(self.hw.stepper_motor.reset_position)
    def stop_motor(self):           return self._do(self.hw.stepper_motor.stop)

    def set_channel(self, channel: TransistorChannel, on: bool):
        fn = self.hw.transistors.turn_on if on else self.hw.transistors.turn_off
        return self._do(fn, channel)

    def acdc_on(self):  return self._do(self.hw.ac_dc_converter.turn_on)
    def acdc_off(self): return self._do(self.hw.ac_dc_converter.turn_off)

    # ------------------------------------------------------------------
    # Подготовка ёмкости — реальные операции устройства (не стенд)
    # ------------------------------------------------------------------
    def fill_tank(self):             return self._do(self.hw.polishing_tank.fill)
    def drain_tank(self):            return self._do(self.hw.polishing_tank.drain)
    def connect_electrodes(self):    return self._do(self.hw.polishing_tank.connect_electrodes)
    def disconnect_electrodes(self): return self._do(self.hw.polishing_tank.disconnect_electrodes)

    # ------------------------------------------------------------------
    # Имитация сигналов датчиков (TestHarness — только стенд)
    # ------------------------------------------------------------------
    def set_lid(self, closed):       return self._do(self.test.set_lid, closed)
    def set_temperature(self, v):    return self._do(self.test.set_temperature, v)

    def simulate_current(self, v):
        result = self.test.simulate_current(v)
        self.process.check_safety()  # стаб не делает это сам для тока
        self.stateChanged.emit()
        return result

    # ------------------------------------------------------------------
    # Мониторинг (вызывать периодически из QTimer)
    # ------------------------------------------------------------------
    def poll(self) -> None:
        self.process.check_safety()
        self.stateChanged.emit()

    def system_status(self) -> str:
        return self.process.get_system_status()

    # ------------------------------------------------------------------
    # Снимок состояния для UI (плоский dict — UI не лезет внутрь стабов)
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        hw, p = self.hw, self.process
        ch = hw.transistors.channels
        return {
            "initialized": p.initialized,
            "process_running": p.process_running,
            "acdc": {
                "on": hw.ac_dc_converter.is_on(),
                "vin": hw.ac_dc_converter.get_input_voltage(),
                "vout": hw.ac_dc_converter.get_output_voltage(),
            },
            "trans": {
                "load_power": hw.transistors.load_power_enabled,
                "ground": hw.transistors.common_ground,
                "channels": {
                    c.value: {
                        "sig": ch[c]["control_signal"],
                        "open": ch[c]["transistor_open"],
                        "load": ch[c]["load_enabled"],
                        "desc": ch[c]["description"],
                    } for c in ch
                },
            },
            "vibro": {"on": hw.vibro_table.is_vibrating()},
            "psu": {
                "on": hw.power_supply_48v.is_on(),
                "v": hw.power_supply_48v.get_voltage(),
                "i": hw.power_supply_48v.get_current(),
                "limit": hw.power_supply_48v.current_limit,
                "max_limit": hw.power_supply_48v.max_current_limit,
                "tripped": hw.power_supply_48v.overcurrent_tripped,
            },
            "lid": {"closed": hw.lid_sensor.is_closed()},
            "driver": {
                "enabled": hw.stepper_driver.enabled,
                "moving": hw.stepper_driver.moving,
                "speed": hw.stepper_driver.speed,
            },
            "motor": {
                "pos": hw.stepper_motor.get_position(),
                "min": hw.stepper_motor.min_position,
                "max": hw.stepper_motor.max_position,
                "moving": hw.stepper_motor.moving,
            },
            "tank": {
                "filled": hw.polishing_tank.filled,
                "anode": hw.polishing_tank.anode_connected,
                "cathode": hw.polishing_tank.cathode_connected,
                "running": hw.polishing_tank.is_process_running(),
                "volt": hw.polishing_tank.get_applied_voltage(),
                "ready": hw.polishing_tank.is_ready(),
            },
            "temp": {
                "t": hw.temperature_sensor.read_temperature(),
                "max": hw.temperature_sensor.max_temperature,
                "over": hw.temperature_sensor.is_overheated(),
            },
        }

    def alarms(self) -> list:
        """Активные аварии/предупреждения: список (severity, text, source)."""
        s = self.snapshot()
        out = []
        if not s["lid"]["closed"]:
            out.append(("err", "Крышка открыта", "lid_sensor.is_open()"))
        if s["temp"]["over"]:
            out.append(("err", f"Перегрев: {s['temp']['t']:.1f} °C > {s['temp']['max']:.0f} °C",
                        "temperature_sensor.is_overheated()"))
        if s["psu"]["tripped"]:
            out.append(("err", "Перегрузка по току источника 48 В",
                        "power_supply_48v.overcurrent_tripped"))
        if s["process_running"] and not s["psu"]["on"]:
            out.append(("err", "Источник 48 В отключился во время процесса",
                        "power_supply_48v.is_on()"))
        if not s["acdc"]["on"]:
            out.append(("warn", "Нет питания AC/DC — запуск невозможен",
                        "ac_dc_converter.is_on()"))
        if s["acdc"]["on"] and not s["tank"]["ready"] and not s["process_running"]:
            out.append(("warn", "Ёмкость для полировки не готова",
                        "polishing_tank.is_ready()"))
        psu = s["psu"]
        if psu["on"] and psu["limit"] * 0.9 <= psu["i"] <= psu["limit"]:
            out.append(("warn", f"Ток близок к лимиту: {psu['i']:.1f} / {psu['limit']:.1f} А",
                        "power_supply_48v.get_current()"))
        return out

    # ------------------------------------------------------------------
    # служебное
    # ------------------------------------------------------------------
    def _do(self, fn, *args):
        result = fn(*args)
        self.stateChanged.emit()
        return result


# Единый общий контроллер на всё приложение (шапка и страница «Оборудование»
# должны видеть одно и то же состояние). Создаётся лениво.
_INSTANCE: "DeviceController | None" = None


def controller() -> DeviceController:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DeviceController()
    return _INSTANCE
