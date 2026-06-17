"""
Заглушки оборудования лазерно-эрозионного робота.

Архитектура:
    Hardware*Stub          — отдельные устройства (соответствуют блокам схемы)
    HardwareRegistry       — владеет всеми устройствами, ничего не решает
    ProcessController      — бизнес-логика (старт/стоп/авария/мониторинг)
    TestHarness            — мок-методы для имитации физических событий
                             (открытие крышки, нагрев и т.п.) — НЕ часть прошивки

Состав оборудования (после перехода на лазерную эрозию):
    AC/DC преобразователь            — питание логики 24 В;
    Блок транзисторных ключей        — коммутация силовых нагрузок (48 В);
    Источник напряжения 48 В         — силовое питание лазера и подачи стола;
    Лазерный излучатель              — рабочий инструмент (параметры с вкладки
                                       «Лазером»): мощность, частота, фокус,
                                       длительность импульса, время воздействия,
                                       режим излучения;
    Шаговый двигатель + драйвер      — позиционирование головки по двум осям X/Z;
    Координатный стол + контроллер   — подача заготовки по одной оси;
    Датчик крышки, датчик температуры.

Все сообщения идут через logger "hardware" — UI подписывается на этот логгер
и показывает сообщения в своём окне.
"""

from __future__ import annotations

import logging
import math
import threading
from enum import Enum
from typing import Optional

logger = logging.getLogger("hardware")


# ============================================================
# Константы и перечисления
# ============================================================

class TransistorChannel(str, Enum):
    """Каналы блока транзисторных ключей (силовые нагрузки 48 В)."""
    TABLE_FEED = "table_feed"     # питание привода подачи координатного стола
    POWER_48V  = "power_48v"      # разрешение питания источника 48 В
    LASER      = "laser"          # подача 48 В на лазерный излучатель


class LaserMode(str, Enum):
    """Режимы излучения лазера (совпадают с подписями на вкладке «Лазером»)."""
    CONTINUOUS = "Непрерывный"
    PULSED     = "Импульсный"
    SINGLE     = "Одиночный импульс"


# ============================================================
# AC/DC преобразователь
# ============================================================

class AcDcConverterStub:
    """
    AC/DC преобразователь 220 В -> 24 В.
    Физически включается тумблером на корпусе — программно его включить нельзя.
    Поэтому по умолчанию считаем, что он УЖЕ включён (стенд воткнут в розетку).
    """

    def __init__(self, initially_on: bool = True):
        self.name = "AC/DC преобразователь"
        self.powered_on = initially_on
        self.input_voltage = 220
        self.output_voltage = 24
        if initially_on:
            logger.info(f"{self.name}: запитан от сети (по умолчанию)")

    def turn_on(self) -> bool:
        self.powered_on = True
        logger.info(f"{self.name}: включен")
        return True

    def turn_off(self) -> bool:
        self.powered_on = False
        logger.info(f"{self.name}: выключен")
        return True

    def is_on(self) -> bool:
        return self.powered_on

    def get_input_voltage(self) -> int:
        return self.input_voltage if self.powered_on else 0

    def get_output_voltage(self) -> int:
        return self.output_voltage if self.powered_on else 0

    def get_status(self) -> str:
        if self.powered_on:
            return (f"AC/DC преобразователь включен. "
                    f"Вход: {self.input_voltage} В, выход: {self.output_voltage} В.")
        return "AC/DC преобразователь выключен."

    def __repr__(self) -> str:
        return f"<AcDcConverter on={self.powered_on}>"


# ============================================================
# Блок транзисторных ключей
# ============================================================

class TransistorSwitchBlockStub:
    """
    Блок транзисторных ключей.
    Транзистор открыт, когда: есть общая земля И на затвор подан управляющий сигнал.
    Питание на нагрузку идёт, когда: транзистор открыт И есть силовое питание.
    """

    def __init__(self):
        self.name = "Блок транзисторных ключей"
        self.common_ground = True
        self.load_power_enabled = False
        self.channels: dict[TransistorChannel, dict] = {
            TransistorChannel.TABLE_FEED: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Питание привода подачи стола",
            },
            TransistorChannel.POWER_48V: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Разрешение питания источника 48 В",
            },
            TransistorChannel.LASER: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Подача 48 В на лазерный излучатель",
            },
        }

    def set_load_power(self, state: bool) -> bool:
        self.load_power_enabled = bool(state)
        self._update_all_channels()
        logger.info(f"{self.name}: силовое питание нагрузок "
                    f"{'включено' if state else 'отключено'}")
        return True

    def set_control_signal(self, channel: TransistorChannel, signal: int) -> bool:
        if channel not in self.channels:
            logger.error(f"{self.name}: канала '{channel}' не существует")
            return False
        if signal not in (0, 1):
            logger.error(f"{self.name}: управляющий сигнал должен быть 0 или 1")
            return False

        self.channels[channel]["control_signal"] = signal
        self._update_channel(channel)
        logger.info(f"{self.name}: канал {channel.value} — "
                    f"{'открыт' if signal == 1 else 'закрыт'}")
        return True

    def turn_on(self, channel: TransistorChannel) -> bool:
        return self.set_control_signal(channel, 1)

    def turn_off(self, channel: TransistorChannel) -> bool:
        return self.set_control_signal(channel, 0)

    def turn_off_all(self) -> bool:
        for channel in self.channels:
            self.channels[channel]["control_signal"] = 0
            self._update_channel(channel)
        logger.info(f"{self.name}: все транзисторы закрыты")
        return True

    def is_channel_on(self, channel: TransistorChannel) -> bool:
        return self.channels.get(channel, {}).get("load_enabled", False)

    def is_transistor_open(self, channel: TransistorChannel) -> bool:
        return self.channels.get(channel, {}).get("transistor_open", False)

    def _update_channel(self, channel: TransistorChannel) -> None:
        data = self.channels[channel]
        data["transistor_open"] = self.common_ground and data["control_signal"] == 1
        data["load_enabled"] = data["transistor_open"] and self.load_power_enabled

    def _update_all_channels(self) -> None:
        for channel in self.channels:
            self._update_channel(channel)

    def get_status(self) -> str:
        lines = [
            f"Силовое питание нагрузок: {'есть' if self.load_power_enabled else 'нет'}",
            f"Общая земля: {'есть' if self.common_ground else 'нет'}",
        ]
        for ch, data in self.channels.items():
            lines.append(
                f"- {ch.value} ({data['description']}): "
                f"сигнал={data['control_signal']}, "
                f"транзистор={'открыт' if data['transistor_open'] else 'закрыт'}, "
                f"нагрузка={'вкл' if data['load_enabled'] else 'выкл'}"
            )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<TransistorBlock load_power={self.load_power_enabled}>"


