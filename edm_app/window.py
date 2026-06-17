"""
window.py — главное окно приложения.

Шапка + строка общего состояния устройства (MasterStatusBar) + верхние
вкладки. Страницы берутся из реестра PAGES.

Все страницы и строка состояния используют один общий DeviceController
(controller()), поэтому показывают согласованное состояние. Здесь же запущен
единый таймер мониторинга, который раз в секунду вызывает check_safety()
(через poll()).
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel, QApplication,
    QTabBar, QScrollArea, QAbstractSpinBox,
)
from PyQt5.QtCore import Qt, QTimer, QEvent

from . import theme
from .pages import ProcessPage, ServiceControlPage, HardwarePage
from .blocks import MasterStatusBar
from .components import AnimatedTabBar
from .hardware import controller

APP_TITLE = "Управление лазерно-эрозионным роботом"

# Реестр страниц верхнего уровня: (заголовок вкладки, класс страницы).
PAGES = [
    ("Процесс", ProcessPage),
    ("Узлы оборудования", HardwarePage),
    ("Сервисное управление", ServiceControlPage),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1450, 820)
        self.pages = {}
        self._kbd_active = False  # включён ли клавиатурный режим (видна рамка)
        self._setup_ui()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        header = QLabel(APP_TITLE)
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setStyleSheet(theme.header_style())
        layout.addWidget(header)

        # Строка общего состояния устройства (видна на всех страницах).
        self.status_bar = MasterStatusBar()
        layout.addWidget(self.status_bar)

        self.tabs = QTabWidget()
        self.tabs.setTabBar(AnimatedTabBar())   # плавная подсветка при наведении
        for title, page_cls in PAGES:
            page = page_cls()
            self.pages[title] = page
            self.tabs.addTab(page, title)
        layout.addWidget(self.tabs)

        # Общий контроллер: строка состояния + единый мониторинг безопасности.
        self._ctl = controller()
        self._ctl.stateChanged.connect(self._update_status_bar)
        self._update_status_bar()

        self._monitor = QTimer(self)
        self._monitor.timeout.connect(self._ctl.poll)
        self._monitor.start(500)

        # Перехват Tab на уровне всего приложения, чтобы переключение страниц
        # работало независимо от того, какой виджет сейчас в фокусе.
        QApplication.instance().installEventFilter(self)

        # Tab должен останавливаться только на реальных органах управления.
        self._strip_container_focus()

    def _update_status_bar(self) -> None:
        self.status_bar.update_from(self._ctl.snapshot(), self._ctl.alarms())

    def _strip_container_focus(self) -> None:
        """Убрать из обхода Tab контейнеры без видимой рамки фокуса
        (полосы вкладок, сами вкладки-контейнеры, области прокрутки).

        Эти виджеты принимают Tab-остановку, но ничего не подсвечивают —
        из-за чего нажатие Tab выглядело «впустую». Страницы переключаются
        по Ctrl, поэтому фокус им не нужен, и Tab теперь идёт только по
        кнопкам и полям ввода.
        """
        central = self.centralWidget()
        for cls in (QTabBar, QTabWidget, QScrollArea):
            for widget in central.findChildren(cls):
                widget.setFocusPolicy(Qt.NoFocus)

    # --- Подсветка фокуса только при навигации с клавиатуры ------------------
    #
    # Рамку показываем, только если фокус пришёл по Tab/Shift+Tab или через
    # горячую клавишу. При получении фокуса мышью или программно — не
    # показываем, а при клике мышью гасим уже показанную рамку.

    _KEY_REASONS = (Qt.TabFocusReason, Qt.BacktabFocusReason,
                    Qt.ShortcutFocusReason)

    @staticmethod
    def _focus_target(widget):
        """Логический виджет для подсветки (у спинбокса фокус держит его
        внутреннее поле ввода — подсвечивать нужно сам спинбокс)."""
        if not isinstance(widget, QWidget):
            return None
        parent = widget.parent()
        return parent if isinstance(parent, QAbstractSpinBox) else widget

    @staticmethod
    def _set_key_focus(widget, on: bool) -> None:
        if widget is None or bool(widget.property("keyFocus")) == on:
            return
        widget.setProperty("keyFocus", on)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def show_page(self, title: str) -> None:
        """Переключиться на страницу по её заголовку."""
        index = self.tabs.indexOf(self.pages[title])
        if index >= 0:
            self.tabs.setCurrentIndex(index)

    def navigate_to(self, top_title: str, inner_title: str = None) -> None:
        """Перейти на верхнюю вкладку и (опц.) на внутреннюю вкладку сервиса.

        Используется чек-листом «Условия запуска» как «маршрут исправления»:
        клик по невыполненному условию ведёт туда, где его можно устранить.
        """
        page = self.pages.get(top_title)
        if page is None:
            return
        idx = self.tabs.indexOf(page)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        if inner_title:
            inner = getattr(page, "tabs_widget", None)
            if isinstance(inner, QTabWidget):
                for j in range(inner.count()):
                    if inner.tabText(j) == inner_title:
                        inner.setCurrentIndex(j)
                        break

    def _trigger_emergency_stop(self) -> None:
        """Аварийная остановка по горячей клавише (Esc).

        Если на текущей странице есть кнопка «АВАРИЙНЫЙ СТОП» — «нажимаем»
        именно её (animateClick: видимая анимация нажатия + штатный сигнал
        clicked → emergency_stop). На страницах без кнопки (напр. «Сервисное
        управление») выполняем то же действие напрямую через контроллер.
        """
        quick = getattr(self.tabs.currentWidget(), "quick", None)
        btn = getattr(quick, "estop_button", None)
        if btn is not None and btn.isEnabled() and btn.isVisible():
            btn.animateClick()
        else:
            self._ctl.emergency_stop()

    # --- Навигация по страницам с клавиатуры --------------------------------
    #
    # Иерархия вкладок «расплющивается» в один кольцевой список:
    #   Процесс → Узлы оборудования →
    #   Сервисное управление[Шаговый привод → Координатный стол →
    #                         Лазером → Параметры устройства] → (снова Процесс)
    # Переключение: Ctrl+Tab / Ctrl+PageUp/PageDown (по кольцу) и Ctrl+N
    # (прямой переход). Обычный Tab оставлен под штатный обход фокуса.
    # Список строится из самих вкладок, поэтому новые пункты в реестрах
    # (PAGES / SERVICE_TABS) подхватываются автоматически.

    def _nav_sequence(self) -> list:
        """Плоская последовательность шагов: (индекс верхней вкладки,
        индекс внутренней вкладки или None)."""
        seq = []
        for i in range(self.tabs.count()):
            inner = getattr(self.tabs.widget(i), "tabs_widget", None)
            if isinstance(inner, QTabWidget) and inner.count() > 0:
                seq.extend((i, j) for j in range(inner.count()))
            else:
                seq.append((i, None))
        return seq

    def _current_nav_step(self, seq: list) -> int:
        """Найти позицию текущего состояния в плоской последовательности."""
        top = self.tabs.currentIndex()
        inner = getattr(self.tabs.widget(top), "tabs_widget", None)
        cur_inner = inner.currentIndex() if isinstance(inner, QTabWidget) else None
        for idx, (t, j) in enumerate(seq):
            if t == top and j == cur_inner:
                return idx
        return 0

    def _apply_nav(self, entry: tuple) -> None:
        """Применить шаг (индекс верхней вкладки, индекс внутренней/None)."""
        self._kbd_active = False  # после смены страницы первый Tab — подсветка
        top, inner_idx = entry
        self.tabs.setCurrentIndex(top)
        if inner_idx is not None:
            inner = getattr(self.tabs.widget(top), "tabs_widget", None)
            if isinstance(inner, QTabWidget):
                inner.setCurrentIndex(inner_idx)

    def _advance_nav(self, step: int) -> None:
        seq = self._nav_sequence()
        if not seq:
            return
        self._apply_nav(seq[(self._current_nav_step(seq) + step) % len(seq)])

    def _goto_nav(self, index: int) -> None:
        """Прямой переход на страницу по её порядковому номеру (Ctrl+N)."""
        seq = self._nav_sequence()
        if 0 <= index < len(seq):
            self._apply_nav(seq[index])

    def _show_key_help(self) -> None:
        """Окно-справка по горячим клавишам (F1)."""
        from PyQt5.QtWidgets import QMessageBox

        pages = []
        for n, (top, inner_idx) in enumerate(self._nav_sequence(), start=1):
            name = self.tabs.tabText(top)
            if inner_idx is not None:
                inner = getattr(self.tabs.widget(top), "tabs_widget", None)
                if isinstance(inner, QTabWidget):
                    name += " → " + inner.tabText(inner_idx)
            pages.append(f"    Ctrl+{n} — {name}")

        text = (
            "ПЕРЕМЕЩЕНИЕ ФОКУСА\n"
            "    Tab / Shift+Tab — следующий / предыдущий элемент страницы\n\n"
            "ДЕЙСТВИЯ С ВЫДЕЛЕННЫМ ЭЛЕМЕНТОМ\n"
            "    Пробел — нажать кнопку / переключить флажок\n"
            "    ↑ / ↓ — изменить число в поле\n"
            "    Enter — применить значение в поле ввода\n"
            "    цифры — ввести значение прямо в поле\n\n"
            "БЕЗОПАСНОСТЬ\n"
            "    Esc — АВАРИЙНАЯ ОСТАНОВКА (в любой момент)\n\n"
            "ПЕРЕКЛЮЧЕНИЕ СТРАНИЦ\n"
            "    Ctrl+Tab / Ctrl+Shift+Tab — следующая / предыдущая\n"
            "    Ctrl+PageDown / Ctrl+PageUp — то же самое\n"
            + "\n".join(pages)
            + "\n\n    F1 — эта справка"
        )
        QMessageBox.information(self, "Управление с клавиатуры", text)

    def eventFilter(self, obj, event):
        et = event.type()

        # Подсветка фокуса: показываем рамку только при клавиатурном фокусе.
        if et == QEvent.FocusIn and isinstance(obj, QWidget):
            self._set_key_focus(self._focus_target(obj),
                                event.reason() in self._KEY_REASONS)
            return super().eventFilter(obj, event)
        if et == QEvent.FocusOut and isinstance(obj, QWidget):
            self._set_key_focus(self._focus_target(obj), False)
            return super().eventFilter(obj, event)
        if et == QEvent.MouseButtonPress:
            # Любой клик мышью гасит рамку и выключает клавиатурный режим.
            self._kbd_active = False
            self._set_key_focus(
                self._focus_target(QApplication.instance().focusWidget()),
                False)
            return super().eventFilter(obj, event)

        if et != QEvent.KeyPress:
            return super().eventFilter(obj, event)

        key = event.key()
        ctrl = bool(event.modifiers() & Qt.ControlModifier)

        if key == Qt.Key_F1:
            self._show_key_help()
            return True

        # Esc — аварийная остановка в любой момент. Отдельная заметная клавиша;
        # Enter оставлен под штатное «применить/подтвердить» в полях ввода.
        # Если открыт модальный диалог (справка F1, подтверждение остановки) —
        # не перехватываем Esc, чтобы клавиша штатно закрыла этот диалог.
        # Автоповтор удержанной клавиши игнорируем.
        if (key == Qt.Key_Escape and not event.isAutoRepeat()
                and QApplication.activeModalWidget() is None
                and QApplication.activePopupWidget() is None):
            self._trigger_emergency_stop()
            return True

        # Переключение страниц по кольцу — только с Ctrl, чтобы обычный Tab
        # остался стандартным обходом фокуса между элементами страницы.
        if ctrl and key in (Qt.Key_Tab, Qt.Key_Backtab):
            self._advance_nav(-1 if key == Qt.Key_Backtab else 1)
            return True
        if ctrl and key in (Qt.Key_PageDown, Qt.Key_PageUp):
            self._advance_nav(1 if key == Qt.Key_PageDown else -1)
            return True
        if ctrl and Qt.Key_1 <= key <= Qt.Key_9:
            self._goto_nav(key - Qt.Key_1)
            return True

        # Первое нажатие Tab/Shift+Tab только включает подсветку на текущем
        # элементе, не переходя на следующий. Дальше Tab двигает фокус штатно.
        if not ctrl and key in (Qt.Key_Tab, Qt.Key_Backtab):
            if not self._kbd_active:
                self._kbd_active = True
                fw = QApplication.instance().focusWidget()
                if fw is not None:
                    self._set_key_focus(self._focus_target(fw), True)
                    return True  # фокус не двигаем — только показываем рамку
            return super().eventFilter(obj, event)

        # Обычный Tab/Shift+Tab и стрелки не трогаем — это штатная навигация
        # по элементам и редактирование полей.
        return super().eventFilter(obj, event)
