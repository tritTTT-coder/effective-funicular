"""
utils.py — Утилиты без зависимостей от UI или аудио.

Содержит:
  - app_dir()           — путь к папке приложения (.exe или .py)
  - sanitize_filename() — очистка строки для безопасного имени файла
  - playlist_initials() — инициалы для карточки плейлиста
"""

import os
import re
import sys

# [ANCHOR: filename_validation] Запрещённые символы Windows в именах файлов/плейлистов.
INVALID_FILENAME_CHARS: str = '<>:"/\\|?*'
_WINDOWS_RESERVED: set[str] = {
    "CON", "PRN", "AUX", "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}


def app_dir() -> str:
    """Папка приложения: рядом с .exe (сборка) или рядом с .py (разработка)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def sanitize_filename(name: str) -> str:
    """Очистка строки для безопасного имени файла или папки.

    Заменяет запрещённые символы и управляющие коды на '_',
    схлопывает пробелы, убирает финальные точки,
    добавляет '_' к зарезервированным именам Windows.
    """
    cleaned: list[str] = []
    for ch in name:
        if ch in INVALID_FILENAME_CHARS or ord(ch) < 32:
            cleaned.append("_")
        else:
            cleaned.append(ch)

    result = re.sub(r"\s+", " ", "".join(cleaned)).strip().strip(".")
    if result.upper() in _WINDOWS_RESERVED:
        result = f"_{result}"
    return result


def playlist_initials(name: str) -> str:
    """Инициалы для карточки плейлиста (первые буквы каждого слова, через точку).

    Примеры:
        "dark age"   -> "D.A"
        "темный век" -> "Т.В"
        ""           -> "?"
    """
    words = re.split(r"\s+", name.strip())
    letters = [word[0].upper() for word in words if word]
    return ".".join(letters) if letters else "?"
