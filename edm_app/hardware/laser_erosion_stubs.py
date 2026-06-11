
from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger("hardware")


# ============================================================
# Константы и перечисления
# ============================================================

class TransistorChannel(str, Enum):
    """Каналы блока транзисторных ключей."""
    VIBRO_TABLE   = "vibro_table"
    POWER_48V     = "power_48v"
    POLISHING     = "polishing_cell"


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
            TransistorChannel.VIBRO_TABLE: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Питание вибростола",
            },
            TransistorChannel.POWER_48V: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Разрешение питания источника 48 В",
            },
            TransistorChannel.POLISHING: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Подача 48 В на ёмкость полировки",
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
# Вибростол
# ============================================================

class VibroTableStub:

    def __init__(self):
        self.name = "Вибростол"
        self.power_supplied = False

    def supply_power(self) -> bool:
        self.power_supplied = True
        logger.info(f"{self.name}: питание подано, вибрация началась")
        return True

    def cut_power(self) -> bool:
        self.power_supplied = False
        logger.info(f"{self.name}: питание отключено, вибрация остановлена")
        return True

    def is_vibrating(self) -> bool:
        return self.power_supplied

    def get_status(self) -> str:
        return ("Вибростол: вибрирует" if self.power_supplied
                else "Вибростол: остановлен")

    def __repr__(self) -> str:
        return f"<VibroTable vibrating={self.power_supplied}>"


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
# Драйвер шагового двигателя
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
# Шаговый двигатель — с неблокирующим движением
# ============================================================

class StepperMotorStub:
    """
    Шаговый двигатель. Движение может быть:
      - мгновенным (по умолчанию) — для unit-тестов;
      - симулированным в фоне (set_async_motion) — для UI, чтобы не блокировать.
    """

    def __init__(self, max_position: int = 1000, min_position: int = 0):
        self.name = "Шаговый двигатель"
        self.driver: Optional[StepperMotorDriverStub] = None
        self.moving = False
        self.position = 0
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
        if not self.driver.start_motion(direction):
            return False

        self.moving = True
        logger.info(f"{self.name}: движение на {steps} шагов")

        if self.async_motion:
            self._start_async_motion(new_position, abs(steps))
        else:
            self._do_motion_sync(new_position)

        return True

    def _do_motion_sync(self, target: int) -> None:
        self.position = target
        self.moving = False
        if self.driver:
            self.driver.stop()
        logger.info(f"{self.name}: позиция {self.position}")

    def _start_async_motion(self, target: int, steps_count: int) -> None:
        self._stop_motion.clear()

        def worker():
            delay = (steps_count / max(self.driver.speed, 1)
                     * self.motion_delay_scale)
            if self._stop_motion.wait(timeout=delay):
                logger.info(f"{self.name}: движение прервано")
            else:
                self.position = target
                logger.info(f"{self.name}: позиция {self.position}")
            self.moving = False
            if self.driver:
                self.driver.stop()

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

    def get_position(self) -> int:
        return self.position

    def reset_position(self) -> bool:
        if self.moving:
            logger.error(f"{self.name}: нельзя сбросить позицию во время движения")
            return False
        self.position = 0
        return True

    def get_status(self) -> str:
        if self.driver is None:
            return "Шаговый двигатель: драйвер не назначен"
        state = "движется" if self.moving else "остановлен"
        return f"Шаговый двигатель {state}, позиция: {self.position}"

    def __repr__(self) -> str:
        return f"<StepperMotor pos={self.position} moving={self.moving}>"


# ============================================================
# Ёмкость для полировки
# ============================================================

