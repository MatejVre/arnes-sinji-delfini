from __future__ import annotations

import json
import os
import platform
import queue
import sqlite3
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import filedialog
from tkinter import font as tkfont
from tkinter import messagebox
from tkinter import scrolledtext

try:
    from desktop.env_file import read_env, update_env_keys
    from desktop.server_panel import REPO_ROOT, start_uvicorn, stop_process
except ImportError:
    from env_file import read_env, update_env_keys
    from server_panel import REPO_ROOT, start_uvicorn, stop_process


# Skladajo se s spletnim UI (topla temna tema + accent)
COLORS = {
    "bg": "#2c2a34",
    "bg_elevated": "#34323e",
    "card": "#3a3844",
    "accent": "#19c37d",
    "accent_hover": "#22d68f",
    "text": "#ececf1",
    "muted": "#9b97a8",
    "border": "#4a4754",
}


class SinjiDesktopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sinji Delfin — skrbništvo")
        self.geometry("920x640")
        self.minsize(720, 520)
        self.configure(bg=COLORS["bg"])

        self._body_font = tkfont.Font(family="Segoe UI", size=11)
        self._title_font = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        self._subtitle_font = tkfont.Font(family="Segoe UI", size=11)
        self._nav_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        self._container = tk.Frame(self, bg=COLORS["bg"])
        self._container.pack(fill=tk.BOTH, expand=True)

        self._pages: dict[str, tk.Frame] = {}
        self._server_proc = None
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._server_log: scrolledtext.ScrolledText | None = None

        self._env_path: Path = REPO_ROOT / ".env"
        self._idx_busy = False

        self._build_welcome()
        self._build_server_page()
        self._build_logs_page()
        self._build_ai_page()
        self._build_index_page()
        self._build_documents_page()
        self._build_groups_page()
        self._build_placeholders()

        self.protocol("WM_DELETE_WINDOW", self._on_close_window)
        self.after(120, self._drain_log_queue)

        self.show_page("welcome")

    def _build_welcome(self) -> None:
        welcome = tk.Frame(self._container, bg=COLORS["bg"])
        self._pages["welcome"] = welcome

        inner = tk.Frame(welcome, bg=COLORS["bg"])
        inner.place(relx=0.5, rely=0.42, anchor=tk.CENTER)

        tk.Label(
            inner,
            text="Sinji Delfin",
            font=self._title_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
        ).pack(pady=(0, 6))

        tk.Label(
            inner,
            text="Sistem AI pomočnikov z nadzorovanim dostopom",
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["bg"],
        ).pack(pady=(0, 4))

        tk.Label(
            inner,
            text="Izberite modul za nastavitve ali vzdrževanje.",
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["bg"],
        ).pack(pady=(0, 28))

        nav = tk.Frame(inner, bg=COLORS["bg"])
        nav.pack()

        # (ključ strani, oznaka na gumbu)
        modules = [
            ("documents", "Dokumenti"),
            ("groups", "Skupine"),
            ("users", "Uporabniki"),
            ("permissions", "Pravice do dokumentov"),
            ("ai", "AI / LLM"),
            ("index", "Indeks (Pinecone)"),
            ("server", "Strežnik in omrežje"),
            ("backup", "Varnostno kopiranje"),
            ("logs", "Dnevnik / konzola"),
        ]

        cols = 3
        for i, (key, label) in enumerate(modules):
            r, c = divmod(i, cols)
            btn = self._make_nav_button(nav, label, lambda k=key: self.show_page(k))
            btn.grid(row=r, column=c, padx=8, pady=8, sticky="ew")

        for col in range(cols):
            nav.grid_columnconfigure(col, weight=1)

        tk.Label(
            welcome,
            text="Strežnik API zaženite v modulu »Strežnik in omrežje«; klepet je nato v brskalniku.",
            font=("Segoe UI", 9),
            fg=COLORS["muted"],
            bg=COLORS["bg"],
        ).pack(side=tk.BOTTOM, pady=16)

    def _make_nav_button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            font=self._nav_font,
            fg=COLORS["text"],
            bg=COLORS["card"],
            activeforeground=COLORS["text"],
            activebackground=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=18,
            pady=14,
            cursor="hand2",
            command=command,
        )
        btn.bind("<Enter>", lambda e: btn.configure(bg=COLORS["bg_elevated"]))
        btn.bind("<Leave>", lambda e: btn.configure(bg=COLORS["card"]))
        return btn

    def _page_header(self, parent: tk.Frame, title: str) -> tk.Frame:
        header = tk.Frame(parent, bg=COLORS["bg_elevated"], height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Button(
            header,
            text="← Nazaj",
            font=self._subtitle_font,
            fg=COLORS["accent"],
            bg=COLORS["bg_elevated"],
            activeforeground=COLORS["accent_hover"],
            activebackground=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=16,
            pady=14,
            cursor="hand2",
            command=lambda: self.show_page("welcome"),
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text=title,
            font=self._nav_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
        ).pack(side=tk.LEFT, padx=(8, 0))
        return header

    def _build_server_page(self) -> None:
        page = tk.Frame(self._container, bg=COLORS["bg"])
        self._pages["server"] = page
        self._page_header(page, "Strežnik in omrežje")

        body = tk.Frame(page, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=20)

        card = tk.Frame(body, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        top = tk.Frame(card, bg=COLORS["card"])
        top.pack(fill=tk.X, padx=20, pady=(18, 12))

        self._var_host = tk.StringVar(value="0.0.0.0")
        self._var_port = tk.StringVar(value="8000")
        self._var_status = tk.StringVar(value="Strežnik: ustavljen")

        row1 = tk.Frame(top, bg=COLORS["card"])
        row1.pack(fill=tk.X, pady=(0, 10))
        tk.Label(row1, text="Gostitelj", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], width=12, anchor=tk.W).pack(
            side=tk.LEFT
        )
        host_e = tk.Entry(
            row1,
            textvariable=self._var_host,
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            insertbackground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            bd=0,
        )
        host_e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, ipadx=8)

        row2 = tk.Frame(top, bg=COLORS["card"])
        row2.pack(fill=tk.X, pady=(0, 14))
        tk.Label(row2, text="Vrata (port)", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], width=12, anchor=tk.W).pack(
            side=tk.LEFT
        )
        port_e = tk.Entry(
            row2,
            textvariable=self._var_port,
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            insertbackground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            bd=0,
            width=8,
        )
        port_e.pack(side=tk.LEFT, ipady=6, ipadx=8)

        btn_row = tk.Frame(top, bg=COLORS["card"])
        btn_row.pack(fill=tk.X, pady=(0, 8))

        self._btn_start = tk.Button(
            btn_row,
            text="Zaženi strežnik",
            font=self._nav_font,
            fg="#ffffff",
            bg=COLORS["accent"],
            activeforeground="#ffffff",
            activebackground=COLORS["accent_hover"],
            highlightthickness=0,
            bd=0,
            padx=22,
            pady=10,
            cursor="hand2",
            command=self._server_start,
        )
        self._btn_start.pack(side=tk.LEFT, padx=(0, 10))

        self._btn_stop = tk.Button(
            btn_row,
            text="Ustavi",
            font=self._nav_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            activeforeground=COLORS["text"],
            activebackground=COLORS["border"],
            highlightthickness=0,
            bd=0,
            padx=22,
            pady=10,
            cursor="hand2",
            command=self._server_stop,
            state=tk.DISABLED,
        )
        self._btn_stop.pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(
            btn_row,
            text="Počisti dnevnik",
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["card"],
            activeforeground=COLORS["text"],
            activebackground=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            command=self._server_clear_log,
        ).pack(side=tk.LEFT)

        tk.Label(
            top,
            textvariable=self._var_status,
            font=self._subtitle_font,
            fg=COLORS["accent"],
            bg=COLORS["card"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(4, 0))

        tk.Label(
            card,
            text=f"Koren projekta: {REPO_ROOT}",
            font=("Segoe UI", 9),
            fg=COLORS["muted"],
            bg=COLORS["card"],
            anchor=tk.W,
        ).pack(fill=tk.X, padx=20, pady=(0, 8))

        log_frame = tk.Frame(card, bg=COLORS["card"])
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        tk.Label(
            log_frame,
            text="Dnevnik (stdout strežnika)",
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["card"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 6))

        self._server_log = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 10),
            fg=COLORS["text"],
            bg="#1e1c24",
            insertbackground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            bd=0,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=14,
        )
        self._server_log.pack(fill=tk.BOTH, expand=True)

    def _build_logs_page(self) -> None:
        page = tk.Frame(self._container, bg=COLORS["bg"])
        self._pages["logs"] = page
        self._page_header(page, "Dnevnik / konzola")

        body = tk.Frame(page, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=40, pady=32)

        card = tk.Frame(body, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(expand=True, pady=40, padx=32)

        tk.Label(
            inner,
            text="Izhod API strežnika je prikazan v modulu »Strežnik in omrežje«.",
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["card"],
            wraplength=480,
            justify=tk.CENTER,
        ).pack()

        tk.Button(
            inner,
            text="Odpri strežnik in dnevnik",
            font=self._nav_font,
            fg="#ffffff",
            bg=COLORS["accent"],
            activeforeground="#ffffff",
            activebackground=COLORS["accent_hover"],
            highlightthickness=0,
            bd=0,
            padx=24,
            pady=12,
            cursor="hand2",
            command=lambda: self.show_page("server"),
        ).pack(pady=(24, 0))

    def _append_log(self, text: str) -> None:
        if self._server_log is None:
            return
        self._server_log.configure(state=tk.NORMAL)
        self._server_log.insert(tk.END, text)
        self._server_log.see(tk.END)
        self._server_log.configure(state=tk.DISABLED)

    def _drain_log_queue(self) -> None:
        try:
            while True:
                line = self._log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        if self._server_proc is not None and self._server_proc.poll() is not None:
            self._server_proc = None
            self._var_status.set("Strežnik: ustavljen (proces se je končal)")
            self._btn_start.configure(state=tk.NORMAL)
            self._btn_stop.configure(state=tk.DISABLED)
        self.after(120, self._drain_log_queue)

    def _server_clear_log(self) -> None:
        if self._server_log is None:
            return
        self._server_log.configure(state=tk.NORMAL)
        self._server_log.delete("1.0", tk.END)
        self._server_log.configure(state=tk.DISABLED)

    def _server_start(self) -> None:
        if self._server_proc is not None and self._server_proc.poll() is None:
            return

        host = self._var_host.get().strip() or "0.0.0.0"
        port_s = self._var_port.get().strip()
        try:
            port = int(port_s)
        except ValueError:
            self._append_log("[napaka] Neveljavna številka vrat.\n")
            return
        if not (1 <= port <= 65535):
            self._append_log("[napaka] Vrata morajo biti med 1 in 65535.\n")
            return

        self._log_queue.put(f"\n[GUI] Zagon: uvicorn API.main:app --host={host} --port={port}\n")
        proc, err = start_uvicorn(host, port, self._log_queue)
        if err:
            self._log_queue.put(f"[napaka] Ni mogoče zagnati: {err}\n")
            self._var_status.set("Strežnik: napaka pri zagonu")
            return

        self._server_proc = proc
        local_url = f"http://127.0.0.1:{port}/ui/"
        self._var_status.set(f"Strežnik: teče — odprite {local_url}")
        self._btn_start.configure(state=tk.DISABLED)
        self._btn_stop.configure(state=tk.NORMAL)

    def _server_stop(self) -> None:
        if self._server_proc is None:
            return
        self._log_queue.put("\n[GUI] Ustavljam strežnik …\n")
        stop_process(self._server_proc)
        self._server_proc = None
        self._var_status.set("Strežnik: ustavljen")
        self._btn_start.configure(state=tk.NORMAL)
        self._btn_stop.configure(state=tk.DISABLED)

    def _on_close_window(self) -> None:
        stop_process(self._server_proc)
        self._server_proc = None
        self.destroy()

    def _build_ai_page(self) -> None:
        page = tk.Frame(self._container, bg=COLORS["bg"])
        self._pages["ai"] = page
        self._page_header(page, "AI / LLM")

        outer = tk.Frame(page, bg=COLORS["bg"])
        outer.pack(fill=tk.BOTH, expand=True, padx=24, pady=16)

        canvas = tk.Canvas(outer, bg=COLORS["bg"], highlightthickness=0)
        sb = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        body = tk.Frame(canvas, bg=COLORS["bg"])
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        inner_win = canvas.create_window((0, 0), window=body, anchor=tk.NW)

        def _on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfig(inner_win, width=max(event.width - 4, 1))

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        card = tk.Frame(body, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        pad = tk.Frame(card, bg=COLORS["card"])
        pad.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        tk.Label(
            pad,
            text="Nastavitve se zapišejo v .env v korenu projekta. Po spremembi ponovno zaženite API strežnik.",
            font=("Segoe UI", 9),
            fg=COLORS["muted"],
            bg=COLORS["card"],
            wraplength=820,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 14))

        self._ai_mode = tk.StringVar(value="local")
        mode_row = tk.Frame(pad, bg=COLORS["card"])
        mode_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(mode_row, text="Način", font=self._nav_font, fg=COLORS["text"], bg=COLORS["card"]).pack(anchor=tk.W)
        mr = tk.Frame(mode_row, bg=COLORS["card"])
        mr.pack(anchor=tk.W, pady=(6, 0))
        tk.Radiobutton(
            mr,
            text="Lokalni model (Hugging Face / CUDA)",
            variable=self._ai_mode,
            value="local",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["card"],
            selectcolor=COLORS["bg"],
            activebackground=COLORS["card"],
            command=self._ai_refresh_mode_visibility,
        ).pack(anchor=tk.W)
        tk.Radiobutton(
            mr,
            text="API ponudnik (OpenAI ali Gemini)",
            variable=self._ai_mode,
            value="api",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["card"],
            selectcolor=COLORS["bg"],
            activebackground=COLORS["card"],
            command=self._ai_refresh_mode_visibility,
        ).pack(anchor=tk.W)

        self._ai_local_frame = tk.LabelFrame(
            pad,
            text="Lokalni model",
            font=self._subtitle_font,
            fg=COLORS["accent"],
            bg=COLORS["card"],
            bd=0,
            highlightthickness=0,
        )
        self._ai_base_model = tk.StringVar(value="cjvt/GaMS3-12B-Instruct")
        self._ai_4bit = tk.IntVar(value=1)
        self._ai_offload = tk.IntVar(value=1)
        self._ai_device_map = tk.StringVar(value="auto")
        self._ai_hf_token = tk.StringVar(value="")
        self._ai_row_entry(self._ai_local_frame, "LLM_BASE_MODEL_ID", self._ai_base_model)
        self._ai_row_check(self._ai_local_frame, "LLM_USE_4BIT (priporočeno na GPU)", self._ai_4bit)
        self._ai_row_check(self._ai_local_frame, "LLM_ENABLE_CPU_OFFLOAD", self._ai_offload)
        self._ai_row_entry(self._ai_local_frame, "LLM_DEVICE_MAP", self._ai_device_map)
        self._ai_row_entry(self._ai_local_frame, "HF_TOKEN (opcijsko)", self._ai_hf_token, show="*")

        self._ai_api_frame = tk.LabelFrame(
            pad,
            text="API",
            font=self._subtitle_font,
            fg=COLORS["accent"],
            bg=COLORS["card"],
            bd=0,
            highlightthickness=0,
        )
        prov_row = tk.Frame(self._ai_api_frame, bg=COLORS["card"])
        prov_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(prov_row, text="LLM_API_PROVIDER", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"]).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        self._ai_provider = tk.StringVar(value="openai")
        om = tk.OptionMenu(
            prov_row,
            self._ai_provider,
            "openai",
            "gemini",
            command=lambda *_: self._ai_refresh_provider_visibility(),
        )
        om.config(font=self._subtitle_font, fg=COLORS["text"], bg=COLORS["bg"], highlightthickness=0, bd=0)
        om.pack(side=tk.LEFT)

        self._ai_openai_frame = tk.Frame(self._ai_api_frame, bg=COLORS["card"])
        self._ai_o_key = tk.StringVar()
        self._ai_o_model = tk.StringVar()
        self._ai_o_base = tk.StringVar()
        self._ai_row_entry(self._ai_openai_frame, "OPENAI_API_KEY", self._ai_o_key, show="*")
        self._ai_row_entry(self._ai_openai_frame, "OPENAI_MODEL", self._ai_o_model)
        self._ai_row_entry(self._ai_openai_frame, "OPENAI_BASE_URL (opcijsko)", self._ai_o_base)

        self._ai_gemini_frame = tk.Frame(self._ai_api_frame, bg=COLORS["card"])
        self._ai_g_key = tk.StringVar()
        self._ai_g_model = tk.StringVar()
        self._ai_g_base = tk.StringVar(value="https://generativelanguage.googleapis.com/v1beta/openai/")
        self._ai_row_entry(self._ai_gemini_frame, "GEMINI_API_KEY", self._ai_g_key, show="*")
        self._ai_row_entry(self._ai_gemini_frame, "GEMINI_MODEL", self._ai_g_model)
        self._ai_row_entry(self._ai_gemini_frame, "GEMINI_BASE_URL", self._ai_g_base)

        btn_row = tk.Frame(pad, bg=COLORS["card"])
        btn_row.pack(fill=tk.X, pady=(16, 8))
        tk.Button(
            btn_row,
            text="Shrani v .env",
            font=self._nav_font,
            fg="#ffffff",
            bg=COLORS["accent"],
            activeforeground="#ffffff",
            activebackground=COLORS["accent_hover"],
            highlightthickness=0,
            bd=0,
            padx=20,
            pady=10,
            cursor="hand2",
            command=self._ai_save,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            btn_row,
            text="Naloži iz .env",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            activeforeground=COLORS["text"],
            activebackground=COLORS["border"],
            highlightthickness=0,
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._ai_load,
        ).pack(side=tk.LEFT)

        self._ai_status = tk.StringVar(value="")
        tk.Label(
            pad,
            textvariable=self._ai_status,
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["card"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(4, 0))

        self._ai_load()
        self._ai_refresh_mode_visibility()

    def _ai_row_entry(
        self,
        parent: tk.Widget,
        label: str,
        var: tk.StringVar,
        show: str | None = None,
    ) -> None:
        row = tk.Frame(parent, bg=COLORS["card"])
        row.pack(fill=tk.X, pady=6)
        tk.Label(row, text=label, font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], width=28, anchor=tk.W).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        e = tk.Entry(
            row,
            textvariable=var,
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            insertbackground=COLORS["text"],
            show=show or "",
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            bd=0,
        )
        e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, ipadx=6)

    def _ai_row_check(self, parent: tk.Widget, label: str, var: tk.IntVar) -> None:
        row = tk.Frame(parent, bg=COLORS["card"])
        row.pack(fill=tk.X, pady=4)
        tk.Checkbutton(
            row,
            text=label,
            variable=var,
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["card"],
            selectcolor=COLORS["bg"],
            activebackground=COLORS["card"],
        ).pack(anchor=tk.W)

    def _ai_refresh_mode_visibility(self) -> None:
        self._ai_local_frame.pack_forget()
        self._ai_api_frame.pack_forget()
        if self._ai_mode.get() == "local":
            self._ai_local_frame.pack(fill=tk.X, pady=(8, 0))
        else:
            self._ai_api_frame.pack(fill=tk.X, pady=(8, 0))
            self._ai_refresh_provider_visibility()

    def _ai_refresh_provider_visibility(self) -> None:
        self._ai_openai_frame.pack_forget()
        self._ai_gemini_frame.pack_forget()
        if self._ai_provider.get() == "gemini":
            self._ai_gemini_frame.pack(fill=tk.X, pady=(8, 0))
        else:
            self._ai_openai_frame.pack(fill=tk.X, pady=(8, 0))

    def _ai_load(self) -> None:
        d = read_env(self._env_path)
        use_local = d.get("USE_LOCAL_LLM", "1").strip().lower() in {"1", "true", "yes", "on"}
        self._ai_mode.set("local" if use_local else "api")
        self._ai_base_model.set(d.get("LLM_BASE_MODEL_ID", "").strip() or "cjvt/GaMS3-12B-Instruct")
        self._ai_4bit.set(1 if d.get("LLM_USE_4BIT", "1").strip().lower() in {"1", "true", "yes", "on"} else 0)
        self._ai_offload.set(1 if d.get("LLM_ENABLE_CPU_OFFLOAD", "1").strip().lower() in {"1", "true", "yes", "on"} else 0)
        self._ai_device_map.set(d.get("LLM_DEVICE_MAP", "auto"))
        self._ai_hf_token.set(d.get("HF_TOKEN", d.get("HUGGINGFACE_HUB_TOKEN", "")))
        prov = d.get("LLM_API_PROVIDER", "openai").strip().lower()
        self._ai_provider.set("gemini" if prov == "gemini" else "openai")
        self._ai_o_key.set(d.get("OPENAI_API_KEY", ""))
        self._ai_o_model.set(d.get("OPENAI_MODEL", ""))
        self._ai_o_base.set(d.get("OPENAI_BASE_URL", ""))
        self._ai_g_key.set(d.get("GEMINI_API_KEY", ""))
        self._ai_g_model.set(d.get("GEMINI_MODEL", ""))
        self._ai_g_base.set(d.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"))
        self._ai_status.set(f"Naloženo iz: {self._env_path}")
        self._ai_refresh_mode_visibility()

    def _ai_save(self) -> None:
        try:
            if self._ai_mode.get() == "local":
                tok = self._ai_hf_token.get().strip()
                updates: dict[str, str | None] = {
                    "USE_LOCAL_LLM": "1",
                    "LLM_BASE_MODEL_ID": self._ai_base_model.get().strip(),
                    "LLM_USE_4BIT": "1" if self._ai_4bit.get() else "0",
                    "LLM_ENABLE_CPU_OFFLOAD": "1" if self._ai_offload.get() else "0",
                    "LLM_DEVICE_MAP": self._ai_device_map.get().strip() or "auto",
                    "HF_TOKEN": tok if tok else "",
                    "HUGGINGFACE_HUB_TOKEN": "",
                    "LLM_API_PROVIDER": "",
                    "OPENAI_API_KEY": "",
                    "OPENAI_MODEL": "",
                    "OPENAI_BASE_URL": "",
                    "GEMINI_API_KEY": "",
                    "GEMINI_MODEL": "",
                    "GEMINI_BASE_URL": "",
                }
            else:
                prov = self._ai_provider.get()
                updates = {
                    "USE_LOCAL_LLM": "0",
                    "LLM_API_PROVIDER": prov,
                    "LLM_BASE_MODEL_ID": "",
                    "LLM_USE_4BIT": "",
                    "LLM_ENABLE_CPU_OFFLOAD": "",
                    "LLM_DEVICE_MAP": "",
                    "HF_TOKEN": "",
                    "HUGGINGFACE_HUB_TOKEN": "",
                }
                if prov == "openai":
                    updates["OPENAI_API_KEY"] = self._ai_o_key.get().strip()
                    updates["OPENAI_MODEL"] = self._ai_o_model.get().strip()
                    ob = self._ai_o_base.get().strip()
                    updates["OPENAI_BASE_URL"] = ob if ob else ""
                    updates["GEMINI_API_KEY"] = ""
                    updates["GEMINI_MODEL"] = ""
                    updates["GEMINI_BASE_URL"] = ""
                else:
                    updates["GEMINI_API_KEY"] = self._ai_g_key.get().strip()
                    updates["GEMINI_MODEL"] = self._ai_g_model.get().strip()
                    gb = self._ai_g_base.get().strip()
                    updates["GEMINI_BASE_URL"] = (
                        gb if gb else "https://generativelanguage.googleapis.com/v1beta/openai/"
                    )
                    updates["OPENAI_API_KEY"] = ""
                    updates["OPENAI_MODEL"] = ""
                    updates["OPENAI_BASE_URL"] = ""

            update_env_keys(self._env_path, updates)
            self._ai_status.set(f"Shranjeno v {self._env_path} — znova zaženite strežnik.")
        except OSError as exc:
            self._ai_status.set(f"Napaka: {exc}")

    def _build_index_page(self) -> None:
        page = tk.Frame(self._container, bg=COLORS["bg"])
        self._pages["index"] = page
        self._page_header(page, "Indeks (Pinecone)")

        body = tk.Frame(page, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=20)

        card = tk.Frame(body, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        pad = tk.Frame(card, bg=COLORS["card"])
        pad.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        tk.Label(
            pad,
            text="Ključ in ime indeksa se shranita v .env. Sprememba imena indeksa velja šele po ponovnem zagonu API strežnika. "
            "»Posodobi indeks« kliče GET /upsert/all (strežnik mora teči).",
            font=("Segoe UI", 9),
            fg=COLORS["muted"],
            bg=COLORS["card"],
            wraplength=820,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 14))

        self._idx_key = tk.StringVar()
        self._idx_name = tk.StringVar(value="sinji-delfini-test")
        self._idx_base = tk.StringVar(value="http://127.0.0.1:8000")
        self._idx_row(pad, "PINECONE_API_KEY", self._idx_key, show="*")
        self._idx_row(pad, "PINECONE_INDEX_NAME", self._idx_name)
        self._idx_row(pad, "Naslov API (za upsert)", self._idx_base)

        btn_row = tk.Frame(pad, bg=COLORS["card"])
        btn_row.pack(fill=tk.X, pady=(12, 8))
        tk.Button(
            btn_row,
            text="Shrani v .env",
            font=self._nav_font,
            fg="#ffffff",
            bg=COLORS["accent"],
            activeforeground="#ffffff",
            activebackground=COLORS["accent_hover"],
            highlightthickness=0,
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            command=self._idx_save,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            btn_row,
            text="Naloži iz .env",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            activeforeground=COLORS["text"],
            activebackground=COLORS["border"],
            highlightthickness=0,
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._idx_load,
        ).pack(side=tk.LEFT, padx=(0, 10))

        self._btn_idx_reindex = tk.Button(
            btn_row,
            text="Posodobi indeks",
            font=self._nav_font,
            fg=COLORS["text"],
            bg="#2a6b4f",
            activeforeground=COLORS["text"],
            activebackground=COLORS["accent"],
            highlightthickness=0,
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            command=self._idx_reindex,
        )
        self._btn_idx_reindex.pack(side=tk.LEFT)

        self._idx_status = tk.StringVar(value="")
        tk.Label(
            pad,
            textvariable=self._idx_status,
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["card"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(4, 8))

        tk.Label(pad, text="Odgovor strežnika", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], anchor=tk.W).pack(
            fill=tk.X
        )
        self._idx_out = scrolledtext.ScrolledText(
            pad,
            font=("Consolas", 10),
            fg=COLORS["text"],
            bg="#1e1c24",
            insertbackground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            bd=0,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=12,
        )
        self._idx_out.pack(fill=tk.BOTH, expand=True)

        self._idx_load()

    def _idx_row(self, parent: tk.Widget, label: str, var: tk.StringVar, show: str | None = None) -> None:
        row = tk.Frame(parent, bg=COLORS["card"])
        row.pack(fill=tk.X, pady=6)
        tk.Label(row, text=label, font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], width=22, anchor=tk.W).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        tk.Entry(
            row,
            textvariable=var,
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            insertbackground=COLORS["text"],
            show=show or "",
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            bd=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, ipadx=6)

    def _idx_load(self) -> None:
        d = read_env(self._env_path)
        self._idx_key.set(d.get("PINECONE_API_KEY", ""))
        self._idx_name.set(d.get("PINECONE_INDEX_NAME", "").strip() or "sinji-delfini-test")
        self._idx_status.set(f"Naloženo iz {self._env_path}")

    def _idx_save(self) -> None:
        try:
            update_env_keys(
                self._env_path,
                {
                    "PINECONE_API_KEY": self._idx_key.get().strip() or "",
                    "PINECONE_INDEX_NAME": self._idx_name.get().strip() or "",
                },
            )
            self._idx_status.set("Shranjeno — ob spremembi indeksa znova zaženite strežnik.")
        except OSError as exc:
            self._idx_status.set(f"Napaka: {exc}")

    def _idx_reindex(self) -> None:
        if self._idx_busy:
            return
        base = self._idx_base.get().strip().rstrip("/")
        if not base:
            self._idx_status.set("Vnesite naslov API.")
            return
        url = f"{base}/upsert/all"
        self._idx_busy = True
        self._btn_idx_reindex.configure(state=tk.DISABLED)
        self._idx_status.set("Poteka upsert … (lahko traja dlje)")

        def work() -> None:
            ok = False
            raw = ""
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=7200) as resp:
                    ok = True
                    raw = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                try:
                    raw = exc.read().decode("utf-8", errors="replace")
                except OSError:
                    raw = str(exc)
                raw = f"HTTP {exc.code}\n{raw}"
            except Exception as exc:
                raw = str(exc)
            self.after(0, lambda o=ok, t=raw: self._idx_reindex_done(o, t))

        threading.Thread(target=work, daemon=True).start()

    def _idx_reindex_done(self, ok: bool, text: str) -> None:
        self._idx_busy = False
        self._btn_idx_reindex.configure(state=tk.NORMAL)
        if ok:
            self._idx_status.set("Upsert končan.")
        else:
            self._idx_status.set("Upsert ni uspel (glej spodaj).")
        display = text
        if text.strip():
            try:
                display = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass
        self._idx_out.configure(state=tk.NORMAL)
        self._idx_out.delete("1.0", tk.END)
        self._idx_out.insert(tk.END, display or "(prazen odgovor)")
        self._idx_out.configure(state=tk.DISABLED)

    def _build_documents_page(self) -> None:
        page = tk.Frame(self._container, bg=COLORS["bg"])
        self._pages["documents"] = page
        self._page_header(page, "Dokumenti")

        body = tk.Frame(page, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=20)

        card = tk.Frame(body, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        pad = tk.Frame(card, bg=COLORS["card"])
        pad.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        tk.Label(
            pad,
            text="Mapa z datotekami .txt in .csv. Pot lahko nastavite z .env ključem DATA_DOCUMENTS_DIR "
            "(absolutna ali relativna na koren projekta). Po spremembi znova zaženite strežnik; za Pinecone še »Posodobi indeks«.",
            font=("Segoe UI", 9),
            fg=COLORS["muted"],
            bg=COLORS["card"],
            wraplength=820,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 14))

        self._doc_path = tk.StringVar(value=str(REPO_ROOT / "data" / "documents"))
        path_row = tk.Frame(pad, bg=COLORS["card"])
        path_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(path_row, text="Mapa dokumentov", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], width=18, anchor=tk.W).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        tk.Entry(
            path_row,
            textvariable=self._doc_path,
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            insertbackground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            bd=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, ipadx=6)
        tk.Button(
            path_row,
            text="Izberi …",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            activebackground=COLORS["border"],
            highlightthickness=0,
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._doc_browse,
        ).pack(side=tk.LEFT, padx=(8, 0))

        btn_row = tk.Frame(pad, bg=COLORS["card"])
        btn_row.pack(fill=tk.X, pady=(0, 10))
        tk.Button(
            btn_row,
            text="Shrani v .env",
            font=self._nav_font,
            fg="#ffffff",
            bg=COLORS["accent"],
            activeforeground="#ffffff",
            activebackground=COLORS["accent_hover"],
            highlightthickness=0,
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
            command=self._doc_save,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            btn_row,
            text="Naloži iz .env",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._doc_load,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            btn_row,
            text="Osveži seznam",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._doc_refresh_list,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            btn_row,
            text="Odpri mapo",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._doc_open_folder,
        ).pack(side=tk.LEFT)

        self._doc_status = tk.StringVar(value="")
        tk.Label(
            pad,
            textvariable=self._doc_status,
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["card"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 8))

        tk.Label(pad, text="Datoteke .txt in .csv v mapi", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], anchor=tk.W).pack(
            fill=tk.X
        )
        list_frame = tk.Frame(pad, bg=COLORS["card"])
        list_frame.pack(fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(list_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._doc_list = tk.Listbox(
            list_frame,
            font=("Consolas", 10),
            fg=COLORS["text"],
            bg="#1e1c24",
            selectbackground=COLORS["accent"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            bd=0,
            yscrollcommand=sb.set,
        )
        self._doc_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._doc_list.yview)

        self._doc_load()
        self._doc_refresh_list()

    def _doc_resolved_dir(self) -> Path:
        raw = self._doc_path.get().strip()
        if not raw:
            return (REPO_ROOT / "data" / "documents").resolve()
        p = Path(raw)
        if not p.is_absolute():
            p = (REPO_ROOT / p).resolve()
        return p

    def _doc_browse(self) -> None:
        initial = self._doc_resolved_dir()
        if not initial.is_dir():
            initial = REPO_ROOT
        picked = filedialog.askdirectory(title="Mapa z dokumenti", initialdir=str(initial))
        if picked:
            self._doc_path.set(picked)
            self._doc_refresh_list()

    def _doc_load(self) -> None:
        d = read_env(self._env_path)
        env_p = d.get("DATA_DOCUMENTS_DIR", "").strip()
        if env_p:
            self._doc_path.set(env_p)
        else:
            self._doc_path.set(str((REPO_ROOT / "data" / "documents").resolve()))
        self._doc_status.set(f"Naloženo iz {self._env_path}")
        self._doc_refresh_list()

    def _doc_save(self) -> None:
        try:
            resolved = self._doc_resolved_dir()
            # shranimo absolutno pot za nedvoumnost
            update_env_keys(
                self._env_path,
                {"DATA_DOCUMENTS_DIR": str(resolved)},
            )
            self._doc_path.set(str(resolved))
            self._doc_status.set("Shranjeno — znova zaženite strežnik.")
            self._doc_refresh_list()
        except OSError as exc:
            self._doc_status.set(f"Napaka: {exc}")

    def _doc_refresh_list(self) -> None:
        self._doc_list.delete(0, tk.END)
        folder = self._doc_resolved_dir()
        if not folder.is_dir():
            self._doc_list.insert(tk.END, f"(mapa ne obstaja: {folder})")
            return
        names = sorted(
            f.name
            for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in {".txt", ".csv"}
        )
        if not names:
            self._doc_list.insert(tk.END, "(ni datotek .txt / .csv)")
            return
        for n in names:
            self._doc_list.insert(tk.END, n)

    def _doc_open_folder(self) -> None:
        folder = self._doc_resolved_dir()
        if not folder.is_dir():
            self._doc_status.set("Mapa ne obstaja.")
            return
        path = str(folder)
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self._doc_status.set("Mapa odprta v sistemu.")
        except OSError as exc:
            self._doc_status.set(f"Ni mogoče odpreti: {exc}")

    def _groups_db(self):
        try:
            from DB.db import Db
        except ImportError:
            root = str(REPO_ROOT)
            if root not in sys.path:
                sys.path.insert(0, root)
            from DB.db import Db

        return Db(db_path=str(REPO_ROOT / "DB" / "app.db"), init_schema_on_start=False)

    def _build_groups_page(self) -> None:
        page = tk.Frame(self._container, bg=COLORS["bg"])
        self._pages["groups"] = page
        self._page_header(page, "Skupine")

        body = tk.Frame(page, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=20)

        card = tk.Frame(body, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        pad = tk.Frame(card, bg=COLORS["card"])
        pad.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        tk.Label(
            pad,
            text="Skupine v SQLite (tabela groups). Brisanje odstrani tudi povezave v user_group in document_group. "
            "Med urejanjem je bolje ustaviti API strežnik (zaklep baze).",
            font=("Segoe UI", 9),
            fg=COLORS["muted"],
            bg=COLORS["card"],
            wraplength=820,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 12))

        self._grp_rows: list[tuple[int, str]] = []
        list_fr = tk.Frame(pad, bg=COLORS["card"])
        list_fr.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        gsb = tk.Scrollbar(list_fr)
        gsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._grp_list = tk.Listbox(
            list_fr,
            font=("Segoe UI", 11),
            fg=COLORS["text"],
            bg="#1e1c24",
            selectbackground=COLORS["accent"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            bd=0,
            height=10,
            yscrollcommand=gsb.set,
        )
        self._grp_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        gsb.config(command=self._grp_list.yview)
        self._grp_list.bind("<<ListboxSelect>>", self._grp_on_select)

        form = tk.Frame(pad, bg=COLORS["card"])
        form.pack(fill=tk.X)

        row1 = tk.Frame(form, bg=COLORS["card"])
        row1.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row1, text="Nova skupina", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], width=14, anchor=tk.W).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self._grp_new_name = tk.StringVar()
        tk.Entry(
            row1,
            textvariable=self._grp_new_name,
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            insertbackground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            bd=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, ipadx=6)
        tk.Button(
            row1,
            text="Dodaj",
            font=self._subtitle_font,
            fg="#ffffff",
            bg=COLORS["accent"],
            activebackground=COLORS["accent_hover"],
            highlightthickness=0,
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._grp_add,
        ).pack(side=tk.LEFT, padx=(10, 0))

        row2 = tk.Frame(form, bg=COLORS["card"])
        row2.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row2, text="Uredi ime", font=self._subtitle_font, fg=COLORS["muted"], bg=COLORS["card"], width=14, anchor=tk.W).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self._grp_edit_name = tk.StringVar()
        tk.Entry(
            row2,
            textvariable=self._grp_edit_name,
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["bg"],
            insertbackground=COLORS["text"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["accent"],
            bd=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, ipadx=6)
        tk.Button(
            row2,
            text="Shrani ime",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._grp_rename,
        ).pack(side=tk.LEFT, padx=(10, 0))

        btn_row = tk.Frame(pad, bg=COLORS["card"])
        btn_row.pack(fill=tk.X, pady=(4, 8))
        tk.Button(
            btn_row,
            text="Osveži seznam",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
            highlightthickness=0,
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._grp_refresh,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            btn_row,
            text="Izbriši izbrano",
            font=self._subtitle_font,
            fg=COLORS["text"],
            bg="#5c3030",
            activebackground="#703838",
            highlightthickness=0,
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._grp_delete,
        ).pack(side=tk.LEFT)

        self._grp_status = tk.StringVar(value="")
        tk.Label(
            pad,
            textvariable=self._grp_status,
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["card"],
            anchor=tk.W,
        ).pack(fill=tk.X)

        self._grp_refresh()

    def _grp_on_select(self, _event: tk.Event | None = None) -> None:
        idxs = self._grp_list.curselection()
        if not idxs:
            return
        self._grp_edit_name.set(self._grp_rows[idxs[0]][1])

    def _grp_selected_id(self) -> int | None:
        idxs = self._grp_list.curselection()
        if not idxs:
            return None
        return self._grp_rows[idxs[0]][0]

    def _grp_refresh(self) -> None:
        self._grp_list.delete(0, tk.END)
        self._grp_rows = []
        db = self._groups_db()
        try:
            rows = db.list_groups()
        except Exception as exc:
            self._grp_status.set(f"Napaka: {exc}")
        else:
            self._grp_rows = [(r["id"], r["name"]) for r in rows]
            for _gid, name in self._grp_rows:
                self._grp_list.insert(tk.END, name)
            self._grp_status.set(f"{len(self._grp_rows)} skupin — {REPO_ROOT / 'DB' / 'app.db'}")
        finally:
            db.close()

    def _grp_add(self) -> None:
        name = self._grp_new_name.get().strip()
        if not name:
            messagebox.showwarning("Skupine", "Vnesite ime nove skupine.")
            return
        db = self._groups_db()
        try:
            db.create_group(name)
            self._grp_new_name.set("")
            self._grp_status.set("Skupina dodana.")
            self._grp_refresh()
        except sqlite3.IntegrityError:
            messagebox.showerror("Skupine", "Skupina s tem imenom že obstaja.")
        except ValueError as exc:
            messagebox.showerror("Skupine", str(exc))
        finally:
            db.close()

    def _grp_rename(self) -> None:
        gid = self._grp_selected_id()
        if gid is None:
            messagebox.showinfo("Skupine", "Izberite skupino na seznamu.")
            return
        name = self._grp_edit_name.get().strip()
        if not name:
            messagebox.showwarning("Skupine", "Ime ne sme biti prazno.")
            return
        db = self._groups_db()
        try:
            db.update_group(gid, name)
            self._grp_status.set("Ime posodobljeno.")
            self._grp_refresh()
        except sqlite3.IntegrityError:
            messagebox.showerror("Skupine", "Skupina s tem imenom že obstaja.")
        except ValueError as exc:
            messagebox.showerror("Skupine", str(exc))
        finally:
            db.close()

    def _grp_delete(self) -> None:
        gid = self._grp_selected_id()
        if gid is None:
            messagebox.showinfo("Skupine", "Izberite skupino na seznamu.")
            return
        name = self._grp_rows[self._grp_list.curselection()[0]][1]
        if not messagebox.askyesno(
            "Skupine",
            f"Izbrisati skupino »{name}«? Povezave z uporabniki in dokumenti bodo odstranjene.",
        ):
            return
        db = self._groups_db()
        try:
            if db.delete_group(gid):
                self._grp_status.set("Skupina izbrisana.")
                self._grp_edit_name.set("")
            else:
                messagebox.showwarning("Skupine", "Skupina ni bila najdena.")
            self._grp_refresh()
        finally:
            db.close()

    def _build_placeholders(self) -> None:
        titles = {
            "users": "Uporabniki",
            "permissions": "Pravice do dokumentov",
            "backup": "Varnostno kopiranje",
        }
        for key, title in titles.items():
            self._pages[key] = self._placeholder_page(title)

    def _placeholder_page(self, title: str) -> tk.Frame:
        page = tk.Frame(self._container, bg=COLORS["bg"])
        self._page_header(page, title)

        body = tk.Frame(page, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=40, pady=32)

        card = tk.Frame(body, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(expand=True, pady=48, padx=32)

        tk.Label(
            inner,
            text="Ta modul bo na voljo v naslednji fazi.",
            font=self._body_font,
            fg=COLORS["text"],
            bg=COLORS["card"],
            wraplength=520,
            justify=tk.CENTER,
        ).pack()

        tk.Label(
            inner,
            text="Tukaj boste urejali nastavitve in podatke za to področje.",
            font=self._subtitle_font,
            fg=COLORS["muted"],
            bg=COLORS["card"],
            wraplength=520,
            justify=tk.CENTER,
        ).pack(pady=(12, 0))

        return page

    def show_page(self, name: str) -> None:
        for child in self._container.winfo_children():
            child.pack_forget()

        page = self._pages.get(name)
        if page is None:
            return
        page.pack(fill=tk.BOTH, expand=True)


def main() -> None:
    app = SinjiDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
