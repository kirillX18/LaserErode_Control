class AcDcConverterStub:

    def __init__(self):
        self.name = "AC/DC преобразователь"
        self.powered_on = False
        self.input_voltage = 220
        self.output_voltage = 24

    def turn_on(self):
        self.powered_on = True
        print(f"{self.name}: включен")
        return True

    def turn_off(self):
        self.powered_on = False
        print(f"{self.name}: выключен")
        return True

    def is_on(self):
        return self.powered_on

    def get_input_voltage(self):
        return self.input_voltage if self.powered_on else 0

    def get_output_voltage(self):
        return self.output_voltage if self.powered_on else 0

    def get_status(self):
        if self.powered_on:
            return (
                f"AC/DC преобразователь включен. "
                f"Входное напряжение: {self.input_voltage} В. "
                f"Выходное напряжение: {self.output_voltage} В."
            )
        return "AC/DC преобразователь выключен. Входное напряжение: 0 В. Выходное напряжение: 0 В."


class TransistorSwitchBlockStub:

    def __init__(self):
        self.name = "Блок транзисторных ключей"
        self.common_ground = True
        self.load_power_enabled = False
        self.channels = {
            "vibro_table": {
                "control_signal": 0,
                "transistor_open": False,
                "load_enabled": False,
                "description": "Питание вибростола",
            },
            "power_48v": {
                "control_signal": 0,
                "transistor_open": False,
                "load_enabled": False,
                "description": "Разрешение питания источника 48 В",
            },
            "polishing_cell": {
                "control_signal": 0,
                "transistor_open": False,
                "load_enabled": False,
                "description": "Подача 48 В на ёмкость полировки",
            },
        }

    def set_load_power(self, state: bool):
        self.load_power_enabled = bool(state)
        self._update_all_channels()
        print(f"{self.name}: силовое питание нагрузок {'включено' if state else 'отключено'}")
        return True

    def set_control_signal(self, channel: str, signal: int):
        if channel not in self.channels:
            print(f"{self.name}: ошибка — канала '{channel}' не существует")
            return False
        if signal not in (0, 1):
            print(f"{self.name}: ошибка — управляющий сигнал должен быть 0 или 1")
            return False

        self.channels[channel]["control_signal"] = signal
        self._update_channel(channel)
        print(
            f"{self.name}: канал '{channel}' — "
            f"{'транзистор открыт' if signal == 1 else 'транзистор закрыт'}"
        )
        return True

    def turn_on(self, channel: str):
        return self.set_control_signal(channel, 1)

    def turn_off(self, channel: str):
        return self.set_control_signal(channel, 0)

    def turn_off_all(self):
        for channel in self.channels:
            self.channels[channel]["control_signal"] = 0
            self._update_channel(channel)
        print(f"{self.name}: все транзисторы закрыты")
        return True

    def is_channel_on(self, channel: str):
        if channel not in self.channels:
            print(f"{self.name}: ошибка — канала '{channel}' не существует")
            return False
        return self.channels[channel]["load_enabled"]

    def is_transistor_open(self, channel: str):
        if channel not in self.channels:
            print(f"{self.name}: ошибка — канала '{channel}' не существует")
            return False
        return self.channels[channel]["transistor_open"]

    def get_channel_state(self, channel: str):
        if channel not in self.channels:
            print(f"{self.name}: ошибка — канала '{channel}' не существует")
            return None
        return dict(self.channels[channel])

    def _update_channel(self, channel: str):
        data = self.channels[channel]
        data["transistor_open"] = self.common_ground and data["control_signal"] == 1
        data["load_enabled"] = data["transistor_open"] and self.load_power_enabled

    def _update_all_channels(self):
        for channel in self.channels:
            self._update_channel(channel)

    def get_status(self):
        lines = [
            f"Силовое питание нагрузок: {'есть' if self.load_power_enabled else 'нет'}",
            f"Общая земля: {'есть' if self.common_ground else 'нет'}",
        ]
        for name, data in self.channels.items():
            lines.append(
                f"- {name} ({data['description']}): сигнал={data['control_signal']}, "
                f"транзистор={'открыт' if data['transistor_open'] else 'закрыт'}, "
                f"нагрузка={'включена' if data['load_enabled'] else 'выключена'}"
            )
        return "\n".join(lines)