# ============================================================
# Источник напряжения 48 В
# ============================================================

class PowerSupply48VStub:

    def __init__(self, current_limit: float = 5.0, max_current_limit: float = 10.0):
        self.name = "Источник напряжения 48 В"
        self.powered_on = False
        self.voltage = 48.0
        self.current = 0.0
        self.current_limit = current_limit
        self.max_current_limit = max_current_limit
        self.overcurrent_tripped = False

    def turn_on(self, power_allowed: bool = True) -> bool:
        if not power_allowed:
            logger.error(f"{self.name}: питание через транзисторный ключ не разрешено")
            return False
        self.overcurrent_tripped = False
        self.powered_on = True
        self.current = min(1.2, self.current_limit)
        logger.info(f"{self.name}: включен, {self.voltage} В")
        return True

    def turn_off(self) -> bool:
        self.powered_on = False
        self.current = 0.0
        logger.info(f"{self.name}: выключен")
        return True

    def is_on(self) -> bool:
        return self.powered_on

    def get_voltage(self) -> float:
        return self.voltage if self.powered_on else 0.0

    def get_current(self) -> float:
        """Чистый геттер — никаких побочных эффектов."""
        return self.current if self.powered_on else 0.0

    def check_overcurrent(self) -> bool:
        """
        Проверка перегрузки. Если ток превышен — выключает источник
        и поднимает флаг аварии. Вызывается из мониторинга процесса.
        Возвращает True, если перегрузки нет.
        """
        if not self.powered_on:
            return True
        if self.current > self.current_limit:
            self.overcurrent_tripped = True
            logger.warning(f"{self.name}: авария — ток {self.current} А "
                           f"превысил лимит {self.current_limit} А")
            self.turn_off()
            return False
        return True

    def set_current_limit(self, value: float) -> bool:
        if value <= 0:
            logger.error(f"{self.name}: лимит тока должен быть > 0")
            return False
        if value > self.max_current_limit:
            logger.error(f"{self.name}: лимит не может быть больше "
                         f"{self.max_current_limit} А")
            return False
        self.current_limit = float(value)
        if self.powered_on:
            self.current = min(self.current, self.current_limit)
        logger.info(f"{self.name}: лимит тока {self.current_limit} А")
        return True

    def simulate_current_draw(self, value: float) -> bool:
        """Тестовая утилита — задать значение тока (использует TestHarness)."""
        if value < 0:
            logger.error(f"{self.name}: ток не может быть отрицательным")
            return False
        self.current = float(value) if self.powered_on else 0.0
        return self.check_overcurrent()

    def get_status(self) -> str:
        if self.powered_on:
            return (f"Источник 48 В: {self.voltage} В, "
                    f"ток {self.current} А, лимит {self.current_limit} А")
        return f"Источник 48 В выключен. Лимит: {self.current_limit} А"

    def __repr__(self) -> str:
        return f"<PSU48V on={self.powered_on} V={self.voltage} I={self.current}>"


# ============================================================
# Датчик крышки
# ============================================================

class LidSensorStub:

    def __init__(self, initially_closed: bool = True):
        self.name = "Датчик закрытия крышки"
        self.lid_closed = initially_closed

    def is_closed(self) -> bool:
        return self.lid_closed

    def is_open(self) -> bool:
        return not self.lid_closed

    def set_lid_state(self, closed: bool) -> bool:
        self.lid_closed = bool(closed)
        logger.info(f"{self.name}: крышка "
                    f"{'закрыта' if self.lid_closed else 'открыта'}")
        return True

    def get_status(self) -> str:
        return f"Крышка {'закрыта' if self.lid_closed else 'открыта'}"

    def __repr__(self) -> str:
        return f"<LidSensor closed={self.lid_closed}>"


# ============================================================
# Драйвер шагового двигателя (две оси X/Z)
# ============================================================

class StepperMotorDriverStub:

    def __init__(self):
        self.name = "Драйвер шагового двигателя"
        self.enabled = False
        self.moving = False
        self.speed = 100
        self.direction = 0

    def enable(self, power_available: bool = True) -> bool:
        if not power_available:
            logger.error(f"{self.name}: нет питания от AC/DC преобразователя")
            return False
        self.enabled = True
        logger.info(f"{self.name}: включен")
        return True

    def disable(self) -> bool:
        self.stop()
        self.enabled = False
        logger.info(f"{self.name}: выключен")
        return True

    def set_speed(self, value: int) -> bool:
        if value <= 0:
            logger.error(f"{self.name}: скорость должна быть > 0")
            return False
        self.speed = int(value)
        logger.info(f"{self.name}: скорость {self.speed} шаг/с")
        return True

    def start_motion(self, direction: int) -> bool:
        if not self.enabled:
            logger.error(f"{self.name}: драйвер выключен")
            return False
        if direction not in (-1, 1):
            logger.error(f"{self.name}: направление должно быть 1 или -1")
            return False
        self.direction = direction
        self.moving = True
        logger.info(f"{self.name}: движение "
                    f"{'вперёд' if direction == 1 else 'назад'}")
        return True

    def stop(self) -> bool:
        self.moving = False
        self.direction = 0
        return True

    def get_status(self) -> str:
        if not self.enabled:
            return f"Драйвер выключен. Скорость: {self.speed} шаг/с"
        if self.moving:
            return f"Драйвер: движение, скорость {self.speed} шаг/с"
        return f"Драйвер включен, мотор остановлен. Скорость: {self.speed} шаг/с"

    def __repr__(self) -> str:
        return f"<StepperDriver enabled={self.enabled} moving={self.moving}>"


