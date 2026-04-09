from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Db:
    def __init__(
        self,
        db_path: str = "DB/app.db",
        schema_path: str | None = None,
        seed_path: str | None = None,
        data_documents_dir: str | None = None,
        data_permissions_path: str | None = None,
        init_schema_on_start: bool = True,
    ) -> None:
        self.db_path = db_path
        project_root = Path(__file__).resolve().parents[1]
        self.schema_path = schema_path or str(Path(__file__).with_name("sqlite_init.sql"))
        self.seed_path = seed_path or str(Path(__file__).with_name("seed.sql"))
        self.data_documents_dir = data_documents_dir or str(project_root / "data" / "documents")
        self.data_permissions_path = data_permissions_path or str(project_root / "data" / "permissions.json")

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        if init_schema_on_start:
            self.init_schema()

    def init_schema(self) -> None:
        schema_sql = Path(self.schema_path).read_text(encoding="utf-8")
        with self.conn:
            self.conn.executescript(schema_sql)

    def seed(self, password_hash: str) -> dict[str, Any]:
        self.init_schema()
        escaped_password_hash = password_hash.replace("'", "''")
        seed_sql = Path(self.seed_path).read_text(encoding="utf-8")
        seed_sql = seed_sql.replace("__PASSWORD_HASH__", escaped_password_hash)
        with self.conn:
            self.conn.executescript(seed_sql)
        dynamic_summary = self._seed_documents_from_data()
        return dynamic_summary

    def _seed_documents_from_data(self) -> dict[str, Any]:
        permissions_raw = Path(self.data_permissions_path).read_text(encoding="utf-8")
        permissions = json.loads(permissions_raw)

        permissions_by_document: dict[str, list[str]] = {}
        for entry in permissions:
            document_name = entry.get("dokument")
            allowed_groups = entry.get("allowed_groups", [])
            if not document_name or not isinstance(allowed_groups, list):
                continue
            permissions_by_document[document_name] = [str(group) for group in allowed_groups]

        documents_dir = Path(self.data_documents_dir)
        files_in_directory = sorted(
            file.name
            for file in documents_dir.iterdir()
            if file.is_file() and file.suffix.lower() in {".txt", ".csv"}
        )
        files_set = set(files_in_directory)
        permissions_set = set(permissions_by_document.keys())

        skipped_files_missing_permissions = sorted(
            document_name for document_name in files_in_directory if document_name not in permissions_set
        )
        ignored_permissions_missing_files = sorted(
            document_name for document_name in permissions_set if document_name not in files_set
        )

        seeded_documents: list[str] = []
        seeded_groups_from_permissions: set[str] = set()

        with self.conn:
            for document_name in files_in_directory:
                allowed_groups = permissions_by_document.get(document_name)
                if allowed_groups is None:
                    continue

                self.conn.execute(
                    "INSERT OR IGNORE INTO documents(name) VALUES (?)",
                    (document_name,),
                )

                document_row = self.conn.execute(
                    "SELECT id FROM documents WHERE name = ? LIMIT 1",
                    (document_name,),
                ).fetchone()
                if document_row is None:
                    continue
                document_id = int(document_row["id"])

                for group_name in allowed_groups:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO groups(name) VALUES (?)",
                        (group_name,),
                    )
                    seeded_groups_from_permissions.add(group_name)

                    group_row = self.conn.execute(
                        "SELECT id FROM groups WHERE name = ? LIMIT 1",
                        (group_name,),
                    ).fetchone()
                    if group_row is None:
                        continue

                    self.conn.execute(
                        "INSERT OR IGNORE INTO document_group(document_id, group_id) VALUES (?, ?)",
                        (document_id, int(group_row["id"])),
                    )

                seeded_documents.append(document_name)

        return {
            "seeded_documents": seeded_documents,
            "seeded_groups_from_permissions": sorted(seeded_groups_from_permissions),
            "skipped_files_missing_permissions": skipped_files_missing_permissions,
            "ignored_permissions_missing_files": ignored_permissions_missing_files,
        }

    def fetch_documents_with_groups(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT d.name AS document_name, g.name AS group_name
            FROM documents d
            LEFT JOIN document_group dg ON dg.document_id = d.id
            LEFT JOIN groups g ON g.id = dg.group_id
            ORDER BY d.name, g.name
            """
        ).fetchall()

        grouped: dict[str, list[str]] = {}
        for row in rows:
            document_name = row["document_name"]
            group_name = row["group_name"]
            grouped.setdefault(document_name, [])
            if group_name is not None:
                grouped[document_name].append(group_name)

        return [
            {
                "document_name": document_name,
                "allowed_groups": sorted(set(group_names)),
            }
            for document_name, group_names in grouped.items()
        ]

    def get_user_groups(self, user_id: int) -> list[str]:
        cursor = self.conn.execute(
            """
            SELECT g.name
            FROM groups g
            JOIN user_group ug ON ug.group_id = g.id
            WHERE ug.user_id = ?
            ORDER BY g.name
            """,
            (user_id,),
        )
        return [row["name"] for row in cursor.fetchall()]

    def cleanup_expired_revoked_tokens(self, now_ts: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM revoked_token WHERE expires_at < ?", (now_ts,))

    def is_token_revoked(self, jti: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM revoked_token WHERE jti = ? LIMIT 1",
            (jti,),
        ).fetchone()
        return row is not None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, name FROM users WHERE id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "name": row["name"]}

    def get_user_for_login(self, username: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, name, password_hash FROM users WHERE name = ? LIMIT 1",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "password_hash": row["password_hash"],
        }

    def create_user(self, username: str, password_hash: str) -> int:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO users(name, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
        return int(cursor.lastrowid)

    def revoke_token(self, jti: str, expires_at: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO revoked_token(jti, expires_at) VALUES (?, ?)",
                (jti, expires_at),
            )

    def reset_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        tables = [row[0] for row in cursor.fetchall()]

        with self.conn:
            for table_name in tables:
                self.conn.execute(f'DROP TABLE IF EXISTS "{table_name}";')

        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.init_schema()

    def close(self) -> None:
        if getattr(self, "conn", None) is not None:
            self.conn.close()