class VibroTableStub:


    def __init__(self):
        self.name = "Вибростол"
        self.power_supplied = False

    def supply_power(self):
        self.power_supplied = True
        print(f"{self.name}: питание подано, вибрация началась")
        return True

    def cut_power(self):
        self.power_supplied = False
        print(f"{self.name}: питание отключено, вибрация остановлена")
        return True

    def is_vibrating(self):
        return self.power_supplied

    def get_status(self):
        return "Вибростол: питание подано, вибрирует" if self.power_supplied else "Вибростол: питание не подано, не вибрирует"


class PowerSupply48VStub:

    def __init__(self):
        self.name = "Источник напряжения 48 В"
        self.powered_on = False
        self.voltage = 48.0
        self.current = 0.0
        self.current_limit = 5.0

    def turn_on(self, power_allowed=True):
        if not power_allowed:
            print(f"{self.name}: ошибка — питание через транзисторный ключ не разрешено")
            return False
        self.powered_on = True
        self.current = min(1.2, self.current_limit)
        print(f"{self.name}: включен, напряжение {self.voltage} В")
        return True

    def turn_off(self):
        self.powered_on = False
        self.current = 0.0
        print(f"{self.name}: выключен")
        return True

    def is_on(self):
        return self.powered_on

    def get_voltage(self):
        return self.voltage if self.powered_on else 0.0

    def get_current(self):
        return self.current if self.powered_on else 0.0

    def set_current_limit(self, value):
        if value <= 0:
            print(f"{self.name}: ошибка — ограничение тока должно быть больше 0")
            return False
        self.current_limit = float(value)
        if self.powered_on:
            self.current = min(self.current, self.current_limit)
        print(f"{self.name}: ограничение тока установлено на {self.current_limit} А")
        return True

    def get_status(self):
        if self.powered_on:
            return (
                f"Источник 48 В включен: напряжение {self.voltage} В, "
                f"ток {self.current} А, ограничение {self.current_limit} А"
            )
        return f"Источник 48 В выключен. Ограничение тока: {self.current_limit} А"


class LidSensorStub:


    def __init__(self):
        self.name = "Датчик закрытия крышки"
        self.lid_closed = False

    def is_closed(self):
        return self.lid_closed

    def is_open(self):
        return not self.lid_closed

    def set_lid_state(self, state):
        self.lid_closed = bool(state)
        print(f"{self.name}: {'крышка закрыта' if self.lid_closed else 'крышка открыта'}")
        return True

    def get_status(self):
        return "Крышка закрыта" if self.lid_closed else "Крышка открыта"


class StepperMotorDriverStub:


    def __init__(self):
        self.name = "Драйвер шагового двигателя"
        self.enabled = False
        self.moving = False
        self.speed = 100
        self.direction = 0

    def enable(self, power_available=True):
        if not power_available:
            print(f"{self.name}: ошибка — нет питания от AC/DC преобразователя")
            return False
        self.enabled = True
        print(f"{self.name}: включен")
        return True

    def disable(self):
        self.stop()
        self.enabled = False
        print(f"{self.name}: выключен")
        return True

    def set_speed(self, value):
        if value <= 0:
            print(f"{self.name}: ошибка — скорость должна быть больше 0")
            return False
        self.speed = int(value)
        print(f"{self.name}: скорость установлена на {self.speed} шаг/с")
        return True

    def start_motion(self, direction):
        if not self.enabled:
            print(f"{self.name}: ошибка — драйвер выключен")
            return False
        if direction not in (-1, 1):
            print(f"{self.name}: ошибка — направление должно быть 1 или -1")
            return False
        self.direction = direction
        self.moving = True
        print(f"{self.name}: начато движение {'вперёд' if direction == 1 else 'назад'}")
        return True

    def stop(self):
        self.moving = False
        self.direction = 0
        print(f"{self.name}: остановлен")
        return True

    def get_status(self):
        if not self.enabled:
            return f"Драйвер выключен. Скорость: {self.speed} шаг/с"
        if self.moving:
            return f"Драйвер включен, движение выполняется. Скорость: {self.speed} шаг/с"
        return f"Драйвер включен, двигатель остановлен. Скорость: {self.speed} шаг/с"