# ============================================================
# Шаговый двигатель — позиционирование головки по двум осям X/Z
# ============================================================

class StepperMotorStub:
    """
    Двухосевой шаговый двигатель (оси X и Z) позиционирования лазерной головки.
    Головка перемещается в горизонтали (X) и по высоте (Z); подача заготовки по
    оси Y выполняется отдельно координатным столом.
    Движение может быть:
      - мгновенным (по умолчанию) — для unit-тестов;
      - симулированным в фоне (set_async_motion) — для UI, чтобы не блокировать.
    Обе оси перемещаются в одном фоновом ходе; время хода — по длинной оси.
    """

    AXES = ("x", "z")

    def __init__(self, max_position: int = 1000, min_position: int = 0):
        self.name = "Шаговый двигатель (X/Z)"
        self.driver: Optional[StepperMotorDriverStub] = None
        self.moving = False
        self.pos: dict[str, int] = {"x": 0, "z": 0}
        self.max_position = max_position
        self.min_position = min_position
        self.async_motion = False
        self.motion_delay_scale = 0.001
        self._motion_thread: Optional[threading.Thread] = None
        self._stop_motion = threading.Event()

    def attach_driver(self, driver: StepperMotorDriverStub) -> bool:
        self.driver = driver
        logger.info(f"{self.name}: драйвер назначен")
        return True

    def set_async_motion(self, enabled: bool, scale: float = 0.001) -> bool:
        """Если True, движение происходит в фоне и не блокирует вызывающий поток."""
        self.async_motion = bool(enabled)
        self.motion_delay_scale = max(0.0, float(scale))
        return True

    def _can_move(self) -> bool:
        if self.driver is None:
            logger.error(f"{self.name}: драйвер не назначен")
            return False
        if not self.driver.enabled:
            logger.error(f"{self.name}: драйвер выключен")
            return False
        return True

    def _in_range(self, value: int) -> bool:
        return self.min_position <= value <= self.max_position

    def move_to(self, x: Optional[int] = None, z: Optional[int] = None) -> bool:
        """Переместить головку в точку (X, Z). None по оси — оставить как есть."""
        if not self._can_move():
            return False
        tx = self.pos["x"] if x is None else int(x)
        tz = self.pos["z"] if z is None else int(z)
        for axis, val in (("X", tx), ("Z", tz)):
            if not self._in_range(val):
                logger.error(f"{self.name}: позиция {axis}={val} вне диапазона "
                             f"[{self.min_position}, {self.max_position}]")
                return False

        dx, dz = tx - self.pos["x"], tz - self.pos["z"]
        if dx == 0 and dz == 0:
            return True

        direction = 1 if (dx if dx != 0 else dz) > 0 else -1
        if not self.driver.start_motion(direction):
            return False

        self.moving = True
        steps = max(abs(dx), abs(dz))
        logger.info(f"{self.name}: перемещение в X={tx}, Z={tz}")

        if self.async_motion:
            self._start_async_motion(tx, tz, steps)
        else:
            self._finish_motion(tx, tz)
        return True

    def move_axis(self, axis: str, position: int) -> bool:
        """Переместить одну ось ('x' или 'z') в заданную позицию."""
        axis = axis.lower()
        if axis not in self.AXES:
            logger.error(f"{self.name}: ось '{axis}' не существует")
            return False
        return self.move_to(**{axis: int(position)})

    def _finish_motion(self, tx: int, tz: int) -> None:
        self.pos["x"], self.pos["z"] = tx, tz
        self.moving = False
        if self.driver:
            self.driver.stop()
        logger.info(f"{self.name}: позиция X={tx}, Z={tz}")

    def _start_async_motion(self, tx: int, tz: int, steps_count: int) -> None:
        self._stop_motion.clear()

        def worker():
            delay = (steps_count / max(self.driver.speed, 1)
                     * self.motion_delay_scale)
            if self._stop_motion.wait(timeout=delay):
                logger.info(f"{self.name}: движение прервано")
                self.moving = False
                if self.driver:
                    self.driver.stop()
            else:
                self._finish_motion(tx, tz)

        self._motion_thread = threading.Thread(target=worker, daemon=True)
        self._motion_thread.start()

    def stop(self) -> bool:
        self._stop_motion.set()
        if self._motion_thread and self._motion_thread.is_alive():
            self._motion_thread.join(timeout=1.0)
        self.moving = False
        if self.driver:
            self.driver.stop()
        return True

    def get_position(self) -> dict:
        return dict(self.pos)

    def reset_position(self) -> bool:
        if self.moving:
            logger.error(f"{self.name}: нельзя сбросить позицию во время движения")
            return False
        self.pos["x"] = self.pos["z"] = 0
        return True

    def get_status(self) -> str:
        if self.driver is None:
            return "Шаговый двигатель: драйвер не назначен"
        state = "движется" if self.moving else "остановлен"
        return f"Шаговый двигатель {state}, позиция X={self.pos['x']}, Z={self.pos['z']}"

    def __repr__(self) -> str:
        return f"<StepperMotor x={self.pos['x']} z={self.pos['z']} moving={self.moving}>"


# ============================================================
# Контроллер координатного стола
# ============================================================

