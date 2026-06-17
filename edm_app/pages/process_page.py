"""
process_page.py — страница «Процесс» (главный пульт оператора).

Программа обработки здесь — плоский контур из векторного файла (DXF/SVG/PLT/
HPGL): он масштабируется под рабочее поле, показывается в 3D на столе, и по
нему ведётся лазерная головка во время процесса (X — головка, Y — стол).
Дополнительно можно загрузить 3D-модель детали STL/OBJ как предпросмотр формы.
Сам технологический процесс запускается ProcessController при соблюдении
условий безопасности.

Раскладка с переключением нижней области по нажатию «Запуск процесса»:
    сверху  (всегда) — панель быстрых действий (Инициализация/Пуск/Пауза/Стоп/
                       Авария) и полоса хода процесса (бейдж + шкала + время);
    ниже    — QStackedWidget из двух режимов:
        • ПОДГОТОВКА (процесс не идёт): программа обработки, условия запуска,
          журнал и 3D-превью объекта;
        • ОБРАБОТКА (процесс запущен): крупная 3D-визуализация объекта работы
          и панель ошибок/предупреждений.

3D-вьюпорт и панель ошибок — единственные экземпляры; при переключении режима
они переносятся в нужный экран (reparent через addWidget), поэтому состояние
(загруженная модель, список аварий) не теряется.

Вся логика идёт через общий DeviceController. check_safety() периодически
вызывается из главного окна, поэтому опасные события (открытая крышка,
перегрев, перегрузка) сразу останавливают процесс и возвращают экран подготовки.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QWidget, QSplitter, QHBoxLayout, QFileDialog, QLabel,
    QStackedWidget, QMessageBox,
)
from PyQt5.QtCore import Qt

from ..base import BasePage, BasePanel
from ..components import (
    IndicatorRow, MetricRow, MeterBar, PrimaryButton, GrayButton, StatusBadge,
)
from ..components import make_mesh_viewer
from ..blocks import QuickActionBar, AlarmPanel, EventLogPanel
from ..hardware import controller, process_readiness


class _ProcessFilePanel(BasePanel):
    """Выбор программы обработки — плоского контура для лазерной эрозии.

    Поддерживаются векторные форматы DXF/SVG/PLT/HPGL: загруженный контур
    масштабируется под рабочее поле станка, показывается в 3D на столе, и по
    нему ведётся головка во время процесса. Дополнительно можно загрузить
    3D-модель детали (STL/OBJ) как предпросмотр формы — она не задаёт траекторию.
    """

    FILTER = ("Программа обработки (*.dxf *.svg *.plt *.hpgl *.hpg);;"
              "3D-модель детали (*.stl *.obj);;"
              "Все файлы (*)")

    def build(self) -> None:
        self._path = ""
        self.m_file = MetricRow("Модель:", "не выбрана")
        self.m_path = MetricRow("Путь:", "—")
        self.body.addWidget(self.m_file)
        self.body.addWidget(self.m_path)

        row = QHBoxLayout()
        self.browse_btn = PrimaryButton("Выбрать модель…")
        self.browse_btn.setMaximumWidth(200)
        self.clear_btn = GrayButton("Очистить")
        self.clear_btn.setMaximumWidth(140)
        row.addWidget(self.browse_btn)
        row.addWidget(self.clear_btn)
        row.addStretch()
        self.body.addLayout(row)

    # ------------------------------------------------------------------
    def set_file(self, path: str) -> None:
        import os
        self._path = path or ""
        if self._path:
            self.m_file.set_value(os.path.basename(self._path), "ok")
            self.m_path.set_value(self._path)
        else:
            self.m_file.set_value("не выбрана", "off")
            self.m_path.set_value("—")

    def current_file(self) -> str:
        return self._path


class _ConditionsPanel(BasePanel):
    """Чек-лист условий запуска процесса (_check_start_conditions)."""

    def build(self) -> None:
        self.r_acdc = IndicatorRow("Питание AC/DC")
        self.r_init = IndicatorRow("Инициализация")
        self.r_lid = IndicatorRow("Крышка закрыта")
        self.r_laser = IndicatorRow("Лазер готов")
        self.r_temp = IndicatorRow("Нет перегрева")
        self.r_prog = IndicatorRow("Программа загружена")
        for r in (self.r_acdc, self.r_init, self.r_lid, self.r_laser,
                  self.r_temp, self.r_prog):
            self.body.addWidget(r)


class _ProgressPanel(BasePanel):
    """Полоса хода процесса: бейдж состояния, шкала прогресса и время.

    Собрана из штатных виджетов приложения (StatusBadge, MeterBar, MetricRow),
    поэтому выглядит как обычная панель. Видна всегда: пока процесс не запущен —
    шкала пуста и состояние «ожидание».
    """

    def build(self) -> None:
        top = QHBoxLayout()
        top.addWidget(QLabel("Обрабатывается:"))
        self.l_file = QLabel("—")
        self.l_file.setStyleSheet("color:#15507a; font-weight:bold;")
        top.addWidget(self.l_file)
        top.addStretch()
        self.badge = StatusBadge("ОЖИДАНИЕ", "off")
        top.addWidget(self.badge)
        self.body.addLayout(top)

        self.bar = MeterBar("ok")
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")
        self.bar.setFixedHeight(26)
        self.body.addWidget(self.bar)

        # Прогресс (%) — основной достоверный индикатор. Время — только
        # ориентировочное: длительность процесса зависит от условий обработки,
        # поэтому точный обратный отсчёт секунд был бы недостоверным (HIG, гл. 7
        # «Feedback»: неточный определённый индикатор подрывает доверие).
        self.m_elapsed = MetricRow("Прошло (ориентир.):", "—")
        self.body.addWidget(self.m_elapsed)
        self.note = QLabel("Прогресс (%) — основной показатель; время "
                           "ориентировочное и зависит от условий обработки.")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#8a8a8a; font-size:11px;")
        self.body.addWidget(self.note)

    # ------------------------------------------------------------------
    def update_state(self, proc: dict, file_name: str) -> None:
        running = bool(proc.get("running", False))
        paused = bool(proc.get("paused", False))
        progress = float(proc.get("progress", 0.0))
        duration = float(proc.get("duration", 0.0))

        self.l_file.setText(file_name or "деталь по умолчанию")

        if not running:
            self.badge.set_state("ОЖИДАНИЕ", "off")
            self.bar.set_kind("off")
            self.bar.set_fraction(0.0)
            self.m_elapsed.set_value("—")
            return

        if paused:
            self.badge.set_state("ПАУЗА", "warn")
            self.bar.set_kind("warn")
        else:
            self.badge.set_state("ИДЁТ ОБРАБОТКА", "ok")
            self.bar.set_kind("ok")
        self.bar.set_fraction(progress / 100.0)

        elapsed = duration * progress / 100.0
        self.m_elapsed.set_value(f"~{elapsed:.0f} с")


class _TablePreviewPanel(BasePanel):
    """3D-визуализация программы обработки и детали на координатном столе.

    Внутри — вьюпорт make_mesh_viewer(): сетка стола, оси и либо контур
    программы обработки (DXF/SVG/PLT/HPGL) с движущейся головкой, либо
    3D-модель детали (STL/OBJ). Вращение — ЛКМ, зум — колесо, панорама —
    СКМ/ПКМ, двойной клик — сброс ракурса.
    """

    def build(self) -> None:
        self.viewer = make_mesh_viewer()
        self.viewer.setToolTip(
            "Вращение — ЛКМ · Зум — колесо · Панорама — СКМ/ПКМ · "
            "Двойной клик — сброс ракурса")
        self.body.addWidget(self.viewer, 1)

        self._mode = None    # "path" | "mesh" | None
        self.m_info = MetricRow("Программа:", "не загружена")
        self.m_dims = MetricRow("Контур / габариты:", "—")
        self.body.addWidget(self.m_info)
        self.body.addWidget(self.m_dims)

    # ------------------------------------------------------------------
    def show_toolpath(self, norm_segments, name, vertices, size_mm) -> None:
        """Показать загруженный контур (нормированные ломаные [0..1])."""
        self.viewer.set_toolpath(norm_segments, name)
        self._mode = "path"
        self.m_info.set_value(f"{name} ({len(norm_segments)} контур.)", "ok")
        self.m_dims.set_value(f"{vertices} точек · поле {size_mm}")

    def show_mesh(self, path: str) -> bool:
        """Загрузить STL/OBJ во вьюпорт как предпросмотр детали."""
        import os
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".stl", ".obj"):
            self.clear()
            self.m_info.set_value("формат без 3D-модели", "warn")
            return False
        try:
            self.viewer.load_file(path)
        except Exception as exc:  # noqa: BLE001 — показать ошибку оператору
            self.clear()
            self.m_info.set_value(f"ошибка чтения: {exc}", "err")
            return False
        self._mode = "mesh"
        info = self.viewer.mesh_info()
        sx, sy, sz = info["size"]
        self.m_info.set_value(f"{info['name']} ({info['tris']} тр.)", "ok")
        self.m_dims.set_value(f"{sx:.1f} × {sy:.1f} × {sz:.1f}")
        return True

    def update_head(self, xf: float, yf: float, on: bool) -> None:
        """Обновить положение головки над полем (только в режиме контура)."""
        if self._mode == "path" and hasattr(self.viewer, "set_head_norm"):
            self.viewer.set_head_norm(xf, yf, on)

    def clear(self) -> None:
        self.viewer.clear()
        self._mode = None
        self.m_info.set_value("не загружена", "off")
        self.m_dims.set_value("—")


class ProcessPage(BasePage):
    title = ""

    def build_content(self, layout: QVBoxLayout) -> None:
        self.ctl = controller()
        self._paused = False  # последнее известное состояние паузы (для кнопки)
        self._running = None  # текущий режим (None — ещё не задан)

        # ── всегда сверху: панель действий ──
        self.quick = QuickActionBar("Управление процессом")
        layout.addWidget(self.quick)

        # Полоса хода процесса показывается только на экране обработки
        # (добавляется в _build_active_page), на экране подготовки её нет.
        self.progress = _ProgressPanel("Ход процесса")

        # ── единственные экземпляры панелей, кочующих между экранами ──
        self.preview = _TablePreviewPanel("3D-визуализация объекта работы")
        self.alarms = AlarmPanel("Ошибки и предупреждения")
        self.file_panel = _ProcessFilePanel("Программа обработки")
        self.conditions = _ConditionsPanel("Условия запуска")
        self.log = EventLogPanel("Журнал событий")

        # ── два режима нижней области ──
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_idle_page())     # индекс 0 — подготовка
        self.stack.addWidget(self._build_active_page())   # индекс 1 — обработка
        layout.addWidget(self.stack, 1)

        # действия
        self.quick.init_button.clicked.connect(self.ctl.initialize)
        self.quick.start_button.clicked.connect(self.ctl.start_process)
        self.quick.pause_button.clicked.connect(self._toggle_pause)
        self.quick.stop_button.clicked.connect(self._confirm_stop)
        self.quick.estop_button.clicked.connect(self.ctl.emergency_stop)
        self.file_panel.browse_btn.clicked.connect(self._choose_file)
        self.file_panel.clear_btn.clicked.connect(self._clear_file)
        self.ctl.logMessage.connect(self.log.append)
        self.ctl.stateChanged.connect(self._refresh)

        # «Маршруты исправления» для чек-листа условий: клик по невыполненному
        # условию ведёт туда, где его можно устранить.
        self.conditions.r_init.set_fix_action(
            "выполнить →", self.ctl.initialize)
        self.conditions.r_laser.set_fix_action(
            "настроить →", lambda: self._goto("Сервисное управление", "Лазером"))
        self.conditions.r_acdc.set_fix_action(
            "показать →", lambda: self._goto("Узлы оборудования"))
        self.conditions.r_lid.set_fix_action(
            "показать →", lambda: self._goto("Узлы оборудования"))
        self.conditions.r_temp.set_fix_action(
            "параметры →",
            lambda: self._goto("Сервисное управление", "Параметры устройства"))
        self.conditions.r_prog.set_fix_action(
            "выбрать →", self._choose_file)

        self._refresh()

    # ------------------------------------------------------------------
    def _goto(self, top: str, inner: str = None) -> None:
        """Перейти на нужную вкладку (через главное окно), если оно доступно."""
        win = self.window()
        if hasattr(win, "navigate_to"):
            win.navigate_to(top, inner)

    # ------------------------------------------------------------------
    # Построение режимов (кочующие панели добавляются в слоты в _apply_mode)
    # ------------------------------------------------------------------
    def _build_idle_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.file_panel)
        lv.addWidget(self.conditions)
        self._idle_alarms_slot = QVBoxLayout()   # сюда переезжает self.alarms
        lv.addLayout(self._idle_alarms_slot)
        lv.addWidget(self.log, 1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self._idle_preview_slot = QVBoxLayout()  # сюда переезжает self.preview
        rv.addLayout(self._idle_preview_slot, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([480, 720])
        root.addWidget(splitter, 1)
        return page

    def _build_active_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)

        root.addWidget(self.progress)   # полоса хода процесса — только здесь

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self._active_preview_slot = QVBoxLayout()  # сюда переезжает self.preview
        lv.addLayout(self._active_preview_slot, 1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self._active_alarms_slot = QVBoxLayout()   # сюда переезжает self.alarms
        rv.addLayout(self._active_alarms_slot, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([760, 380])
        root.addWidget(splitter, 1)
        return page

    def _apply_mode(self, running: bool) -> None:
        """Перенести кочующие панели в нужный экран и переключить стек."""
        if running == self._running:
            return
        if running:
            # На экране обработки панель аварий — высокий «сайдбар»: список
            # заполняет всю колонку рядом с 3D-объектом (без пустот по центру).
            self.alarms.list.setMaximumHeight(16777215)
            self._active_preview_slot.addWidget(self.preview)
            self._active_alarms_slot.addWidget(self.alarms)
            self.stack.setCurrentIndex(1)
        else:
            # На экране подготовки панель компактная (под ней — журнал).
            self.alarms.list.setMaximumHeight(150)
            self._idle_preview_slot.addWidget(self.preview)
            self._idle_alarms_slot.addWidget(self.alarms)
            self.stack.setCurrentIndex(0)
        self._running = running

    # ------------------------------------------------------------------
    def _toggle_pause(self) -> None:
        if self._paused:
            self.ctl.resume_process()
        else:
            self.ctl.pause_process()

    def _confirm_stop(self) -> None:
        """Подтверждение управляемой остановки: она сбрасывает прогресс в 0,
        поэтому это потеря результата работы (HIG, гл. 3 «Alerts»). Аварийный
        стоп подтверждения не требует — там важнее мгновенность."""
        s = self.ctl.snapshot()
        if not s.get("process_running"):
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

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбор программы обработки", "", _ProcessFilePanel.FILTER)
        if not path:
            return
        self.file_panel.set_file(path)

        from ..hardware import toolpath as tp_mod
        if tp_mod.is_toolpath_file(path):
            self._load_toolpath(path)
        else:
            self.ctl.clear_toolpath()
            shown = self.preview.show_mesh(path)
            self.log.append("info", f"Выбрана 3D-модель детали: {path}")
            if shown:
                info = self.preview.viewer.mesh_info()
                self.log.append("info",
                                f"3D-модель загружена: {info['tris']} треугольников")

    def _load_toolpath(self, path: str) -> None:
        """Разобрать векторный контур, показать в 3D и отправить на станок."""
        from ..hardware import toolpath as tp_mod
        s = self.ctl.snapshot()
        m, tb = s["motor"], s["table"]
        x_range = (m["min"], m["max"])     # ход головки (X)
        y_range = (tb["min"], tb["max"])   # ход стола (Y)
        try:
            tp = tp_mod.load_toolpath(path)
            track, norm_segments, _ = tp_mod.fit_to_machine(tp, x_range, y_range)
        except Exception as exc:  # noqa: BLE001 — показать ошибку оператору
            self.preview.clear()
            self.ctl.clear_toolpath()
            self.log.append("err", f"Не удалось загрузить контур: {exc}")
            return
        size = f"{x_range[1] - x_range[0]}×{y_range[1] - y_range[0]}"
        self.preview.show_toolpath(norm_segments, tp.name, tp.vertex_count, size)
        self.ctl.load_toolpath(track)
        self.log.append(
            "info",
            f"Программа обработки [{tp.fmt}] загружена: "
            f"{len(norm_segments)} контур., {tp.vertex_count} точек")

    def _clear_file(self) -> None:
        if self.file_panel.current_file():
            self.file_panel.set_file("")
            self.preview.clear()
            self.ctl.clear_toolpath()
            self.log.append("info", "Программа обработки сброшена")

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        s = self.ctl.snapshot()
        on = lambda b: "ok" if b else "off"
        proc = s.get("process", {})
        running = bool(proc.get("running", s["process_running"]))
        self._paused = bool(proc.get("paused", False))

        # переключение экрана подготовка/обработка
        self._apply_mode(running)

        # полоса хода процесса
        import os
        f = self.file_panel.current_file()
        self.progress.update_state(proc, os.path.basename(f) if f else "")

        # анимация головки над контуром: положение берём из снимка
        # (X — головка, Y — стол), нормируем по ходу осей
        m, tb = s["motor"], s["table"]
        mspan = max(1, m["max"] - m["min"])
        tspan = max(1, tb["max"] - tb["min"])
        self.preview.update_head((m["x"] - m["min"]) / mspan,
                                 (tb["pos"] - tb["min"]) / tspan, True)

        # условия запуска
        self.conditions.r_acdc.set_state(on(s["acdc"]["on"]),
                                         "есть" if s["acdc"]["on"] else "нет")
        self.conditions.r_init.set_state(on(s["initialized"]),
                                         "выполнена" if s["initialized"] else "нет")
        self.conditions.r_lid.set_state("ok" if s["lid"]["closed"] else "err",
                                        "закрыта" if s["lid"]["closed"] else "открыта")
        self.conditions.r_laser.set_state("ok" if s["laser"]["ready"] else "warn",
                                          "готов" if s["laser"]["ready"] else "не настроен")
        self.conditions.r_temp.set_state("err" if s["temp"]["over"] else "ok",
                                         "перегрев" if s["temp"]["over"] else "норма")
        tp_loaded = s.get("toolpath", {}).get("loaded", False)
        self.conditions.r_prog.set_state(
            "ok" if tp_loaded else "warn",
            "загружена" if tp_loaded else "нет")

        # быстрые действия + аварии
        can_start, reason = process_readiness(s)
        self.quick.set_enabled_states(
            can_start=can_start,
            can_stop=running,
            can_pause=running,
            paused=self._paused,
            initialized=s["initialized"],
            running=running,
            start_reason=reason)
        self.alarms.set_alarms(self.ctl.alarms())

        # выбор файла блокируется на время процесса
        self.file_panel.browse_btn.setEnabled(not running)
        self.file_panel.clear_btn.setEnabled(not running)
