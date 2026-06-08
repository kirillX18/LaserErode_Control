from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QSplitter, QScrollArea,
)

from ..base import BasePage
from ..components import SectionTitle
from ..blocks import (
    DeviceCard, AlarmPanel, EventLogPanel, DiagnosticsPanel,
    QuickActionBar, TestHarnessPanel,
)
from ..hardware import controller, TransistorChannel


class HardwarePage(BasePage):
    title = ""  # собственный заголовок-секция не нужен (есть бейджи и панели)

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()
        self.cards: dict[str, DeviceCard] = {}

        # --- панель быстрых действий ---
        self.quick = QuickActionBar("Управление процессом")
        layout.addWidget(self.quick)

        # --- основная раскладка: слева узлы+параметры, справа диагностика ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([900, 540])
        layout.addWidget(splitter, 1)

        self._wire()
        self._refresh()  # первичная отрисовка

    # ==================================================================
    # ЛЕВАЯ ЧАСТЬ: карточки узлов + параметры
    # ==================================================================
    def _build_left(self) -> QWidget:
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.addWidget(SectionTitle("Модули устройства"))

        grid = QGridLayout()
        v.addLayout(grid)
        self._build_cards(grid)

        v.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    def _build_cards(self, grid: QGridLayout) -> None:
        # AC/DC ----------------------------------------------------------
        c = DeviceCard("AC/DC преобразователь")
        c.add_metric("vin", "Вход")
        c.add_metric("vout", "Выход")
        self.cards["acdc"] = c

        # Источник 48 В --------------------------------------------------
        c = DeviceCard("Источник 48 В")
        c.add_metric("v", "Напряжение")
        c.add_metric("i", "Ток")
        c.add_bar("i", "ok")
        self.cards["psu"] = c

        # Транзисторные ключи (широкая карточка) -------------------------
        c = DeviceCard("Блок транзисторных ключей")
        chan_desc = self.ctl.snapshot()["trans"]["channels"]
        for ch in TransistorChannel:
            label = chan_desc.get(ch.value, {}).get("desc", ch.value)
            c.add_metric(ch.value, label)
        self.cards["trans"] = c

        # Вибростол ------------------------------------------------------
        c = DeviceCard("Вибростол")
        c.add_metric("state", "Состояние")
        self.cards["vibro"] = c

        # Драйвер ШД -----------------------------------------------------
        c = DeviceCard("Драйвер ШД")
        c.add_metric("state", "Состояние")
        c.add_metric("speed", "Скорость")
        self.cards["driver"] = c

        # Шаговый двигатель ---------------------------------------------
        c = DeviceCard("Шаговый двигатель")
        c.add_metric("pos", "Позиция")
        c.add_metric("moving", "Движение")
        c.add_bar("pos", "ok")
        c.add_action("Сброс", self.ctl.reset_motor, role="gray")
        c.add_action("Стоп", self.ctl.stop_motor, role="gray")
        self.cards["motor"] = c

        # Ёмкость полировки ----------------------------------------------
        c = DeviceCard("Ёмкость полировки")
        c.add_metric("filled", "Рабочая жидкость")
        c.add_metric("elec", "Анод / катод")
        c.add_metric("volt", "Напряжение процесса")
        self.cards["tank"] = c

        # Датчик крышки --------------------------------------------------
        c = DeviceCard("Датчик крышки")
        c.add_metric("state", "Положение крышки")
        self.cards["lid"] = c

        # Датчик температуры --------------------------------------------
        c = DeviceCard("Датчик температуры")
        c.add_metric("t", "Температура")
        c.add_metric("max", "Порог перегрева")
        c.add_bar("t", "warn")
        self.cards["temp"] = c

        # Размещение: 2 колонки; «транзисторы» — на всю ширину.
        order = ["acdc", "psu", "trans", "vibro", "driver",
                 "motor", "tank", "lid", "temp"]
        r = c0 = 0
        for key in order:
            card = self.cards[key]
            if key == "trans":
                if c0 != 0:
                    r += 1; c0 = 0
                grid.addWidget(card, r, 0, 1, 2)
                r += 1
            else:
                grid.addWidget(card, r, c0)
                c0 += 1
                if c0 == 2:
                    c0 = 0; r += 1

    # ==================================================================
    # ПРАВАЯ ЧАСТЬ: аварии, диагностика, журнал, стенд
    # ==================================================================
    def _build_right(self) -> QWidget:
        inner = QWidget()
        v = QVBoxLayout(inner)

        self.alarms = AlarmPanel("Ошибки и предупреждения")
        self.diag = DiagnosticsPanel("Диагностика")
        self.log = EventLogPanel("Журнал событий (logger «hardware»)")
        self.harness = TestHarnessPanel()

        v.addWidget(self.alarms)
        v.addWidget(self.diag)
        v.addWidget(self.log, 1)
        v.addWidget(self.harness)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    # ==================================================================
    # ПОДКЛЮЧЕНИЕ СИГНАЛОВ
    # ==================================================================
    def _wire(self) -> None:
        self.quick.init_button.clicked.connect(self.ctl.initialize)
        self.quick.start_button.clicked.connect(self.ctl.start_process)
        self.quick.stop_button.clicked.connect(self.ctl.stop_process)
        self.quick.estop_button.clicked.connect(self.ctl.emergency_stop)
        self.diag.refresh_button.clicked.connect(
            lambda: self.diag.set_status(self.ctl.system_status()))

        h = self.harness
        h.lid_check.toggled.connect(self.ctl.set_lid)
        h.temp_button.clicked.connect(
            lambda: self.ctl.set_temperature(h.temp_spin.value()))
        h.curr_button.clicked.connect(
            lambda: self.ctl.simulate_current(h.curr_spin.value()))

        self.ctl.logMessage.connect(self.log.append)
        self.ctl.stateChanged.connect(self._refresh)

    # ==================================================================
    # ОБНОВЛЕНИЕ ВСЕХ ВИДЖЕТОВ ПО СНИМКУ СОСТОЯНИЯ
    # ==================================================================
    def _refresh(self) -> None:
        s = self.ctl.snapshot()

        # быстрые действия
        self.quick.set_enabled_states(
            can_start=s["initialized"] and not s["process_running"],
            can_stop=s["process_running"])

        on = lambda b: "ok" if b else "off"

        # AC/DC
        a = s["acdc"]; card = self.cards["acdc"]
        card.set_state("Вкл" if a["on"] else "Выкл", on(a["on"]))
        card.set_metric("vin", f"{a['vin']} В", "ok" if a["on"] else "off")
        card.set_metric("vout", f"{a['vout']} В", "ok" if a["on"] else "off")

        # PSU 48 В
        p = s["psu"]; card = self.cards["psu"]
        st = "err" if p["tripped"] else on(p["on"])
        card.set_state("Авария" if p["tripped"] else ("Вкл" if p["on"] else "Выкл"), st)
        card.set_metric("v", f"{p['v']:.0f} В", on(p["on"]))
        over = p["on"] and p["i"] > p["limit"]
        card.set_metric("i", f"{p['i']:.1f} / {p['limit']:.1f} А",
                        "err" if over else on(p["on"]))
        card.set_bar("i", p["i"] / p["max_limit"] if p["on"] else 0,
                     "err" if over else "ok")

        # Транзисторы
        t = s["trans"]; card = self.cards["trans"]
        any_load = any(c["load"] for c in t["channels"].values())
        if not t["load_power"]:
            card.set_state("Без питания", "off")
        else:
            card.set_state("Под нагрузкой" if any_load else "Питание есть",
                           "ok" if any_load else "warn")
        for name, c in t["channels"].items():
            txt = (f"сигнал={c['sig']}, "
                   f"{'открыт' if c['open'] else 'закрыт'}, "
                   f"{'нагрузка вкл' if c['load'] else 'нагрузка выкл'}")
            card.set_metric(name, txt, on(c["load"]))

        # Вибростол
        v = s["vibro"]; card = self.cards["vibro"]
        card.set_state("Вибрация" if v["on"] else "Стоп", on(v["on"]))
        card.set_metric("state", "вибрирует" if v["on"] else "остановлен", on(v["on"]))

        # Драйвер ШД
        d = s["driver"]; card = self.cards["driver"]
        if d["enabled"]:
            card.set_state("Движение" if d["moving"] else "Вкл",
                           "ok" if d["moving"] else "warn")
        else:
            card.set_state("Выкл", "off")
        card.set_metric("state", "включен" if d["enabled"] else "выключен", on(d["enabled"]))
        card.set_metric("speed", f"{d['speed']} шаг/с", "ok")

        # Шаговый двигатель
        m = s["motor"]; card = self.cards["motor"]
        card.set_state("Движение" if m["moving"] else "Стоп",
                       "warn" if m["moving"] else "off")
        card.set_metric("pos", str(m["pos"]), "ok")
        card.set_metric("moving", "движется" if m["moving"] else "остановлен",
                        "warn" if m["moving"] else "off")
        span = max(1, m["max"] - m["min"])
        card.set_bar("pos", (m["pos"] - m["min"]) / span, "ok")

        # Ёмкость
        k = s["tank"]; card = self.cards["tank"]
        card.set_state("Процесс" if k["running"] else ("Готова" if k["ready"] else "Не готова"),
                       "ok" if k["running"] else ("warn" if k["ready"] else "off"))
        card.set_metric("filled", "есть" if k["filled"] else "нет", on(k["filled"]))
        elec = f"{'+' if k['anode'] else '−'} / {'+' if k['cathode'] else '−'}"
        card.set_metric("elec", elec, on(k["anode"] and k["cathode"]))
        card.set_metric("volt", f"{k['volt']:.1f} В", "ok")

        # Крышка
        l = s["lid"]; card = self.cards["lid"]
        card.set_state("Закрыта" if l["closed"] else "Открыта", "ok" if l["closed"] else "err")
        card.set_metric("state", "закрыта" if l["closed"] else "открыта",
                        "ok" if l["closed"] else "err")

        # Температура
        tp = s["temp"]; card = self.cards["temp"]
        card.set_state("Перегрев" if tp["over"] else "Норма", "err" if tp["over"] else "ok")
        card.set_metric("t", f"{tp['t']:.1f} °C", "err" if tp["over"] else "ok")
        card.set_metric("max", f"{tp['max']:.0f} °C")
        card.set_bar("t", tp["t"] / tp["max"] if tp["max"] else 0,
                     "err" if tp["over"] else "warn")

        # аварии + диагностика (если уже открывалась)
        self.alarms.set_alarms(self.ctl.alarms())
        if not self.diag.view.toPlainText().startswith("Нажмите"):
            self.diag.set_status(self.ctl.system_status())
