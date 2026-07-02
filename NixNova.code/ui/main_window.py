"""
ui/main_window.py — Главное окно NixNova на CustomTkinter.

Визуальный стек: customtkinter (CTk) поверх tkinter.
Логика воспроизведения, плейлистов и поиска — без изменений.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

from core.audio_engine import AudioEngine
from core.playlist_manager import PlaylistManager
from ui.theme import Theme
from utils import playlist_initials

# ---------------------------------------------------------------------------
# Глобальная настройка CTk — тёмный режим, без системной темы
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ---------------------------------------------------------------------------
# Цвета (дублируем константами чтобы удобно передавать в CTk-параметры)
# ---------------------------------------------------------------------------
C_BG         = "#0f1115"   # фон окна
C_SIDEBAR    = "#0f1115"   # фон sidebar
C_LIST_BG    = "#0b0d12"   # фон списка треков
C_BTN        = "#1a1f2a"   # обычная кнопка
C_BTN_H      = "#242b3a"   # hover обычной кнопки
C_ACCENT     = "#2d4a7a"   # акцентная кнопка (play, активный плейлист)
C_ACCENT_H   = "#3d63a0"   # hover акцента
C_SHUFFLE_ON = "#3d5f40"
C_SHUFFLE_H  = "#4d7a52"
C_TROUGH     = "#3a4a66"   # желоб слайдера
C_THUMB      = "#a8d0ff"   # активный бегунок
C_ROW_SEL    = "#2a3447"   # выделенная строка
C_ROW_HOVER  = "#1c2433"
C_CHECK      = "#3d5270"
C_MUTED      = "#a9a9a9"
C_FG         = "#e6e6e6"
C_SEARCH_BG  = "#141820"
C_TOOLTIP    = "#2a3447"
C_ICON_BG    = "#1f2d45"
C_ICON_H     = "#2f4570"

FONT_SMALL   = ("Segoe UI", 10)
FONT_NORM    = ("Segoe UI", 11)
FONT_BOLD    = ("Segoe UI", 11, "bold")
FONT_ICON    = ("Segoe UI Symbol", 16)
FONT_ICON_SM = ("Segoe UI Symbol", 12)
FONT_LIST    = ("Segoe UI", 11)


# ---------------------------------------------------------------------------
# Фабрики CTk-виджетов
# ---------------------------------------------------------------------------

def _cbtn(parent, text, cmd, *,
          fg_color=C_BTN, hover_color=C_BTN_H,
          text_color=C_FG, font=FONT_SMALL,
          corner_radius=8, width=0, height=32,
          anchor="center") -> ctk.CTkButton:
    """Универсальная CTkButton."""
    kw = dict(
        text=text, command=cmd,
        fg_color=fg_color, hover_color=hover_color,
        text_color=text_color,
        font=font, corner_radius=corner_radius,
        height=height, border_width=0,
        anchor=anchor,
    )
    if width:
        kw["width"] = width
    return ctk.CTkButton(parent, **kw)


def _icon_cbtn(parent, text, cmd, *,
               accent=False, width=52, height=40) -> ctk.CTkButton:
    """Кнопка-иконка транспортной панели."""
    fg  = C_ACCENT  if accent else C_ICON_BG
    hov = C_ACCENT_H if accent else C_ICON_H
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg, hover_color=hov,
        text_color="#ffffff",
        font=FONT_ICON,
        corner_radius=10,
        width=width, height=height,
        border_width=0,
    )


def _clabel(parent, text="", *, text_color=C_FG, font=FONT_SMALL,
            bg_color="transparent", anchor="w", wraplength=0) -> ctk.CTkLabel:
    kw = dict(text=text, text_color=text_color, font=font,
              bg_color=bg_color, anchor=anchor)
    if wraplength:
        kw["wraplength"] = wraplength
    return ctk.CTkLabel(parent, **kw)


def _tooltip_tk(widget, text_or_fn, store: dict) -> None:
    """Тултип через обычный tk.Toplevel (CTk не имеет встроенного)."""
    tip = tk.Toplevel(widget)
    tip.withdraw()
    tip.overrideredirect(True)
    tip.configure(bg=C_TOOLTIP)
    lbl = tk.Label(tip, text="", bg=C_TOOLTIP, fg=C_FG,
                   font=FONT_SMALL, padx=8, pady=4)
    lbl.pack()
    store[widget] = tip

    def show(_e=None):
        lbl.configure(text=text_or_fn() if callable(text_or_fn) else text_or_fn)
        tip.update_idletasks()
        x = widget.winfo_rootx() + (widget.winfo_width() - tip.winfo_reqwidth()) // 2
        y = widget.winfo_rooty() - tip.winfo_reqheight() - 6
        tip.geometry(f"+{max(0,x)}+{max(0,y)}")
        tip.deiconify()
        tip.lift()

    def hide(_e=None):
        tip.withdraw()

    widget.bind("<Enter>", show, add=True)
    widget.bind("<Leave>", hide, add=True)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------

class MainWindow(ctk.CTk):
    """Главное окно NixNova на CustomTkinter."""

    def __init__(self, engine: AudioEngine,
                 manager: PlaylistManager, theme: Theme) -> None:
        super().__init__()
        self._engine  = engine
        self._manager = manager
        self._t       = theme

        # ---- окно -----------------------------------------------------------
        self.title("NixNova")
        self.geometry("860x580")
        self.minsize(520, 400)
        self.resizable(True, True)
        self.configure(fg_color=C_BG)
        self._is_fullscreen = False
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Escape>", self._exit_fullscreen)

        # ---- состояние воспроизведения --------------------------------------
        self._tracks:         list[str]  = []
        self._all_tracks:     list[str]  = []
        self._selected_index: int | None = None
        self._checked_names:  set[str]   = set()
        self._track_rows:     list[tuple] = []   # (frame_tk, label_ctk)
        self._tooltips:       dict        = {}
        self.shuffle_enabled  = False
        self._shuffle_order:  list[int]  = []
        self._view_mode       = "library"

        # ---- громкость ------------------------------------------------------
        self._volume_var = tk.IntVar(value=engine.get_volume())
        self._vol_drag   = False

        # ---- поиск ----------------------------------------------------------
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_search())

        # ---- sidebar --------------------------------------------------------
        self._sidebar_mode = "playlists"

        # ---- сборка ---------------------------------------------------------
        self._build_ui()
        self._manager.load_playlists()
        self._refresh_sidebar()
        self.refresh_list()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Map>", self._restore_volume_after_map)
        self.after(200, self._tick)

    # =========================================================================
    # Fullscreen
    # =========================================================================

    def _toggle_fullscreen(self, _e=None):
        self._is_fullscreen = not self._is_fullscreen
        self.attributes("-fullscreen", self._is_fullscreen)
        return "break"

    def _exit_fullscreen(self, _e=None):
        if self._is_fullscreen:
            self._is_fullscreen = False
            self.attributes("-fullscreen", False)

    # =========================================================================
    # Построение UI
    # =========================================================================

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # -----------------------------------------------------------------
        # row 0 — Top bar
        # -----------------------------------------------------------------
        topbar = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0, height=46)
        topbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        topbar.grid_propagate(False)
        topbar.grid_columnconfigure(1, weight=1)

        # Бургер ☰
        self.btn_burger = _cbtn(
            topbar, "☰", self._toggle_sidebar_menu,
            fg_color=C_BTN, hover_color=C_BTN_H,
            font=FONT_ICON_SM, width=40, height=36,
        )
        self.btn_burger.grid(row=0, column=0, sticky="w", padx=(0, 6))
        _tooltip_tk(self.btn_burger, "Меню", self._tooltips)

        # Статус (временные уведомления)
        self.lbl_hint = _clabel(topbar, "", text_color=C_MUTED, font=FONT_SMALL)
        self.lbl_hint.grid(row=0, column=1, sticky="w", padx=(4, 0))

        # Поиск — компактный, справа
        search_frame = ctk.CTkFrame(
            topbar, fg_color=C_SEARCH_BG,
            corner_radius=8, border_width=1, border_color="#2a3447",
        )
        search_frame.grid(row=0, column=2, sticky="e")

        _clabel(search_frame, "🔍", text_color=C_MUTED,
                font=("Segoe UI Symbol", 10)).pack(side="left", padx=(8, 2))

        self.entry_search = ctk.CTkEntry(
            search_frame, textvariable=self._search_var,
            fg_color=C_SEARCH_BG, border_width=0,
            text_color=C_FG, placeholder_text="Поиск...",
            placeholder_text_color=C_MUTED,
            font=FONT_SMALL, width=160, height=30,
            corner_radius=0,
        )
        self.entry_search.pack(side="left", padx=(0, 6))
        self.entry_search.bind("<Escape>", lambda _e: self._search_var.set(""))

        # -----------------------------------------------------------------
        # row 1 — Main area: sidebar | list | volume
        # -----------------------------------------------------------------
        main = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 4))
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)

        # -- Sidebar ----------------------------------------------------------
        self.sidebar = ctk.CTkFrame(main, fg_color=C_SIDEBAR,
                                    corner_radius=12, width=200)
        self.sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(0, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        self.sidebar_body = ctk.CTkFrame(self.sidebar, fg_color="transparent",
                                         corner_radius=0)
        self.sidebar_body.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # -- Список треков ----------------------------------------------------
        list_outer = ctk.CTkFrame(main, fg_color=C_LIST_BG, corner_radius=12)
        list_outer.grid(row=0, column=1, sticky="nsew")
        list_outer.grid_rowconfigure(0, weight=1)
        list_outer.grid_columnconfigure(0, weight=1)

        # Скролл внутри CTkScrollableFrame не нужен — используем свой canvas
        # чтобы сохранить click/hover поведение строк
        self.list_canvas = tk.Canvas(
            list_outer, bg=C_LIST_BG,
            highlightthickness=0, bd=0,
        )
        self.list_canvas.grid(row=0, column=0, sticky="nsew",
                              padx=(6, 0), pady=6)

        list_scroll = ctk.CTkScrollbar(
            list_outer, orientation="vertical",
            command=self.list_canvas.yview,
            fg_color=C_LIST_BG, button_color="#2a3447",
            button_hover_color="#3a4a66",
        )
        list_scroll.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 4))
        self.list_canvas.configure(yscrollcommand=list_scroll.set)

        self.list_inner = tk.Frame(self.list_canvas, bg=C_LIST_BG)
        self._canvas_win = self.list_canvas.create_window(
            (0, 0), window=self.list_inner, anchor="nw"
        )
        self.list_inner.bind("<Configure>", self._on_list_configure)
        self.list_canvas.bind("<Configure>", self._on_canvas_configure)
        self.list_canvas.bind("<Enter>", lambda _e: self.list_canvas.bind_all(
            "<MouseWheel>", self._on_mousewheel))
        self.list_canvas.bind("<Leave>", lambda _e: self.list_canvas.unbind_all(
            "<MouseWheel>"))

        # -- Громкость (правая колонка) ---------------------------------------
        vol_col = ctk.CTkFrame(main, fg_color=C_BG, corner_radius=0, width=52)
        vol_col.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        vol_col.grid_propagate(False)
        vol_col.grid_rowconfigure(0, weight=1)   # верхняя пружина
        vol_col.grid_rowconfigure(4, weight=1)   # нижняя пружина
        vol_col.grid_columnconfigure(0, weight=1)

        # Цифра громкости (кликается → Entry)
        self._vol_label = ctk.CTkLabel(
            vol_col, textvariable=self._volume_var,
            text_color=C_FG, font=FONT_SMALL,
            fg_color=C_BTN, corner_radius=6,
            width=36, height=26, cursor="xterm",
        )
        self._vol_label.grid(row=1, column=0, pady=(0, 6))
        self._vol_label.bind("<Button-1>", self._start_volume_edit)
        self._vol_label.bind("<Enter>",
            lambda _e: self._vol_label.configure(fg_color=C_BTN_H))
        self._vol_label.bind("<Leave>",
            lambda _e: self._vol_label.configure(fg_color=C_BTN))

        # Entry для ввода точного значения
        vcmd = (self.register(self._validate_vol_entry), "%P")
        self._vol_entry = ctk.CTkEntry(
            vol_col, fg_color=C_BTN, border_width=1,
            border_color=C_ACCENT, text_color=C_FG,
            font=FONT_SMALL, width=36, height=26,
            corner_radius=6, justify="center",
            validate="key", validatecommand=vcmd,
        )
        self._vol_entry.bind("<Return>", self._commit_volume_edit)
        self._vol_entry.bind("<FocusOut>", self._commit_volume_edit)
        self._vol_entry.bind("<Escape>", self._cancel_volume_edit)

        # Вертикальный слайдер громкости
        # CTk не имеет вертикального CTkSlider — используем tk.Scale
        self._vol_slider = tk.Scale(
            vol_col,
            from_=100, to=0, orient="vertical",
            variable=self._volume_var,
            showvalue=False, sliderrelief="flat",
            troughcolor=C_TROUGH, bg=C_BG, fg=C_FG,
            highlightthickness=0, bd=0,
            width=14, sliderlength=14,
            activebackground=C_THUMB,
            command=self._on_volume_slider,
        )
        self._vol_slider.grid(row=2, column=0)
        self._vol_slider.configure(length=220)
        self._vol_slider.bind("<ButtonPress-1>",
                              lambda _e: setattr(self, "_vol_drag", True))
        self._vol_slider.bind("<ButtonRelease-1>",
                              lambda _e: setattr(self, "_vol_drag", False))

        # Иконка динамика
        _clabel(vol_col, "🔊", text_color=C_MUTED,
                font=FONT_ICON_SM).grid(row=3, column=0, pady=(8, 0))

        # -----------------------------------------------------------------
        # row 2 — Transport bar
        # -----------------------------------------------------------------
        transport = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        transport.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        transport.grid_columnconfigure(1, weight=1)

        # Время
        self.lbl_time = _clabel(
            transport, "00:00 / 00:00",
            text_color=C_MUTED, font=FONT_SMALL,
        )
        self.lbl_time.grid(row=0, column=0, sticky="w", pady=(0, 6))

        # Seek-слайдер — CTkSlider
        self.seek_var = tk.DoubleVar(value=0.0)
        self.seek_scale = ctk.CTkSlider(
            transport,
            from_=0.0, to=100.0,
            variable=self.seek_var,
            fg_color=C_TROUGH,
            progress_color=C_ACCENT,
            button_color=C_THUMB,
            button_hover_color="#c0e0ff",
            height=14,
            corner_radius=4,
        )
        self.seek_scale.grid(row=0, column=1, sticky="ew",
                             padx=(10, 0), pady=(0, 6))
        self.seek_scale.bind("<ButtonPress-1>",   self._on_seek_press)
        self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        # Кнопки транспорта
        btn_row = ctk.CTkFrame(transport, fg_color=C_BG, corner_radius=0)
        btn_row.grid(row=1, column=0, columnspan=2, sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=0)
        btn_row.grid_columnconfigure(2, weight=1)

        # Левый блок — «назад» и «выбрано»
        self._nav_frame = ctk.CTkFrame(btn_row, fg_color="transparent",
                                       corner_radius=0)
        self._nav_frame.grid(row=0, column=0, sticky="w")

        self.btn_back = _cbtn(
            self._nav_frame, "← Все треки", self._show_all_tracks,
            height=30, corner_radius=8,
        )
        self.btn_selection = _cbtn(
            self._nav_frame, "Выбрано: 0",
            self._show_selection_actions_menu,
            height=30, corner_radius=8,
        )
        # оба скрыты изначально

        # Центральные кнопки
        center = ctk.CTkFrame(btn_row, fg_color="transparent", corner_radius=0)
        center.grid(row=0, column=1)

        self.btn_shuffle = _cbtn(
            center, "🔀", self._toggle_shuffle,
            fg_color=C_BTN, hover_color=C_BTN_H,
            font=FONT_ICON_SM, width=44, height=38, corner_radius=10,
        )
        self.btn_shuffle.pack(side="left", padx=3)
        _tooltip_tk(self.btn_shuffle, self._shuffle_tooltip_text, self._tooltips)

        self.btn_prev = _icon_cbtn(center, "⏮", self.play_previous)
        self.btn_prev.pack(side="left", padx=3)
        _tooltip_tk(self.btn_prev, "Предыдущая", self._tooltips)

        self.btn_play_pause = _icon_cbtn(
            center, "▶", self.play_pause, accent=True, width=60, height=44,
        )
        self.btn_play_pause.pack(side="left", padx=3)
        _tooltip_tk(self.btn_play_pause, self._play_tooltip_text, self._tooltips)

        self.btn_next = _icon_cbtn(center, "⏭", self.play_next)
        self.btn_next.pack(side="left", padx=3)
        _tooltip_tk(self.btn_next, "Следующая", self._tooltips)

    # =========================================================================
    # Sidebar
    # =========================================================================

    def _toggle_sidebar_menu(self) -> None:
        self._sidebar_mode = "playlists" if self._sidebar_mode == "settings" \
                             else "settings"
        self._refresh_sidebar()

    def _refresh_sidebar(self) -> None:
        for w in self.sidebar_body.winfo_children():
            w.destroy()
        self.sidebar_body.grid_rowconfigure(0, weight=1)
        self.sidebar_body.grid_columnconfigure(0, weight=1)

        mode = self._sidebar_mode
        if mode == "playlists":
            self._build_sidebar_playlists()
        elif mode == "settings":
            self._build_sidebar_settings()
        elif mode == "new_pl":
            self._build_sidebar_new_playlist()

    # -- Плейлисты ------------------------------------------------------------
    def _build_sidebar_playlists(self) -> None:
        body = self.sidebar_body

        # Заголовок + кнопка +
        hdr = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        hdr.pack(fill="x", pady=(0, 6))
        _clabel(hdr, "Плейлисты", text_color=C_MUTED,
                font=FONT_SMALL).pack(side="left")
        btn_new = _cbtn(
            hdr, "+", self._open_new_playlist_panel,
            font=("Segoe UI", 13, "bold"), width=30, height=26,
            corner_radius=8,
        )
        btn_new.pack(side="right")
        _tooltip_tk(btn_new, "Создать плейлист", self._tooltips)

        # Кнопка «Все треки»
        is_lib = self._view_mode == "library"
        _cbtn(
            body, "Все треки", self._show_all_tracks,
            fg_color=C_ACCENT if is_lib else C_BTN,
            hover_color=C_ACCENT_H if is_lib else C_BTN_H,
            height=34, corner_radius=8, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        # Прокручиваемый список плейлистов
        pl_scroll_frame = ctk.CTkScrollableFrame(
            body, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#2a3447",
            scrollbar_button_hover_color=C_TROUGH,
        )
        pl_scroll_frame.pack(fill="both", expand=True)
        pl_scroll_frame.grid_columnconfigure(0, weight=1)

        for pl in self._manager.playlists:
            pid  = pl["id"]
            name = pl["name"]
            is_active = self._view_mode == pid
            btn = _cbtn(
                pl_scroll_frame, name,
                lambda p=pid: self._open_playlist(p),
                fg_color=C_ACCENT if is_active else C_BTN,
                hover_color=C_ACCENT_H if is_active else C_BTN_H,
                height=34, corner_radius=8, anchor="w",
            )
            btn.pack(fill="x", pady=2)
            btn.bind("<Button-3>", lambda e, p=pid, n=name:
                     self._playlist_context_menu(e, p, n))

        if not self._manager.playlists:
            _clabel(pl_scroll_frame, "Нет плейлистов",
                    text_color=C_MUTED, font=FONT_SMALL,
                    wraplength=160).pack(pady=10, padx=4)

    def _playlist_context_menu(self, event, pid: str, name: str) -> None:
        menu = tk.Menu(self, tearoff=0, bg=C_BTN, fg=C_FG,
                       activebackground=C_ACCENT)
        menu.add_command(
            label=f"Удалить «{name}»",
            command=lambda: self._delete_playlist_by_id(pid, name),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _delete_playlist_by_id(self, pid: str, name: str) -> None:
        """Подтверждение → удаление → навигация → обновление sidebar."""
        if not messagebox.askyesno(
            "Удалить плейлист",
            f"Удалить плейлист «{name}»?\nФайлы в my_music не удалятся.",
        ):
            return
        success, err = self._manager.delete_playlist(pid)
        if not success:
            messagebox.showerror("Ошибка удаления", f"Не удалось удалить плейлист.\n\n{err}")
            return
        # Если удалённый плейлист был активен — переходим в библиотеку
        if self._view_mode == pid:
            self._show_all_tracks()
        else:
            # Просто обновляем sidebar — текущий вид не меняется
            self._refresh_sidebar()
        self._set_hint(f"Плейлист «{name}» удалён", restore_after_ms=2500)

    # -- Настройки ------------------------------------------------------------
    def _build_sidebar_settings(self) -> None:
        body = self.sidebar_body

        hdr = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        hdr.pack(fill="x", pady=(0, 10))
        _clabel(hdr, "Настройки", text_color=C_MUTED,
                font=FONT_SMALL).pack(side="left")
        _cbtn(hdr, "✕", self._toggle_sidebar_menu,
              width=28, height=26, corner_radius=6).pack(side="right")

        _cbtn(body, "Добавить .mp3", self._add_files,
              height=36, corner_radius=8).pack(fill="x", pady=4)
        _cbtn(body, "Создать плейлист", self._open_new_playlist_panel,
              height=36, corner_radius=8).pack(fill="x", pady=4)

    # -- Создание плейлиста ---------------------------------------------------
    def _open_new_playlist_panel(self) -> None:
        self._sidebar_mode = "new_pl"
        self._refresh_sidebar()

    def _build_sidebar_new_playlist(self) -> None:
        body = self.sidebar_body

        hdr = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        hdr.pack(fill="x", pady=(0, 10))
        _clabel(hdr, "Новый плейлист", text_color=C_MUTED,
                font=FONT_SMALL).pack(side="left")
        _cbtn(hdr, "✕", lambda: self._set_sidebar("playlists"),
              width=28, height=26, corner_radius=6).pack(side="right")

        _clabel(body, "Название", text_color=C_FG,
                font=FONT_SMALL).pack(fill="x", pady=(0, 4))

        name_var = ctk.StringVar()
        entry = ctk.CTkEntry(
            body, textvariable=name_var,
            fg_color=C_LIST_BG, border_width=1, border_color="#2a3447",
            text_color=C_FG, font=FONT_SMALL,
            corner_radius=8, height=34,
        )
        entry.pack(fill="x")
        entry.focus_set()

        preview = _clabel(body, "●", text_color=C_MUTED, font=FONT_SMALL)
        preview.pack(fill="x", pady=(6, 0))

        def on_change(*_):
            raw = name_var.get().strip()
            preview.configure(
                text=f"Инициалы: {playlist_initials(raw)}" if raw else "●"
            )
        name_var.trace_add("write", on_change)

        def do_create():
            raw = name_var.get().strip()
            success, result = self._manager.create_playlist(raw)
            if not success:
                preview.configure(text=f"⚠ {result}", text_color="#e05252")
                return
            self._on_playlist_created(result)

        _cbtn(
            body, "Создать", do_create,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            height=36, corner_radius=8,
        ).pack(fill="x", pady=(12, 0))
        entry.bind("<Return>", lambda _e: do_create())

    def _set_sidebar(self, mode: str) -> None:
        self._sidebar_mode = mode
        self._refresh_sidebar()

    # =========================================================================
    # Поиск
    # =========================================================================

    def _apply_search(self) -> None:
        self.refresh_list()

    # =========================================================================
    # Навигация
    # =========================================================================

    def _open_playlist(self, playlist_id: str) -> None:
        meta = self._manager.load_playlist_meta(playlist_id)
        if not meta:
            return
        self._view_mode = playlist_id
        self._search_var.set("")
        self.entry_search.configure(state="disabled")
        self._show_back_btn(True)
        self._selected_index = None
        self._checked_names.clear()
        self._update_selection_ui()
        self._set_sidebar("playlists")
        self.refresh_list()

    def _show_all_tracks(self) -> None:
        self._view_mode = "library"
        self.entry_search.configure(state="normal")
        self._show_back_btn(False)
        self._selected_index = None
        self._checked_names.clear()
        self._update_selection_ui()
        self._set_sidebar("playlists")
        self.refresh_list()

    def _show_back_btn(self, visible: bool) -> None:
        if visible:
            self.btn_back.pack(side="left", padx=(0, 4))
        else:
            self.btn_back.pack_forget()

    # =========================================================================
    # Список треков
    # =========================================================================

    def refresh_list(self, *, select_name: str | None = None) -> None:
        for row, _ in self._track_rows:
            row.destroy()
        self._track_rows.clear()

        self._all_tracks = self._manager.tracks_for_view(self._view_mode)

        query = self._search_var.get().strip().lower()
        if query and self._view_mode == "library":
            self._tracks = [n for n in self._all_tracks if query in n.lower()]
        else:
            self._tracks = list(self._all_tracks)

        if self.shuffle_enabled and len(self._shuffle_order) != len(self._all_tracks):
            self._reshuffle_play_order()

        for index, name in enumerate(self._tracks):
            # Строка — обычный tk.Frame для hover-цвета и canvas-совместимости
            row = tk.Frame(self.list_inner, bg=C_LIST_BG, cursor="hand2")
            row.pack(fill="x", padx=6, pady=2)

            lbl = tk.Label(
                row, text=name, bg=C_LIST_BG, fg=C_FG,
                anchor="w", font=FONT_LIST, cursor="hand2",
                padx=12, pady=6,
            )
            lbl.pack(side="left", fill="x", expand=True)

            for w in (row, lbl):
                w.bind("<Button-1>", lambda _e, i=index: self._on_track_click(i))
                w.bind("<Button-3>", lambda e, n=name:
                       self._show_track_context_menu(e, n))

            def _enter(e, r=row, l=lbl, i=index, n=name):
                if n not in self._checked_names and i != self._selected_index:
                    r.configure(bg=C_ROW_HOVER); l.configure(bg=C_ROW_HOVER)
            def _leave(e, r=row, l=lbl, i=index, n=name):
                color = (C_CHECK if n in self._checked_names
                         else C_ROW_SEL if i == self._selected_index
                         else C_LIST_BG)
                r.configure(bg=color); l.configure(bg=color)

            for w in (row, lbl):
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)

            self._track_rows.append((row, lbl))

        if select_name and select_name in self._tracks:
            self._selected_index = self._tracks.index(select_name)
        elif self._selected_index is not None and \
                self._selected_index >= len(self._tracks):
            self._selected_index = len(self._tracks) - 1 if self._tracks else None
        elif self._selected_index is None and self._tracks:
            self._selected_index = 0

        self._checked_names &= set(self._tracks)
        self._update_selection_ui()
        self._update_row_highlights()
        self.list_inner.update_idletasks()
        self._on_list_configure()

    def _update_row_highlights(self) -> None:
        for i, (row, lbl) in enumerate(self._track_rows):
            name = self._tracks[i]
            color = (C_CHECK    if name in self._checked_names else
                     C_ROW_SEL  if i == self._selected_index else
                     C_LIST_BG)
            row.configure(bg=color)
            lbl.configure(bg=color)

    def _on_track_click(self, index: int) -> None:
        if index < 0 or index >= len(self._tracks):
            return
        track_name = self._tracks[index]
        self._selected_index = index
        self._update_row_highlights()
        self._play_file(os.path.join(self._manager.music_dir, track_name))

    def _select_index(self, index: int, *, play: bool = False) -> None:
        if index < 0 or index >= len(self._tracks):
            return
        self._selected_index = index
        self._update_row_highlights()
        if play:
            self._play_track_at_index(index)

    # =========================================================================
    # Scroll helpers
    # =========================================================================

    def _on_list_configure(self, _e=None) -> None:
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))

    def _on_canvas_configure(self, e) -> None:
        self.list_canvas.itemconfig(self._canvas_win, width=e.width)

    def _on_mousewheel(self, e) -> None:
        if self.list_canvas.winfo_exists():
            self.list_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    # =========================================================================
    # Громкость
    # =========================================================================

    def _validate_vol_entry(self, new_val: str) -> bool:
        if new_val == "": return True
        if not new_val.isdigit(): return False
        if len(new_val) > 3: return False
        if int(new_val) > 100: return False
        return True

    def _on_volume_slider(self, value: str) -> None:
        if not self._vol_drag: return
        self._engine.set_volume(int(float(value)))

    def _restore_volume_after_map(self, _e=None) -> None:
        self._volume_var.set(self._engine.get_volume())

    def _start_volume_edit(self, _e=None) -> None:
        self._vol_label.grid_remove()
        self._vol_entry.delete(0, "end")
        self._vol_entry.insert(0, str(self._volume_var.get()))
        self._vol_entry.grid(row=1, column=0, pady=(0, 6))
        self._vol_entry.focus_set()
        self._vol_entry.select_range(0, "end")

    def _commit_volume_edit(self, _e=None) -> None:
        raw = self._vol_entry.get().strip()
        self._vol_entry.grid_remove()
        self._vol_label.grid(row=1, column=0, pady=(0, 6))
        try:
            level = max(0, min(100, int(raw)))
        except ValueError:
            return
        self._volume_var.set(level)
        self._engine.set_volume(level)

    def _cancel_volume_edit(self, _e=None) -> None:
        self._vol_entry.grid_remove()
        self._vol_label.grid(row=1, column=0, pady=(0, 6))

    # =========================================================================
    # Tooltip helpers
    # =========================================================================

    def _play_tooltip_text(self) -> str:
        if self._engine.is_playing and not self._engine.is_paused:
            return "Пауза"
        if self._engine.is_playing and self._engine.is_paused:
            return "Продолжить"
        return "Старт"

    def _shuffle_tooltip_text(self) -> str:
        return "Выключить перемешивание" if self.shuffle_enabled else "Перемешать"

    # =========================================================================
    # Hint
    # =========================================================================

    def _set_hint(self, text: str, *, restore_after_ms: int = 0) -> None:
        self.lbl_hint.configure(text=text)
        if restore_after_ms > 0:
            self.after(restore_after_ms, self._restore_hint)

    def _restore_hint(self) -> None:
        self.lbl_hint.configure(text="")

    # =========================================================================
    # Воспроизведение
    # =========================================================================

    def play_pause(self) -> None:
        if not self._engine.is_playing:
            path = self._selected_track_path() or self._first_track_path()
            if path:
                if self._selected_index is None and self._tracks:
                    self._selected_index = 0
                    self._update_row_highlights()
                self._play_file(path)
            return
        self._engine.play_pause()
        self._sync_play_button()

    def play_next(self) -> None:
        if not self._all_tracks: return
        next_idx = self._next_play_index(self._current_track_index())
        name = self._all_tracks[next_idx]
        if name in self._tracks:
            self._selected_index = self._tracks.index(name)
            self._update_row_highlights()
        self._play_file(os.path.join(self._manager.music_dir, name))

    def play_previous(self) -> None:
        if not self._all_tracks: return
        prev_idx = self._prev_play_index(self._current_track_index())
        name = self._all_tracks[prev_idx]
        if name in self._tracks:
            self._selected_index = self._tracks.index(name)
            self._update_row_highlights()
        self._play_file(os.path.join(self._manager.music_dir, name))

    def _play_file(self, path: str) -> None:
        if not os.path.exists(path): return
        name = os.path.basename(path)
        if name in self._tracks:
            self._selected_index = self._tracks.index(name)
            self._update_row_highlights()
        try:
            ok = self._engine.play(path)
        except RuntimeError as exc:
            messagebox.showerror("Ошибка воспроизведения", str(exc))
            return
        if ok:
            self._sync_seek_scale_limits()
            self.seek_var.set(0.0)
            self._update_time_labels(0.0)
            self._sync_play_button()
        else:
            self._engine.current_file = None

    def _play_track_at_index(self, index: int) -> None:
        self._play_file(os.path.join(self._manager.music_dir,
                                     self._tracks[index]))

    def _on_track_finished(self) -> None:
        if not self._all_tracks:
            self._reset_transport(); return
        next_idx = self._next_play_index(self._current_track_index())
        name = self._all_tracks[next_idx]
        if name in self._tracks:
            self._selected_index = self._tracks.index(name)
            self._update_row_highlights()
        self._play_file(os.path.join(self._manager.music_dir, name))

    def _on_position_changed(self, pos_s: float) -> None:
        self.seek_var.set(pos_s)
        self._update_time_labels(pos_s)

    # =========================================================================
    # Seek / transport
    # =========================================================================

    def _on_seek_press(self, _e) -> None:
        self._engine.begin_seek()

    def _on_seek_release(self, _e) -> None:
        seconds = float(self.seek_var.get())
        try:
            self._engine.end_seek(seconds)
        except RuntimeError as exc:
            messagebox.showerror("Перемотка", str(exc))
        self.seek_var.set(seconds)
        self._update_time_labels(seconds)

    def _sync_seek_scale_limits(self) -> None:
        max_s = max(0.0, float(self._engine.track_length_s))
        self.seek_scale.configure(to=max_s if max_s > 0 else 100.0)
        self._update_time_labels(0.0)

    def _update_time_labels(self, pos_s: float) -> None:
        total = self._engine.track_length_s if self._engine.track_length_s > 0 else 0.0
        self.lbl_time.configure(
            text=f"{AudioEngine.format_time(pos_s)} / {AudioEngine.format_time(total)}"
        )

    def _sync_play_button(self) -> None:
        playing = self._engine.is_playing and not self._engine.is_paused
        self.btn_play_pause.configure(text="⏸" if playing else "▶")
        tip = self._tooltips.get(self.btn_play_pause)
        if tip:
            tip.withdraw()

    def _reset_transport(self) -> None:
        self._engine.stop()
        self._sync_play_button()
        self.seek_var.set(0.0)
        self._update_time_labels(0.0)

    # =========================================================================
    # Shuffle
    # =========================================================================

    def _toggle_shuffle(self) -> None:
        self.shuffle_enabled = not self.shuffle_enabled
        if self.shuffle_enabled:
            self._reshuffle_play_order()
        self._sync_shuffle_button()

    def _reshuffle_play_order(self) -> None:
        import random
        if not self._all_tracks:
            self._shuffle_order = []; return
        self._shuffle_order = list(range(len(self._all_tracks)))
        random.shuffle(self._shuffle_order)

    def _sync_shuffle_button(self) -> None:
        tip = self._tooltips.get(self.btn_shuffle)
        if tip:
            tip.withdraw()
        if self.shuffle_enabled:
            self.btn_shuffle.configure(fg_color=C_SHUFFLE_ON,
                                       hover_color=C_SHUFFLE_H)
        else:
            self.btn_shuffle.configure(fg_color=C_BTN,
                                       hover_color=C_BTN_H)

    def _next_play_index(self, current_index: int | None) -> int:
        n = len(self._all_tracks)
        if not n: return 0
        if self.shuffle_enabled:
            if not self._shuffle_order or len(self._shuffle_order) != n:
                self._reshuffle_play_order()
            order = self._shuffle_order
            if current_index is None: return order[0]
            if current_index not in order: return order[0]
            pos = order.index(current_index)
            if pos + 1 < len(order): return order[pos + 1]
            self._reshuffle_play_order()
            return self._shuffle_order[0]
        if current_index is None: return 0
        return (current_index + 1) % n

    def _prev_play_index(self, current_index: int | None) -> int:
        n = len(self._all_tracks)
        if not n: return 0
        if self.shuffle_enabled:
            if not self._shuffle_order or len(self._shuffle_order) != n:
                self._reshuffle_play_order()
            order = self._shuffle_order
            if current_index is None: return order[-1]
            if current_index not in order: return order[-1]
            pos = order.index(current_index)
            return order[pos - 1] if pos > 0 else order[-1]
        if current_index is None: return n - 1
        return (current_index - 1) % n

    # =========================================================================
    # Track helpers
    # =========================================================================

    def _selected_track_path(self) -> str | None:
        if self._selected_index is None or not self._tracks: return None
        return os.path.join(self._manager.music_dir,
                            self._tracks[self._selected_index])

    def _first_track_path(self) -> str | None:
        if not self._all_tracks: return None
        return os.path.join(self._manager.music_dir, self._all_tracks[0])

    def _current_track_index(self) -> int | None:
        if self._engine.current_file:
            name = os.path.basename(self._engine.current_file)
            if name in self._all_tracks:
                return self._all_tracks.index(name)
        return None

    # =========================================================================
    # Multi-select
    # =========================================================================

    def _toggle_track_check(self, track_name: str) -> None:
        if track_name in self._checked_names:
            self._checked_names.discard(track_name)
        else:
            self._checked_names.add(track_name)
        self._update_selection_ui()
        self._update_row_highlights()

    def _update_selection_ui(self) -> None:
        count = len(self._checked_names)
        if count > 0:
            self.btn_selection.configure(text=f"Выбрано: {count}")
            self.btn_selection.pack(side="left", padx=(0, 4))
        else:
            self.btn_selection.pack_forget()

    def _clear_selection(self) -> None:
        self._checked_names.clear()
        self._update_selection_ui()
        self._update_row_highlights()

    # =========================================================================
    # Context menus
    # =========================================================================

    def _show_track_context_menu(self, event, track_name: str) -> None:
        menu = tk.Menu(self, tearoff=0, bg=C_BTN, fg=C_FG,
                       activebackground=C_ACCENT)

        if track_name in self._checked_names:
            menu.add_command(label="Снять выделение",
                             command=lambda: self._toggle_track_check(track_name))
        else:
            menu.add_command(label="Выделить",
                             command=lambda: self._toggle_track_check(track_name))

        use_batch = bool(self._checked_names) and track_name in self._checked_names
        targets = list(self._checked_names) if use_batch else [track_name]

        if self._view_mode == "library":
            if self._manager.playlists:
                pl_menu = tk.Menu(menu, tearoff=0, bg=C_BTN, fg=C_FG,
                                  activebackground=C_ACCENT)
                for pl in self._manager.playlists:
                    pl_menu.add_command(
                        label=pl["name"],
                        command=lambda pid=pl["id"], names=targets:
                            self._batch_add_to_playlist(pid, names),
                    )
                menu.add_cascade(
                    label="Добавить в плейлист" if len(targets) == 1
                          else f"Добавить выделенные ({len(targets)})",
                    menu=pl_menu,
                )
            else:
                menu.add_command(label="Добавить в плейлист", state="disabled")

            if len(targets) == 1:
                menu.add_command(label="Переименовать",
                                 command=lambda: self.rename_track(track_name))
            menu.add_command(
                label="Удалить" if len(targets) == 1
                      else f"Удалить ({len(targets)})",
                command=lambda names=targets: self._delete_tracks(names),
            )
        else:
            menu.add_command(
                label="Убрать из плейлиста" if len(targets) == 1
                      else f"Убрать ({len(targets)})",
                command=lambda names=targets:
                    self._remove_tracks_from_playlist(names),
            )

        if self._checked_names:
            menu.add_separator()
            menu.add_command(label="Снять всё", command=self._clear_selection)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_selection_actions_menu(self) -> None:
        if not self._checked_names: return
        menu = tk.Menu(self, tearoff=0, bg=C_BTN, fg=C_FG,
                       activebackground=C_ACCENT)

        if self._view_mode == "library" and self._manager.playlists:
            pl_menu = tk.Menu(menu, tearoff=0, bg=C_BTN, fg=C_FG,
                              activebackground=C_ACCENT)
            for pl in self._manager.playlists:
                pl_menu.add_command(
                    label=pl["name"],
                    command=lambda pid=pl["id"]:
                        self._batch_add_to_playlist(pid, list(self._checked_names)),
                )
            menu.add_cascade(label="Добавить в плейлист", menu=pl_menu)
        elif self._view_mode == "library":
            menu.add_command(label="Добавить в плейлист", state="disabled")

        if len(self._checked_names) == 1 and self._view_mode == "library":
            only = next(iter(self._checked_names))
            menu.add_command(label="Переименовать",
                             command=lambda: self.rename_track(only))

        if self._view_mode == "library":
            menu.add_command(label="Удалить выделенные",
                             command=self._delete_selected_tracks)
        else:
            menu.add_command(label="Убрать из плейлиста",
                             command=self._remove_selected_from_playlist)

        menu.add_command(label="Снять выделение", command=self._clear_selection)

        try:
            x = self.btn_selection.winfo_rootx()
            y = self.btn_selection.winfo_rooty() + self.btn_selection.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # =========================================================================
    # Операции над треками
    # =========================================================================

    def _batch_add_to_playlist(self, pid: str, names: list[str]) -> None:
        added, skipped = self._manager.add_tracks_to_playlist(pid, names)
        pl_name = self._manager.playlist_name(pid)
        self._set_hint(f"В «{pl_name}»: +{added}, пропущено {skipped}",
                       restore_after_ms=2500)
        self._clear_selection()

    def _delete_tracks(self, track_names: list[str]) -> None:
        if not track_names: return
        count = len(track_names)
        prompt = (
            f"Удалить {count} файл(ов)?\nСсылки в плейлистах убираются."
            if count > 1 else f"Удалить «{track_names[0]}»?"
        )
        if not messagebox.askyesno("Удалить", prompt): return

        is_current_deleted = False
        for name in track_names:
            path = self._manager.track_path(name)
            if (self._engine.current_file and
                    os.path.normcase(self._engine.current_file) ==
                    os.path.normcase(path)):
                is_current_deleted = True
                self._engine.release()
            if os.path.isfile(path):
                try: os.remove(path)
                except OSError: continue
            self._manager.remove_track_from_all_playlists(name)

        self._checked_names -= set(track_names)
        self._update_selection_ui()
        if is_current_deleted:
            self._engine.current_file = None
            self._reset_transport()

        self._refresh_sidebar()
        self.refresh_list()
        self._set_hint(f"Удалено: {count}", restore_after_ms=2500)

    def _delete_selected_tracks(self) -> None:
        if self._checked_names:
            self._delete_tracks(list(self._checked_names))

    def _remove_tracks_from_playlist(self, track_names: list[str]) -> None:
        if self._view_mode == "library" or not track_names: return
        removed = self._manager.remove_tracks_from_playlist(
            self._view_mode, track_names)
        self._checked_names -= set(track_names)
        self._update_selection_ui()
        self._set_hint(f"Убрано: {removed}", restore_after_ms=2500)
        self.refresh_list()

    def _remove_selected_from_playlist(self) -> None:
        if self._view_mode != "library" and self._checked_names:
            self._remove_tracks_from_playlist(list(self._checked_names))

    def rename_track(self, track_name: str | None = None) -> None:
        if track_name is None:
            if self._selected_index is None:
                messagebox.showinfo("Переименование", "Выберите трек.")
                return
            track_name = self._tracks[self._selected_index]

        old_path = self._manager.track_path(track_name)
        if not os.path.exists(old_path):
            self.refresh_list(); return

        base = track_name[:-4] if track_name.lower().endswith(".mp3") else track_name
        new_base = simpledialog.askstring("Переименовать", "Новое имя:",
                                          initialvalue=base)
        if not new_base: return

        is_current = (
            self._engine.current_file is not None and
            os.path.normcase(self._engine.current_file) ==
            os.path.normcase(old_path)
        )
        resume_pos = 0.0; resume_paused = False; should_resume = False

        if is_current and self._engine.is_playing:
            resume_pos    = self._engine.current_position_s()
            resume_paused = self._engine.is_paused
            should_resume = True
            self._engine.release()
        elif is_current:
            self._engine.release()

        success, result = self._manager.rename_track(track_name, new_base)
        if not success:
            if is_current and should_resume:
                try: self._engine.play(old_path)
                except RuntimeError: pass
            messagebox.showerror("Переименование", result)
            return

        new_name = result
        self._refresh_sidebar()
        self.refresh_list(select_name=new_name)

        if is_current:
            new_path = self._manager.track_path(new_name)
            self._engine.track_length_s = self._engine._probe_length(new_path)
            self._sync_seek_scale_limits()
            if should_resume:
                try:
                    self._engine._load_at(new_path, resume_pos,
                                          paused=resume_paused)
                    self.seek_var.set(resume_pos)
                    self._update_time_labels(resume_pos)
                    self._sync_play_button()
                except RuntimeError:
                    self._engine.current_file = new_path
            else:
                self._engine.current_file = new_path
                self._engine.is_playing   = False
                self._engine.is_paused    = False
                self.seek_var.set(0.0)
                self._update_time_labels(0.0)
                self._sync_play_button()

    # =========================================================================
    # Settings / файлы
    # =========================================================================

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите mp3 файлы",
            filetypes=[("MP3 files", "*.mp3")],
        )
        if not paths: return
        copied, skipped = self._manager.import_files(paths)
        self._on_files_added()
        self._set_hint(f"Добавлено: {copied}, пропущено: {skipped}",
                       restore_after_ms=3000)
        self._set_sidebar("playlists")

    def _on_files_added(self) -> None:
        self.refresh_list()

    def _on_playlist_created(self, playlist_id: str) -> None:
        """После создания плейлиста — сразу переходим в него."""
        name = self._manager.playlist_name(playlist_id)
        self._set_hint(f"Создан: {name}", restore_after_ms=2500)
        # Переключаемся в новый плейлист — пользователь видит его сразу
        self._view_mode = playlist_id
        self._selected_index = None
        self._checked_names.clear()
        self._show_back_btn(True)
        self.entry_search.configure(state="disabled")
        self._set_sidebar("playlists")   # обновляет sidebar с подсветкой нового
        self.refresh_list()

    def _on_playlist_deleted(self, pid: str) -> None:
        """Колбэк на внешнее удаление плейлиста (совместимость)."""
        if self._view_mode == pid:
            self._show_all_tracks()
        else:
            self._refresh_sidebar()
        self._set_hint("Плейлист удалён", restore_after_ms=2500)

    def refresh_playlist_strip(self) -> None:
        self._refresh_sidebar()

    # =========================================================================
    # Tick
    # =========================================================================

    def _tick(self) -> None:
        try:
            self._engine.tick()
        finally:
            self.after(200, self._tick)

    def _on_close(self) -> None:
        self._engine.shutdown()
        self.destroy()