class PolishingTankStub:

    def __init__(self):
        self.name = "Ёмкость для полировки"
        self.filled = False
        self.anode_connected = False
        self.cathode_connected = False
        self.process_running = False
        self.applied_voltage = 0.0

    def fill(self) -> bool:
        self.filled = True
        logger.info(f"{self.name}: заполнена рабочей жидкостью")
        return True

    def drain(self) -> bool:
        if self.process_running:
            logger.error(f"{self.name}: нельзя сливать во время процесса")
            return False
        self.filled = False
        logger.info(f"{self.name}: жидкость слита")
        return True

    def connect_electrodes(self) -> bool:
        self.anode_connected = True
        self.cathode_connected = True
        logger.info(f"{self.name}: электроды подключены")
        return True

    def disconnect_electrodes(self) -> bool:
        if self.process_running:
            logger.error(f"{self.name}: нельзя отключать электроды во время процесса")
            return False
        self.anode_connected = False
        self.cathode_connected = False
        logger.info(f"{self.name}: электроды отключены")
        return True

    def is_ready(self) -> bool:
        return self.filled and self.anode_connected and self.cathode_connected

    def start_process(self, voltage: float, voltage_applied: bool = True) -> bool:
        if not self.filled:
            logger.error(f"{self.name}: не заполнена жидкостью")
            return False
        if not (self.anode_connected and self.cathode_connected):
            logger.error(f"{self.name}: электроды не подключены")
            return False
        if not voltage_applied:
            logger.error(f"{self.name}: транзисторный ключ закрыт")
            return False
        if voltage <= 0:
            logger.error(f"{self.name}: напряжение должно быть > 0 В")
            return False

        self.process_running = True
        self.applied_voltage = float(voltage)
        logger.info(f"{self.name}: процесс запущен, {voltage} В")
        return True

    def stop_process(self) -> bool:
        self.process_running = False
        self.applied_voltage = 0.0
        logger.info(f"{self.name}: процесс остановлен")
        return True

    def is_process_running(self) -> bool:
        return self.process_running

    def get_applied_voltage(self) -> float:
        return self.applied_voltage

    def get_status(self) -> str:
        parts = [
            f"жидкость={'есть' if self.filled else 'нет'}",
            f"анод={'+' if self.anode_connected else '−'}",
            f"катод={'+' if self.cathode_connected else '−'}",
        ]
        if self.process_running:
            parts.append(f"процесс={self.applied_voltage} В")
        else:
            parts.append("процесс=остановлен")
        return f"Ёмкость для полировки: {', '.join(parts)}"

    def __repr__(self) -> str:
        return (f"<PolishingTank filled={self.filled} "
                f"electrodes={self.anode_connected and self.cathode_connected} "
                f"running={self.process_running}>")


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
        stepper_speed: int = 200,
        current_limit: float = 5.0,
        max_temperature: float = 60.0,
        initial_temperature: float = 25.0,
        tank_filled_at_start: bool = True,
        electrodes_connected_at_start: bool = True,
        ac_dc_initially_on: bool = True,
        lid_initially_closed: bool = True,
    ):
        self.ac_dc_converter   = AcDcConverterStub(initially_on=ac_dc_initially_on)
        self.transistors       = TransistorSwitchBlockStub()
        self.vibro_table       = VibroTableStub()
        self.power_supply_48v  = PowerSupply48VStub(current_limit=current_limit)
        self.lid_sensor        = LidSensorStub(initially_closed=lid_initially_closed)
        self.stepper_driver    = StepperMotorDriverStub()
        self.stepper_motor     = StepperMotorStub()
        self.polishing_tank    = PolishingTankStub()
        self.temperature_sensor = TemperatureSensorStub(
            initial=initial_temperature, max_temperature=max_temperature,
        )

        # Стартовые настройки — применяются при init.
        self._initial_stepper_speed = stepper_speed
        self._initial_tank_filled = tank_filled_at_start
        self._initial_electrodes_connected = electrodes_connected_at_start

    def apply_initial_state(self) -> None:
        """Подготавливает железо в стартовое состояние (вызывается при init)."""
        self.stepper_motor.attach_driver(self.stepper_driver)
        self.stepper_driver.set_speed(self._initial_stepper_speed)
        if self._initial_tank_filled:
            self.polishing_tank.fill()
        if self._initial_electrodes_connected:
            self.polishing_tank.connect_electrodes()


# ============================================================
# ProcessController — бизнес-логика
# ============================================================

