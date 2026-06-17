#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Запуск интерфейса «Управление лазерно-эрозионным роботом».

КАК ЗАПУСКАТЬ (Windows, терминал):
    1) Один раз установить зависимости:
           pip install PyQt5
    2) Перейти в папку, где лежит ЭТОТ файл (рядом должна быть папка edm_app):
           cd C:\путь\к\папке
    3) Запустить:
           python main.py

ВАЖНО: файл main.py должен лежать РЯДОМ с папкой edm_app, например:
    моя_папка\
        main.py          <- запускаем это
        edm_app\         <- папка целиком
"""

import os
import sys


def _fail(message: str) -> None:
    """Показать понятную ошибку и завершиться (без «тихого» падения)."""
    print("=" * 60)
    print("ОШИБКА ЗАПУСКА")
    print("=" * 60)
    print(message)
    print("=" * 60)
    # Пауза, чтобы окно терминала не закрылось мгновенно при двойном клике.
    try:
        input("Нажмите Enter для выхода...")
    except EOFError:
        pass
    sys.exit(1)


def main() -> int:
    # 1. Проверяем, что рядом действительно лежит пакет edm_app.
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(os.path.join(here, "edm_app")):
        _fail(
            "Рядом с main.py не найдена папка 'edm_app'.\n\n"
            "Убедитесь, что папка edm_app лежит в той же папке, что и main.py,\n"
            "и что вы запускаете терминал из этой папки.\n\n"
            f"Сейчас main.py находится здесь:\n  {here}\n"
            f"Содержимое этой папки:\n  {os.listdir(here)}"
        )
    # Гарантируем, что Python найдёт пакет, даже если терминал открыт не здесь.
    if here not in sys.path:
        sys.path.insert(0, here)

    # 2. Проверяем зависимости с понятными подсказками.
    try:
        import PyQt5  # noqa: F401
    except ImportError:
        _fail("Не установлен PyQt5.\nВыполните:  pip install PyQt5")

    # 3. Запускаем приложение.
    from edm_app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
