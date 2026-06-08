from PyQt5.QtWidgets import QVBoxLayout, QWidget, QSplitter
from PyQt5.QtCore import Qt

from ..base import BasePage, BasePanel
from ..components import IndicatorRow, MetricRow
from ..blocks import QuickActionBar, AlarmPanel, EventLogPanel
from ..hardware import controller


class _ConditionsPanel(BasePanel):
    """Чек-лист условий запуска процесса (_check_start_conditions)."""

    def build(self) -> None:
        self.r_acdc = IndicatorRow("Питание AC/DC")
        self.r_init = IndicatorRow("Инициализация")
        self.r_lid = IndicatorRow("Крышка закрыта")
        self.r_tank = IndicatorRow("Ёмкость готова")
        self.r_temp = IndicatorRow("Нет перегрева")
        for r in (self.r_acdc, self.r_init, self.r_lid, self.r_tank, self.r_temp):
            self.body.addWidget(r)


class _ProcessReadouts(BasePanel):
    """Ключевые параметры процесса (живые значения)."""

    def build(self) -> None:
        self.m_proc = MetricRow("Процесс:", "—")
        self.m_v = MetricRow("Источник 48 В — напряжение:", "—")
        self.m_i = MetricRow("Источник 48 В — ток:", "—")
        self.m_volt = MetricRow("Напряжение полировки:", "—")
        self.m_temp = MetricRow("Температура:", "—")
        self.m_pos = MetricRow("Позиция привода:", "—")
        self.m_vibro = MetricRow("Вибростол:", "—")
        for m in (self.m_proc, self.m_v, self.m_i, self.m_volt,
                  self.m_temp, self.m_pos, self.m_vibro):
            self.body.addWidget(m)


class ProcessPage(BasePage):
    title = ""

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()

        self.quick = QuickActionBar("Управление процессом")
        layout.addWidget(self.quick)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        self.conditions = _ConditionsPanel("Условия запуска")
        self.readouts = _ProcessReadouts("Состояние процесса")
        lv.addWidget(self.conditions)
        lv.addWidget(self.readouts)
        lv.addStretch()

        right = QWidget()
        rv = QVBoxLayout(right)
        self.alarms = AlarmPanel("Ошибки и предупреждения")
        self.log = EventLogPanel("Журнал событий")
        rv.addWidget(self.alarms)
        rv.addWidget(self.log, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([600, 600])
        layout.addWidget(splitter, 1)

        # действия
        self.quick.init_button.clicked.connect(self.ctl.initialize)
        self.quick.start_button.clicked.connect(self.ctl.start_process)
        self.quick.stop_button.clicked.connect(self.ctl.stop_process)
        self.quick.estop_button.clicked.connect(self.ctl.emergency_stop)
        self.ctl.logMessage.connect(self.log.append)
        self.ctl.stateChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        on = lambda b: "ok" if b else "off"

        # условия запуска
        self.conditions.r_acdc.set_state(on(s["acdc"]["on"]),
                                         "есть" if s["acdc"]["on"] else "нет")
        self.conditions.r_init.set_state(on(s["initialized"]),
                                         "выполнена" if s["initialized"] else "нет")
        self.conditions.r_lid.set_state("ok" if s["lid"]["closed"] else "err",
                                        "закрыта" if s["lid"]["closed"] else "открыта")
        self.conditions.r_tank.set_state("ok" if s["tank"]["ready"] else "warn",
                                         "готова" if s["tank"]["ready"] else "не готова")
        self.conditions.r_temp.set_state("err" if s["temp"]["over"] else "ok",
                                         "перегрев" if s["temp"]["over"] else "норма")

        # параметры процесса
        r, p = self.readouts, s["psu"]
        r.m_proc.set_value("запущен" if s["process_running"] else "остановлен",
                           "ok" if s["process_running"] else "off")
        r.m_v.set_value(f"{p['v']:.0f} В", on(p["on"]))
        over = p["on"] and p["i"] > p["limit"]
        r.m_i.set_value(f"{p['i']:.1f} / {p['limit']:.1f} А",
                        "err" if over else on(p["on"]))
        r.m_volt.set_value(f"{s['tank']['volt']:.1f} В", "ok")
        r.m_temp.set_value(f"{s['temp']['t']:.1f} °C",
                           "err" if s["temp"]["over"] else "ok")
        r.m_pos.set_value(str(s["motor"]["pos"]), "ok")
        r.m_vibro.set_value("вибрирует" if s["vibro"]["on"] else "остановлен",
                            on(s["vibro"]["on"]))

        # быстрые действия + аварии
        self.quick.set_enabled_states(
            can_start=s["initialized"] and not s["process_running"],
            can_stop=s["process_running"])
        self.alarms.set_alarms(self.ctl.alarms())