class ProcessController:
    """
    Управление технологическим процессом.
    Только то, что относится к старту/остановке/мониторингу —
    никаких мок-методов здесь нет.
    """

    def __init__(self, hardware: HardwareRegistry):
        self.hw = hardware
        self.initialized = False
        self.process_running = False

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

        self.hw.apply_initial_state()
        self.hw.transistors.set_load_power(True)

        if not self.hw.stepper_driver.enable(power_available=logic_power):
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
        if not self.hw.polishing_tank.is_ready():
            logger.error("Ёмкость для полировки не готова")
            return False
        return True

    # ---- процесс ----
    def start_process(self) -> bool:
        logger.info("=== Запуск процесса ===")
        if not self._check_start_conditions():
            return False

        t = self.hw.transistors
        t.set_load_power(self.hw.ac_dc_converter.get_output_voltage() > 0)

        if not t.turn_on(TransistorChannel.POWER_48V):
            return False
        if not self.hw.power_supply_48v.turn_on(
            power_allowed=t.is_channel_on(TransistorChannel.POWER_48V)
        ):
            self.stop_process()
            return False

        if not t.turn_on(TransistorChannel.POLISHING):
            self.stop_process(); return False
        if not t.turn_on(TransistorChannel.VIBRO_TABLE):
            self.stop_process(); return False

        if t.is_channel_on(TransistorChannel.VIBRO_TABLE):
            self.hw.vibro_table.supply_power()
        else:
            self.stop_process(); return False

        voltage_applied = (
            t.is_channel_on(TransistorChannel.POLISHING)
            and self.hw.power_supply_48v.is_on()
        )
        voltage = self.hw.power_supply_48v.get_voltage() if voltage_applied else 0.0
        if not self.hw.polishing_tank.start_process(voltage, voltage_applied):
            self.stop_process()
            return False

        self.process_running = True
        logger.info("=== Процесс запущен ===")
        return True

    def stop_process(self) -> bool:
        logger.info("=== Остановка процесса ===")
        self.hw.polishing_tank.stop_process()
        self.hw.vibro_table.cut_power()
        self.hw.transistors.turn_off(TransistorChannel.VIBRO_TABLE)
        self.hw.transistors.turn_off(TransistorChannel.POLISHING)
        self.hw.transistors.turn_off(TransistorChannel.POWER_48V)
        self.hw.power_supply_48v.turn_off()
        self.process_running = False
        logger.info("=== Процесс остановлен ===")
        return True

    def emergency_stop(self) -> bool:
        logger.warning("!!! АВАРИЙНАЯ ОСТАНОВКА !!!")
        self.hw.stepper_motor.stop()
        self.hw.stepper_driver.disable()
        self.hw.polishing_tank.stop_process()
        self.hw.vibro_table.cut_power()
        self.hw.transistors.turn_off_all()
        self.hw.power_supply_48v.turn_off()
        self.process_running = False
        # Авария оставляет железо в обесточенном состоянии (привод заглушён,
        # ключи и источник выключены), поэтому система больше не считается
        # инициализированной: запуск блокируется до повторной инициализации,
        # которая заново включит привод и проверит условия.
        self.initialized = False
        return True

    # ---- движение мотора ----
    def move_motor_to(self, position: int) -> bool:
        if not self._require_initialized():
            return False
        if self.process_running:
            logger.error("Нельзя двигать мотор во время процесса")
            return False
        if not self.hw.stepper_driver.enabled:
            self.hw.stepper_driver.enable(
                power_available=self.hw.ac_dc_converter.get_output_voltage() > 0
            )
        return self.hw.stepper_motor.move_to_position(position)

    def set_motor_speed(self, speed: int) -> bool:
        if not self._require_initialized():
            return False
        return self.hw.stepper_driver.set_speed(speed)

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
            f"[Вибростол] {self.hw.vibro_table.get_status()}",
            f"[Источник 48 В] {self.hw.power_supply_48v.get_status()}",
            f"[Крышка] {self.hw.lid_sensor.get_status()}",
            f"[Драйвер ШД] {self.hw.stepper_driver.get_status()}",
            f"[ШД] {self.hw.stepper_motor.get_status()}",
            f"[Ёмкость] {self.hw.polishing_tank.get_status()}",
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
    приходят от датчиков (открытие крышки, нагрев, наполнение ёмкости...).

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

    def fill_tank(self) -> bool:
        return self.hw.polishing_tank.fill()

    def drain_tank(self) -> bool:
        return self.hw.polishing_tank.drain()

    def connect_electrodes(self) -> bool:
        return self.hw.polishing_tank.connect_electrodes()

    def disconnect_electrodes(self) -> bool:
        return self.hw.polishing_tank.disconnect_electrodes()

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
        self.vibro_table       = self.hw.vibro_table
        self.power_supply_48v  = self.hw.power_supply_48v
        self.lid_sensor        = self.hw.lid_sensor
        self.stepper_driver    = self.hw.stepper_driver
        self.stepper_motor     = self.hw.stepper_motor
        self.polishing_tank    = self.hw.polishing_tank
        self.temperature_sensor = self.hw.temperature_sensor

    # делегирование методов
    def initialize(self):           return self.process.initialize()
    def start_process(self):        return self.process.start_process()
    def stop_process(self):         return self.process.stop_process()
    def emergency_stop(self):       return self.process.emergency_stop()
    def move_motor_to(self, p):     return self.process.move_motor_to(p)
    def set_stepper_speed(self, s): return self.process.set_motor_speed(s)
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
    def fill_tank_mock(self):             return self.test.fill_tank()
    def drain_tank_mock(self):            return self.test.drain_tank()
    def connect_electrodes_mock(self):    return self.test.connect_electrodes()
    def disconnect_electrodes_mock(self): return self.test.disconnect_electrodes()


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

    print("\n>>> Запуск процесса")
    process.start_process()

    print("\n>>> Открываем крышку — должна сработать авария")
    test.set_lid(False)

    print("\n>>> Финальный статус")
    print(process.get_system_status())
