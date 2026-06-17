"""
hardware_page.py — страница «Оборудование (узлы)».

Главная страница-перенос HTML-дизайна HMI в Qt. Слева — карточки 9 узлов
устройства и форма параметров; справа — аварии, журнал и стендовая
имитация. Сверху — панель быстрых действий. Вся логика идёт через
DeviceController (адаптер к классам-заглушкам).

Карточки строятся декларативно из CARD_SPECS, поэтому добавить новый узел —
это одна запись в списке + одна строка в _refresh().
"""

import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QSplitter, QScrollArea,
    QMessageBox,
)

from ..base import BasePage
from ..components import SectionTitle
from ..blocks import (
    DeviceCard, AlarmPanel, EventLogPanel,
    QuickActionBar, TestHarnessPanel,
)
from ..hardware import controller, process_readiness, TransistorChannel


# Стендовая имитация сигналов датчиков — только в режиме разработчика
# (переменная окружения EDM_DEV=1). В рабочем интерфейсе её нет, чтобы оператор
# не мог «вручную» задать температуру/ток и навредить ложными данными.
DEV_MODE = os.environ.get("EDM_DEV") == "1"


class HardwarePage(BasePage):
    title = ""  # собственный заголовок-секция не нужен (есть бейджи и панели)

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()
        self.cards: dict[str, DeviceCard] = {}
        self._paused = False

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

        # Координатный стол ----------------------------------------------
        c = DeviceCard("Координатный стол (ось Y)")
        c.add_metric("ctrl", "Контроллер")
        c.add_metric("pos", "Позиция")
        c.add_bar("pos", "ok")
        self.cards["table"] = c

        # Драйвер ШД -----------------------------------------------------
        c = DeviceCard("Драйвер ШД")
        c.add_metric("state", "Состояние")
        c.add_metric("speed", "Скорость")
        self.cards["driver"] = c

        # Шаговый двигатель (X/Z) ---------------------------------------
        c = DeviceCard("Шаговый двигатель (X/Z)")
        c.add_metric("x", "Позиция X")
        c.add_metric("z", "Позиция Z")
        c.add_metric("moving", "Движение")
        self.cards["motor"] = c

        # Лазерный излучатель --------------------------------------------
        c = DeviceCard("Лазерный излучатель")
        c.add_metric("power", "Мощность")
        c.add_metric("freq", "Частота")
        c.add_metric("mode", "Режим")
        self.cards["laser"] = c

        # Датчик крышки --------------------------------------------------
        c = DeviceCard("Датчик крышки")
        c.add_metric("state", "Положение крышки")
        self.cards["lid"] = c

        # Датчик температуры --------------------------------------------
        c = DeviceCard("Датчик температуры")
        c.add_metric("t", "Температура")
        c.add_metric("max", "Порог перегрева")
        c.add_bar("t", "ok")
        self.cards["temp"] = c

        # Размещение: 2 колонки; «транзисторы» — на всю ширину.
        order = ["acdc", "psu", "trans", "table", "driver",
                 "motor", "laser", "lid", "temp"]
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
        self.log = EventLogPanel("Журнал событий (logger «hardware»)")

        v.addWidget(self.alarms)
        v.addWidget(self.log, 1)

        # Стендовая имитация датчиков — только в режиме разработчика.
        self.harness = TestHarnessPanel() if DEV_MODE else None
        if self.harness is not None:
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
        self.quick.pause_button.clicked.connect(self._toggle_pause)
        self.quick.stop_button.clicked.connect(self._confirm_stop)
        self.quick.estop_button.clicked.connect(self.ctl.emergency_stop)

        # Стендовая имитация — только если панель построена (режим разработчика).
        if self.harness is not None:
            h = self.harness
            h.lid_check.toggled.connect(self.ctl.set_lid)
            h.temp_button.clicked.connect(
                lambda: self.ctl.set_temperature(h.temp_spin.value()))
            h.curr_button.clicked.connect(
                lambda: self.ctl.simulate_current(h.curr_spin.value()))

        self.ctl.logMessage.connect(self.log.append)
        self.ctl.stateChanged.connect(self._refresh)

    # ------------------------------------------------------------------
    def _toggle_pause(self) -> None:
        if self._paused:
            self.ctl.resume_process()
        else:
            self.ctl.pause_process()

    def _confirm_stop(self) -> None:
        """Та же логика, что на странице «Процесс»: остановка сбрасывает
        прогресс, поэтому требует подтверждения (HIG, гл. 3 «Alerts»)."""
        if not self.ctl.snapshot().get("process_running"):
            self.ctl.stop_process()
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Остановить процесс?")
        box.setText("Остановка прервёт обработку и сбросит прогресс в 0.")
        box.setInformativeText("Продолжить остановку?")
        yes = box.addButton("Остановить", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.exec_()
        if box.clickedButton() is yes:
            self.ctl.stop_process()

    # ==================================================================
    # ОБНОВЛЕНИЕ ВСЕХ ВИДЖЕТОВ ПО СНИМКУ СОСТОЯНИЯ
    # ==================================================================
    def _refresh(self) -> None:
        s = self.ctl.snapshot()

        # быстрые действия — те же условия и поведение, что на «Процессе»
        proc = s.get("process", {})
        running = bool(proc.get("running", s["process_running"]))
        self._paused = bool(proc.get("paused", False))
        can_start, reason = process_readiness(s)
        self.quick.set_enabled_states(
            can_start=can_start,
            can_stop=running,
            can_pause=running,
            paused=self._paused,
            initialized=s["initialized"],
            running=running,
            start_reason=reason)

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

        # Координатный стол
        tb = s["table"]; card = self.cards["table"]
        if not tb["online"]:
            card.set_state("Нет связи", "warn")
        else:
            card.set_state("Движение" if tb["moving"] else "Готов",
                           "warn" if tb["moving"] else "ok")
        if not tb["online"]:
            ctrl_txt, ctrl_role = "нет связи", "warn"
        elif tb["enabled"]:
            ctrl_txt, ctrl_role = f"готов, {tb['speed']} шаг/с", "ok"
        else:
            ctrl_txt, ctrl_role = "движение запрещено", "off"
        card.set_metric("ctrl", ctrl_txt, ctrl_role)
        card.set_metric("pos", str(tb["pos"]),
                        "warn" if tb["moving"] else "ok")
        span = max(1, tb["max"] - tb["min"])
        card.set_bar("pos", (tb["pos"] - tb["min"]) / span,
                     "warn" if tb["moving"] else "ok")

        # Драйвер ШД
        d = s["driver"]; card = self.cards["driver"]
        if not d["enabled"]:
            card.set_state("Выкл", "off")
        elif not d.get("connected", True):
            card.set_state("Нет связи с ШД", "warn")
        else:
            card.set_state("Движение" if d["moving"] else "Вкл", "ok")
        card.set_metric("state", "включен" if d["enabled"] else "выключен", on(d["enabled"]))
        card.set_metric("speed", f"{d['speed']} шаг/с", "ok")

        # Шаговый двигатель (X/Z)
        m = s["motor"]; card = self.cards["motor"]
        card.set_state("Движение" if m["moving"] else "Стоп",
                       "warn" if m["moving"] else "off")
        card.set_metric("x", str(m["x"]), "ok")
        card.set_metric("z", str(m["z"]), "ok")
        card.set_metric("moving", "движется" if m["moving"] else "остановлен",
                        "warn" if m["moving"] else "off")

        # Лазер
        lz = s["laser"]; card = self.cards["laser"]
        if lz["emitting"]:
            card.set_state("Излучение", "ok")
        elif lz["ready"]:
            card.set_state("Готов", "off")
        else:
            card.set_state("Не настроен", "warn")
        card.set_metric("power", f"{lz['power']} Вт",
                        "ok" if lz["emitting"] else on(lz["ready"]))
        card.set_metric("freq", f"{lz['frequency']} Гц", "ok")
        card.set_metric("mode", lz["mode"].lower(), "ok")

        # Крышка
        l = s["lid"]; card = self.cards["lid"]
        card.set_state("Закрыта" if l["closed"] else "Открыта", "ok" if l["closed"] else "err")
        card.set_metric("state", "закрыта" if l["closed"] else "открыта",
                        "ok" if l["closed"] else "err")

        # Температура
        tp = s["temp"]; card = self.cards["temp"]
        near = bool(tp["max"]) and not tp["over"] and tp["t"] >= tp["max"] - 5
        if tp["over"]:
            t_role, t_state = "err", "Перегрев"
        elif near:
            t_role, t_state = "warn", "Близко к перегреву"
        else:
            t_role, t_state = "ok", "Норма"
        card.set_state(t_state, t_role)
        card.set_metric("t", f"{tp['t']:.1f} °C", t_role)
        card.set_metric("max", f"{tp['max']:.0f} °C")
        card.set_bar("t", tp["t"] / tp["max"] if tp["max"] else 0, t_role)

        # аварии
        self.alarms.set_alarms(self.ctl.alarms())
