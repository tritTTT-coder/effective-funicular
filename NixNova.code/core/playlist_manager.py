"""
core/playlist_manager.py — Менеджер библиотеки треков и плейлистов.

Правила:
  - Никакого импорта tkinter или pygame здесь.
  - Вся работа с диском (JSON, файловая система) — только здесь.
  - UI получает данные через возвращаемые значения методов.

Публичный API:
    pm = PlaylistManager(music_dir, playlists_dir)

    # Библиотека
    pm.all_library_tracks()                  -> list[str]
    pm.tracks_for_view(view_mode)            -> list[str]
    pm.import_files(src_paths)               -> tuple[int, int]  (copied, skipped)
    pm.rename_track(old_name, new_name)      -> bool

    # Плейлисты
    pm.load_playlists()                      -> list[dict]
    pm.create_playlist(name)                 -> str   (playlist_id)
    pm.delete_playlist(playlist_id)          -> bool
    pm.add_track_to_playlist(pid, name)      -> bool
    pm.remove_track_from_playlist(pid, name) -> bool
    pm.remove_tracks_from_playlist(pid, names) -> int  (removed count)
    pm.remove_track_from_all_playlists(name) -> None
    pm.add_tracks_to_playlist(pid, names)    -> tuple[int, int]  (added, skipped)

    # Мета
    pm.load_playlist_meta(playlist_id)       -> dict | None
    pm.playlist_name(playlist_id)            -> str
"""

import json
import os
import shutil
import uuid

from utils import sanitize_filename

META_FILENAME = "meta.json"


