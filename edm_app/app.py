"""
app.py — точка входа: создаёт QApplication, применяет тему и показывает окно.
"""

import sys

from PyQt5.QtWidgets import QApplication

from . import theme
from .window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.STYLESHEET)
    app.setFont(theme.default_font())
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(run())