class TableControllerStub:
    """
    Контроллер координатного стола (одна ось подачи).
    Управляет приводом подачи: выходит на связь (online) по логическому питанию,
    разрешает движение (enabled) при наличии питания, задаёт скорость и
    направление. Аналог драйвера ШД, но для отдельного привода подачи стола.
    """

    def __init__(self):
        self.name = "Контроллер стола"
        self.online = False        # есть ли связь с контроллером
        self.enabled = False       # разрешено ли движение
        self.moving = False
        self.speed = 100
        self.direction = 0

    def connect(self) -> bool:
        self.online = True
        logger.info(f"{self.name}: на связи")
        return True

    def disconnect(self) -> bool:
        self.disable()
        self.online = False
        logger.info(f"{self.name}: связь потеряна")
        return True

    def enable(self, power_available: bool = True) -> bool:
        if not self.online:
            logger.error(f"{self.name}: нет связи с контроллером")
            return False
        if not power_available:
            logger.error(f"{self.name}: нет питания")
            return False
        self.enabled = True
        logger.info(f"{self.name}: движение разрешено")
        return True

    def disable(self) -> bool:
        self.stop()
        self.enabled = False
        return True

    def set_speed(self, value: int) -> bool:
        if value <= 0:
            logger.error(f"{self.name}: скорость должна быть > 0")
            return False
        self.speed = int(value)
        logger.info(f"{self.name}: скорость {self.speed} шаг/с")
        return True

    def start_motion(self, direction: int) -> bool:
        if not self.enabled:
            logger.error(f"{self.name}: движение не разрешено")
            return False
        if direction not in (-1, 1):
            logger.error(f"{self.name}: направление должно быть 1 или -1")
            return False
        self.direction = direction
        self.moving = True
        return True

    def stop(self) -> bool:
        self.moving = False
        self.direction = 0
        return True

    def get_status(self) -> str:
        if not self.online:
            return "Контроллер стола: нет связи"
        if not self.enabled:
            return f"Контроллер стола: на связи, движение запрещено. Скорость: {self.speed} шаг/с"
        if self.moving:
            return f"Контроллер стола: движение, скорость {self.speed} шаг/с"
        return f"Контроллер стола: готов, скорость {self.speed} шаг/с"

    def __repr__(self) -> str:
        return f"<TableController online={self.online} enabled={self.enabled}>"


# ============================================================
# Координатный стол — подача заготовки по одной оси
# ============================================================

class PositioningTableStub:
    """
    Координатный стол подачи заготовки по оси Y. Движется по ОДНОЙ оси,
    перемещением управляет отдельный контроллер (TableControllerStub).
    Движение может быть мгновенным (unit-тесты) или фоновым (set_async_motion) —
    чтобы не блокировать UI.
    """

    def __init__(self, max_position: int = 500, min_position: int = 0):
        self.name = "Координатный стол (ось Y)"
        self.controller: Optional[TableControllerStub] = None
        self.moving = False
        self.position = 0
        self.max_position = max_position
        self.min_position = min_position
        self.async_motion = False
        self.motion_delay_scale = 0.001
        self._motion_thread: Optional[threading.Thread] = None
        self._stop_motion = threading.Event()

    def attach_controller(self, controller: TableControllerStub) -> bool:
        self.controller = controller
        logger.info(f"{self.name}: контроллер назначен")
        return True

    def set_async_motion(self, enabled: bool, scale: float = 0.001) -> bool:
        self.async_motion = bool(enabled)
        self.motion_delay_scale = max(0.0, float(scale))
        return True

    def _can_move(self) -> bool:
        if self.controller is None:
            logger.error(f"{self.name}: контроллер не назначен")
            return False
        if not self.controller.enabled:
            logger.error(f"{self.name}: контроллер не разрешает движение")
            return False
        return True

    def move_to_position(self, position: int) -> bool:
        position = int(position)
        if not self.min_position <= position <= self.max_position:
            logger.error(f"{self.name}: позиция {position} вне диапазона "
                         f"[{self.min_position}, {self.max_position}]")
            return False
        return self.move_steps(position - self.position)

    def move_steps(self, steps: int) -> bool:
        if not self._can_move():
            return False
        steps = int(steps)
        if steps == 0:
            return True

        new_position = self.position + steps
        if not self.min_position <= new_position <= self.max_position:
            logger.error(f"{self.name}: целевая позиция вне диапазона")
            return False

        direction = 1 if steps > 0 else -1
        if not self.controller.start_motion(direction):
            return False

        self.moving = True
        logger.info(f"{self.name}: подача на {steps} шагов")

        if self.async_motion:
            self._start_async_motion(new_position, abs(steps))
        else:
            self._finish_motion(new_position)
        return True

    def _finish_motion(self, target: int) -> None:
        self.position = target
        self.moving = False
        if self.controller:
            self.controller.stop()
        logger.info(f"{self.name}: позиция {self.position}")

    def _start_async_motion(self, target: int, steps_count: int) -> None:
        self._stop_motion.clear()

        def worker():
            delay = (steps_count / max(self.controller.speed, 1)
                     * self.motion_delay_scale)
            if self._stop_motion.wait(timeout=delay):
                logger.info(f"{self.name}: подача прервана")
                self.moving = False
                if self.controller:
                    self.controller.stop()
            else:
                self._finish_motion(target)

        self._motion_thread = threading.Thread(target=worker, daemon=True)
        self._motion_thread.start()

    def stop(self) -> bool:
        self._stop_motion.set()
        if self._motion_thread and self._motion_thread.is_alive():
            self._motion_thread.join(timeout=1.0)
        self.moving = False
        if self.controller:
            self.controller.stop()
        return True

    def get_position(self) -> int:
        return self.position

    def reset_position(self) -> bool:
        if self.moving:
            logger.error(f"{self.name}: нельзя сбросить позицию во время движения")
            return False
        self.position = 0
        return True

    def get_status(self) -> str:
        state = "движется" if self.moving else "остановлен"
        return f"Координатный стол {state}, позиция: {self.position}"

    def __repr__(self) -> str:
        return f"<PositioningTable pos={self.position} moving={self.moving}>"


# ============================================================
# Лазерный излучатель — рабочий инструмент
# ============================================================

