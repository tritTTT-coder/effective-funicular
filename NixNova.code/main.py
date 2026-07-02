"""
main.py — Точка входа My Music Player.

Порядок инициализации:
    1. pygame (AudioEngine.init_pygame)
    2. PlaylistManager — пути к my_music/ и playlists/
    3. AudioEngine     — колбэки подключаются к MainWindow
    4. MainWindow      — получает engine + manager через DI
    5. mainloop()
"""

import sys
from tkinter import messagebox

from core.audio_engine import AudioEngine
from core.playlist_manager import PlaylistManager
from ui.main_window import MainWindow
from ui.theme import THEME
from utils import app_dir
import os


def main() -> None:
    # 1. Инициализируем pygame до создания любых окон tkinter.
    try:
        AudioEngine.init_pygame()
    except RuntimeError as exc:
        # Если аудио недоступно — показываем ошибку и выходим.
        # messagebox требует хотя бы корневого окна tkinter.
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Audio init error", str(exc))
        root.destroy()
        sys.exit(1)

    # 2. Пути к хранилищу.
    base = app_dir()
    music_dir = os.path.join(base, "my_music")
    playlists_dir = os.path.join(base, "playlists")

    # 3. PlaylistManager — чистый слой данных, без зависимостей.
    manager = PlaylistManager(music_dir=music_dir, playlists_dir=playlists_dir)

    # 4. AudioEngine с заглушками для колбэков (заменятся после создания окна).
    #    Используем список как изменяемую ячейку для forward-reference на window.
    _window_ref: list[MainWindow] = []

    def on_track_finished() -> None:
        if _window_ref:
            _window_ref[0]._on_track_finished()

    def on_position_changed(pos_s: float) -> None:
        if _window_ref:
            _window_ref[0]._on_position_changed(pos_s)

    engine = AudioEngine(
        on_track_finished=on_track_finished,
        on_position_changed=on_position_changed,
    )

    # 5. Главное окно — получает зависимости через конструктор.
    window = MainWindow(engine=engine, manager=manager, theme=THEME)
    _window_ref.append(window)

    window.mainloop()


if __name__ == "__main__":
    main()
