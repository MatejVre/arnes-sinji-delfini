from __future__ import annotations

from pathlib import Path

""" simple read/write .env file"""

def _unquote(val: str) -> str:
    v = val.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def _quote(val: str) -> str:
    if not val:
        return '""'
    if any(c in val for c in ' \t#"\''):
        return '"' + val.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return val


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        if not key:
            continue
        out[key] = _unquote(rest)
    return out


def write_env(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={_quote(v)}" for k, v in sorted(data.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_env_keys(path: Path, updates: dict[str, str | None]) -> None:
    """Združi v obstoječi .env; None = preskok, \"\" = odstrani ključ."""
    current = read_env(path)
    for key, value in updates.items():
        if value is None:
            continue
        stripped = value.strip()
        if stripped == "":
            current.pop(key, None)
        else:
            current[key] = stripped
    write_env(path, current)
