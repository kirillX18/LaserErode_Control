"""
controller.py — адаптер между классами-заглушками и UI.

Это единственное место, где UI «знает» о железе. Страницы и виджеты не
обращаются к стабам напрямую — они вызывают методы DeviceController и читают
плоский снимок состояния snapshot(). Так UI остаётся независимым от внутренней
структуры стабов: при замене заглушек на реальную прошивку меняется только
этот файл.

АСИНХРОННОСТЬ (правильная схема Qt):
    Всё, что трогает железо, живёт в отдельном потоке (_HardwareWorker в своём
    QThread). Поток UI НИКОГДА не ждёт железо, а поток железа НИКОГДА не трогает
    виджеты — общение идёт только сигналами Qt (queued-connection):

      • команды (initialize, move_to, …) уходят в воркер сигналом и ставятся
        в очередь — выполняются по одной, не мешая друг другу и не вешая UI;
      • воркер собирает снимок состояния у себя и присылает готовый dict
        (snapshotReady) — UI получает копию и только перерисовывается, общей
        изменяемой памяти между потоками нет;
      • busyChanged/commandFinished позволяют UI блокировать кнопки и показывать
        занятость на время выполнения команды.

    Публичный интерфейс DeviceController не изменился: страницы и виджеты
    работают как раньше (snapshot(), alarms(), stateChanged, logMessage,
    команды-методы). Поэтому остальные файлы менять не нужно.

Связь идёт через сигналы Qt:
    logMessage(level, text)   — сообщения логгера «hardware» (для окна журнала);
    stateChanged()            — что-то изменилось, UI должен перерисоваться;
    busyChanged(bool)         — идёт ли сейчас выполнение команды;
    commandFinished(name, ok) — команда завершилась (имя, успех).
"""

from __future__ import annotations

import logging
import time

from PyQt5.QtCore import (
    QObject, QThread, QMetaObject, pyqtSignal, pyqtSlot, Qt,
)
from PyQt5.QtWidgets import QApplication

from .laser_erosion_stubs import (
    HardwareRegistry, ProcessController, TestHarness, TransistorChannel,
)


class _SignalLogHandler(logging.Handler):
    """Перенаправляет записи логгера «hardware» в сигнал Qt.

    Обработчик срабатывает в том потоке, где идёт логирование (то есть в потоке
    воркера). Это безопасно: emit сигнала можно вызывать из любого потока —
    Qt доставит его получателям (виджетам в UI-потоке) через очередь.
    """

    def __init__(self, controller: "DeviceController"):
        super().__init__()
        self._controller = controller

    def emit(self, record: logging.LogRecord) -> None:
        self._controller.logMessage.emit(record.levelname.lower(),
                                         record.getMessage())


def process_readiness(s: dict):
    """(can_start, reason) — выполнены ли ВСЕ условия запуска процесса.

    Единый источник правды для чек-листа «Условия запуска» и доступности
    кнопки «Запуск процесса» на всех страницах. Порядок проверок повторяет
    ProcessController._check_start_conditions; возвращается первая
    невыполненная причина (или "" если всё готово).
    """
    if s.get("process_running") or s.get("process", {}).get("running"):
        return False, "Процесс уже идёт"
    checks = [
        (s["initialized"],      "Сначала выполните инициализацию"),
        (s["acdc"]["on"],       "Нет питания AC/DC"),
        (s["lid"]["closed"],    "Закройте крышку рабочей зоны"),
        (not s["temp"]["over"], "Перегрев — дождитесь остывания"),
        (s["laser"]["ready"],   "Настройте лазер (задайте мощность > 0 Вт)"),
        (s["robot"]["online"],  "Контроллер робота не на связи"),
        (s["fixture"]["clamped"], "Зафиксируйте деталь в креплении"),
        (s.get("toolpath", {}).get("loaded", False)
            or s.get("part", {}).get("loaded", False),
            "Загрузите программу обработки (контур) или 3D-модель детали"),
    ]
    for ok, reason in checks:
        if not ok:
            return False, reason
    return True, ""


