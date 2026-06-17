"""
theme.py — единый источник правды для оформления.

Здесь собраны: палитра цветов, глобальная таблица стилей (QSS) и фабрика
шрифтов. Любое изменение дизайна делается в одном месте и применяется ко
всему приложению, без правки отдельных виджетов.
"""

from PyQt5.QtGui import QFont


class Palette:
    """Цвета интерфейса (вынесены, чтобы менять тему централизованно)."""
    BG = "#f0f0f0"
    PANEL = "#fafafa"
    BORDER = "#b0b0b0"

    GREEN = "#1e8c1e"
    GREEN_HOVER = "#239c23"
    GREEN_PRESSED = "#176e17"

    RED = "#d52020"
    RED_HOVER = "#e23232"
    RED_PRESSED = "#b01818"

    AMBER = "#e0a800"          # янтарный — управляемая остановка (не авария)
    AMBER_HOVER = "#f0b90b"
    AMBER_PRESSED = "#c79100"

    GRAY = "#cfcfcf"
    HEADER_BG = "#7a7a7a"
    TITLE_BLUE = "#1f4e79"
    TAB_BG = "#e4e4e4"

    # Индикатор фокуса (управление с клавиатуры). Амбер хорошо виден на
    # зелёных/красных/серых кнопках; синий — на белых полях ввода.
    FOCUS = "#ffc107"
    FOCUS_FIELD = "#1f4e79"

    # --- статусы узлов (страница «Оборудование», HMI-перенос) ---
    OK = GREEN            # включено / работа
    OK_BG = "#e3f4e3"
    WARN = "#b8860b"      # ожидание / предупреждение
    WARN_BG = "#faf0d2"
    ERR = RED             # ошибка / авария
    ERR_BG = "#fbe2e2"
    OFF = "#8a8a8a"       # выключено
    OFF_BG = "#ececec"
    ACCENT = TITLE_BLUE   # синий акцент (значения, время)
    VALUE = "#15507a"     # цвет числовых значений


# Имена objectName, по которым в QSS задаётся особый стиль кнопок.
# Используются через helper-функции в components/buttons.py.
ROLE_PRIMARY = ""          # обычная зелёная кнопка (стиль по умолчанию)
ROLE_DANGER = "danger"     # широкая красная кнопка ("Вернуться в нулевое...")
ROLE_RED = "red"           # маленькая красная кнопка ("−")
ROLE_SMALL = "small"       # компактная кнопка шага
ROLE_GRAY = "gray"         # серая кнопка ("Назад")
ROLE_STOP = "stop"         # янтарная кнопка управляемой остановки