class StepperMotorStub:


    def __init__(self):
        self.name = "Шаговый двигатель"
        self.driver = None
        self.moving = False
        self.position = 0
        self.max_position = 1000
        self.min_position = 0

    def attach_driver(self, driver):
        self.driver = driver
        print(f"{self.name}: драйвер назначен")
        return True

    def _can_move(self):
        if self.driver is None:
            print(f"{self.name}: ошибка — драйвер не назначен")
            return False
        if not self.driver.enabled:
            print(f"{self.name}: ошибка — драйвер выключен")
            return False
        return True

    def move_steps(self, steps):
        if not self._can_move():
            return False
        steps = int(steps)
        new_position = self.position + steps
        if new_position > self.max_position:
            print(f"{self.name}: ошибка — превышена максимальная позиция {self.max_position}")
            return False
        if new_position < self.min_position:
            print(f"{self.name}: ошибка — позиция не может быть меньше {self.min_position}")
            return False
        if steps == 0:
            print(f"{self.name}: перемещение не требуется")
            return True

        direction = 1 if steps > 0 else -1
        if not self.driver.start_motion(direction):
            return False
        self.moving = True
        print(f"{self.name}: движение {'вперёд' if steps > 0 else 'назад'} на {abs(steps)} шагов")
        self.position = new_position
        self.moving = False
        self.driver.stop()
        print(f"{self.name}: движение завершено, текущая позиция {self.position}")
        return True

    def move_to_position(self, position):
        position = int(position)
        if position > self.max_position:
            print(f"{self.name}: ошибка — позиция больше максимальной {self.max_position}")
            return False
        if position < self.min_position:
            print(f"{self.name}: ошибка — позиция меньше минимальной {self.min_position}")
            return False
        return self.move_steps(position - self.position)

    def stop(self):
        self.moving = False
        if self.driver is not None:
            self.driver.stop()
        print(f"{self.name}: остановлен")
        return True

    def get_position(self):
        return self.position

    def reset_position(self):
        self.position = 0
        print(f"{self.name}: позиция сброшена в 0")
        return True

    def get_status(self):
        if self.driver is None:
            return "Шаговый двигатель: драйвер не назначен"
        if self.moving:
            return f"Шаговый двигатель движется, текущая позиция: {self.position} шагов"
        return f"Шаговый двигатель остановлен, текущая позиция: {self.position} шагов"