def _compute_alarms(s: dict) -> list:
    """Активные аварии/предупреждения по снимку: список (severity, text, source).

    Чистая функция от снимка — считается в UI-потоке по уже полученной копии,
    к железу не обращается.
    """
    out = []
    if not s["lid"]["closed"]:
        out.append(("err", "Крышка открыта", "lid_sensor.is_open()"))
    if s["temp"]["over"]:
        out.append(("err", f"Перегрев: {s['temp']['t']:.1f} °C > {s['temp']['max']:.0f} °C",
                    "temperature_sensor.is_overheated()"))
    if s["psu"]["tripped"]:
        out.append(("err", "Перегрузка по току источника эрозии",
                    "edm_power_supply.overcurrent_tripped"))
    if s["process_running"] and not s["psu"]["on"]:
        out.append(("err", "Источник эрозии отключился во время процесса",
                    "edm_power_supply.is_on()"))
    if s["process_running"] and not s.get("process", {}).get("paused") \
            and not s["water"]["flowing"]:
        out.append(("err", "Нет подачи воды — потеря охлаждения",
                    "water.is_flowing()"))
    if not s["acdc"]["on"]:
        out.append(("warn", "Нет питания AC/DC — запуск невозможен",
                    "ac_dc_converter.is_on()"))
    if s["acdc"]["on"] and not s["laser"]["ready"] and not s["process_running"]:
        out.append(("warn", "Лазер не настроен (мощность 0 Вт)",
                    "laser.is_ready()"))
    if s["acdc"]["on"] and not s["robot"]["online"] and not s["process_running"]:
        out.append(("warn", "Контроллер робота не на связи",
                    "robot_controller.online"))
    if s["acdc"]["on"] and not s["fixture"]["clamped"] and not s["process_running"]:
        out.append(("warn", "Деталь не зафиксирована в креплении",
                    "fixture.is_clamped()"))
    psu = s["psu"]
    if psu["on"] and psu["limit"] * 0.9 <= psu["i"] <= psu["limit"]:
        out.append(("warn", f"Ток близок к лимиту: {psu['i']:.1f} / {psu['limit']:.1f} А",
                    "edm_power_supply.get_current()"))
    return out


