"""
hardware_page.py — страница «Оборудование (узлы)».

Главная страница-перенос дизайна HMI в Qt. Слева — карточки узлов
лазерно-эрозионного робота; справа — аварии, журнал и стендовая имитация.
Сверху — панель быстрых действий. Вся логика идёт через DeviceController
(адаптер к классам-заглушкам).

Карточки строятся декларативно, поэтому добавить новый узел — это одна
карточка в _build_cards() + один блок в _refresh().
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QSplitter, QScrollArea,
    QMessageBox, QLabel,
)

from ..base import BasePage
from ..components import SectionTitle, ToggleSwitch
from ..blocks import (
    DeviceCard, AlarmPanel, EventLogPanel,
    QuickActionBar, TestHarnessPanel,
)
from ..hardware import controller, process_readiness, TransistorChannel


# Стендовая имитация сигналов датчиков — только в режиме разработчика
# (переменная окружения EDM_DEV=1).
DEV_MODE = os.environ.get("EDM_DEV") == "1"


class HardwarePage(BasePage):
    title = ""

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()
        self.cards: dict[str, DeviceCard] = {}
        self._paused = False

        self.quick = QuickActionBar("Управление процессом")
        layout.addWidget(self.quick)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([900, 540])
        layout.addWidget(splitter, 1)

        self._wire()
        self._refresh()

    # ==================================================================
    # ЛЕВАЯ ЧАСТЬ: карточки узлов
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

        # Блок транзисторных ключей (широкая карточка) -------------------
        c = DeviceCard("Блок транзисторных ключей")
        chan_desc = self.ctl.snapshot()["trans"]["channels"]
        for ch in TransistorChannel:
            label = chan_desc.get(ch.value, {}).get("desc", ch.value)
            c.add_metric(ch.value, label)
        self.cards["trans"] = c

        # Источник питания эрозии ----------------------------------------
        c = DeviceCard("Источник питания эрозии")
        c.add_metric("v", "Напряжение")
        c.add_metric("i", "Ток")
        c.add_bar("i", "ok")
        self.cards["edm"] = c

        # Источник питания лазера ----------------------------------------
        c = DeviceCard("Источник питания лазера")
        c.add_metric("v", "Напряжение")
        c.add_metric("interlock", "Блокировки")
        self.cards["laser_psu"] = c

        # Контроллер 8-суставного манипулятора ---------------------------------
        c = DeviceCard("Контроллер манипулятора")
        c.add_metric("link", "Связь")
        c.add_metric("speed", "Скорость")
        self.cards["robot"] = c

        # Роботизированный 8-суставной манипулятор ------------------------------
        c = DeviceCard("8-суставной манипулятор")
        c.add_metric("tcp", "Инструмент X/Y/Z")
        c.add_metric("j14", "Суставы J1–J4")
        c.add_metric("j58", "Суставы J5–J8")
        c.add_metric("moving", "Движение")
        self.cards["arm"] = c

        # Лазерно-эрозионная рабочая головка -----------------------------
        c = DeviceCard("Лазерно-эрозионная головка")
        c.add_metric("laser", "Лазер")
        c.add_metric("edm", "Эрозия (катод/анод)")
        c.add_metric("water", "Полив зоны")
        self.cards["head"] = c

        # Лазерный излучатель --------------------------------------------
        c = DeviceCard("Лазерный излучатель")
        c.add_metric("power", "Мощность")
        c.add_metric("freq", "Частота")
        c.add_metric("mode", "Режим")
        self.cards["laser"] = c

        # Система подачи воды --------------------------------------------
        c = DeviceCard("Система подачи воды")
        c.add_metric("pump", "Насос / клапан")
        c.add_metric("pressure", "Давление")
        c.add_metric("flow", "Расход")
        c.add_bar("flow", "ok")
        c.add_metric("drain", "Слив")
        self.cards["water"] = c

        # Крепление детали -----------------------------------------------
        c = DeviceCard("Крепление детали")
        c.add_metric("state", "Фиксация")
        self.cards["fixture"] = c

        # Датчик крышки --------------------------------------------------
        c = DeviceCard("Датчик крышки")
        c.add_metric("state", "Положение крышки")
        self.cards["lid"] = c

        # Датчик температуры ---------------------------------------------
        c = DeviceCard("Датчик температуры")
        c.add_metric("t", "Температура")
        c.add_metric("max", "Порог перегрева")
        c.add_bar("t", "ok")
        self.cards["temp"] = c

        # Размещение: 2 колонки; «транзисторы» — на всю ширину.
        order = ["acdc", "trans", "edm", "laser_psu", "robot", "arm",
                 "head", "laser", "water", "fixture", "lid", "temp"]
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
    # ПРАВАЯ ЧАСТЬ: аварии, журнал, стенд
    # ==================================================================
    def _build_right(self) -> QWidget:
        inner = QWidget()
        v = QVBoxLayout(inner)

        self.alarms = AlarmPanel("Ошибки и предупреждения")
        self.log = EventLogPanel("Журнал событий (logger «hardware»)")
        v.addWidget(self.alarms)
        v.addWidget(self.log, 1)

        # Тумблер «Режим тестирования» открывает стендовую панель имитации
        # сигналов датчиков (поднять температуру/ток, открыть-закрыть крышку).
        # Панель есть всегда, но скрыта; EDM_DEV=1 лишь включает её сразу.
        test_row = QHBoxLayout()
        self.test_toggle = ToggleSwitch()
        test_label = QLabel("Режим тестирования (стенд)")
        test_label.setStyleSheet("font-weight:bold;")
        test_row.addWidget(self.test_toggle)
        test_row.addWidget(test_label)
        test_row.addStretch()
        v.addLayout(test_row)

        self.harness = TestHarnessPanel()
        self.harness.setVisible(DEV_MODE)
        self.test_toggle.setChecked(DEV_MODE)
        self.test_toggle.toggled.connect(self.harness.setVisible)
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

        if self.harness is not None:
            h = self.harness
            h.lid_check.toggled.connect(self.ctl.set_lid)
            h.temp_button.clicked.connect(
                lambda: self.ctl.set_temperature(h.temp_spin.value()))
            h.curr_button.clicked.connect(
                lambda: self.ctl.simulate_current(h.curr_spin.value()))

        self.ctl.logMessage.connect(self.log.append)
        self.ctl.stateChanged.connect(self._refresh)

    def _toggle_pause(self) -> None:
        if self._paused:
            self.ctl.resume_process()
        else:
            self.ctl.pause_process()

    def _confirm_stop(self) -> None:
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
        on = lambda b: "ok" if b else "off"

        proc = s.get("process", {})
        running = bool(proc.get("running", s["process_running"]))
        self._paused = bool(proc.get("paused", False))
        can_start, reason = process_readiness(s)
        self.quick.set_enabled_states(
            can_start=can_start, can_stop=running, can_pause=running,
            paused=self._paused, initialized=s["initialized"],
            running=running, start_reason=reason)

        # AC/DC ----------------------------------------------------------
        a = s["acdc"]; card = self.cards["acdc"]
        card.set_state("Вкл" if a["on"] else "Выкл", on(a["on"]))
        card.set_metric("vin", f"{a['vin']} В", "ok" if a["on"] else "off")
        card.set_metric("vout", f"{a['vout']} В", "ok" if a["on"] else "off")

        # Транзисторы ----------------------------------------------------
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

        # Источник эрозии ------------------------------------------------
        p = s["edm"]; card = self.cards["edm"]
        st = "err" if p["tripped"] else on(p["on"])
        card.set_state("Авария" if p["tripped"] else ("Вкл" if p["on"] else "Выкл"), st)
        card.set_metric("v", f"{p['v']:.0f} В", on(p["on"]))
        over = p["on"] and p["i"] > p["limit"]
        card.set_metric("i", f"{p['i']:.1f} / {p['limit']:.1f} А",
                        "err" if over else on(p["on"]))
        card.set_bar("i", p["i"] / p["max_limit"] if p["on"] else 0,
                     "err" if over else "ok")

        # Источник лазера ------------------------------------------------
        lp = s["laser_psu"]; card = self.cards["laser_psu"]
        card.set_state("Вкл" if lp["on"] else "Выкл", on(lp["on"]))
        card.set_metric("v", f"{lp['v']:.0f} В", on(lp["on"]))
        if lp["on"]:
            ilk_txt, ilk_role = "сняты (крышка закрыта, готов)", "ok"
        elif not s["lid"]["closed"]:
            ilk_txt, ilk_role = "крышка открыта", "err"
        else:
            ilk_txt, ilk_role = "ожидание готовности", "off"
        card.set_metric("interlock", ilk_txt, ilk_role)

        # Контроллер манипулятора ----------------------------------------------
        rc = s["robot"]; card = self.cards["robot"]
        if not rc["online"]:
            card.set_state("Нет связи", "warn")
            card.set_metric("link", "нет связи", "warn")
        else:
            card.set_state("Движение" if rc["moving"] else "Готов",
                           "warn" if rc["moving"] else "ok")
            card.set_metric("link", "готов" if rc["enabled"] else "движение запрещено",
                            "ok" if rc["enabled"] else "off")
        card.set_metric("speed", str(rc["speed"]), "ok")

        # 8-суставной манипулятор -----------------------------------------------
        arm = s["arm"]; card = self.cards["arm"]
        card.set_state("Движение" if arm["moving"] else "Стоп",
                       "warn" if arm["moving"] else "off")
        card.set_metric("tcp", f"{arm['x']:.0f} / {arm['y']:.0f} / {arm['z']:.0f}", "ok")
        j = arm["joints"]
        card.set_metric("j14", "  ".join(f"{n} {j[n]:.0f}°" for n in ("J1", "J2", "J3", "J4")))
        card.set_metric("j58", "  ".join(f"{n} {j[n]:.0f}°" for n in ("J5", "J6", "J7", "J8")))
        card.set_metric("moving", "движется" if arm["moving"] else "остановлен",
                        "warn" if arm["moving"] else "off")

        # Рабочая головка ------------------------------------------------
        hd = s["head"]; lz = s["laser"]; ca = s["cathode"]; w = s["water"]
        card = self.cards["head"]
        card.set_state("Обработка" if hd["machining"] else "Простой",
                       "ok" if hd["machining"] else "off")
        card.set_metric("laser", "излучает" if lz["emitting"] else "выкл",
                        "ok" if lz["emitting"] else "off")
        card.set_metric("edm",
                        ("эрозия идёт" if ca["active"] else
                         ("подключены" if ca["connected"] else "не подключены")),
                        "ok" if ca["active"] else ("off" if ca["connected"] else "warn"))
        card.set_metric("water", "есть" if w["flowing"] else "нет",
                        "ok" if w["flowing"] else "off")

        # Лазерный излучатель --------------------------------------------
        card = self.cards["laser"]
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

        # Система подачи воды --------------------------------------------
        card = self.cards["water"]
        flowing = w["flowing"]
        if flowing:
            card.set_state("Подача", "ok")
        elif w["pump"] or w["valve"]:
            card.set_state("Нет потока", "warn")
        else:
            card.set_state("Выкл", "off")
        card.set_metric("pump",
                        f"{'вкл' if w['pump'] else 'выкл'} / "
                        f"{'открыт' if w['valve'] else 'закрыт'}",
                        on(flowing))
        card.set_metric("pressure", f"{w['pressure']:.1f} бар", on(flowing))
        card.set_metric("flow", f"{w['flow']:.1f} л/мин",
                        "ok" if flowing else ("warn" if (w["pump"] or w["valve"]) else "off"))
        card.set_bar("flow", min(1.0, w["flow"] / 5.0), "ok" if flowing else "warn")
        card.set_metric("drain", "открыт" if w["drain"] else "закрыт",
                        "warn" if w["drain"] else "off")

        # Крепление детали -----------------------------------------------
        fx = s["fixture"]; card = self.cards["fixture"]
        card.set_state("Зажато" if fx["clamped"] else "Свободно",
                       "ok" if fx["clamped"] else "warn")
        card.set_metric("state", "деталь зажата" if fx["clamped"] else "деталь не зажата",
                        "ok" if fx["clamped"] else "warn")

        # Крышка ---------------------------------------------------------
        l = s["lid"]; card = self.cards["lid"]
        card.set_state("Закрыта" if l["closed"] else "Открыта",
                       "ok" if l["closed"] else "err")
        card.set_metric("state", "закрыта" if l["closed"] else "открыта",
                        "ok" if l["closed"] else "err")

        # Температура ----------------------------------------------------
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

        self.alarms.set_alarms(self.ctl.alarms())