class LaserStub:
    """
    Лазерный излучатель — рабочий инструмент эрозионной обработки.
    Заменяет прежнюю ёмкость для полировки с электродами (анод/катод).

    Параметры берутся с вкладки «Лазером»:
        power     — мощность, Вт              (0 … 500)
        frequency — частота импульсов, Гц      (0 … 100000)
        focus     — фокусное смещение, мкм     (-5000 … 5000)
        pulse     — длительность импульса, мкс (0 … 1000)
        exposure  — время воздействия, мс      (0 … 10000)
        mode      — режим излучения            (LaserMode)

    Излучение включается, когда задана мощность (> 0) И подано силовое питание
    (48 В через транзисторный ключ LASER).
    """

    PARAM_RANGES = {
        "power":     (0, 500),
        "frequency": (0, 100000),
        "focus":     (-5000, 5000),
        "pulse":     (0, 1000),
        "exposure":  (0, 10000),
    }
    PARAM_UNITS = {
        "power": "Вт", "frequency": "Гц", "focus": "мкм",
        "pulse": "мкс", "exposure": "мс",
    }

    def __init__(self):
        self.name = "Лазерный излучатель"
        self.powered = False        # подано ли силовое питание (48 В)
        self.emitting = False       # идёт ли излучение
        self.power = 0
        self.frequency = 0
        self.focus = 0
        self.pulse = 0
        self.exposure = 0
        self.mode = LaserMode.CONTINUOUS

    def set_param(self, key: str, value) -> bool:
        if key not in self.PARAM_RANGES:
            logger.error(f"{self.name}: неизвестный параметр '{key}'")
            return False
        lo, hi = self.PARAM_RANGES[key]
        value = int(value)
        if not lo <= value <= hi:
            logger.error(f"{self.name}: {key}={value} вне диапазона [{lo}, {hi}]")
            return False
        setattr(self, key, value)
        unit = self.PARAM_UNITS.get(key, "")
        logger.info(f"{self.name}: {key} = {value} {unit}".rstrip())
        return True

    def set_mode(self, mode) -> bool:
        try:
            self.mode = LaserMode(mode) if not isinstance(mode, LaserMode) else mode
        except ValueError:
            logger.error(f"{self.name}: неизвестный режим '{mode}'")
            return False
        logger.info(f"{self.name}: режим — {self.mode.value.lower()}")
        return True

    def is_ready(self) -> bool:
        """Готов к излучению, если задана ненулевая мощность."""
        return self.power > 0

    def start_emission(self, power_applied: bool = True) -> bool:
        if self.power <= 0:
            logger.error(f"{self.name}: мощность не задана")
            return False
        if not power_applied:
            logger.error(f"{self.name}: нет силового питания (транзисторный ключ закрыт)")
            return False
        self.powered = True
        self.emitting = True
        logger.info(f"{self.name}: излучение включено, "
                    f"{self.power} Вт, режим {self.mode.value.lower()}")
        return True

    def stop_emission(self) -> bool:
        self.emitting = False
        self.powered = False
        logger.info(f"{self.name}: излучение выключено")
        return True

    def is_emitting(self) -> bool:
        return self.emitting

    def get_status(self) -> str:
        if self.emitting:
            return (f"Лазер: излучение {self.power} Вт, {self.frequency} Гц, "
                    f"режим {self.mode.value.lower()}")
        params = (f"мощность={self.power} Вт, частота={self.frequency} Гц, "
                  f"фокус={self.focus} мкм, импульс={self.pulse} мкс, "
                  f"воздействие={self.exposure} мс, режим {self.mode.value.lower()}")
        return f"Лазер: излучение выключено ({params})"

    def __repr__(self) -> str:
        return (f"<Laser emitting={self.emitting} P={self.power}Вт "
                f"f={self.frequency}Гц mode={self.mode.value}>")


# ============================================================
# Датчик температуры
# ============================================================

class TemperatureSensorStub:

    def __init__(self, initial: float = 25.0, max_temperature: float = 60.0):
        self.name = "Датчик температуры"
        self.temperature = initial
        self.max_temperature = max_temperature

    def read_temperature(self) -> float:
        return self.temperature

    def set_temperature(self, value: float) -> bool:
        self.temperature = float(value)
        return True

    def is_overheated(self) -> bool:
        return self.temperature > self.max_temperature

    def set_max_temperature(self, value: float) -> bool:
        if value <= 0:
            logger.error(f"{self.name}: макс. температура должна быть > 0")
            return False
        self.max_temperature = float(value)
        return True

    def get_status(self) -> str:
        warn = " ВНИМАНИЕ: перегрев!" if self.is_overheated() else ""
        return f"Температура: {self.temperature} °C (max {self.max_temperature}).{warn}"

    def __repr__(self) -> str:
        return f"<TempSensor t={self.temperature} max={self.max_temperature}>"


# ============================================================
# HardwareRegistry — просто владеет всеми устройствами
# ============================================================

class HardwareRegistry:
    """
    Контейнер с устройствами. Сам ничего не решает.
    ProcessController и TestHarness работают через него.
    """

    def __init__(
        self,
        stepper_speed: int = 150,
        table_speed: int = 100,
        current_limit: float = 8.0,
        max_temperature: float = 80.0,
        initial_temperature: float = 25.0,
        laser_power_at_start: int = 200,
        ac_dc_initially_on: bool = True,
        lid_initially_closed: bool = True,
    ):
        self.ac_dc_converter   = AcDcConverterStub(initially_on=ac_dc_initially_on)
        self.transistors       = TransistorSwitchBlockStub()
        self.power_supply_48v  = PowerSupply48VStub(current_limit=current_limit)
        self.lid_sensor        = LidSensorStub(initially_closed=lid_initially_closed)
        self.stepper_driver    = StepperMotorDriverStub()
        self.stepper_motor     = StepperMotorStub()
        self.table_controller  = TableControllerStub()
        self.table             = PositioningTableStub()
        self.laser             = LaserStub()
        self.temperature_sensor = TemperatureSensorStub(
            initial=initial_temperature, max_temperature=max_temperature,
        )

        # Заводская настройка под обработку СТАЛИ: импульсный режим и параметры
        # лазера, подобранные под лазерно-эрозионную обработку стальной заготовки.
        # Видны в снимке сразу при запуске — вкладки «Лазером» и «Параметры
        # устройства» открываются уже заполненными под сталь.
        self.laser.set_mode(LaserMode.PULSED)
        self.laser.set_param("power", laser_power_at_start)  # 200 Вт
        self.laser.set_param("frequency", 20000)             # 20 кГц
        self.laser.set_param("focus", 0)                     # фокус на поверхности
        self.laser.set_param("pulse", 100)                   # 100 мкс
        self.laser.set_param("exposure", 1000)               # 1000 мс

        # Исходное положение: головка в центре стола (X) и чуть выше его
        # поверхности (Z), стол — по центру хода подачи (Y).
        m = self.stepper_motor
        m.pos["x"] = (m.min_position + m.max_position) // 2
        m.pos["z"] = m.min_position + round((m.max_position - m.min_position) * 0.15)
        self.table.position = (self.table.min_position + self.table.max_position) // 2

        # Скорости привода и стола под сталь — выставляем сразу, чтобы профиль
        # был виден в снимке ещё до инициализации (повторно подтвердятся в init).
        self.stepper_driver.set_speed(stepper_speed)
        self.table_controller.set_speed(table_speed)

        # Стартовые настройки — применяются при init.
        self._initial_stepper_speed = stepper_speed
        self._initial_table_speed = table_speed
        self._initial_laser_power = laser_power_at_start

    def apply_initial_state(self) -> None:
        """Подготавливает железо в стартовое состояние (вызывается при init)."""
        # Привод головки X/Z
        self.stepper_motor.attach_driver(self.stepper_driver)
        self.stepper_driver.set_speed(self._initial_stepper_speed)
        # Координатный стол + его контроллер
        self.table.attach_controller(self.table_controller)
        self.table_controller.set_speed(self._initial_table_speed)
        # Лазер: стартовая мощность (по умолчанию 0 — задаётся оператором с вкладки)
        if self._initial_laser_power > 0:
            self.laser.set_param("power", self._initial_laser_power)


