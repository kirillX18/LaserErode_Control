import os
import sys


def _fail(message: str) -> None:
    print("=" * 60)
    print("ОШИБКА ЗАПУСКА")
    print("=" * 60)
    print(message)
    print("=" * 60)
    try:
        input("Нажмите Enter для выхода...")
    except EOFError:
        pass
    sys.exit(1)


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(os.path.join(here, "edm_app")):
        _fail(
            "Рядом с main.py не найдена папка 'edm_app'.\n\n"
            "Убедитесь, что папка edm_app лежит в той же папке, что и main.py,\n"
            "и что вы запускаете терминал из этой папки.\n\n"
            f"Сейчас main.py находится здесь:\n  {here}\n"
            f"Содержимое этой папки:\n  {os.listdir(here)}"
        )

    if here not in sys.path:
        sys.path.insert(0, here)

    try:
        import PyQt5  
    except ImportError:
        _fail("Не установлен PyQt5.\nВыполните:  pip install PyQt5")

    from edm_app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