# ======================================================================
# Воркер: живёт в отдельном потоке, единственный, кто трогает железо.
# ======================================================================
class _HardwareWorker(QObject):
    """Владеет стабами и выполняет все обращения к железу в своём потоке.

    Наружу отдаёт только сигналы. Команды принимает слотом run(name, args):
    каждый вызов попадает в очередь событий потока и выполняется по очереди,
    поэтому команды не накладываются друг на друга, а долгая операция (реальное
    железо) не вешает UI — она просто блокирует ЭТОТ поток.
    """

    snapshotReady = pyqtSignal(dict)        # готовый снимок состояния (копия)
    commandDone = pyqtSignal(str, bool)     # (имя команды, успех)

    def __init__(self):
        super().__init__()                  # без parent — обязательно для moveToThread
        self.hw = HardwareRegistry()
        self.process = ProcessController(self.hw)
        self.test = TestHarness(self.hw, self.process)

        # Фоновое движение руки остаётся включённым: стаб сам имитирует ход в
        # своём потоке, индикатор «движется» виден до завершения. Поток воркера
        # при этом свободен.
        self.hw.arm.set_async_motion(True, scale=0.4)

        # Момент предыдущего опроса — для подсчёта реального dt прогресса процесса.
        self._last_poll: float | None = None

        # Карта команд: имя -> вызываемое.
        self._dispatch = {
            "initialize": self.process.initialize,
            "start_process": self.process.start_process,
            "stop_process": self.process.stop_process,
            "pause_process": self.process.pause_process,
            "resume_process": self.process.resume_process,
            "emergency_stop": self.process.emergency_stop,
            "set_current_limit": self.hw.edm_power_supply.set_current_limit,
            "set_max_temp": self.hw.temperature_sensor.set_max_temperature,
            "set_load_power": self.hw.transistors.set_load_power,
            "set_channel": self._set_channel,
            "acdc_on": self.hw.ac_dc_converter.turn_on,
            "acdc_off": self.hw.ac_dc_converter.turn_off,
            "load_toolpath": self.process.set_toolpath,
            "clear_toolpath": self.process.clear_toolpath,
            "set_part_loaded": self.process.set_part_loaded,
            "set_machining_motion": self.process.set_machining_motion,
            "set_laser_param": self.hw.laser.set_param,
            "set_laser_mode": self.hw.laser.set_mode,
            # --- рука и контроллер робота ---
            "set_speed": self.process.set_arm_speed,
            "set_arm_speed": self.process.set_arm_speed,
            "move_to": self.process.move_tool_to,
            "move_tool": self.process.move_tool_to,
            "move_joint": self.process.move_joint,
            "reset_motor": self._home_arm,
            "home_arm": self._home_arm,
            "stop_motor": self.hw.arm.stop,
            "stop_arm": self.hw.arm.stop,
            # --- совместимость со старым «столом» (Y теперь — ось руки) ---
            "move_table": self._move_table_compat,
            "set_table_speed": self.process.set_arm_speed,
            "reset_table": self._home_arm,
            "stop_table": self.hw.arm.stop,
            # --- система воды ---
            "set_water": self.process.set_water_supply,
            "set_drain": self.process.set_drain,
            # --- крепление детали ---
            "clamp_fixture": self.process.clamp_fixture,
            # --- имитация сигналов датчиков (стенд) ---
            "set_lid": self.test.set_lid,
            "set_temperature": self.test.set_temperature,
            "simulate_current": self._simulate_current,
            "simulate_water_flow": self.test.simulate_water_flow,
            "simulate_water_pressure": self.test.simulate_water_pressure,
        }

    # --- обёртки для команд со своей логикой ---------------------------
    def _set_channel(self, channel: TransistorChannel, on: bool):
        fn = self.hw.transistors.turn_on if on else self.hw.transistors.turn_off
        return fn(channel)

    def _home_arm(self):
        return self.hw.arm.home()

    def _move_table_compat(self, y):
        """Старая команда «стол по Y» — теперь это перемещение руки по оси Y."""
        return self.process.move_tool_to(y=y)

    def _simulate_current(self, v):
        result = self.test.simulate_current(v)
        self.process.check_safety()  # стаб не делает это сам для тока
        return result

    # --- слоты, вызываемые из UI через queued-connection ----------------
    @pyqtSlot(str, object)
    def run(self, name: str, args: tuple) -> None:
        """Выполнить команду. Может блокировать — это поток воркера, не UI."""
        fn = self._dispatch.get(name)
        ok = False
        if fn is not None:
            try:
                ok = bool(fn(*args))
            except Exception:                      # noqa: BLE001 — не роняем поток
                logging.getLogger("hardware").exception(
                    "Ошибка выполнения команды %s", name)
                ok = False
        self.snapshotReady.emit(self._snapshot())
        self.commandDone.emit(name, ok)

    @pyqtSlot()
    def poll(self) -> None:
        """Периодический мониторинг безопасности + рассылка снимка."""
        now = time.monotonic()
        if self._last_poll is not None:
            self.process.advance_progress(now - self._last_poll)
        self._last_poll = now
        self.process.drive_scan()
        self.process.check_safety()
        self.snapshotReady.emit(self._snapshot())

    # --- снимок состояния (плоский dict — UI не лезет внутрь стабов) -----
    def _snapshot(self) -> dict:
        hw, p = self.hw, self.process
        ch = hw.transistors.channels
        arm = hw.arm
        rc = hw.robot_controller
        edm = hw.edm_power_supply
        return {
            "initialized": p.initialized,
            "process_running": p.process_running,
            "process": {
                "running": p.process_running,
                "paused": p.paused,
                "progress": p.progress,
                "duration": p.PROCESS_DURATION,
            },
            "system_status": p.get_system_status(),
            "toolpath": {
                "loaded": bool(p.toolpath),
                "points": len(p.toolpath),
            },
            "part": {
                "loaded": bool(p.part_loaded),
            },
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
            # Источник эрозии (основной силовой источник с защитой по току).
            "edm": {
                "on": edm.is_on(),
                "v": edm.get_voltage(),
                "i": edm.get_current(),
                "limit": edm.current_limit,
                "max_limit": edm.max_current_limit,
                "tripped": edm.overcurrent_tripped,
            },
            "laser_psu": {
                "on": hw.laser_power_supply.is_on(),
                "v": hw.laser_power_supply.get_voltage(),
            },
            "lid": {"closed": hw.lid_sensor.is_closed()},
            # Контроллер 8-суставного робота.
            "robot": {
                "online": rc.online,
                "enabled": rc.enabled,
                "moving": rc.moving,
                "speed": rc.speed,
            },
            # Роботизированная 8-суставная рука: положение инструмента + суставы.
            "arm": {
                "x": arm.tool["x"], "y": arm.tool["y"], "z": arm.tool["z"],
                "ranges": {a: list(arm.ranges[a]) for a in arm.AXES},
                "joints": {j: v for j, v in arm.get_joints().items()},
                "limits": {j: list(lim) for j, lim in arm.JOINT_LIMITS.items()},
                "moving": arm.moving,
            },
            # Лазерно-эрозионная рабочая головка.
            "head": {"machining": hw.head.is_machining()},
            "cathode": {"connected": hw.cathode.connected, "active": hw.cathode.active},
            "anode": {"connected": hw.anode.connected},
            "laser": {
                "powered": hw.laser.powered,
                "emitting": hw.laser.is_emitting(),
                "ready": hw.laser.is_ready(),
                "power": hw.laser.power,
                "frequency": hw.laser.frequency,
                "focus": hw.laser.focus,
                "pulse": hw.laser.pulse,
                "exposure": hw.laser.exposure,
                "mode": hw.laser.mode.value,
            },
            # Система подачи воды.
            "water": {
                "pump": hw.water.pump_on,
                "valve": hw.water.valve_open,
                "pressure": hw.water.get_pressure(),
                "flow": hw.water.get_flow(),
                "flowing": hw.water.is_flowing(),
                "drain": hw.water.drain_open,
                "min_flow": hw.water.min_flow,
            },
            # Неподвижное крепление детали.
            "fixture": {"clamped": hw.fixture.is_clamped()},
            "temp": {
                "t": hw.temperature_sensor.read_temperature(),
                "max": hw.temperature_sensor.max_temperature,
                "over": hw.temperature_sensor.is_overheated(),
            },

            # ----------------------------------------------------------------
            # Обратная совместимость со старым UI (ШД + стол + источник 48 В).
            # Позиционирование теперь выполняет рука: X/Z — оси инструмента,
            # Y — третья ось руки (бывший «стол»). Источник «psu» = источник
            # эрозии. Эти алиасы позволяют существующим вкладкам работать без
            # правок до их миграции на ключи arm/robot/edm/water/fixture.
            # ----------------------------------------------------------------
            "motor": {
                "x": int(round(arm.tool["x"])),
                "z": int(round(arm.tool["z"])),
                "min": arm.ranges["x"][0],
                "max": arm.ranges["x"][1],
                "moving": arm.moving,
            },
            "table": {
                "pos": int(round(arm.tool["y"])),
                "min": arm.ranges["y"][0],
                "max": arm.ranges["y"][1],
                "moving": arm.moving,
                "online": rc.online,
                "enabled": rc.enabled,
                "speed": rc.speed,
            },
            "driver": {
                "enabled": rc.enabled,
                "moving": rc.moving,
                "speed": rc.speed,
                "connected": arm.controller is rc,
            },
            "psu": {
                "on": edm.is_on(),
                "v": edm.get_voltage(),
                "i": edm.get_current(),
                "limit": edm.current_limit,
                "max_limit": edm.max_current_limit,
                "tripped": edm.overcurrent_tripped,
            },
        }


