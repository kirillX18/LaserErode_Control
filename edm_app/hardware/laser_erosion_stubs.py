"""
Заглушки оборудования лазерно-эрозионного робота.

Архитектура:
    Hardware*Stub          — отдельные устройства (соответствуют блокам схемы)
    HardwareRegistry       — владеет всеми устройствами, ничего не решает
    ProcessController      — бизнес-логика (старт/стоп/авария/мониторинг)
    TestHarness            — мок-методы для имитации физических событий
                             (открытие крышки, нагрев, ток, давление воды) —
                             НЕ часть прошивки

Состав оборудования (после перехода на роботизированную лазерно-эрозионную
обработку):
    AC/DC преобразователь            — питание логики 24 В;
    Блок транзисторных ключей        — коммутация силовых нагрузок:
                                       приводы руки, лазер, эрозия, подача воды;
    Источник питания эрозии          — напряжение на катод/анод, защита от
                                       перегрузки по току;
    Источник питания лазера          — питание лазерного излучателя, включается
                                       только при закрытой крышке и готовности;
    Роботизированная 8-суставная рука — позиционирование рабочей головки
                                       (заменяет шаговые приводы и стол);
    Контроллер 8-суставного робота   — движение суставов J1…J8 и траектория;
    Лазерно-эрозионная рабочая головка — узел из:
        лазерный излучатель          — параметры с вкладки «Лазером»;
        эрозионный катод             — электроэрозионное воздействие;
        эрозионный анод              — работает с катодом и источником эрозии;
        сопло подачи воды            — вода из системы подачи в рабочую зону;
    Система подачи воды              — насос, клапан, датчики давления/расхода,
                                       слив (заменяет полировочную ванну);
    Крепление детали (рабочий стол)  — неподвижное основание под заготовку;
    Датчик температуры               — нагрев лазера, электродов, рабочей зоны;
    Датчик закрытия защитной крышки  — лазер и эрозия не пускаются при открытой.

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
    """Каналы блока транзисторных ключей (силовые нагрузки)."""
    ARM_DRIVES = "arm_drives"   # питание приводов суставов роботизированной руки
    EDM        = "edm"          # разрешение источника эрозии (катод/анод)
    LASER      = "laser"        # подача питания на лазерный излучатель
    WATER      = "water"        # питание насоса/клапана подачи воды


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

    Коммутирует силовые нагрузки лазерно-эрозионного робота:
        приводы суставов руки, лазер, эрозионный процесс, подача воды.
    """

    def __init__(self):
        self.name = "Блок транзисторных ключей"
        self.common_ground = True
        self.load_power_enabled = False
        self.channels: dict[TransistorChannel, dict] = {
            TransistorChannel.ARM_DRIVES: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Питание приводов суставов руки",
            },
            TransistorChannel.EDM: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Разрешение источника эрозии (катод/анод)",
            },
            TransistorChannel.LASER: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Подача питания на лазерный излучатель",
            },
            TransistorChannel.WATER: {
                "control_signal": 0, "transistor_open": False, "load_enabled": False,
                "description": "Питание насоса и клапана подачи воды",
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
# Источник питания эрозионного процесса
# ============================================================

class EdmPowerSupplyStub:
    """
    Источник питания эрозионного процесса.
    Подаёт напряжение на эрозионный катод и анод, имеет защиту от перегрузки
    по току (отключается при превышении лимита). Включается только при наличии
    разрешения через транзисторный ключ EDM.
    """

    def __init__(self, voltage: float = 80.0,
                 current_limit: float = 5.0, max_current_limit: float = 10.0):
        self.name = "Источник питания эрозии"
        self.powered_on = False
        self.voltage = float(voltage)
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
        return self.current if self.powered_on else 0.0

    def check_overcurrent(self) -> bool:
        """
        Проверка перегрузки. Если ток превышен — выключает источник
        и поднимает флаг аварии. Возвращает True, если перегрузки нет.
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
            return (f"Источник эрозии: {self.voltage} В, "
                    f"ток {self.current} А, лимит {self.current_limit} А")
        return f"Источник эрозии выключен. Лимит: {self.current_limit} А"

    def __repr__(self) -> str:
        return f"<EdmPSU on={self.powered_on} V={self.voltage} I={self.current}>"


# ============================================================
# Источник питания лазера
# ============================================================

class LaserPowerSupplyStub:
    """
    Источник питания лазерного излучателя.
    Включается ТОЛЬКО при закрытой защитной зоне (крышке) и готовности системы.
    Питание разрешается через транзисторный ключ LASER.
    """

    def __init__(self, voltage: float = 48.0):
        self.name = "Источник питания лазера"
        self.powered_on = False
        self.voltage = float(voltage)

    def turn_on(self, power_allowed: bool, lid_closed: bool,
                system_ready: bool) -> bool:
        if not power_allowed:
            logger.error(f"{self.name}: питание через транзисторный ключ не разрешено")
            return False
        if not lid_closed:
            logger.error(f"{self.name}: защитная крышка открыта — питание запрещено")
            return False
        if not system_ready:
            logger.error(f"{self.name}: система не готова — питание запрещено")
            return False
        self.powered_on = True
        logger.info(f"{self.name}: включен, {self.voltage} В")
        return True

    def turn_off(self) -> bool:
        self.powered_on = False
        logger.info(f"{self.name}: выключен")
        return True

    def is_on(self) -> bool:
        return self.powered_on

    def get_voltage(self) -> float:
        return self.voltage if self.powered_on else 0.0

    def get_status(self) -> str:
        if self.powered_on:
            return f"Источник лазера включен, {self.voltage} В"
        return "Источник лазера выключен"

    def __repr__(self) -> str:
        return f"<LaserPSU on={self.powered_on} V={self.voltage}>"


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
# Контроллер 8-суставного робота
# ============================================================

class RobotControllerStub:
    """
    Контроллер 8-суставного робота.
    Заменяет управление шаговым приводом. Выходит на связь (online) по
    логическому питанию, разрешает движение суставов (enabled) при наличии
    питания приводов, задаёт скорость отработки траектории. Отвечает за
    выполнение движения суставов J1–J8 и прохождение траектории обработки.
    """

    def __init__(self):
        self.name = "Контроллер робота"
        self.online = False        # есть ли связь с контроллером
        self.enabled = False       # разрешено ли движение суставов
        self.moving = False
        self.speed = 100           # темп отработки траектории, усл. ед.
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
            logger.error(f"{self.name}: нет питания приводов")
            return False
        self.enabled = True
        logger.info(f"{self.name}: движение суставов разрешено")
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
        logger.info(f"{self.name}: темп траектории {self.speed}")
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
            return "Контроллер робота: нет связи"
        if not self.enabled:
            return f"Контроллер робота: на связи, движение запрещено. Темп: {self.speed}"
        if self.moving:
            return f"Контроллер робота: отработка траектории, темп {self.speed}"
        return f"Контроллер робота: готов, темп {self.speed}"

    def __repr__(self) -> str:
        return f"<RobotController online={self.online} enabled={self.enabled}>"


# ============================================================
# Роботизированная 8-суставная рука
# ============================================================

class RoboticArmStub:
    """
    Роботизированная рука с 8 суставами (J1…J8). Заменяет шаговые приводы и
    координатный стол: позиционирование рабочей головки по трём осям рабочей
    зоны (X, Y, Z) выполняется рукой.

    Каждый сустав имеет привод, датчик положения (текущий угол) и ограничение
    угла поворота (min/max). Движением суставов и отработкой траектории
    управляет RobotControllerStub.

    Положение инструмента (TCP) — авторитетные декартовы координаты рабочей
    зоны; углы суставов в этой модели рассчитываются детерминированно по
    положению инструмента (упрощённая обратная задача), остаются в пределах
    ограничений и служат для отображения позы руки.

    Движение может быть мгновенным (unit-тесты) или фоновым (set_async_motion).
    """

    # Имена суставов и их угловые ограничения (градусы)
    JOINT_LIMITS = {
        "J1": (-180, 180),   # поворот основания
        "J2": (-90, 90),     # плечо
        "J3": (-150, 150),   # локоть
        "J4": (-180, 180),   # предплечье
        "J5": (-120, 120),   # кисть (наклон)
        "J6": (-180, 180),   # кисть (поворот)
        "J7": (-120, 120),   # инструмент (наклон)
        "J8": (-360, 360),   # инструмент (вращение)
    }
    JOINTS = tuple(JOINT_LIMITS.keys())
    AXES = ("x", "y", "z")

    def __init__(self,
                 x_range=(0, 1000), y_range=(0, 500), z_range=(0, 400)):
        self.name = "8-суставная рука"
        self.controller: Optional[RobotControllerStub] = None
        self.moving = False
        self.tool = {"x": 0, "y": 0, "z": 0}
        self.ranges = {"x": tuple(x_range), "y": tuple(y_range), "z": tuple(z_range)}
        self.joints = {j: 0.0 for j in self.JOINTS}
        self.async_motion = False
        self.motion_delay_scale = 0.001
        self._motion_thread: Optional[threading.Thread] = None
        self._stop_motion = threading.Event()
        self._sync_joints()

    # ---- связь с контроллером ----
    def attach_controller(self, controller: RobotControllerStub) -> bool:
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

    def _in_range(self, axis: str, value: float) -> bool:
        lo, hi = self.ranges[axis]
        return lo <= value <= hi

    # ---- кинематика (упрощённая обратная задача для отображения позы) ----
    def _sync_joints(self) -> None:
        """Пересчитать углы суставов по текущему положению инструмента."""
        for i, j in enumerate(self.JOINTS):
            lo, hi = self.JOINT_LIMITS[j]
            ax = self.AXES[i % 3]
            rlo, rhi = self.ranges[ax]
            span = (rhi - rlo) or 1
            frac = (self.tool[ax] - rlo) / span          # 0..1
            # фаза, чтобы суставы расходились по-разному, но в пределах лимитов
            phase = (i + 1) / (len(self.JOINTS) + 1)
            angle = (lo + hi) / 2 + (hi - lo) / 2 * math.sin(2 * math.pi * (frac + phase))
            self.joints[j] = round(max(lo, min(hi, angle)), 1)

    # ---- движение инструмента (TCP) ----
    def move_tool(self, x: Optional[float] = None, y: Optional[float] = None,
                  z: Optional[float] = None) -> bool:
        """Переместить инструмент в точку (X, Y, Z). None по оси — оставить как есть."""
        if not self._can_move():
            return False
        target = {
            "x": self.tool["x"] if x is None else float(x),
            "y": self.tool["y"] if y is None else float(y),
            "z": self.tool["z"] if z is None else float(z),
        }
        for ax in self.AXES:
            if not self._in_range(ax, target[ax]):
                lo, hi = self.ranges[ax]
                logger.error(f"{self.name}: {ax.upper()}={target[ax]} вне диапазона "
                             f"[{lo}, {hi}]")
                return False

        dist = math.dist(
            (self.tool["x"], self.tool["y"], self.tool["z"]),
            (target["x"], target["y"], target["z"]),
        )
        if dist == 0:
            return True

        if not self.controller.start_motion(1):
            return False

        self.moving = True
        logger.info(f"{self.name}: перемещение инструмента в "
                    f"X={target['x']:.0f}, Y={target['y']:.0f}, Z={target['z']:.0f}")

        if self.async_motion:
            self._start_async_motion(target, dist)
        else:
            self._finish_motion(target)
        return True

    def move_joint(self, joint: str, angle: float) -> bool:
        """Повернуть отдельный сустав J1…J8 в заданный угол (наладка)."""
        joint = joint.upper()
        if joint not in self.JOINT_LIMITS:
            logger.error(f"{self.name}: сустав '{joint}' не существует")
            return False
        if not self._can_move():
            return False
        lo, hi = self.JOINT_LIMITS[joint]
        angle = float(angle)
        if not lo <= angle <= hi:
            logger.error(f"{self.name}: угол {joint}={angle}° вне диапазона "
                         f"[{lo}, {hi}]")
            return False
        self.joints[joint] = round(angle, 1)
        logger.info(f"{self.name}: {joint} = {self.joints[joint]}°")
        return True

    def _finish_motion(self, target: dict) -> None:
        self.tool = dict(target)
        self._sync_joints()
        self.moving = False
        if self.controller:
            self.controller.stop()
        logger.info(f"{self.name}: позиция инструмента "
                    f"X={self.tool['x']:.0f}, Y={self.tool['y']:.0f}, "
                    f"Z={self.tool['z']:.0f}")

    def _start_async_motion(self, target: dict, dist: float) -> None:
        self._stop_motion.clear()

        def worker():
            delay = dist / max(self.controller.speed, 1) * self.motion_delay_scale
            if self._stop_motion.wait(timeout=delay):
                logger.info(f"{self.name}: движение прервано")
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

    def home(self) -> bool:
        """Вернуть руку в исходную позу (центр X/Y, верх Z)."""
        if self.moving:
            logger.error(f"{self.name}: нельзя домой во время движения")
            return False
        self.tool = {
            "x": (self.ranges["x"][0] + self.ranges["x"][1]) / 2,
            "y": (self.ranges["y"][0] + self.ranges["y"][1]) / 2,
            "z": self.ranges["z"][1],
        }
        self._sync_joints()
        logger.info(f"{self.name}: переход в исходную позу")
        return True

    def get_tool_position(self) -> dict:
        return dict(self.tool)

    def get_joints(self) -> dict:
        return dict(self.joints)

    def get_status(self) -> str:
        if self.controller is None:
            return "Рука: контроллер не назначен"
        state = "движется" if self.moving else "остановлена"
        return (f"Рука {state}, инструмент "
                f"X={self.tool['x']:.0f}, Y={self.tool['y']:.0f}, Z={self.tool['z']:.0f}")

    def __repr__(self) -> str:
        return (f"<RoboticArm x={self.tool['x']:.0f} y={self.tool['y']:.0f} "
                f"z={self.tool['z']:.0f} moving={self.moving}>")


# ============================================================
# Эрозионный катод
# ============================================================

class ErosionCathodeStub:
    """Эрозионный катод — часть рабочей головки, инструмент эрозии."""

    def __init__(self):
        self.name = "Эрозионный катод"
        self.connected = False     # подключён к источнику эрозии
        self.active = False        # идёт ли эрозионное воздействие

    def connect(self) -> bool:
        self.connected = True
        logger.info(f"{self.name}: подключён к источнику эрозии")
        return True

    def disconnect(self) -> bool:
        self.active = False
        self.connected = False
        logger.info(f"{self.name}: отключён")
        return True

    def set_active(self, state: bool, source_on: bool) -> bool:
        if state and not (self.connected and source_on):
            logger.error(f"{self.name}: нет питания/подключения источника эрозии")
            return False
        self.active = bool(state)
        logger.info(f"{self.name}: эрозия {'идёт' if self.active else 'остановлена'}")
        return True

    def get_status(self) -> str:
        if not self.connected:
            return "Катод: не подключён"
        return f"Катод: подключён, эрозия {'идёт' if self.active else 'нет'}"

    def __repr__(self) -> str:
        return f"<Cathode connected={self.connected} active={self.active}>"


# ============================================================
# Эрозионный анод
# ============================================================

class ErosionAnodeStub:
    """Эрозионный анод — часть рабочей головки, работает с катодом."""

    def __init__(self):
        self.name = "Эрозионный анод"
        self.connected = False

    def connect(self) -> bool:
        self.connected = True
        logger.info(f"{self.name}: подключён к источнику эрозии")
        return True

    def disconnect(self) -> bool:
        self.connected = False
        logger.info(f"{self.name}: отключён")
        return True

    def get_status(self) -> str:
        return f"Анод: {'подключён' if self.connected else 'не подключён'}"

    def __repr__(self) -> str:
        return f"<Anode connected={self.connected}>"


# ============================================================
# Лазерный излучатель — рабочий инструмент
# ============================================================

class LaserStub:
    """
    Лазерный излучатель — часть лазерно-эрозионной рабочей головки.
    Используется для лазерной обработки совместно с электроэрозионным воздействием.

    Параметры берутся с вкладки «Лазером»:
        power     — мощность, Вт              (0 … 500)
        frequency — частота импульсов, Гц      (0 … 100000)
        focus     — фокусное смещение, мкм     (-5000 … 5000)
        pulse     — длительность импульса, мкс (0 … 1000)
        exposure  — время воздействия, мс      (0 … 10000)
        mode      — режим излучения            (LaserMode)

    Излучение включается, когда задана мощность (> 0) И подано силовое питание
    от источника лазера (через транзисторный ключ LASER).
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
        self.powered = False        # подано ли силовое питание
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
            logger.error(f"{self.name}: нет силового питания (источник лазера выключен)")
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
# Система подачи воды
# ============================================================

class WaterSupplySystemStub:
    """
    Система подачи воды в рабочую зону (заменяет полировочную ванну).
    Вода не хранится в ванне, а подаётся напрямую в рабочую зону через сопло.

    Состав: насос, электромагнитный клапан, канал подачи, датчик давления,
    датчик расхода, слив (отвод воды).

    Поток есть, когда: насос включён И клапан открыт. При потоке устанавливаются
    рабочие давление и расход; без потока — нулевые.
    """

    def __init__(self, work_pressure: float = 2.5, work_flow: float = 3.0,
                 min_flow: float = 0.5):
        self.name = "Система подачи воды"
        self.pump_on = False
        self.valve_open = False
        self.pressure = 0.0        # бар (датчик давления)
        self.flow = 0.0            # л/мин (датчик расхода)
        self.drain_open = False    # слив рабочей зоны
        self._work_pressure = float(work_pressure)
        self._work_flow = float(work_flow)
        self.min_flow = float(min_flow)   # минимальный расход для охлаждения

    def set_pump(self, state: bool, power_available: bool = True) -> bool:
        if state and not power_available:
            logger.error(f"{self.name}: нет питания насоса")
            return False
        self.pump_on = bool(state)
        self._update_sensors()
        logger.info(f"{self.name}: насос {'включён' if self.pump_on else 'выключен'}")
        return True

    def set_valve(self, state: bool) -> bool:
        self.valve_open = bool(state)
        self._update_sensors()
        logger.info(f"{self.name}: клапан "
                    f"{'открыт' if self.valve_open else 'закрыт'}")
        return True

    def set_drain(self, state: bool) -> bool:
        self.drain_open = bool(state)
        logger.info(f"{self.name}: слив "
                    f"{'открыт' if self.drain_open else 'закрыт'}")
        return True

    def start_supply(self, power_available: bool = True) -> bool:
        """Подать воду в рабочую зону: открыть клапан и включить насос."""
        if not self.set_valve(True):
            return False
        return self.set_pump(True, power_available=power_available)

    def stop_supply(self) -> bool:
        """Прекратить подачу: выключить насос и закрыть клапан."""
        self.set_pump(False)
        self.set_valve(False)
        return True

    def _update_sensors(self) -> None:
        flowing = self.pump_on and self.valve_open
        self.pressure = self._work_pressure if flowing else 0.0
        self.flow = self._work_flow if flowing else 0.0

    def is_flowing(self) -> bool:
        return self.flow >= self.min_flow

    def get_pressure(self) -> float:
        return self.pressure

    def get_flow(self) -> float:
        return self.flow

    def simulate_pressure(self, value: float) -> bool:
        """Тестовая утилита — задать давление (TestHarness)."""
        self.pressure = max(0.0, float(value))
        return True

    def simulate_flow(self, value: float) -> bool:
        """Тестовая утилита — задать расход (TestHarness)."""
        self.flow = max(0.0, float(value))
        return True

    def get_status(self) -> str:
        return (f"Вода: насос {'вкл' if self.pump_on else 'выкл'}, "
                f"клапан {'открыт' if self.valve_open else 'закрыт'}, "
                f"давление {self.pressure:.1f} бар, расход {self.flow:.1f} л/мин, "
                f"слив {'открыт' if self.drain_open else 'закрыт'}")

    def __repr__(self) -> str:
        return f"<WaterSupply pump={self.pump_on} valve={self.valve_open} flow={self.flow}>"


# ============================================================
# Лазерно-эрозионная рабочая головка
# ============================================================

class WorkingHeadStub:
    """
    Лазерно-эрозионная рабочая головка — узел, объединяющий эрозионную обработку
    и лазерное воздействие. Содержит лазерный излучатель, эрозионные катод и анод
    и сопло подачи воды (вода поступает из системы подачи воды).

    Сам по себе ничего не решает — это композиция узлов головки. Энергоподача и
    запуск воздействия выполняются ProcessController через источники питания.
    """

    def __init__(self, laser: LaserStub, cathode: ErosionCathodeStub,
                 anode: ErosionAnodeStub, water: WaterSupplySystemStub):
        self.name = "Лазерно-эрозионная рабочая головка"
        self.laser = laser
        self.cathode = cathode
        self.anode = anode
        self.water = water       # сопло подачи воды питается от системы подачи

    def is_machining(self) -> bool:
        """Идёт ли обработка: излучение лазера ИЛИ эрозия."""
        return self.laser.is_emitting() or self.cathode.active

    def get_status(self) -> str:
        return (f"Головка: лазер {'излучает' if self.laser.is_emitting() else 'выкл'}, "
                f"эрозия {'идёт' if self.cathode.active else 'нет'}, "
                f"полив {'есть' if self.water.is_flowing() else 'нет'}")

    def __repr__(self) -> str:
        return f"<WorkingHead machining={self.is_machining()}>"


# ============================================================
# Крепление детали (неподвижный рабочий стол)
# ============================================================

class WorkpieceFixtureStub:
    """
    Крепление детали — неподвижное основание для фиксации заготовки во время
    обработки. Позиционирование полностью выполняет 8-суставная рука, поэтому
    стол не перемещается — он только удерживает (зажимает) деталь.
    """

    def __init__(self):
        self.name = "Крепление детали"
        self.clamped = False

    def clamp(self) -> bool:
        self.clamped = True
        logger.info(f"{self.name}: деталь зажата")
        return True

    def release(self) -> bool:
        self.clamped = False
        logger.info(f"{self.name}: деталь освобождена")
        return True

    def is_clamped(self) -> bool:
        return self.clamped

    def get_status(self) -> str:
        return f"Крепление детали: {'деталь зажата' if self.clamped else 'свободно'}"

    def __repr__(self) -> str:
        return f"<Fixture clamped={self.clamped}>"


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
        arm_speed: int = 150,
        edm_current_limit: float = 8.0,
        max_temperature: float = 80.0,
        initial_temperature: float = 25.0,
        laser_power_at_start: int = 200,
        ac_dc_initially_on: bool = True,
        lid_initially_closed: bool = True,
    ):
        # Питание и коммутация
        self.ac_dc_converter   = AcDcConverterStub(initially_on=ac_dc_initially_on)
        self.transistors       = TransistorSwitchBlockStub()
        self.edm_power_supply  = EdmPowerSupplyStub(current_limit=edm_current_limit)
        self.laser_power_supply = LaserPowerSupplyStub()

        # Безопасность
        self.lid_sensor        = LidSensorStub(initially_closed=lid_initially_closed)
        self.temperature_sensor = TemperatureSensorStub(
            initial=initial_temperature, max_temperature=max_temperature,
        )

        # Позиционирование: контроллер робота + 8-суставная рука
        self.robot_controller  = RobotControllerStub()
        self.arm               = RoboticArmStub()

        # Рабочая головка: лазер + эрозионные электроды + сопло воды
        self.laser             = LaserStub()
        self.cathode           = ErosionCathodeStub()
        self.anode             = ErosionAnodeStub()
        self.water             = WaterSupplySystemStub()
        self.head              = WorkingHeadStub(
            self.laser, self.cathode, self.anode, self.water)

        # Неподвижное крепление детали
        self.fixture           = WorkpieceFixtureStub()

        # Заводская настройка лазера под обработку СТАЛИ (видна в снимке сразу).
        self.laser.set_mode(LaserMode.PULSED)
        self.laser.set_param("power", laser_power_at_start)  # 200 Вт
        self.laser.set_param("frequency", 20000)             # 20 кГц
        self.laser.set_param("focus", 0)                     # фокус на поверхности
        self.laser.set_param("pulse", 100)                   # 100 мкс
        self.laser.set_param("exposure", 1000)               # 1000 мс

        # Исходная поза руки: инструмент в центре рабочей зоны, вверху по Z.
        a = self.arm
        a.tool["x"] = (a.ranges["x"][0] + a.ranges["x"][1]) / 2
        a.tool["y"] = (a.ranges["y"][0] + a.ranges["y"][1]) / 2
        a.tool["z"] = a.ranges["z"][1]
        a._sync_joints()

        # Темп отработки траектории — выставляем сразу (повторно подтвердится в init).
        self.robot_controller.set_speed(arm_speed)

        # Стартовые настройки — применяются при init.
        self._initial_arm_speed = arm_speed
        self._initial_laser_power = laser_power_at_start

    def apply_initial_state(self) -> None:
        """Подготавливает железо в стартовое состояние (вызывается при init)."""
        # Рука + контроллер робота
        self.arm.attach_controller(self.robot_controller)
        self.robot_controller.set_speed(self._initial_arm_speed)
        # Лазер: стартовая мощность
        if self._initial_laser_power > 0:
            self.laser.set_param("power", self._initial_laser_power)


