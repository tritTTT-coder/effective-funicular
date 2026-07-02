"""
core/audio_engine.py — Чистый слой воспроизведения на базе pygame.mixer.

Правила:
  - Никакого импорта tkinter здесь.
  - UI уведомляется только через колбэки (on_track_finished, on_position_changed).
  - Всё состояние воспроизведения инкапсулировано внутри AudioEngine.

Публичный API:
    engine = AudioEngine(on_track_finished=..., on_position_changed=...)
    engine.play(path)
    engine.play_pause()
    engine.stop()
    engine.seek(seconds)
    engine.tick()           — вызывается из UI-цикла (after 200 мс)
    engine.shutdown()       — вызвать перед закрытием окна
"""

import os
from collections.abc import Callable

import pygame


class AudioEngine:
    """Управляет воспроизведением mp3 через pygame.mixer.

    Параметры колбэков:
        on_track_finished()             — трек завершился естественно
        on_position_changed(pos_s: float) — обновлённая позиция (каждые ~200 мс)
    """

    def __init__(
        self,
        on_track_finished: Callable[[], None],
        on_position_changed: Callable[[float], None],
    ) -> None:
        self._on_track_finished = on_track_finished
        self._on_position_changed = on_position_changed

        # Событие pygame, которое pygame.mixer генерирует по окончании трека.
        self._end_event: int = pygame.USEREVENT + 1

        # ---- Публично читаемое состояние ------------------------------------
        self.current_file: str | None = None
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.track_length_s: float = 0.0

        # ---- Внутреннее состояние -------------------------------------------
        self._start_offset_s: float = 0.0   # смещение при последнем play(start=)
        self._seeking: bool = False          # True пока пользователь тянет слайдер

        # ---- Громкость (0–100, независимо от системной) ---------------------
        # pygame.mixer.music.set_volume() принимает 0.0–1.0
        self._volume: int = 80              # начальный уровень 80%
        pygame.mixer.music.set_volume(self._volume / 100.0)

    # -------------------------------------------------------------------------
    # Инициализация / завершение
    # -------------------------------------------------------------------------
    @staticmethod
    def init_pygame() -> None:
        """Инициализирует pygame и pygame.mixer.

        Вызывается единожды из main.py до создания AudioEngine.
        Выбрасывает RuntimeError если аудиоустройство недоступно.
        """
        pygame.init()
        try:
            pygame.mixer.init()
        except Exception as exc:
            raise RuntimeError(
                "Не удалось инициализировать аудио.\n"
                "Проверьте аудиоустройство/драйвер.\n\n"
                f"Детали: {exc}"
            ) from exc

    def shutdown(self) -> None:
        """Корректно останавливает воспроизведение и освобождает pygame."""
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            pygame.quit()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Основной публичный API
    # -------------------------------------------------------------------------
    def play(self, path: str) -> bool:
        """Загружает и воспроизводит файл с начала.

        Возвращает True при успехе, False если файл не найден или ошибка.
        """
        if not os.path.exists(path):
            return False
        self.release()
        self.track_length_s = self._probe_length(path)
        return self._load_at(path, position=0.0, paused=False)

    def play_pause(self) -> None:
        """Переключает паузу/воспроизведение текущего трека."""
        if not self.is_playing:
            return
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
        else:
            pygame.mixer.music.pause()
            self.is_paused = True

    def stop(self) -> None:
        """Останавливает воспроизведение и сбрасывает позицию."""
        self.release()
        self._start_offset_s = 0.0

    def seek(self, seconds: float) -> bool:
        """Перематывает текущий трек на указанную позицию.

        Возвращает True при успехе.
        """
        if not self.current_file or not os.path.exists(self.current_file):
            return False
        seconds = max(0.0, float(seconds))
        if self.track_length_s > 0:
            seconds = min(seconds, self.track_length_s)
        was_paused = self.is_paused
        return self._load_at(self.current_file, seconds, paused=was_paused)

    def release(self) -> None:
        """Останавливает микшер и сбрасывает флаги (файл не очищается)."""
        try:
            pygame.mixer.music.set_endevent(0)
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
        except Exception:
            pass
        self.is_playing = False
        self.is_paused = False

    # -------------------------------------------------------------------------
    # Слайдер: сигнализируем движку что пользователь тянет ползунок
    # -------------------------------------------------------------------------
    def begin_seek(self) -> None:
        """Вызывается при нажатии на слайдер перемотки (ButtonPress)."""
        self._seeking = True

    def end_seek(self, target_seconds: float) -> bool:
        """Вызывается при отпускании слайдера (ButtonRelease)."""
        self._seeking = False
        return self.seek(target_seconds)

    # -------------------------------------------------------------------------
    # Громкость — независима от системного микшера ОС
    # -------------------------------------------------------------------------
    def set_volume(self, level: int) -> None:
        """Устанавливает внутреннюю громкость плеера.

        Args:
            level: целое от 0 до 100.
                   0   — полная тишина.
                   100 — максимальная громкость движка.
        """
        self._volume = max(0, min(100, int(level)))
        # pygame принимает float 0.0–1.0; деление изолирует нас от системной громкости
        pygame.mixer.music.set_volume(self._volume / 100.0)

    def get_volume(self) -> int:
        """Возвращает текущий уровень громкости (0–100)."""
        return self._volume

    # -------------------------------------------------------------------------
    # Игровой цикл — вызывается из after() главного окна
    # -------------------------------------------------------------------------
    def tick(self) -> None:
        """Обрабатывает события pygame и обновляет позицию.

        Должен вызываться регулярно (~200 мс) из UI-цикла tkinter.
        """
        for event in pygame.event.get():
            if event.type == self._end_event:
                self._on_track_finished()

        if self.is_playing and not self.is_paused:
            pos = self.current_position_s()
            if not self._seeking:
                self._on_position_changed(pos)

    # -------------------------------------------------------------------------
    # Вспомогательные запросы состояния
    # -------------------------------------------------------------------------
    def current_position_s(self) -> float:
        """Текущая позиция воспроизведения в секундах."""
        if not self.is_playing:
            return 0.0
        ms = pygame.mixer.music.get_pos()
        if ms < 0:
            return 0.0
        return self._start_offset_s + (ms / 1000.0)

    @staticmethod
    def format_time(seconds: float) -> str:
        """Форматирует секунды в строку MM:SS."""
        seconds = max(0, int(seconds))
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    # -------------------------------------------------------------------------
    # Приватные методы
    # -------------------------------------------------------------------------
    def _probe_length(self, path: str) -> float:
        """Возвращает длину аудиофайла в секундах через pygame.mixer.Sound."""
        try:
            snd = pygame.mixer.Sound(path)
            return float(snd.get_length())
        except Exception:
            return 0.0

    def _load_at(self, path: str, position: float, *, paused: bool) -> bool:
        """Загружает файл и начинает воспроизведение с позиции position.

        Внутренний метод — вся обработка ошибок pygame централизована здесь.
        Возвращает True при успехе.
        """
        position = max(0.0, float(position))
        if self.track_length_s > 0:
            position = min(position, self.track_length_s)

        try:
            pygame.mixer.music.load(path)
            try:
                pygame.mixer.music.play(start=position)
            except Exception:
                pygame.mixer.music.play()
                try:
                    pygame.mixer.music.set_pos(position)
                except Exception:
                    position = 0.0

            if paused:
                pygame.mixer.music.pause()

            pygame.mixer.music.set_endevent(self._end_event)
        except Exception as exc:
            # Пробрасываем наружу — UI решает как показать ошибку.
            raise RuntimeError(f"Не удалось загрузить файл.\n\n{exc}") from exc

        self.current_file = path
        self.is_playing = True
        self.is_paused = paused
        self._start_offset_s = position
        return True
