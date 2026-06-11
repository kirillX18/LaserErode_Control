from typing import Callable, Iterable

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel

from .buttons import SmallButton, RedButton


class StepRow(QWidget):
    """Одна строка шага: подпись, кнопка «минус» и кнопка «плюс».

    label_first=True  -> формат [подпись][−][+]  (как у суставов/лазера)
    label_first=False -> формат [−val][+val]      (как у осей XYZ)
    """

    def __init__(self, label: str, step: float,
                 on_step: Callable[[float], None],
                 minus_text: str = "−", plus_text: str = "+",
                 minus_red: bool = True, label_first: bool = True,
                 parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)

        if label_first:
            lbl = QLabel(label)
            lbl.setMinimumWidth(34)
            h.addWidget(lbl)

        minus = RedButton(minus_text) if minus_red else SmallButton(minus_text)
        plus = SmallButton(plus_text)
        minus.clicked.connect(lambda: on_step(-step))
        plus.clicked.connect(lambda: on_step(step))
        h.addWidget(minus)
        h.addWidget(plus)

        if not label_first:
            h.addStretch()


class StepControl(QWidget):
    """Группа строк шага. Принимает список величин шага и общий колбэк."""

    def __init__(self, steps: Iterable[float],
                 on_step: Callable[[float], None],
                 label_fmt: str = "{:g}", label_first: bool = True,
                 minus_red: bool = True, signed_labels: bool = False,
                 parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        for step in steps:
            if label_first:
                label = label_fmt.format(step)
                minus_text, plus_text = "−", "+"
            else:
                # формат осей XYZ: текст самой кнопки несёт величину (-1.0/+1.0)
                label = ""
                minus_text = f"-{step:g}"
                plus_text = f"+{step:g}"
            v.addWidget(StepRow(
                label, step, on_step,
                minus_text=minus_text, plus_text=plus_text,
                minus_red=minus_red, label_first=label_first))