class PolishingTankStub:


    def __init__(self):
        self.name = "Ёмкость для полировки"
        self.filled = False
        self.anode_connected = False
        self.cathode_connected = False
        self.process_running = False
        self.applied_voltage = 0.0

    def fill(self):
        self.filled = True
        print(f"{self.name}: заполнена рабочей жидкостью")
        return True

    def drain(self):
        if self.process_running:
            print(f"{self.name}: ошибка — нельзя сливать жидкость во время процесса")
            return False
        self.filled = False
        print(f"{self.name}: рабочая жидкость слита")
        return True

    def connect_electrodes(self):
        self.anode_connected = True
        self.cathode_connected = True
        print(f"{self.name}: анод и катод подключены")
        return True

    def disconnect_electrodes(self):
        if self.process_running:
            print(f"{self.name}: ошибка — нельзя отключать электроды во время процесса")
            return False
        self.anode_connected = False
        self.cathode_connected = False
        print(f"{self.name}: анод и катод отключены")
        return True

    def is_ready(self):
        return self.filled and self.anode_connected and self.cathode_connected

    def start_process(self, voltage, voltage_applied=True):
        if not self.filled:
            print(f"{self.name}: ошибка — ёмкость не заполнена рабочей жидкостью")
            return False
        if not self.anode_connected:
            print(f"{self.name}: ошибка — анод не подключён")
            return False
        if not self.cathode_connected:
            print(f"{self.name}: ошибка — катод не подключён")
            return False
        if not voltage_applied:
            print(f"{self.name}: ошибка — транзисторный ключ полировки закрыт")
            return False
        if voltage <= 0:
            print(f"{self.name}: ошибка — напряжение должно быть больше 0 В")
            return False

        self.process_running = True
        self.applied_voltage = float(voltage)
        print(f"{self.name}: процесс полировки запущен, напряжение {voltage} В")
        return True

    def stop_process(self):
        self.process_running = False
        self.applied_voltage = 0.0
        print(f"{self.name}: процесс полировки остановлен")
        return True

    def is_process_running(self):
        return self.process_running

    def get_applied_voltage(self):
        return self.applied_voltage

    def get_status(self):
        status = "Ёмкость для полировки\n"
        status += "- Рабочая жидкость: есть\n" if self.filled else "- Рабочая жидкость: отсутствует\n"
        status += "- Анод: подключён\n" if self.anode_connected else "- Анод: не подключён\n"
        status += "- Катод: подключён\n" if self.cathode_connected else "- Катод: не подключён\n"
        status += f"- Процесс: запущен, напряжение {self.applied_voltage} В" if self.process_running else "- Процесс: остановлен"
        return status


class TemperatureSensorStub:


    def __init__(self):
        self.name = "Датчик температуры"
        self.temperature = 25.0
        self.max_temperature = 60.0

    def read_temperature(self):
        print(f"{self.name}: текущая температура {self.temperature} °C")
        return self.temperature

    def set_temperature(self, value):
        self.temperature = float(value)
        print(f"{self.name}: температура установлена на {self.temperature} °C")
        return True

    def is_overheated(self):
        return self.temperature > self.max_temperature

    def set_max_temperature(self, value):
        if value <= 0:
            print(f"{self.name}: ошибка — максимальная температура должна быть больше 0")
            return False
        self.max_temperature = float(value)
        print(f"{self.name}: максимально допустимая температура {self.max_temperature} °C")
        return True

    def get_status(self):
        if self.is_overheated():
            return f"Датчик температуры: {self.temperature} °C. ВНИМАНИЕ: перегрев!"
        return f"Датчик температуры: {self.temperature} °C. Состояние: норма"