# ============================================================
# ProcessController — бизнес-логика
# ============================================================

class ProcessController:
    """
    Управление технологическим процессом лазерной эрозии.
    Только то, что относится к старту/остановке/мониторингу —
    никаких мок-методов здесь нет.
    """

    # Номинальная длительность цикла полировки, с (симуляция: реальный рецепт
    # длительности не задаёт — прогресс набирается за это время).
    PROCESS_DURATION = 30.0

    def __init__(self, hardware: HardwareRegistry):
        self.hw = hardware
        self.initialized = False
        self.process_running = False
        self.paused = False          # процесс на паузе (излучение приостановлено)
        self.progress = 0.0          # выполнение цикла, 0…100 %

        # Программа обработки — плоский контур в координатах станка:
        #   точки (X головки, Y стола). По нему ведётся головка во время
        #   процесса (drive_scan), позиция выбирается по доле прогресса.
        self.toolpath: list = []     # [(X, Y), …]
        self._tp_cum: list = []      # накопленная длина пути до каждой точки
        self._tp_total: float = 0.0  # полная длина пути

    # ---- программа обработки (контур) ----
    def set_toolpath(self, points) -> bool:
        """Загрузить контур (список точек (X, Y) в координатах станка)."""
        pts = [(int(p[0]), int(p[1])) for p in (points or [])]
        self.toolpath = pts
        self._tp_cum = [0.0]
        total = 0.0
        for a, b in zip(pts, pts[1:]):
            total += math.hypot(b[0] - a[0], b[1] - a[1])
            self._tp_cum.append(total)
        self._tp_total = total
        logger.info(f"Программа обработки загружена: {len(pts)} точек контура")
        return True

    def clear_toolpath(self) -> bool:
        self.toolpath = []
        self._tp_cum = []
        self._tp_total = 0.0
        logger.info("Программа обработки сброшена")
        return True

    def _point_at(self, frac: float):
        """Точка (X, Y) на контуре по доле пройденного пути frac∈[0..1]."""
        if not self.toolpath:
            return None
        if self._tp_total <= 0:
            return self.toolpath[0]
        target = max(0.0, min(1.0, frac)) * self._tp_total
        # ищем сегмент, на который попадает target
        for i in range(1, len(self._tp_cum)):
            if self._tp_cum[i] >= target:
                seg = self._tp_cum[i] - self._tp_cum[i - 1] or 1.0
                u = (target - self._tp_cum[i - 1]) / seg
                a, b = self.toolpath[i - 1], self.toolpath[i]
                return (int(round(a[0] + (b[0] - a[0]) * u)),
                        int(round(a[1] + (b[1] - a[1]) * u)))
        return self.toolpath[-1]

    # ---- инициализация ----
    def initialize(self) -> bool:
        logger.info("=== Инициализация контроллера ===")

        if not self.hw.ac_dc_converter.is_on():
            logger.error("Нет питания от AC/DC преобразователя")
            return False

        logic_power = self.hw.ac_dc_converter.get_output_voltage() > 0
        if not logic_power:
            logger.error("AC/DC не выдаёт выходное напряжение")
            return False

        # Назначаем приводы и стартовые скорости/параметры
        self.hw.apply_initial_state()
        self.hw.transistors.set_load_power(True)

        # Привод головки X/Z — запитан от логического напряжения, готов к наладке
        if not self.hw.stepper_driver.enable(power_available=logic_power):
            return False

        # Контроллер стола выходит на связь и разрешает наладочные перемещения
        self.hw.table_controller.connect()
        if not self.hw.table_controller.enable(power_available=logic_power):
            return False

        self.initialized = True
        logger.info("=== Контроллер готов к работе ===")
        return True

    # ---- проверки ----
    def _require_initialized(self) -> bool:
        if not self.initialized:
            logger.error("Оборудование не инициализировано")
            return False
        return True

    def _check_start_conditions(self) -> bool:
        if not self._require_initialized():
            return False
        if not self.hw.ac_dc_converter.is_on():
            logger.error("Нет питания AC/DC")
            return False
        if not self.hw.lid_sensor.is_closed():
            logger.error("Крышка открыта — запуск запрещён")
            return False
        if self.hw.temperature_sensor.is_overheated():
            logger.error("Перегрев — запуск запрещён")
            return False
        if not self.hw.laser.is_ready():
            logger.error("Лазер не настроен (мощность 0 Вт)")
            return False
        if not self.hw.table_controller.online:
            logger.error("Контроллер стола не на связи")
            return False
        if not self.toolpath:
            logger.error("Не загружена программа обработки (контур)")
            return False
        return True

    # ---- процесс ----
    def start_process(self) -> bool:
        logger.info("=== Запуск процесса ===")
        if not self._check_start_conditions():
            return False

        t = self.hw.transistors
        t.set_load_power(self.hw.ac_dc_converter.get_output_voltage() > 0)

        # 1) Разрешаем и включаем источник 48 В
        if not t.turn_on(TransistorChannel.POWER_48V):
            return False
        if not self.hw.power_supply_48v.turn_on(
            power_allowed=t.is_channel_on(TransistorChannel.POWER_48V)
        ):
            self.stop_process()
            return False

        # 2) Подаём силовое питание на привод подачи стола
        if not t.turn_on(TransistorChannel.TABLE_FEED):
            self.stop_process(); return False

        # 3) Подаём 48 В на лазер и включаем излучение
        if not t.turn_on(TransistorChannel.LASER):
            self.stop_process(); return False

        power_applied = (
            t.is_channel_on(TransistorChannel.LASER)
            and self.hw.power_supply_48v.is_on()
        )
        if not self.hw.laser.start_emission(power_applied):
            self.stop_process()
            return False

        self.process_running = True
        self.paused = False
        self.progress = 0.0
        # головка встаёт в начало контура (если программа загружена)
        if self.toolpath:
            self.hw.stepper_motor.pos["x"] = self.toolpath[0][0]
            self.hw.table.position = self.toolpath[0][1]
        logger.info("=== Процесс запущен ===")
        return True

    def stop_process(self) -> bool:
        logger.info("=== Остановка процесса ===")
        self.hw.laser.stop_emission()
        self.hw.table.stop()
        self._stop_scan()
        self.hw.transistors.turn_off(TransistorChannel.LASER)
        self.hw.transistors.turn_off(TransistorChannel.TABLE_FEED)
        self.hw.transistors.turn_off(TransistorChannel.POWER_48V)
        self.hw.power_supply_48v.turn_off()
        self.process_running = False
        self.paused = False
        self.progress = 0.0
        logger.info("=== Процесс остановлен ===")
        return True

    def pause_process(self) -> bool:
        """Приостановить процесс: гасим излучение и подачу стола, прогресс замирает."""
        if not self.process_running:
            logger.error("Процесс не запущен — пауза недоступна")
            return False
        if self.paused:
            return True
        self.hw.laser.stop_emission()
        self.hw.table.stop()
        self._stop_scan()
        self.paused = True
        logger.info("=== Процесс приостановлен ===")
        return True

    def resume_process(self) -> bool:
        """Возобновить процесс после паузы: снова включаем излучение."""
        if not self.process_running:
            logger.error("Процесс не запущен — возобновление недоступно")
            return False
        if not self.paused:
            return True
        power_applied = (
            self.hw.transistors.is_channel_on(TransistorChannel.LASER)
            and self.hw.power_supply_48v.is_on()
        )
        if not self.hw.laser.start_emission(power_applied):
            logger.error("Не удалось возобновить излучение")
            return False
        self.paused = False
        logger.info("=== Процесс возобновлён ===")
        return True

    def advance_progress(self, dt: float) -> None:
        """Продвинуть прогресс цикла на dt секунд (вызывается из мониторинга).

        Пока процесс на паузе или не запущен — прогресс не растёт. По достижении
        100 % процесс штатно завершается (stop_process).
        """
        if not self.process_running or self.paused or self.PROCESS_DURATION <= 0:
            return
        self.progress = min(
            100.0, self.progress + dt / self.PROCESS_DURATION * 100.0)
        if self.progress >= 100.0:
            logger.info("=== Процесс завершён (100 %) ===")
            self.stop_process()

    # ---- движение головки по контуру во время процесса ----
    def drive_scan(self) -> None:
        """Вести головку по загруженному контуру, пока идёт обработка.

        Позиция вдоль контура выбирается по доле прогресса: X задаёт головку
        (шаговый привод), Y — координатный стол. Если контур не загружен,
        просто горит индикатор «движется» как признак активной обработки.
        На паузе и вне процесса индикатор гаснет.
        """
        if not self.process_running or self.paused:
            return
        d = self.hw.stepper_driver
        if not d.enabled:
            return
        self.hw.stepper_motor.moving = True
        d.moving = True
        d.direction = 1

        # ведём головку и стол по точке контура для текущей доли прогресса
        pt = self._point_at(self.progress / 100.0)
        if pt is not None:
            self.hw.stepper_motor.pos["x"] = pt[0]
            self.hw.table.position = pt[1]
            self.hw.table.moving = True

    def _stop_scan(self) -> None:
        """Погасить индикатор движения ШД (флаги ШД и драйвера)."""
        self.hw.stepper_motor.moving = False
        self.hw.stepper_driver.moving = False
        self.hw.stepper_driver.direction = 0
        self.hw.table.moving = False

    def emergency_stop(self) -> bool:
        logger.warning("!!! АВАРИЙНАЯ ОСТАНОВКА !!!")
        self.hw.stepper_motor.stop()
        self.hw.stepper_driver.disable()
        self.hw.laser.stop_emission()
        self.hw.table.stop()
        self.hw.table_controller.disable()
        self.hw.transistors.turn_off_all()
        self.hw.power_supply_48v.turn_off()
        self.process_running = False
        self.paused = False
        self.progress = 0.0
        # Авария оставляет железо в обесточенном состоянии (приводы заглушены,
        # ключи и источник выключены), поэтому система больше не считается
        # инициализированной: запуск блокируется до повторной инициализации,
        # которая заново включит приводы и проверит условия.
        self.initialized = False
        return True

    # ---- движение головки X/Z ----
    def move_motor_to(self, x=None, z=None) -> bool:
        if not self._require_initialized():
            return False
        if self.process_running:
            logger.error("Нельзя двигать привод во время процесса")
            return False
        if not self.hw.stepper_driver.enabled:
            self.hw.stepper_driver.enable(
                power_available=self.hw.ac_dc_converter.get_output_voltage() > 0
            )
        return self.hw.stepper_motor.move_to(x, z)

    def set_motor_speed(self, speed: int) -> bool:
        if not self._require_initialized():
            return False
        return self.hw.stepper_driver.set_speed(speed)

    # ---- движение координатного стола ----
    def move_table_to(self, position: int) -> bool:
        if not self._require_initialized():
            return False
        if self.process_running:
            logger.error("Нельзя двигать стол во время процесса")
            return False
        if not self.hw.table_controller.enabled:
            self.hw.table_controller.enable(
                power_available=self.hw.ac_dc_converter.get_output_voltage() > 0
            )
        return self.hw.table.move_to_position(position)

    def set_table_speed(self, speed: int) -> bool:
        if not self._require_initialized():
            return False
        return self.hw.table_controller.set_speed(speed)

    # ---- мониторинг (вызывать периодически) ----
    def check_safety(self) -> bool:
        """Опрос состояния безопасности. Вернёт False, если случилась авария."""
        if not self.process_running:
            return True

        if self.hw.lid_sensor.is_open():
            logger.warning("Крышка открыта во время процесса!")
            self.emergency_stop()
            return False

        if self.hw.temperature_sensor.is_overheated():
            logger.warning("Перегрев во время процесса!")
            self.emergency_stop()
            return False

        if not self.hw.power_supply_48v.check_overcurrent():
            logger.warning("Перегрузка по току!")
            self.emergency_stop()
            return False

        if not self.hw.power_supply_48v.is_on():
            logger.warning("Источник 48 В отключился")
            self.emergency_stop()
            return False

        return True

    # ---- статус целиком ----
    def get_system_status(self) -> str:
        lines = [
            "========== СТАТУС СИСТЕМЫ ==========",
            f"Инициализация: {'выполнена' if self.initialized else 'нет'}",
            f"Процесс: {'запущен' if self.process_running else 'остановлен'}",
            "",
            f"[AC/DC] {self.hw.ac_dc_converter.get_status()}",
            f"[Транзисторы]\n{self.hw.transistors.get_status()}",
            f"[Источник 48 В] {self.hw.power_supply_48v.get_status()}",
            f"[Крышка] {self.hw.lid_sensor.get_status()}",
            f"[Драйвер ШД] {self.hw.stepper_driver.get_status()}",
            f"[ШД X/Z] {self.hw.stepper_motor.get_status()}",
            f"[Контроллер стола] {self.hw.table_controller.get_status()}",
            f"[Стол] {self.hw.table.get_status()}",
            f"[Лазер] {self.hw.laser.get_status()}",
            f"[Температура] {self.hw.temperature_sensor.get_status()}",
            "====================================",
        ]
        return "\n".join(lines)


