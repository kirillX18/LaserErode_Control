"""
status.py — переиспользуемые виджеты отображения состояния.

HTML-дизайн строится на цветных индикаторах, «пилюлях»-бейджах, строках
«параметр → значение» и шкалах. Здесь их Qt-аналоги, оформленные через
theme.py (цвета не зашиты в виджеты):

    StatusDot  — цветной индикатор-точка        (HTML .idot / .dot)
    StatusBadge— текстовая «пилюля» состояния    (HTML .badge / .pill)
    MetricRow  — строка [подпись] … [значение]   (HTML .metric)
    MeterBar   — горизонтальная шкала 0…100 %     (HTML .bar)

Состояние задаётся строкой: "ok" | "warn" | "err" | "off".
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QLabel, QWidget, QHBoxLayout, QProgressBar, QSizePolicy,
)

from .. import theme


class StatusDot(QLabel):
    """Маленький цветной кружок-индикатор."""

    def __init__(self, state: str = "off", size: int = 12, parent=None):
        super().__init__(parent)
        self._size = size
        self.set_state(state)

    def set_state(self, state: str) -> None:
        self.setStyleSheet(theme.dot_style(state, self._size))


class StatusBadge(QLabel):
    """Текстовая «пилюля» состояния (цвет + подпись)."""

    def __init__(self, text: str = "—", state: str = "off", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_state(text, state)

    def set_state(self, text: str, state: str = "off") -> None:
        self.setText(text)
        self.setStyleSheet(theme.badge_style(state))


class _ElidingLabel(QLabel):
    """QLabel, сокращающая длинный текст многоточием по ширине виджета.

    Обычная QLabel сообщает компоновке минимальную ширину, равную ширине
    ПОЛНОГО текста. Из-за этого длинная строка (например, путь к файлу)
    раздвигает колонку и не даёт сжимать окно. Эта метка хранит полный текст
    отдельно, отображает усечённый вариант и через политику размера Ignored
    не навязывает компоновке свою «полную» ширину — поэтому может сжиматься
    до нуля, а полный текст доступен во всплывающей подсказке.
    """

    def __init__(self, text: str = "", mode=Qt.ElideMiddle, parent=None):
        super().__init__(parent)
        self._full = str(text)
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self._apply()

    def setText(self, text) -> None:           # noqa: N802 (Qt-стиль)
        self._full = str(text)
        self.setToolTip(self._full if self._full not in ("", "—") else "")
        self._apply()

    def text(self) -> str:                     # вернуть полный, а не усечённый
        return self._full

    def _apply(self) -> None:
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._full, self._mode, max(0, self.width())))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply()


class MetricRow(QWidget):
    """Строка «подпись … значение» с возможностью подкрасить значение.

    При elide=True значение усекается многоточием и не растягивает строку по
    ширине (для путей, имён файлов и прочих потенциально длинных значений).
    """

    def __init__(self, label: str, value: str = "—", parent=None,
                 elide: bool = False):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 1, 0, 1)
        self._key = QLabel(label)
        self._elide = elide
        if elide:
            self._val = _ElidingLabel(value, Qt.ElideMiddle)
            self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            h.addWidget(self._key)
            h.addWidget(self._val, 1)   # значение занимает остаток и сжимается
        else:
            self._val = QLabel(value)
            self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            h.addWidget(self._key)
            h.addStretch()
            h.addWidget(self._val)

    def set_value(self, value, state: str | None = None) -> None:
        self._val.setText(str(value))
        if state is None:
            self._val.setStyleSheet(theme.value_style())
        else:
            fg, _ = theme.state_colors(state)
            self._val.setStyleSheet(f"color:{fg}; font-weight:bold;")


class MeterBar(QProgressBar):
    """Горизонтальная шкала 0…100 % с цветом по состоянию."""

    def __init__(self, kind: str = "ok", parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.setStyleSheet(theme.meter_style(kind))

    def set_fraction(self, fraction: float) -> None:
        self.setValue(max(0, min(100, int(round(fraction * 100)))))


class _LinkLabel(QLabel):
    """Кликабельная подпись-ссылка (для «маршрута исправления» условий)."""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class IndicatorRow(QWidget):
    """Строка-индикатор: [точка] подпись … [состояние] [исправить →].

    Используется в списках условий запуска и сводках состояния, где важно
    цветом показать «ок / не ок» (HTML — строки со светофором-точкой). Если
    задано действие set_fix_action(), при невыполненном условии справа
    появляется кликабельная ссылка-«маршрут исправления»: она ведёт туда, где
    условие можно устранить (вкладка настройки, инициализация и т. п.).
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 1, 0, 1)
        self.dot = StatusDot("off", 10)
        self._key = QLabel(label)
        self._val = QLabel("—")
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.fix = _LinkLabel("")
        self.fix.setStyleSheet(
            f"color:{theme.Palette.TITLE_BLUE}; text-decoration:underline;")
        self.fix.setCursor(Qt.PointingHandCursor)
        self.fix.setVisible(False)
        h.addWidget(self.dot)
        h.addWidget(self._key)
        h.addStretch()
        h.addWidget(self._val)
        h.addWidget(self.fix)

        self._fix_cb = None
        self._fix_label = "исправить →"
        self.fix.clicked.connect(self._on_fix)

    def set_fix_action(self, label: str, callback) -> None:
        """Назначить действие-исправление и подпись ссылки (например,
        «настроить →»). Ссылка показывается только когда условие не выполнено."""
        self._fix_label = label
        self._fix_cb = callback

    def _on_fix(self) -> None:
        if self._fix_cb is not None:
            self._fix_cb()

    def set_state(self, state: str, text: str) -> None:
        self.dot.set_state(state)
        self._val.setText(text)
        fg, _ = theme.state_colors(state)
        self._val.setStyleSheet(f"color:{fg}; font-weight:bold;")
        show = self._fix_cb is not None and state != "ok"
        if show:
            self.fix.setText("   " + self._fix_label)
        self.fix.setVisible(show)


class LastMessageBar(QLabel):
    """Компактная строка последнего сообщения/результата операции.

    Подключается к сигналу DeviceController.logMessage и показывает последнее
    событие прямо на вкладке — чтобы реакция на действие (в т. ч. ошибка) была
    видна локально, а не только в общем журнале на другой странице.
    """

    def __init__(self, parent=None):
        super().__init__("Готов к работе", parent)
        self.setWordWrap(True)
        self._apply("info")

    def _apply(self, level: str) -> None:
        color = {"warning": theme.Palette.WARN,
                 "error": theme.Palette.ERR}.get(level, theme.Palette.OFF)
        self.setStyleSheet(f"color:{color}; padding:3px 2px;")

    def set_message(self, level: str, text: str) -> None:
        self._apply(level)
        self.setText(text)