class PlaylistManager:
    """Управляет треками в my_music/ и плейлистами в playlists/.

    Зависимостей на UI и pygame нет — только stdlib.
    """

    def __init__(self, music_dir: str, playlists_dir: str) -> None:
        self.music_dir: str = music_dir
        self.playlists_dir: str = playlists_dir

        os.makedirs(self.music_dir, exist_ok=True)
        os.makedirs(self.playlists_dir, exist_ok=True)

        # Кэш плейлистов — обновляется через load_playlists().
        self._playlists: list[dict] = []

    # =========================================================================
    # Библиотека треков
    # =========================================================================

    def all_library_tracks(self) -> list[str]:
        """Возвращает список всех .mp3 в my_music/ (отсортированный)."""
        try:
            names = [
                f
                for f in os.listdir(self.music_dir)
                if os.path.isfile(os.path.join(self.music_dir, f))
                and f.lower().endswith(".mp3")
            ]
        except FileNotFoundError:
            os.makedirs(self.music_dir, exist_ok=True)
            names = []
        names.sort(key=str.lower)
        return names

    def tracks_for_view(self, view_mode: str) -> list[str]:
        """Треки для текущего экрана: вся библиотека или выбранный плейлист.

        Args:
            view_mode: "library" или playlist_id.
        """
        if view_mode == "library":
            return self.all_library_tracks()

        meta = self.load_playlist_meta(view_mode)
        if not meta:
            return self.all_library_tracks()

        library = set(self.all_library_tracks())
        return [name for name in meta.get("tracks", []) if name in library]

    def track_path(self, track_name: str) -> str:
        """Полный путь к треку в my_music/."""
        return os.path.join(self.music_dir, track_name)

    def import_files(self, src_paths: tuple[str, ...] | list[str]) -> tuple[int, int]:
        """Копирует mp3-файлы в my_music/.

        Returns:
            (copied, skipped) — количество скопированных и пропущенных файлов.
        """
        copied = skipped = 0
        for src in src_paths:
            try:
                base = os.path.basename(src)
                dst = os.path.join(self.music_dir, base)
                if os.path.exists(dst):
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
            except Exception:
                continue
        return copied, skipped

    def rename_track(self, old_name: str, new_base: str) -> tuple[bool, str]:
        """Переименовывает mp3 в my_music/ и обновляет ссылки в плейлистах.

        Args:
            old_name:  текущее имя файла (с расширением).
            new_base:  новое имя без расширения (ещё не санированное).

        Returns:
            (success, new_name_or_error_message)
        """
        old_path = self.track_path(old_name)
        if not os.path.exists(old_path):
            return False, "Файл не найден."

        raw_base = new_base.strip().strip(".")
        clean_base = sanitize_filename(raw_base)
        if not clean_base:
            return False, "Имя пустое или содержит только недопустимые символы."

        new_name = f"{clean_base}.mp3"
        new_path = self.track_path(new_name)
        if os.path.exists(new_path) and os.path.normcase(new_path) != os.path.normcase(old_path):
            return False, "Файл с таким именем уже существует."

        try:
            os.rename(old_path, new_path)
        except Exception as exc:
            return False, str(exc)

        self._rename_track_in_playlists(old_name, new_name)
        self.load_playlists()
        return True, new_name

    # =========================================================================
    # Плейлисты — хранилище
    # =========================================================================

    def load_playlists(self) -> list[dict]:
        """Сканирует playlists/ и обновляет внутренний кэш.

        Returns:
            Список словарей: [{"id": str, "name": str, "tracks": list[str]}, ...]
        """
        playlists: list[dict] = []
        if not os.path.isdir(self.playlists_dir):
            self._playlists = playlists
            return playlists

        for entry in os.listdir(self.playlists_dir):
            folder = os.path.join(self.playlists_dir, entry)
            if not os.path.isdir(folder):
                continue
            meta = self.load_playlist_meta(entry)
            if meta is None:
                continue
            playlists.append(
                {
                    "id": entry,
                    "name": meta.get("name", entry),
                    "tracks": list(meta.get("tracks", [])),
                }
            )

        playlists.sort(key=lambda p: p["name"].lower())
        self._playlists = playlists
        return playlists

    @property
    def playlists(self) -> list[dict]:
        """Текущий кэш плейлистов (без чтения с диска)."""
        return self._playlists

    def load_playlist_meta(self, playlist_id: str) -> dict | None:
        """Читает meta.json плейлиста с диска.

        Returns:
            Словарь {"name": str, "tracks": list[str]} или None при ошибке.
        """
        path = self._meta_path(playlist_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("tracks", [])
            data.setdefault("name", playlist_id)
            return data
        except (OSError, json.JSONDecodeError):
            return None

    def playlist_name(self, playlist_id: str) -> str:
        """Возвращает имя плейлиста по его id (из кэша)."""
        for pl in self._playlists:
            if pl["id"] == playlist_id:
                return pl["name"]
        meta = self.load_playlist_meta(playlist_id)
        return meta.get("name", playlist_id) if meta else playlist_id

    # =========================================================================
    # Плейлисты — CRUD
    # =========================================================================

    def create_playlist(self, raw_name: str) -> tuple[bool, str]:
        """Создаёт новый плейлист с уникальным id.

        Args:
            raw_name: пользовательский ввод (будет санирован).

        Returns:
            (success, playlist_id_or_error_message)
        """
        clean_name = sanitize_filename(raw_name.strip())
        if not clean_name:
            return False, "Введите корректное название."

        playlist_id = f"{clean_name}_{uuid.uuid4().hex[:8]}"
        os.makedirs(self._folder_path(playlist_id), exist_ok=True)
        self._save_meta(playlist_id, {"name": clean_name, "tracks": []})
        self.load_playlists()
        return True, playlist_id

    def delete_playlist(self, playlist_id: str) -> tuple[bool, str]:
        """Удаляет папку плейлиста с диска.

        Returns:
            (success, error_message_or_empty)
        """
        folder = self._folder_path(playlist_id)
        try:
            shutil.rmtree(folder)
        except Exception as exc:
            return False, str(exc)
        self.load_playlists()
        return True, ""

    def add_track_to_playlist(self, playlist_id: str, track_name: str) -> bool:
        """Добавляет ссылку на трек в плейлист (без копирования файла).

        Returns:
            True — добавлено, False — уже есть или ошибка.
        """
        if not os.path.isfile(self.track_path(track_name)):
            return False

        meta = self.load_playlist_meta(playlist_id)
        if meta is None:
            return False

        tracks: list[str] = meta.setdefault("tracks", [])
        if track_name in tracks:
            return False

        tracks.append(track_name)
        self._save_meta(playlist_id, meta)
        self.load_playlists()
        return True

    def add_tracks_to_playlist(
        self, playlist_id: str, track_names: list[str]
    ) -> tuple[int, int]:
        """Пакетное добавление треков в плейлист.

        Returns:
            (added, skipped)
        """
        added = skipped = 0
        for name in track_names:
            if self.add_track_to_playlist(playlist_id, name):
                added += 1
            else:
                skipped += 1
        return added, skipped

    def remove_track_from_playlist(self, playlist_id: str, track_name: str) -> bool:
        """Убирает ссылку на трек из плейлиста (файл в my_music не удаляется).

        Returns:
            True если трек был найден и убран.
        """
        meta = self.load_playlist_meta(playlist_id)
        if meta is None:
            return False

        tracks: list[str] = meta.get("tracks", [])
        if track_name not in tracks:
            return False

        tracks.remove(track_name)
        meta["tracks"] = tracks
        self._save_meta(playlist_id, meta)
        self.load_playlists()
        return True

    def remove_tracks_from_playlist(
        self, playlist_id: str, track_names: list[str]
    ) -> int:
        """Пакетное удаление треков из плейлиста.

        Returns:
            Количество удалённых ссылок.
        """
        meta = self.load_playlist_meta(playlist_id)
        if meta is None:
            return 0

        tracks: list[str] = meta.get("tracks", [])
        removed = 0
        for name in track_names:
            if name in tracks:
                tracks.remove(name)
                removed += 1

        meta["tracks"] = tracks
        self._save_meta(playlist_id, meta)
        self.load_playlists()
        return removed

    def remove_track_from_all_playlists(self, track_name: str) -> None:
        """Убирает ссылку на трек из всех плейлистов (при удалении файла)."""
        for playlist in self._playlists:
            if track_name not in playlist["tracks"]:
                continue
            playlist["tracks"].remove(track_name)
            meta = self.load_playlist_meta(playlist["id"])
            if meta:
                meta["tracks"] = playlist["tracks"]
                self._save_meta(playlist["id"], meta)

    # =========================================================================
    # Приватные методы
    # =========================================================================

    def _folder_path(self, playlist_id: str) -> str:
        return os.path.join(self.playlists_dir, playlist_id)

    def _meta_path(self, playlist_id: str) -> str:
        return os.path.join(self._folder_path(playlist_id), META_FILENAME)

    def _save_meta(self, playlist_id: str, meta: dict) -> None:
        folder = self._folder_path(playlist_id)
        os.makedirs(folder, exist_ok=True)
        with open(self._meta_path(playlist_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _rename_track_in_playlists(self, old_name: str, new_name: str) -> None:
        """После переименования mp3 обновляет ссылки во всех плейлистах."""
        for playlist in self._playlists:
            tracks: list[str] = playlist["tracks"]
            if old_name not in tracks:
                continue
            updated = [new_name if t == old_name else t for t in tracks]
            playlist["tracks"] = updated
            meta = self.load_playlist_meta(playlist["id"])
            if meta:
                meta["tracks"] = updated
                self._save_meta(playlist["id"], meta)