# ============================================================
# TestHarness — мок-методы для имитации физических событий
# ============================================================

class TestHarness:
    """
    Утилиты для имитации физических событий, которые в реальной системе
    приходят от датчиков (открытие крышки, нагрев, ток источника).

    В реальной прошивке этого класса НЕТ. Он нужен только для проверки
    UI без подключённого железа.
    """

    def __init__(self, hardware: HardwareRegistry,
                 process: Optional[ProcessController] = None):
        self.hw = hardware
        self.process = process  # нужен, чтобы триггерить check_safety после событий

    def set_lid(self, closed: bool) -> bool:
        self.hw.lid_sensor.set_lid_state(closed)
        return self._notify_process()

    def set_temperature(self, value: float) -> bool:
        self.hw.temperature_sensor.set_temperature(value)
        return self._notify_process()

    def simulate_current(self, value: float) -> bool:
        return self.hw.power_supply_48v.simulate_current_draw(value)

    def _notify_process(self) -> bool:
        if self.process is not None:
            return self.process.check_safety()
        return True


# ============================================================
# Совместимость со старым кодом (если где-то использовал старое имя)
# ============================================================

class LaserErosionRobotController:
    """
    Фасад поверх HardwareRegistry + ProcessController + TestHarness,
    сохраняет старый API на случай, если он где-то используется.
    Новый код лучше работать напрямую с тремя классами выше.
    """

    def __init__(self, **kwargs):
        self.hw = HardwareRegistry(**kwargs)
        self.process = ProcessController(self.hw)
        self.test = TestHarness(self.hw, self.process)

        # Прямые ссылки для обратной совместимости
        self.ac_dc_converter   = self.hw.ac_dc_converter
        self.transistors       = self.hw.transistors
        self.power_supply_48v  = self.hw.power_supply_48v
        self.lid_sensor        = self.hw.lid_sensor
        self.stepper_driver    = self.hw.stepper_driver
        self.stepper_motor     = self.hw.stepper_motor
        self.table_controller  = self.hw.table_controller
        self.table             = self.hw.table
        self.laser             = self.hw.laser
        self.temperature_sensor = self.hw.temperature_sensor

    # делегирование методов
    def initialize(self):           return self.process.initialize()
    def start_process(self):        return self.process.start_process()
    def stop_process(self):         return self.process.stop_process()
    def emergency_stop(self):       return self.process.emergency_stop()
    def move_motor_to(self, x=None, z=None): return self.process.move_motor_to(x, z)
    def move_table_to(self, p):     return self.process.move_table_to(p)
    def set_stepper_speed(self, s): return self.process.set_motor_speed(s)
    def set_table_speed(self, s):   return self.process.set_table_speed(s)
    def read_temperature(self):     return self.hw.temperature_sensor.read_temperature()
    def is_lid_closed(self):        return self.hw.lid_sensor.is_closed()
    def check_safety_during_process(self): return self.process.check_safety()
    def get_system_status(self):    return self.process.get_system_status()

    @property
    def initialized(self):    return self.process.initialized
    @property
    def process_running(self): return self.process.process_running

    # мок-методы (для обратной совместимости — но лучше использовать self.test)
    def set_lid_state_mock(self, s):      return self.test.set_lid(s)
    def set_temperature_mock(self, v):    return self.test.set_temperature(v)


# ============================================================
# Самопроверка
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    hw = HardwareRegistry()
    process = ProcessController(hw)
    test = TestHarness(hw, process)

    print(">>> Инициализация")
    process.initialize()

    print("\n>>> Задаём параметры лазера (с вкладки «Лазером»)")
    hw.laser.set_param("power", 500)
    hw.laser.set_param("frequency", 1000)
    hw.laser.set_mode("Импульсный")

    print("\n>>> Запуск процесса")
    process.start_process()

    print("\n>>> Открываем крышку — должна сработать авария")
    test.set_lid(False)

    print("\n>>> Финальный статус")
    print(process.get_system_status())
