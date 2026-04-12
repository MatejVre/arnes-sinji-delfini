from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont


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
        self._build_welcome()
        self._build_placeholders()

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

        hint = tk.Label(
            welcome,
            text="Poznejša različica bo povezala module z dejansko konfiguracijo in storitvijo.",
            font=("Segoe UI", 9),
            fg=COLORS["muted"],
            bg=COLORS["bg"],
        )
        hint.pack(side=tk.BOTTOM, pady=16)

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

    def _build_placeholders(self) -> None:
        titles = {
            "documents": "Dokumenti",
            "groups": "Skupine",
            "users": "Uporabniki",
            "permissions": "Pravice do dokumentov",
            "ai": "AI / LLM",
            "index": "Indeks (Pinecone)",
            "server": "Strežnik in omrežje",
            "backup": "Varnostno kopiranje",
            "logs": "Dnevnik / konzola",
        }
        for key, title in titles.items():
            self._pages[key] = self._placeholder_page(title)

    def _placeholder_page(self, title: str) -> tk.Frame:
        page = tk.Frame(self._container, bg=COLORS["bg"])

        header = tk.Frame(page, bg=COLORS["bg_elevated"], height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        back_btn = tk.Button(
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
        )
        back_btn.pack(side=tk.LEFT)

        tk.Label(
            header,
            text=title,
            font=self._nav_font,
            fg=COLORS["text"],
            bg=COLORS["bg_elevated"],
        ).pack(side=tk.LEFT, padx=(8, 0))

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
