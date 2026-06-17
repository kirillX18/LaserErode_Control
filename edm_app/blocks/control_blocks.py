"""
control_blocks.py — панели управления, общие для страниц устройства:

    QuickActionBar   — панель быстрых действий (Инициализация/Пуск/Стоп/Авария);
    ParameterForm    — форма числовых параметров (лимит тока, скорость, …);
    TestHarnessPanel — имитация сигналов датчиков (TestHarness, только стенд).
"""

from typing import Callable

from PyQt5.QtWidgets import (
    QHBoxLayout, QGridLayout, QLabel, QDoubleSpinBox, QCheckBox,
)

from ..base import BasePanel
from ..components import PrimaryButton, DangerButton, GrayButton, StopButton
from .. import theme


class QuickActionBar(BasePanel):
    """Горизонтальная панель быстрых действий процесса.

    Визуальная иерархия отражает порядок работы: пока процесс не
    инициализирован — главная (зелёная) кнопка «Инициализация»; после неё
    главной становится «Запуск процесса». «Пауза» — нейтральная, чтобы не
    сливаться с «Запуском». «Стоп» — янтарная управляемая остановка (единый
    термин и цвет во всём приложении), «АВАРИЙНЫЙ СТОП» — красная и отнесена
    вправо. Под рядом кнопок — строка с первой невыполненной причиной запуска.
    """

    def build(self) -> None:
        row = QHBoxLayout()
        self.body.addLayout(row)

        self.init_button = PrimaryButton("Инициализация")
        self.init_button.setMaximumWidth(200)
        self.start_button = PrimaryButton("Запуск процесса")
        self.pause_button = GrayButton("Пауза")
        self.pause_button.setMaximumWidth(160)
        self.stop_button = StopButton("Стоп")
        self.estop_button = DangerButton("АВАРИЙНЫЙ СТОП")
        self.estop_button.setToolTip(
            "Аварийная остановка — горячая клавиша Esc (в любой момент)")

        row.addWidget(self.init_button)
        row.addWidget(self.start_button)
        row.addWidget(self.pause_button)
        row.addWidget(self.stop_button)
        row.addStretch()
        row.addWidget(self.estop_button)

        # Строка-подсказка: первая невыполненная причина запуска. Пуста, когда
        # запуск доступен или процесс уже идёт.
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color:{theme.Palette.WARN}; padding:2px 2px 0;")
        self.body.addWidget(self.hint)

    def set_enabled_states(self, *, can_start: bool, can_stop: bool,
                           can_pause: bool = False, paused: bool = False,
                           initialized: bool = False, running: bool = False,
                           start_reason: str = "") -> None:
        self.start_button.setEnabled(can_start)
        self.stop_button.setEnabled(can_stop)
        self.pause_button.setEnabled(can_pause)
        self.pause_button.setText("Продолжить" if paused else "Пауза")

        # Перенос «главной» зелёной кнопки по этапу работы.
        if running or initialized:
            self.init_button.set_role(theme.ROLE_GRAY)
        else:
            self.init_button.set_role(theme.ROLE_PRIMARY)
        # «Запуск» остаётся зелёной ролью; пока недоступен — QSS красит его
        # как disabled (серый), поэтому глаз не уводит на него раньше времени.

        # Причина недоступности запуска — подсказкой на кнопке и строкой снизу.
        if not can_start and not running and start_reason:
            self.start_button.setToolTip(start_reason)
            self.hint.setText("⚠  " + start_reason)
        else:
            self.start_button.setToolTip("")
            self.hint.setText("")


class ParameterForm(BasePanel):
    """Форма числовых параметров: строка = подпись + поле + кнопка действия."""

    def build(self) -> None:
        self.grid = QGridLayout()
        self.body.addLayout(self.grid)
        self._row = 0
        self.fields: dict[str, QDoubleSpinBox] = {}

    def add_row(self, key: str, label: str, *, lo: float, hi: float,
                value: float, step: float = 1.0, decimals: int = 1,
                suffix: str = "", button: str = "Задать",
                callback: Callable[[float], None]) -> None:
        self.grid.addWidget(QLabel(label), self._row, 0)
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        self.fields[key] = spin
        self.grid.addWidget(spin, self._row, 1)

        btn = PrimaryButton(button)
        btn.setMaximumWidth(130)
        btn.clicked.connect(lambda: callback(spin.value()))
        self.grid.addWidget(btn, self._row, 2)
        self.grid.setColumnStretch(1, 1)
        self._row += 1

    def set_range(self, key: str, lo: float, hi: float) -> None:
        if key in self.fields:
            self.fields[key].setRange(lo, hi)

    def set_value(self, key: str, value: float) -> None:
        if key in self.fields:
            self.fields[key].setValue(value)

    def sync(self, key: str, value: float) -> None:
        """Подтянуть поле к реальному значению, не мешая ручному вводу."""
        spin = self.fields.get(key)
        if spin is not None and not spin.hasFocus():
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)


class TestHarnessPanel(BasePanel):
    """
    Имитация сигналов датчиков (крышка, температура, ток). В реальной
    прошивке этих методов нет — панель стендовая. Подготовка ёмкости
    (жидкость/электроды) — реальные операции, они на вкладке
    «Эрозия и полировка».
    """

    def build(self) -> None:
        note = QLabel("Только стенд: имитирует сигналы датчиков для проверки "
                      "UI без подключённого железа (TestHarness).")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.Palette.WARN};")
        self.body.addWidget(note)

        self.lid_check = QCheckBox("Крышка закрыта")
        self.lid_check.setChecked(True)
        self.body.addWidget(self.lid_check)

        grid = QGridLayout()
        self.temp_spin = self._spin(0, 120, 25.0, " °C")
        self.curr_spin = self._spin(0, 15, 0.0, " А", decimals=1, step=0.1)
        grid.addWidget(QLabel("Температура:"), 0, 0)
        grid.addWidget(self.temp_spin, 0, 1)
        self.temp_button = PrimaryButton("Задать")
        self.temp_button.setMaximumWidth(110)
        grid.addWidget(self.temp_button, 0, 2)
        grid.addWidget(QLabel("Ток источника:"), 1, 0)
        grid.addWidget(self.curr_spin, 1, 1)
        self.curr_button = PrimaryButton("Задать")
        self.curr_button.setMaximumWidth(110)
        grid.addWidget(self.curr_button, 1, 2)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

    def _spin(self, lo, hi, value, suffix, decimals=1, step=1.0):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(decimals)
        sp.setSingleStep(step)
        sp.setValue(value)
        sp.setSuffix(suffix)
        return sp
