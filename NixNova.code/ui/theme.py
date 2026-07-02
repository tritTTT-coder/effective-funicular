"""
ui/theme.py — Единый источник цветовой палитры и типографики.

Использование:
    from ui.theme import Theme
    t = Theme()
    widget.configure(bg=t.bg, fg=t.fg)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Минималистичная тёмная палитра плеера.

    frozen=True гарантирует, что цвета не будут случайно изменены
    в runtime — вся тема задаётся один раз при создании экземпляра.
    """

    # ---- Базовые цвета -------------------------------------------------------
    bg: str = "#0f1115"
    fg: str = "#e6e6e6"
    muted: str = "#a9a9a9"

    # ---- Кнопки (плоские, текстовые) ----------------------------------------
    btn_bg: str = "#1a1f2a"
    btn_bg_active: str = "#242b3a"

    # ---- Карточки плейлистов -------------------------------------------------
    card_bg: str = "#151a24"
    card_hover: str = "#1c2433"

    # ---- Ползунок перемотки --------------------------------------------------
    seek_trough: str = "#3a4a66"
    seek_thumb_active: str = "#a8d0ff"

    # ---- Иконки-кнопки (транспорт) ------------------------------------------
    icon_bg: str = "#1f2d45"
    icon_bg_active: str = "#2f4570"
    icon_accent_bg: str = "#2d4a7a"       # кнопка Play (акцент)
    icon_accent_active: str = "#3d63a0"

    # ---- Shuffle (включён / выключен) ----------------------------------------
    shuffle_on_bg: str = "#3d5f40"
    shuffle_on_active: str = "#4d7a52"

    # ---- Мультивыбор (checked строка) ----------------------------------------
    check_bg: str = "#3d5270"

    # ---- Список треков -------------------------------------------------------
    list_bg: str = "#0b0d12"             # фон канваса + строк
    row_selected: str = "#2a3447"        # активная/выделенная строка

    # ---- Тултип --------------------------------------------------------------
    tooltip_bg: str = "#2a3447"

    # ---- Шрифты --------------------------------------------------------------
    font_ui: tuple[str, int] = ("Segoe UI", 10)
    font_ui_small: tuple[str, int] = ("Segoe UI", 9)
    font_ui_bold: tuple[str, int, str] = ("Segoe UI", 10, "bold")
    font_icon: tuple[str, int] = ("Segoe UI Symbol", 17)
    font_list: tuple[str, int] = ("Segoe UI", 10)
    font_playlist_name: tuple[str, int] = ("Segoe UI", 8)
    font_playlist_initials: tuple[str, int, str] = ("Segoe UI", 14, "bold")

    # ---- Размеры карточки плейлиста -----------------------------------------
    playlist_card_size: int = 96


# Глобальный синглтон — используется во всём UI.
# Если понадобится светлая тема, достаточно заменить этот объект.
THEME = Theme()