class LaserErosionRobotController:

    def __init__(
        self,
        stepper_speed=200,
        current_limit=5.0,
        max_temperature=60.0,
        initial_temperature=25.0,
        tank_filled=True,
        electrodes_connected=True,
    ):
        self.ac_dc_converter = AcDcConverterStub()
        self.transistors = TransistorSwitchBlockStub()
        self.vibro_table = VibroTableStub()
        self.power_supply_48v = PowerSupply48VStub()
        self.lid_sensor = LidSensorStub()
        self.stepper_driver = StepperMotorDriverStub()
        self.stepper_motor = StepperMotorStub()
        self.polishing_tank = PolishingTankStub()
        self.temperature_sensor = TemperatureSensorStub()

        self.stepper_speed = stepper_speed
        self.current_limit = current_limit
        self.max_temperature = max_temperature
        self.initial_temperature = initial_temperature
        self.default_tank_filled = tank_filled
        self.default_electrodes_connected = electrodes_connected

        self.initialized = False
        self.process_running = False

    def initialize(self):
        print("=== Инициализация контроллера ===")

        # Контроллер не включает AC/DC преобразователь.
        # Если AC/DC выключен, контроллер в реальности не запитан
        # и не может выполнять управляющую программу.
        # В заглушке мы только проверяем, что внешнее питание уже есть.
        if not self.ac_dc_converter.is_on():
            print("Ошибка: нет питания от AC/DC преобразователя. Контроллер не может начать работу")
            return False

        logic_power_available = self.ac_dc_converter.get_output_voltage() > 0
        if not logic_power_available:
            print("Ошибка: AC/DC преобразователь не выдаёт выходное напряжение")
            return False

        self.transistors.set_load_power(True)

        self.power_supply_48v.set_current_limit(self.current_limit)

        self.stepper_driver.set_speed(self.stepper_speed)
        self.stepper_driver.enable(power_available=logic_power_available)
        self.stepper_motor.attach_driver(self.stepper_driver)

        # В учебной заглушке эти состояния можно подготовить автоматически,
        # но по смыслу схемы это не управление крышкой.
        if self.default_tank_filled:
            self.polishing_tank.fill()
        if self.default_electrodes_connected:
            self.polishing_tank.connect_electrodes()

        self.temperature_sensor.set_max_temperature(self.max_temperature)
        self.temperature_sensor.set_temperature(self.initial_temperature)

        self.initialized = True
        print("=== Контроллер готов к работе ===")
        return True

    def _require_initialized(self):
        if not self.initialized:
            print("Ошибка: оборудование не инициализировано")
            return False
        return True

    def _check_start_conditions(self):
        if not self._require_initialized():
            return False
        if not self.ac_dc_converter.is_on():
            print("Ошибка: отсутствует питание от AC/DC преобразователя")
            return False
        if not self.lid_sensor.is_closed():
            print("Ошибка: крышка открыта. Запуск запрещён")
            return False
        if self.temperature_sensor.is_overheated():
            print("Ошибка: перегрев. Запуск запрещён")
            return False
        if not self.polishing_tank.is_ready():
            print("Ошибка: ёмкость для полировки не готова")
            return False
        return True

    def start_process(self):
        print("=== Запуск процесса ===")
        if not self._check_start_conditions():
            return False

        self.transistors.set_load_power(self.ac_dc_converter.get_output_voltage() > 0)

        if not self.transistors.turn_on("power_48v"):
            return False
        if not self.power_supply_48v.turn_on(power_allowed=self.transistors.is_channel_on("power_48v")):
            self.stop_process()
            return False

        if not self.transistors.turn_on("polishing_cell"):
            self.stop_process()
            return False
        if not self.transistors.turn_on("vibro_table"):
            self.stop_process()
            return False

        if self.transistors.is_channel_on("vibro_table"):
            self.vibro_table.supply_power()
        else:
            print("Ошибка: питание на вибростол не подано")
            self.stop_process()
            return False

        voltage = self.power_supply_48v.get_voltage()
        voltage_applied_to_tank = self.transistors.is_channel_on("polishing_cell") and self.power_supply_48v.is_on()
        if not self.polishing_tank.start_process(voltage, voltage_applied=voltage_applied_to_tank):
            self.stop_process()
            return False

        self.process_running = True
        print("=== Процесс успешно запущен ===")
        return True

    def stop_process(self):
        print("=== Остановка процесса ===")
        self.polishing_tank.stop_process()
        self.vibro_table.cut_power()
        self.transistors.turn_off("vibro_table")
        self.transistors.turn_off("polishing_cell")
        self.transistors.turn_off("power_48v")
        self.power_supply_48v.turn_off()
        self.process_running = False
        print("=== Процесс остановлен ===")
        return True

    def emergency_stop(self):
        print("!!! АВАРИЙНАЯ ОСТАНОВКА !!!")
        self.stepper_motor.stop()
        self.stepper_driver.disable()
        self.polishing_tank.stop_process()
        self.vibro_table.cut_power()
        self.transistors.turn_off_all()
        self.power_supply_48v.turn_off()
        self.process_running = False
        print("Все исполнительные устройства остановлены")
        return True

    def move_motor_to(self, position):
        if not self._require_initialized():
            return False
        if self.process_running:
            print("Ошибка: нельзя перемещать двигатель во время процесса")
            return False
        if not self.stepper_driver.enabled:
            self.stepper_driver.enable(power_available=self.ac_dc_converter.get_output_voltage() > 0)
        return self.stepper_motor.move_to_position(position)

    def set_stepper_speed(self, speed):
        if not self._require_initialized():
            return False
        self.stepper_speed = speed
        return self.stepper_driver.set_speed(speed)

    def read_temperature(self):
        if not self._require_initialized():
            return None
        return self.temperature_sensor.read_temperature()

    def is_lid_closed(self):
        if not self._require_initialized():
            return False
        return self.lid_sensor.is_closed()

    def check_lid_before_start(self):
        if not self._require_initialized():
            return False
        if self.lid_sensor.is_closed():
            print("Крышка закрыта. Запуск разрешён по датчику крышки")
            return True

        print("Крышка открыта. Запуск запрещён")
        return False

    def check_lid_during_process(self):
        if not self._require_initialized():
            return False
        if self.process_running and self.lid_sensor.is_open():
            print("Крышка открыта во время работы!")
            self.emergency_stop()
            return False

        return True

    def set_temperature_mock(self, value):
        if not self._require_initialized():
            return False
        self.temperature_sensor.set_temperature(value)
        if self.temperature_sensor.is_overheated() and self.process_running:
            print("Обнаружен перегрев во время работы!")
            self.emergency_stop()
        return True

    def fill_tank_mock(self):
        if not self._require_initialized():
            return False
        return self.polishing_tank.fill()

    def drain_tank_mock(self):
        if not self._require_initialized():
            return False
        return self.polishing_tank.drain()

    def connect_electrodes_mock(self):
        if not self._require_initialized():
            return False
        return self.polishing_tank.connect_electrodes()

    def disconnect_electrodes_mock(self):
        if not self._require_initialized():
            return False
        return self.polishing_tank.disconnect_electrodes()

    def get_system_status(self):
        status = "========== СТАТУС СИСТЕМЫ ==========\n"
        status += f"Инициализация: {'выполнена' if self.initialized else 'не выполнена'}\n"
        status += f"Процесс: {'запущен' if self.process_running else 'остановлен'}\n\n"

        status += "[AC/DC преобразователь]\n" + self.ac_dc_converter.get_status() + "\n\n"
        status += "[Транзисторы]\n" + self.transistors.get_status() + "\n\n"
        status += "[Вибростол]\n" + self.vibro_table.get_status() + "\n\n"
        status += "[Источник 48 В]\n" + self.power_supply_48v.get_status() + "\n\n"
        status += "[Датчик крышки]\n" + self.lid_sensor.get_status() + "\n\n"
        status += "[Драйвер шагового двигателя]\n" + self.stepper_driver.get_status() + "\n\n"
        status += "[Шаговый двигатель]\n" + self.stepper_motor.get_status() + "\n\n"
        status += "[Ёмкость для полировки]\n" + self.polishing_tank.get_status() + "\n\n"
        status += "[Датчик температуры]\n" + self.temperature_sensor.get_status() + "\n"
        status += "===================================="
        return status


if __name__ == "__main__":
    controller = LaserErosionRobotController()
    print(controller.get_system_status())

    # Внешние условия, которые контроллер сам не создаёт:
    # 1) AC/DC уже включён извне и питает контроллер;
    # 2) крышка закрыта оператором, датчик только сообщает это состояние.
    controller.ac_dc_converter.turn_on()
    controller.lid_sensor.set_lid_state(True)

    controller.initialize()
    controller.move_motor_to(300)
    controller.start_process()
    print(controller.get_system_status())
    controller.set_temperature_mock(75)
    print(controller.get_system_status())
