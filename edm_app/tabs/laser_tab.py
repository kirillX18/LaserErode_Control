"""
laser_tab.py — вкладка «Лазером» (настройка параметров лазерного воздействия).

Интерфейс ручной настройки лазера для электроэрозионной обработки. Слева —
пять одинаковых по устройству блоков-параметров (мощность, частота импульсов,
фокусное смещение, длительность импульса, время воздействия), справа — выбор
режима излучения. Значения и режим передаются в DeviceController (set_laser_param /
set_laser_mode), который применяет их к лазерному узлу заглушки; текущее
применённое состояние подтягивается из snapshot()["laser"]. Результат каждого
действия дополнительно отражается строкой внизу (LastMessageBar).

Каждый блок-параметр построен из уже существующих компонентов: MetricRow
показывает текущее (применённое) значение, числовое поле QSpinBox задаёт
нужное, а PrimaryButton «Задать» применяет его.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSpinBox,
    QButtonGroup, QRadioButton,
)

from ..base import BaseServiceTab, BasePanel
from ..components import (
    MetricRow, PrimaryButton, LastMessageBar,
)
from ..hardware import controller
from .. import theme


class _LaserParamPanel(BasePanel):
    """Блок одного параметра лазера: поле ввода значения и кнопка «Задать».

    Текущее (применённое) значение показывается строкой сверху; нужное
    значение набирается в числовом поле (нативные стрелки/↑↓ дают осмысленный
    шаг — свой для каждого параметра) и применяется кнопкой «Задать», которая
    сообщает его наружу через колбэк on_apply(name, value). Пока введённое
    значение не применено, об этом сообщает строка-индикатор — иначе шаг по
    стрелкам менял бы поле, не трогая прибор, без обратной связи.
    """

    def __init__(self, title: str, lo: int, hi: int, step: int, on_apply,
                 unit: str = "", parent=None):
        self._title_text = title
        self._lo, self._hi = lo, hi
        self._step = step
        self._unit = unit
        self._value = 0
        self._on_apply = on_apply
        super().__init__(title, parent)

    def build(self) -> None:
        # Текущее применённое значение — строкой «подпись … значение».
        self.value_row = MetricRow("Текущее значение:", self._fmt(0))
        self.body.addWidget(self.value_row)

        # Строка ввода: подпись — поле со счётчиком — «Задать».
        grid = QGridLayout()
        grid.addWidget(QLabel("Задать значение:"), 0, 0)
        self.spin = QSpinBox()
        self.spin.setRange(self._lo, self._hi)
        self.spin.setSingleStep(self._step)     # осмысленный шаг под параметр
        self.spin.setValue(0)
        if self._unit:
            self.spin.setSuffix(f" {self._unit}")
        self.spin.valueChanged.connect(self._on_spin_changed)
        grid.addWidget(self.spin, 0, 1)
        self.apply_btn = PrimaryButton("Задать")
        self.apply_btn.setMaximumWidth(120)
        self.apply_btn.clicked.connect(self._apply)
        grid.addWidget(self.apply_btn, 0, 2)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        # Индикатор «введённое значение ещё не применено».
        self.pending = QLabel("")
        self.pending.setStyleSheet(
            f"color:{theme.Palette.WARN}; font-size:11px;")
        self.body.addWidget(self.pending)

    # ------------------------------------------------------------------
    def _fmt(self, value) -> str:
        """Значение с единицей измерения (если она задана)."""
        return f"{value} {self._unit}".rstrip() if self._unit else str(value)

    def _on_spin_changed(self, _value) -> None:
        self._update_pending()

    def _update_pending(self) -> None:
        changed = self.spin.value() != self._value
        self.pending.setText(
            "● значение не применено — нажмите «Задать»" if changed else "")

    def _apply(self) -> None:
        self._value = self.spin.value()
        self.value_row.set_value(self._fmt(self._value))
        self._update_pending()
        if self._on_apply is not None:
            self._on_apply(self._title_text, self._value, self._unit)

    def show_applied(self, value) -> None:
        """Показать текущее применённое значение из состояния устройства.

        Если оператор не вводил новое значение, поле ввода тоже подтягивается к
        применённому — так заводские параметры (профиль под сталь) сразу видны
        и в строке «Текущее значение», и в поле, без ложного «не применено».
        """
        no_pending = self.spin.value() == self._value
        self._value = value
        self.value_row.set_value(self._fmt(value))
        if no_pending:
            self.spin.blockSignals(True)
            self.spin.setValue(value)
            self.spin.blockSignals(False)
        self._update_pending()

    def set_param_enabled(self, enabled: bool, reason: str = "") -> None:
        """Погасить/включить блок целиком (неприменимые в режиме параметры)."""
        self.setEnabled(enabled)
        self.setToolTip("" if enabled else reason)

    def value(self) -> int:
        return self._value


class _ModePanel(BasePanel):
    """Блок «Режим работы»: три взаимоисключающих режима с квадратным переключателем."""

    MODES = ["Непрерывный", "Импульсный", "Одиночный импульс"]

    # Квадратный индикатор переключателя (по умолчанию у QRadioButton он круглый).
    _SQUARE = (
        "QRadioButton { background: transparent; spacing: 8px; padding: 3px 0; }"
        "QRadioButton::indicator {"
        f"  width: 16px; height: 16px; border: 2px solid {theme.Palette.BORDER};"
        "  border-radius: 0px; background: white; }"
        f"QRadioButton::indicator:hover {{ border-color: {theme.Palette.GREEN}; }}"
        f"QRadioButton::indicator:checked {{ background: {theme.Palette.GREEN};"
        f"  border-color: {theme.Palette.GREEN_PRESSED}; }}"
    )

    def __init__(self, on_change, parent=None):
        self._on_change = on_change
        super().__init__("Режим работы", parent)

    def build(self) -> None:
        self.group = QButtonGroup(self)
        for i, name in enumerate(self.MODES):
            rb = QRadioButton(name)
            rb.setStyleSheet(self._SQUARE)
            if name == "Импульсный":        # по умолчанию — режим под сталь
                rb.setChecked(True)
            self.group.addButton(rb, i)
            self.body.addWidget(rb)
        self.body.addStretch()
        self.group.buttonClicked.connect(self._changed)

    def _changed(self, btn) -> None:
        if self._on_change is not None:
            self._on_change(btn.text())

    def current_mode(self) -> str:
        i = self.group.checkedId()
        return self.MODES[i] if i >= 0 else ""


class LaserControlTab(BaseServiceTab):
    """Вкладка «Лазером»: параметры воздействия слева, режим излучения справа."""

    # (название блока, нижняя граница, верхняя граница, шаг, единица).
    # Диапазоны и шаг привязаны к физике параметра, а не к «большому круглому
    # числу»: шаг подобран так, чтобы стрелки/↑↓ давали осмысленное изменение в
    # рабочем диапазоне конкретного лазера. Фокус регулируется «в обе стороны».
    PARAM_SPECS = [
        ("Мощность лазера",        0,      500,    5,    "Вт"),
        ("Частота импульсов",      0,      100000, 500,  "Гц"),
        ("Фокусное смещение",     -5000,   5000,   50,   "мкм"),
        ("Длительность импульса",  0,      1000,   5,    "мкс"),
        ("Время воздействия",      0,      10000,  50,   "мс"),
    ]

    # Соответствие «название блока → ключ параметра в заглушке лазера».
    PARAM_KEYS = {
        "Мощность лазера":        "power",
        "Частота импульсов":      "frequency",
        "Фокусное смещение":      "focus",
        "Длительность импульса":  "pulse",
        "Время воздействия":      "exposure",
    }

    # Какие параметры применимы в каждом режиме излучения. Непрерывный режим
    # не оперирует импульсами (частота/длительность не имеют смысла), одиночный
    # импульс — это единичный выстрел (нет частоты и времени воздействия).
    MODE_ENABLED = {
        "Непрерывный": {"Мощность лазера", "Фокусное смещение",
                        "Время воздействия"},
        "Импульсный": {"Мощность лазера", "Частота импульсов",
                       "Фокусное смещение", "Длительность импульса",
                       "Время воздействия"},
        "Одиночный импульс": {"Мощность лазера", "Фокусное смещение",
                              "Длительность импульса"},
    }

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()
        main = QHBoxLayout()

        # --- слева: блоки-параметры (сетка 2 колонки) ---
        grid = QGridLayout()
        self.params: dict[str, _LaserParamPanel] = {}
        positions = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
        for (name, lo, hi, step, unit), (r, c) in zip(self.PARAM_SPECS, positions):
            panel = _LaserParamPanel(name, lo, hi, step,
                                     on_apply=self._apply_param, unit=unit)
            self.params[name] = panel
            grid.addWidget(panel, r, c)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        main.addLayout(grid, 3)

        # --- справа: режим работы ---
        self.mode = _ModePanel(on_change=self._mode_changed)
        right = QVBoxLayout()
        right.addWidget(self.mode)
        right.addStretch()
        main.addLayout(right, 1)

        layout.addLayout(main)
        layout.addStretch()

        # строка локального результата действий
        self.status_line = LastMessageBar()
        layout.addWidget(self.status_line)

        self.ctl.logMessage.connect(self.status_line.set_message)
        self.ctl.stateChanged.connect(self._refresh)
        self._apply_mode_gating(self.mode.current_mode())  # начальный режим
        self._refresh()

    # ------------------------------------------------------------------
    def _apply_param(self, name: str, value: int, unit: str = "") -> None:
        key = self.PARAM_KEYS.get(name)
        if key is not None:
            self.ctl.set_laser_param(key, value)
        shown = f"{value} {unit}".rstrip() if unit else str(value)
        self.status_line.set_message("info", f"{name}: задано значение {shown}")

    def _mode_changed(self, mode_text: str) -> None:
        self.ctl.set_laser_mode(mode_text)
        self._apply_mode_gating(mode_text)
        self.status_line.set_message("info", f"Режим работы: {mode_text.lower()}")

    def _apply_mode_gating(self, mode_text: str) -> None:
        """Погасить неприменимые в выбранном режиме параметры."""
        enabled = self.MODE_ENABLED.get(mode_text, set(self.params))
        for name, panel in self.params.items():
            on = name in enabled
            panel.set_param_enabled(
                on, "" if on else f"Недоступно в режиме «{mode_text.lower()}»")

    def _refresh(self) -> None:
        las = self.ctl.snapshot()["laser"]
        by_key = {
            "power": "Мощность лазера",
            "frequency": "Частота импульсов",
            "focus": "Фокусное смещение",
            "pulse": "Длительность импульса",
            "exposure": "Время воздействия",
        }
        for key, name in by_key.items():
            panel = self.params.get(name)
            if panel is not None:
                panel.show_applied(las[key])
