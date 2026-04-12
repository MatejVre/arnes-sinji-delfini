from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont
from tkinter import scrolledtext

try:
    from desktop.server_panel import REPO_ROOT, start_uvicorn, stop_process
except ImportError:
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

        self._build_welcome()
        self._build_server_page()
        self._build_logs_page()
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

    def _build_placeholders(self) -> None:
        titles = {
            "documents": "Dokumenti",
            "groups": "Skupine",
            "users": "Uporabniki",
            "permissions": "Pravice do dokumentov",
            "ai": "AI / LLM",
            "index": "Indeks (Pinecone)",
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