# ======================================================================
# Фасад: живёт в UI-потоке, наружу — прежний интерфейс DeviceController.
# ======================================================================
class DeviceController(QObject):
    """Фасад над воркером. Команды ставит в очередь, состояние отдаёт из кэша."""

    logMessage = pyqtSignal(str, str)        # (level, text)
    stateChanged = pyqtSignal()              # без аргументов — как раньше
    busyChanged = pyqtSignal(bool)           # идёт ли выполнение команды
    commandFinished = pyqtSignal(str, bool)  # (имя, успех)

    # Внутренний сигнал-«почтальон» к воркеру (queued, т.к. разные потоки).
    _command = pyqtSignal(str, object)

    def __init__(self, parent=None, busy_cursor: bool = True):
        super().__init__(parent)

        self._worker = _HardwareWorker()
        # Снимок, доступный сразу (страницы читают snapshot() уже в __init__,
        # до старта потока). Считаем синхронно — конкурентного доступа ещё нет.
        self._snap: dict = self._worker._snapshot()
        self._pending = 0                    # сколько команд «в полёте»

        # Подписываемся на логгер «hardware» (как и раньше).
        self._handler = _SignalLogHandler(self)
        self._handler.setLevel(logging.INFO)
        log = logging.getLogger("hardware")
        log.setLevel(logging.INFO)
        log.addHandler(self._handler)
        log.propagate = False

        # Переносим воркер в свой поток и связываем сигналы.
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._worker.snapshotReady.connect(self._on_snapshot)    # queued -> UI
        self._worker.commandDone.connect(self._on_command_done)  # queued -> UI
        self._command.connect(self._worker.run)                  # queued -> воркер
        self._thread.start()

        # Видимая занятость без правок страниц: курсор ожидания на время команды.
        if busy_cursor:
            self.busyChanged.connect(self._toggle_wait_cursor)

        # Чистое завершение потока при выходе из приложения (без правок window.py).
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    # ------------------------------------------------------------------
    # Постановка команд в очередь воркера (fire-and-forget; результат —
    # сигналом commandFinished). Возвращаемое значение нигде не использовалось.
    # ------------------------------------------------------------------
    def _request(self, name: str, *args) -> None:
        self._pending += 1
        if self._pending == 1:
            self.busyChanged.emit(True)
        self._command.emit(name, args)

    # ------------------------------------------------------------------
    # Команды процесса
    # ------------------------------------------------------------------
    def initialize(self):      self._request("initialize")
    def start_process(self):   self._request("start_process")
    def stop_process(self):    self._request("stop_process")
    def pause_process(self):   self._request("pause_process")
    def resume_process(self):  self._request("resume_process")
    def emergency_stop(self):  self._request("emergency_stop")

    # ------------------------------------------------------------------
    # Параметры
    # ------------------------------------------------------------------
    def set_current_limit(self, v): self._request("set_current_limit", v)
    def set_speed(self, v):         self._request("set_arm_speed", v)
    def set_arm_speed(self, v):     self._request("set_arm_speed", v)
    def move_to(self, x=None, z=None): self._request("move_to", x, z)
    def move_tool(self, x=None, y=None, z=None): self._request("move_tool", x, y, z)
    def move_joint(self, joint, angle): self._request("move_joint", joint, angle)
    def set_max_temp(self, v):      self._request("set_max_temp", v)
    def set_load_power(self, on):   self._request("set_load_power", on)
    def reset_motor(self):          self._request("reset_motor")
    def home_arm(self):             self._request("home_arm")
    def stop_motor(self):           self._request("stop_motor")
    def stop_arm(self):             self._request("stop_arm")

    def set_channel(self, channel: TransistorChannel, on: bool):
        self._request("set_channel", channel, on)

    def acdc_on(self):  self._request("acdc_on")
    def acdc_off(self): self._request("acdc_off")

    # ------------------------------------------------------------------
    # Ось Y руки (бывший координатный стол — оставлен для совместимости UI)
    # ------------------------------------------------------------------
    def move_table(self, pos):       self._request("move_table", pos)
    def set_table_speed(self, v):    self._request("set_table_speed", v)
    def reset_table(self):           self._request("reset_table")
    def stop_table(self):            self._request("stop_table")

    # ------------------------------------------------------------------
    # Система подачи воды и крепление детали
    # ------------------------------------------------------------------
    def set_water(self, on):         self._request("set_water", on)
    def set_drain(self, on):         self._request("set_drain", on)
    def clamp_fixture(self, on):     self._request("clamp_fixture", on)

    # ------------------------------------------------------------------
    # Программа обработки (плоский контур из DXF/SVG/PLT/HPGL)
    # ------------------------------------------------------------------
    def load_toolpath(self, points): self._request("load_toolpath", points)
    def clear_toolpath(self):        self._request("clear_toolpath")
    def set_part_loaded(self, on):   self._request("set_part_loaded", on)
    def set_machining_motion(self, xf=None, yf=None):
        self._request("set_machining_motion", xf, yf)

    # ------------------------------------------------------------------
    # Лазерный излучатель (параметры с вкладки «Лазером»)
    # ------------------------------------------------------------------
    def set_laser_param(self, key, value): self._request("set_laser_param", key, value)
    def set_laser_mode(self, mode):        self._request("set_laser_mode", mode)

    # ------------------------------------------------------------------
    # Имитация сигналов датчиков (TestHarness — только стенд)
    # ------------------------------------------------------------------
    def set_lid(self, closed):       self._request("set_lid", closed)
    def set_temperature(self, v):    self._request("set_temperature", v)
    def simulate_current(self, v):   self._request("simulate_current", v)
    def simulate_water_flow(self, v):     self._request("simulate_water_flow", v)
    def simulate_water_pressure(self, v): self._request("simulate_water_pressure", v)

    # ------------------------------------------------------------------
    # Мониторинг (вызывается периодически из QTimer в window.py)
    # ------------------------------------------------------------------
    def poll(self) -> None:
        """«Метроном»: ставим в очередь воркеру опрос безопасности.

        Сама проверка и сбор снимка идут в потоке воркера; UI не блокируется.
        """
        QMetaObject.invokeMethod(self._worker, "poll", Qt.QueuedConnection)

    def system_status(self) -> str:
        return self._snap.get("system_status", "")

    # ------------------------------------------------------------------
    # Состояние для UI — из кэша (копия, без обращений к железу)
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return self._snap

    def alarms(self) -> list:
        return _compute_alarms(self._snap)

    def is_busy(self) -> bool:
        return self._pending > 0

    # ------------------------------------------------------------------
    # Завершение
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)

    # ------------------------------------------------------------------
    # Слоты UI-потока (приём сигналов воркера)
    # ------------------------------------------------------------------
    @pyqtSlot(dict)
    def _on_snapshot(self, snap: dict) -> None:
        self._snap = snap
        self.stateChanged.emit()

    @pyqtSlot(str, bool)
    def _on_command_done(self, name: str, ok: bool) -> None:
        if self._pending > 0:
            self._pending -= 1
        if self._pending == 0:
            self.busyChanged.emit(False)
        self.commandFinished.emit(name, ok)

    @pyqtSlot(bool)
    def _toggle_wait_cursor(self, busy: bool) -> None:
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()


# Единый общий контроллер на всё приложение (шапка и страница «Оборудование»
# должны видеть одно и то же состояние). Создаётся лениво.
_INSTANCE: "DeviceController | None" = None


def controller() -> DeviceController:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DeviceController()
    return _INSTANCE