# ============================================================
# ProcessController — бизнес-логика
# ============================================================

class ProcessController:
    """
    Управление технологическим процессом лазерно-эрозионной обработки.
    Только старт/остановка/мониторинг — никаких мок-методов здесь нет.
    """

    # Номинальная длительность цикла обработки, с (симуляция).
    PROCESS_DURATION = 30.0

    def __init__(self, hardware: HardwareRegistry):
        self.hw = hardware
        self.initialized = False
        self.process_running = False
        self.paused = False
        self.progress = 0.0

        # Программа обработки — плоский контур в координатах рабочей зоны:
        #   точки (X, Y). По нему рука ведёт головку во время процесса.
        self.toolpath: list = []     # [(X, Y), …]
        self._tp_cum: list = []
        self._tp_total: float = 0.0
        # Признак загруженной 3D-модели детали (STL/OBJ). Это альтернативный
        # вид задания: прошивка несквозного отверстия по модели не требует
        # плоского контура, поэтому загруженная деталь сама по себе разрешает
        # запуск процесса (см. _check_start_conditions / process_readiness).
        self.part_loaded: bool = False
        # Параметры хода головки при прошивке отверстия (доли рабочей зоны
        # X/Y, куда подвести инструмент). По Z головка опускается с ростом
        # прогресса — имитация подвода и заглубления, как на реальном станке.
        self._mach_motion = None     # (xf, yf) или None

    # ---- программа обработки (контур) ----
    def set_toolpath(self, points) -> bool:
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

    def set_part_loaded(self, on) -> bool:
        """Отметить, загружена ли 3D-модель детали (задание-«прошивка»)."""
        self.part_loaded = bool(on)
        logger.info("3D-модель детали загружена" if self.part_loaded
                    else "3D-модель детали выгружена")
        return True

    def set_machining_motion(self, xf=None, yf=None) -> bool:
        """Задать точку подвода головки для прошивки (доли рабочей зоны X/Y),
        либо сбросить (xf=None). По ней рука ведёт инструмент во время процесса."""
        if xf is None or yf is None:
            self._mach_motion = None
        else:
            self._mach_motion = (max(0.0, min(1.0, float(xf))),
                                 max(0.0, min(1.0, float(yf))))
        return True

    def _drive_machining_head(self) -> None:
        """Двигать инструмент руки по ходу прошивки: быстрый подвод по X/Y к
        точке отверстия, затем опускание по Z (фаза лазера — у поверхности,
        фаза эрозии — заглубление). Делает движение заглушки видимым и
        согласованным в показе детали и на вкладке «Позиционирование»."""
        if self._mach_motion is None:
            return
        arm = self.hw.arm
        xf, yf = self._mach_motion
        rx = arm.ranges["x"]; ry = arm.ranges["y"]; rz = arm.ranges["z"]
        tx = rx[0] + xf * (rx[1] - rx[0])
        ty = ry[0] + yf * (ry[1] - ry[0])
        p = max(0.0, min(1.0, self.progress / 100.0))
        # профиль высоты Z (доля зоны, 1 — вверху): подвод → лазер → заглубление
        if p < 0.08:                      # быстрый подвод сверху к поверхности
            zf = 0.85 - (0.85 - 0.55) * (p / 0.08)
        elif p < 0.22:                    # лазер режет эмаль — почти у поверхности
            zf = 0.55 - 0.05 * ((p - 0.08) / 0.14)
        else:                             # эрозия — заглубление электрода
            zf = 0.50 - 0.24 * ((p - 0.22) / 0.78)
        tz = rz[0] + max(0.0, min(1.0, zf)) * (rz[1] - rz[0])
        moved = (abs(arm.tool["x"] - tx) + abs(arm.tool["y"] - ty)
                 + abs(arm.tool["z"] - tz)) > 1e-6
        arm.tool["x"] = tx; arm.tool["y"] = ty; arm.tool["z"] = tz
        arm._sync_joints()
        arm.moving = moved

    def _point_at(self, frac: float):
        if not self.toolpath:
            return None
        if self._tp_total <= 0:
            return self.toolpath[0]
        target = max(0.0, min(1.0, frac)) * self._tp_total
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

        # Назначаем приводы и стартовые параметры
        self.hw.apply_initial_state()
        self.hw.transistors.set_load_power(True)

        # Контроллер робота выходит на связь и разрешает наладочные движения.
        # Питание приводов руки — через транзисторный ключ ARM_DRIVES.
        self.hw.transistors.turn_on(TransistorChannel.ARM_DRIVES)
        arm_power = self.hw.transistors.is_channel_on(TransistorChannel.ARM_DRIVES)
        self.hw.robot_controller.connect()
        if not self.hw.robot_controller.enable(power_available=arm_power):
            return False

        # Зажимаем деталь в неподвижном креплении.
        self.hw.fixture.clamp()

        # Эрозионные электроды подключаем к источнику (источник пока выключен).
        self.hw.cathode.connect()
        self.hw.anode.connect()

        # Система воды в исходном состоянии: насос выкл, клапан закрыт, слив закрыт.
        self.hw.water.stop_supply()
        self.hw.water.set_drain(False)

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
        if not self.hw.robot_controller.online:
            logger.error("Контроллер робота не на связи")
            return False
        if not self.hw.fixture.is_clamped():
            logger.error("Деталь не зафиксирована в креплении")
            return False
        if not self.toolpath and not self.part_loaded:
            logger.error("Не загружена программа обработки (контур) "
                         "или 3D-модель детали")
            return False
        return True

    # ---- процесс ----
    def start_process(self) -> bool:
        logger.info("=== Запуск процесса ===")
        if not self._check_start_conditions():
            return False

        t = self.hw.transistors
        t.set_load_power(self.hw.ac_dc_converter.get_output_voltage() > 0)

        # 1) Разрешаем питание эрозии и включаем источник эрозии
        if not t.turn_on(TransistorChannel.EDM):
            self.stop_process(); return False
        if not self.hw.edm_power_supply.turn_on(
            power_allowed=t.is_channel_on(TransistorChannel.EDM)
        ):
            self.stop_process(); return False
        # Запускаем эрозионное воздействие (катод + анод)
        if not self.hw.cathode.set_active(True, self.hw.edm_power_supply.is_on()):
            self.stop_process(); return False

        # 2) Подаём воду в рабочую зону (питание насоса через ключ WATER)
        if not t.turn_on(TransistorChannel.WATER):
            self.stop_process(); return False
        if not self.hw.water.start_supply(
            power_available=t.is_channel_on(TransistorChannel.WATER)
        ):
            self.stop_process(); return False

        # 3) Включаем источник лазера (только при закрытой крышке и готовности)
        if not t.turn_on(TransistorChannel.LASER):
            self.stop_process(); return False
        if not self.hw.laser_power_supply.turn_on(
            power_allowed=t.is_channel_on(TransistorChannel.LASER),
            lid_closed=self.hw.lid_sensor.is_closed(),
            system_ready=self.initialized,
        ):
            self.stop_process(); return False

        # 4) Включаем излучение лазера
        if not self.hw.laser.start_emission(self.hw.laser_power_supply.is_on()):
            self.stop_process(); return False

        self.process_running = True
        self.paused = False
        self.progress = 0.0
        # головка встаёт в начало контура (если программа загружена)
        if self.toolpath:
            self.hw.arm.tool["x"] = self.toolpath[0][0]
            self.hw.arm.tool["y"] = self.toolpath[0][1]
            self.hw.arm._sync_joints()
        elif self._mach_motion is not None:
            # задание-«прошивка»: сразу подводим инструмент к точке отверстия
            self._drive_machining_head()
        logger.info("=== Процесс запущен ===")
        return True

    def stop_process(self) -> bool:
        logger.info("=== Остановка процесса ===")
        self.hw.laser.stop_emission()
        self.hw.laser_power_supply.turn_off()
        self.hw.cathode.set_active(False, False)
        self.hw.edm_power_supply.turn_off()
        self.hw.water.stop_supply()
        self._stop_scan()
        self.hw.transistors.turn_off(TransistorChannel.LASER)
        self.hw.transistors.turn_off(TransistorChannel.EDM)
        self.hw.transistors.turn_off(TransistorChannel.WATER)
        self.process_running = False
        self.paused = False
        self.progress = 0.0
        self.hw.arm.moving = False        # головка остановлена
        logger.info("=== Процесс остановлен ===")
        return True

    def pause_process(self) -> bool:
        """Пауза: гасим излучение, эрозию и подачу воды; прогресс замирает."""
        if not self.process_running:
            logger.error("Процесс не запущен — пауза недоступна")
            return False
        if self.paused:
            return True
        self.hw.laser.stop_emission()
        self.hw.cathode.set_active(False, False)
        self.hw.water.set_pump(False)
        self._stop_scan()
        self.paused = True
        self.hw.arm.moving = False        # на паузе головка замирает
        logger.info("=== Процесс приостановлен ===")
        return True

    def resume_process(self) -> bool:
        """Возобновление после паузы: снова включаем воздействие."""
        if not self.process_running:
            logger.error("Процесс не запущен — возобновление недоступно")
            return False
        if not self.paused:
            return True
        # Снова подаём воду
        self.hw.water.set_pump(
            True, power_available=self.hw.transistors.is_channel_on(TransistorChannel.WATER))
        # Снова включаем эрозию
        self.hw.cathode.set_active(True, self.hw.edm_power_supply.is_on())
        # Снова включаем излучение
        power_applied = self.hw.laser_power_supply.is_on()
        if not self.hw.laser.start_emission(power_applied):
            logger.error("Не удалось возобновить излучение")
            return False
        self.paused = False
        logger.info("=== Процесс возобновлён ===")
        return True

    def advance_progress(self, dt: float) -> None:
        if not self.process_running or self.paused or self.PROCESS_DURATION <= 0:
            return
        self.progress = min(
            100.0, self.progress + dt / self.PROCESS_DURATION * 100.0)
        self._drive_machining_head()      # ход головки по прогрессу (прошивка)
        if self.progress >= 100.0:
            logger.info("=== Процесс завершён (100 %) ===")
            self.stop_process()

    # ---- движение головки по контуру во время процесса ----
    def drive_scan(self) -> None:
        if not self.process_running or self.paused:
            return
        rc = self.hw.robot_controller
        if not rc.enabled:
            return
        self.hw.arm.moving = True
        rc.moving = True
        rc.direction = 1

        pt = self._point_at(self.progress / 100.0)
        if pt is not None:
            self.hw.arm.tool["x"] = pt[0]
            self.hw.arm.tool["y"] = pt[1]
            self.hw.arm._sync_joints()

    def _stop_scan(self) -> None:
        self.hw.arm.moving = False
        self.hw.robot_controller.moving = False
        self.hw.robot_controller.direction = 0

    def emergency_stop(self) -> bool:
        logger.warning("!!! АВАРИЙНАЯ ОСТАНОВКА !!!")
        self.hw.arm.stop()
        self.hw.robot_controller.disable()
        self.hw.laser.stop_emission()
        self.hw.laser_power_supply.turn_off()
        self.hw.cathode.set_active(False, False)
        self.hw.edm_power_supply.turn_off()
        self.hw.water.stop_supply()
        self.hw.water.set_drain(True)        # сбрасываем воду из рабочей зоны
        self.hw.transistors.turn_off_all()
        self.process_running = False
        self.paused = False
        self.progress = 0.0
        # Авария оставляет железо обесточенным — требуется повторная инициализация.
        self.initialized = False
        return True

    # ---- движение руки (наладка) ----
    def move_tool_to(self, x=None, y=None, z=None) -> bool:
        if not self._require_initialized():
            return False
        if self.process_running:
            logger.error("Нельзя двигать руку во время процесса")
            return False
        if not self.hw.robot_controller.enabled:
            self.hw.robot_controller.enable(
                power_available=self.hw.transistors.is_channel_on(
                    TransistorChannel.ARM_DRIVES)
            )
        return self.hw.arm.move_tool(x, y, z)

    def move_joint(self, joint: str, angle: float) -> bool:
        if not self._require_initialized():
            return False
        if self.process_running:
            logger.error("Нельзя двигать сустав во время процесса")
            return False
        if not self.hw.robot_controller.enabled:
            self.hw.robot_controller.enable(
                power_available=self.hw.transistors.is_channel_on(
                    TransistorChannel.ARM_DRIVES)
            )
        return self.hw.arm.move_joint(joint, angle)

    def set_arm_speed(self, speed: int) -> bool:
        if not self._require_initialized():
            return False
        return self.hw.robot_controller.set_speed(speed)

    # ---- система воды (наладка) ----
    def set_water_supply(self, on: bool) -> bool:
        if not self._require_initialized():
            return False
        if on:
            self.hw.transistors.turn_on(TransistorChannel.WATER)
            return self.hw.water.start_supply(
                power_available=self.hw.transistors.is_channel_on(TransistorChannel.WATER))
        self.hw.water.stop_supply()
        return self.hw.transistors.turn_off(TransistorChannel.WATER)

    def set_drain(self, on: bool) -> bool:
        if not self._require_initialized():
            return False
        return self.hw.water.set_drain(on)

    # ---- крепление детали (наладка) ----
    def clamp_fixture(self, on: bool) -> bool:
        if not self._require_initialized():
            return False
        if self.process_running:
            logger.error("Нельзя менять зажим во время процесса")
            return False
        return self.hw.fixture.clamp() if on else self.hw.fixture.release()

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

        if not self.hw.edm_power_supply.check_overcurrent():
            logger.warning("Перегрузка по току источника эрозии!")
            self.emergency_stop()
            return False

        if not self.hw.edm_power_supply.is_on():
            logger.warning("Источник эрозии отключился")
            self.emergency_stop()
            return False

        # Потеря охлаждения: при активной обработке нет потока воды
        if not self.paused and not self.hw.water.is_flowing():
            logger.warning("Нет подачи воды во время процесса — потеря охлаждения!")
            self.emergency_stop()
            return False

        return True

    # ---- статус целиком ----
    def get_system_status(self) -> str:
        a = self.hw.arm
        joints = ", ".join(f"{j}={v:.0f}°" for j, v in a.get_joints().items())
        lines = [
            "========== СТАТУС СИСТЕМЫ ==========",
            f"Инициализация: {'выполнена' if self.initialized else 'нет'}",
            f"Процесс: {'запущен' if self.process_running else 'остановлен'}",
            "",
            f"[AC/DC] {self.hw.ac_dc_converter.get_status()}",
            f"[Транзисторы]\n{self.hw.transistors.get_status()}",
            f"[Источник эрозии] {self.hw.edm_power_supply.get_status()}",
            f"[Источник лазера] {self.hw.laser_power_supply.get_status()}",
            f"[Крышка] {self.hw.lid_sensor.get_status()}",
            f"[Контроллер робота] {self.hw.robot_controller.get_status()}",
            f"[Рука] {a.get_status()}",
            f"  суставы: {joints}",
            f"[Головка] {self.hw.head.get_status()}",
            f"[Катод] {self.hw.cathode.get_status()}",
            f"[Анод] {self.hw.anode.get_status()}",
            f"[Лазер] {self.hw.laser.get_status()}",
            f"[Вода] {self.hw.water.get_status()}",
            f"[Крепление] {self.hw.fixture.get_status()}",
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
    приходят от датчиков (крышка, нагрев, ток эрозии, давление/расход воды).
    В реальной прошивке этого класса НЕТ.
    """

    def __init__(self, hardware: HardwareRegistry,
                 process: Optional[ProcessController] = None):
        self.hw = hardware
        self.process = process

    def set_lid(self, closed: bool) -> bool:
        self.hw.lid_sensor.set_lid_state(closed)
        return self._notify_process()

    def set_temperature(self, value: float) -> bool:
        self.hw.temperature_sensor.set_temperature(value)
        return self._notify_process()

    def simulate_current(self, value: float) -> bool:
        return self.hw.edm_power_supply.simulate_current_draw(value)

    def simulate_water_flow(self, value: float) -> bool:
        self.hw.water.simulate_flow(value)
        return self._notify_process()

    def simulate_water_pressure(self, value: float) -> bool:
        self.hw.water.simulate_pressure(value)
        return self._notify_process()

    def _notify_process(self) -> bool:
        if self.process is not None:
            return self.process.check_safety()
        return True


# ============================================================
# Совместимость со старым кодом
# ============================================================

class LaserErosionRobotController:
    """
    Фасад поверх HardwareRegistry + ProcessController + TestHarness,
    сохраняет старый API. Новый код лучше работать напрямую с тремя классами.
    """

    def __init__(self, **kwargs):
        self.hw = HardwareRegistry(**kwargs)
        self.process = ProcessController(self.hw)
        self.test = TestHarness(self.hw, self.process)

        # Прямые ссылки для обратной совместимости
        self.ac_dc_converter    = self.hw.ac_dc_converter
        self.transistors        = self.hw.transistors
        self.edm_power_supply   = self.hw.edm_power_supply
        self.laser_power_supply = self.hw.laser_power_supply
        self.lid_sensor         = self.hw.lid_sensor
        self.robot_controller   = self.hw.robot_controller
        self.arm                = self.hw.arm
        self.laser              = self.hw.laser
        self.cathode            = self.hw.cathode
        self.anode              = self.hw.anode
        self.water              = self.hw.water
        self.head               = self.hw.head
        self.fixture            = self.hw.fixture
        self.temperature_sensor = self.hw.temperature_sensor

    def initialize(self):           return self.process.initialize()
    def start_process(self):        return self.process.start_process()
    def stop_process(self):         return self.process.stop_process()
    def emergency_stop(self):       return self.process.emergency_stop()
    def move_tool_to(self, x=None, y=None, z=None):
        return self.process.move_tool_to(x, y, z)
    def move_joint(self, j, a):     return self.process.move_joint(j, a)
    def set_arm_speed(self, s):     return self.process.set_arm_speed(s)
    def read_temperature(self):     return self.hw.temperature_sensor.read_temperature()
    def is_lid_closed(self):        return self.hw.lid_sensor.is_closed()
    def check_safety_during_process(self): return self.process.check_safety()
    def get_system_status(self):    return self.process.get_system_status()

    @property
    def initialized(self):    return self.process.initialized
    @property
    def process_running(self): return self.process.process_running

    def set_lid_state_mock(self, s):      return self.test.set_lid(s)
    def set_temperature_mock(self, v):    return self.test.set_temperature(v)


# ============================================================
# Самопроверка
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    hw = HardwareRegistry()
    process = ProcessController(hw)
    test = TestHarness(hw, process)

    print(">>> Инициализация")
    process.initialize()

    print("\n>>> Загружаем простой контур")
    process.set_toolpath([(100, 100), (400, 100), (400, 300), (100, 300), (100, 100)])

    print("\n>>> Задаём параметры лазера (с вкладки «Лазером»)")
    hw.laser.set_param("power", 300)
    hw.laser.set_mode("Импульсный")

    print("\n>>> Запуск процесса")
    process.start_process()
    process.drive_scan()

    print("\n>>> Открываем крышку — должна сработать авария")
    test.set_lid(False)

    print("\n>>> Финальный статус")
    print(process.get_system_status())
