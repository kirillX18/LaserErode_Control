"""
laser_tab.py — вкладка «Лазером» (настройка параметров лазерного воздействия).

Интерфейс ручной настройки лазера для электроэрозионной обработки. Слева —
пять одинаковых по устройству блоков-параметров (мощность, частота импульсов,
фокусное смещение, длительность импульса, время воздействия), справа — выбор
режима излучения. У устройства-заглушки лазерного узла нет, поэтому вкладка
держит собственное локальное состояние, а результат действия показывает в
строке внизу (LastMessageBar). Когда в стабах появится лазер, _apply_param и
_mode_changed достаточно перенаправить в DeviceController.

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
    MetricRow, StepControl, PrimaryButton, LastMessageBar,
)
from .. import theme


class _LaserParamPanel(BasePanel):
    """Блок одного параметра лазера: поле ввода значения, кнопки шага и «Задать».

    Текущее (применённое) значение показывается строкой сверху; нужное
    значение набирается в числовом поле или подбирается кнопками шага
    (±1 / ±10) и применяется кнопкой «Задать», которая сообщает его наружу
    через колбэк on_apply(name, value).
    """

    def __init__(self, title: str, lo: int, hi: int, on_apply, parent=None):
        self._title_text = title
        self._lo, self._hi = lo, hi
        self._value = 0
        self._on_apply = on_apply
        super().__init__(title, parent)

    def build(self) -> None:
        # Текущее значение — строкой «подпись … значение», как на остальных
        # вкладках (ср. «Текущая позиция:», «Текущая скорость:»).
        self.value_row = MetricRow("Текущее значение:", "0")
        self.body.addWidget(self.value_row)

        # Строка ввода: подпись — поле со счётчиком — «Задать»
        # (как «Задать скорость:» / «Задать лимит тока:» на других вкладках).
        grid = QGridLayout()
        grid.addWidget(QLabel("Задать значение:"), 0, 0)
        self.spin = QSpinBox()
        self.spin.setRange(self._lo, self._hi)
        self.spin.setValue(0)
        grid.addWidget(self.spin, 0, 1)
        self.apply_btn = PrimaryButton("Задать")
        self.apply_btn.setMaximumWidth(120)
        self.apply_btn.clicked.connect(self._apply)
        grid.addWidget(self.apply_btn, 0, 2)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        # Кнопки шага под полем: меняют значение в поле на ±1 / ±10.
        self.steps = StepControl((1, 10), self._step,
                                 label_first=False, minus_red=False)
        self.body.addWidget(self.steps)

    # ------------------------------------------------------------------
    def _step(self, delta: float) -> None:
        # setValue сам ограничит значение диапазоном поля.
        self.spin.setValue(int(self.spin.value() + delta))

    def _apply(self) -> None:
        self._value = self.spin.value()
        self.value_row.set_value(self._value)
        if self._on_apply is not None:
            self._on_apply(self._title_text, self._value)

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
            if i == 0:                      # по умолчанию — непрерывный режим
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

    # (название блока, нижняя граница, верхняя граница).
    # Фокусное смещение регулируется «в обе стороны», поэтому может быть < 0.
    PARAM_SPECS = [
        ("Мощность лазера",        0,       100000),
        ("Частота импульсов",      0,       100000),
        ("Фокусное смещение",     -100000,  100000),
        ("Длительность импульса",  0,       100000),
        ("Время воздействия",      0,       100000),
    ]

    def build_content(self, layout: QVBoxLayout) -> None:
        main = QHBoxLayout()

        # --- слева: блоки-параметры (сетка 2 колонки) ---
        grid = QGridLayout()
        self.params: dict[str, _LaserParamPanel] = {}
        positions = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
        for (name, lo, hi), (r, c) in zip(self.PARAM_SPECS, positions):
            panel = _LaserParamPanel(name, lo, hi, on_apply=self._apply_param)
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

    # ------------------------------------------------------------------
    def _apply_param(self, name: str, value: int) -> None:
        self.status_line.set_message("info", f"{name}: задано значение {value}")

    def _mode_changed(self, mode_text: str) -> None:
        self.status_line.set_message("info", f"Режим работы: {mode_text.lower()}")