# Глобальная таблица стилей. Строится из палитры, чтобы не дублировать цвета.
STYLESHEET = f"""
QMainWindow, QWidget {{ background: {Palette.BG}; }}

QGroupBox {{
    border: 1px solid {Palette.BORDER};
    border-radius: 3px;
    margin-top: 10px;
    font-weight: bold;
    background: {Palette.PANEL};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}

QPushButton {{
    background: {Palette.GREEN};
    color: white;
    border: 2px solid transparent;
    border-radius: 3px;
    padding: 6px 8px;
    font-weight: bold;
}}
QPushButton:hover    {{ background: {Palette.GREEN_HOVER}; }}
QPushButton:pressed  {{ background: {Palette.GREEN_PRESSED}; }}
QPushButton:disabled {{ background: #cfcfcf; color: #888888; }}
QPushButton[keyFocus="true"] {{ border: 2px solid {Palette.FOCUS}; }}

QPushButton#{ROLE_DANGER}            {{ background: {Palette.RED}; }}
QPushButton#{ROLE_DANGER}:hover      {{ background: {Palette.RED_HOVER}; }}
QPushButton#{ROLE_DANGER}:pressed    {{ background: {Palette.RED_PRESSED}; }}

QPushButton#{ROLE_RED}               {{ background: {Palette.RED}; }}
QPushButton#{ROLE_RED}:hover         {{ background: {Palette.RED_HOVER}; }}
QPushButton#{ROLE_RED}:pressed       {{ background: {Palette.RED_PRESSED}; }}

QPushButton#{ROLE_SMALL} {{
    padding: 5px 4px;
    min-width: 44px;
}}

QPushButton#{ROLE_GRAY} {{
    background: {Palette.GRAY};
    color: black;
}}

QPushButton#{ROLE_STOP}            {{ background: {Palette.AMBER}; color: black; }}
QPushButton#{ROLE_STOP}:hover      {{ background: {Palette.AMBER_HOVER}; }}
QPushButton#{ROLE_STOP}:pressed    {{ background: {Palette.AMBER_PRESSED}; }}

QPushButton#{ROLE_DANGER}:disabled,
QPushButton#{ROLE_RED}:disabled,
QPushButton#{ROLE_STOP}:disabled,
QPushButton#{ROLE_GRAY}:disabled {{ background: #cfcfcf; color: #888888; }}

QLineEdit, QDoubleSpinBox, QSpinBox, QTextEdit, QPlainTextEdit, QListWidget {{
    background: white;
    border: 1px solid {Palette.BORDER};
    border-radius: 3px;
    padding: 4px;
}}
QLineEdit[keyFocus="true"], QDoubleSpinBox[keyFocus="true"],
QSpinBox[keyFocus="true"], QTextEdit[keyFocus="true"],
QPlainTextEdit[keyFocus="true"], QListWidget[keyFocus="true"] {{
    border: 2px solid {Palette.FOCUS_FIELD};
}}
QCheckBox[keyFocus="true"], QRadioButton[keyFocus="true"] {{
    border: 1px solid {Palette.FOCUS_FIELD};
    border-radius: 3px;
}}

QTabBar::tab {{
    background: {Palette.TAB_BG};
    border: 1px solid {Palette.BORDER};
    padding: 6px 12px;
    margin-right: 1px;
}}
QTabBar::tab:selected {{ background: {Palette.PANEL}; }}
QTabBar:focus {{ outline: none; }}
"""


def default_font() -> QFont:
    """Шрифт приложения по умолчанию."""
    return QFont("Sans Serif", 9)


def title_style() -> str:
    """Инлайновый стиль для заголовков-секций (синие, жирные)."""
    return f"color:{Palette.TITLE_BLUE}; font-weight:bold;"


def header_style() -> str:
    """Стиль для главной шапки окна (тонкая полоса: имя несёт и заголовок окна,
    поэтому баннер не «съедает» рабочую область)."""
    return (f"background:{Palette.HEADER_BG}; color:white; "
            f"padding:3px 8px; font-size:11px;")


# --- помощники оформления статусных виджетов (страница «Оборудование») ---

_STATE_COLORS = {
    "ok":   (Palette.OK,   Palette.OK_BG),
    "warn": (Palette.WARN, Palette.WARN_BG),
    "err":  (Palette.ERR,  Palette.ERR_BG),
    "off":  (Palette.OFF,  Palette.OFF_BG),
}


def state_colors(state: str):
    """(цвет текста, цвет фона) для состояния ok/warn/err/off."""
    return _STATE_COLORS.get(state, _STATE_COLORS["off"])


def badge_style(state: str = "off") -> str:
    """Стиль «пилюли»-бейджа состояния."""
    fg, bg = state_colors(state)
    return (f"QLabel{{ color:{fg}; background:{bg}; border:1px solid {fg}; "
            f"border-radius:8px; padding:2px 8px; font-weight:bold; }}")


def dot_style(state: str = "off", size: int = 12) -> str:
    """Стиль кружка-индикатора."""
    fg, _ = state_colors(state)
    r = size // 2
    return (f"QLabel{{ background:{fg}; border-radius:{r}px; "
            f"min-width:{size}px; max-width:{size}px; "
            f"min-height:{size}px; max-height:{size}px; }}")


def value_style() -> str:
    """Стиль для числового значения по умолчанию."""
    return f"color:{Palette.VALUE}; font-weight:bold;"


def meter_style(kind: str = "ok") -> str:
    """Стиль шкалы MeterBar по типу ok/warn/err/off."""
    fg, bg = state_colors(kind)
    return (f"QProgressBar{{ border:1px solid {Palette.BORDER}; "
            f"border-radius:3px; background:{bg}; }}"
            f"QProgressBar::chunk{{ background:{fg}; border-radius:2px; }}")
