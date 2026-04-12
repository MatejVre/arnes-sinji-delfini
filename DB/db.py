from __future__ import annotations

import json
import os
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
        if data_documents_dir is not None:
            p = Path(data_documents_dir)
            if not p.is_absolute():
                p = (project_root / p).resolve()
            self.data_documents_dir = str(p)
        else:
            env_dir = os.getenv("DATA_DOCUMENTS_DIR", "").strip()
            if env_dir:
                p = Path(env_dir)
                if not p.is_absolute():
                    p = (project_root / p).resolve()
                self.data_documents_dir = str(p)
            else:
                self.data_documents_dir = str((project_root / "data" / "documents").resolve())
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
        self._apply_schema_migrations()

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
            SELECT d.id AS document_id, d.name AS document_name, g.name AS group_name
            FROM documents d
            LEFT JOIN document_group dg ON dg.document_id = d.id
            LEFT JOIN groups g ON g.id = dg.group_id
            ORDER BY d.name, g.name
            """
        ).fetchall()

        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            document_id = int(row["document_id"])
            document_name = row["document_name"]
            group_name = row["group_name"]
            if document_id not in grouped:
                grouped[document_id] = {
                    "document_id": document_id,
                    "document_name": document_name,
                    "allowed_groups": [],
                }
            if group_name is not None:
                grouped[document_id]["allowed_groups"].append(group_name)

        result: list[dict[str, Any]] = []
        for document_id in sorted(grouped.keys()):
            item = grouped[document_id]
            item["allowed_groups"] = sorted(set(item["allowed_groups"]))
            result.append(item)
        return result

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

    def list_groups(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name FROM groups ORDER BY name COLLATE NOCASE",
        ).fetchall()
        return [{"id": int(row["id"]), "name": row["name"]} for row in rows]

    def create_group(self, name: str) -> int:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Ime skupine ne sme biti prazno.")
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO groups(name) VALUES (?)",
                (cleaned,),
            )
        return int(cursor.lastrowid)

    def update_group(self, group_id: int, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Ime skupine ne sme biti prazno.")
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE groups SET name = ? WHERE id = ?",
                (cleaned, group_id),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Skupina z id {group_id} ne obstaja.")

    def delete_group(self, group_id: int) -> bool:
        with self.conn:
            cursor = self.conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        return cursor.rowcount > 0

    def get_chat_owner_id(self, chat_id: int) -> int | None:
        row = self.conn.execute(
            "SELECT user_id FROM chat WHERE id = ? LIMIT 1",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        return int(row["user_id"])

    def get_chat_meta(self, chat_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, user_id, name FROM chat WHERE id = ? LIMIT 1",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "user_id": int(row["user_id"]),
            "name": row["name"],
        }

    def fetch_latest_chat_messages(self, chat_id: int, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        rows = self.conn.execute(
            """
            SELECT role, content, created_at
            FROM chat_message
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()

        messages = [
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        messages.reverse()
        return messages

    def insert_chat_message(self, chat_id: int, role: str, content: str) -> int:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO chat_message(chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content),
            )
        return int(cursor.lastrowid)

    def insert_chat_message_documents(self, chat_message_id: int, document_ids: list[int]) -> None:
        unique_ids = sorted(set(int(document_id) for document_id in document_ids if isinstance(document_id, int) or str(document_id).isdigit()))
        if not unique_ids:
            return

        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO chat_message_document(chat_message_id, document_id) VALUES (?, ?)",
                [(chat_message_id, document_id) for document_id in unique_ids],
            )

    def extract_unique_allowed_document_ids(self, allowed_matches: list[dict[str, Any]]) -> list[int]:
        doc_ids: set[int] = set()
        doc_names: set[str] = set()

        for match in allowed_matches:
            metadata = match.get("metadata") or {}

            document_id = metadata.get("document_id")
            if isinstance(document_id, int):
                doc_ids.add(document_id)
            elif isinstance(document_id, str) and document_id.isdigit():
                doc_ids.add(int(document_id))

            document_name = metadata.get("document_name")
            if isinstance(document_name, str) and document_name.strip():
                doc_names.add(document_name.strip())

        if doc_names:
            placeholders = ",".join("?" for _ in doc_names)
            rows = self.conn.execute(
                f"SELECT id FROM documents WHERE name IN ({placeholders})",
                tuple(sorted(doc_names)),
            ).fetchall()
            for row in rows:
                doc_ids.add(int(row["id"]))

        return sorted(doc_ids)

    def get_chat(self, chat_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, role, content, created_at
            FROM chat_message
            WHERE chat_id = ?
            ORDER BY id ASC
            """,
            (chat_id,),
        ).fetchall()

        messages = [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
                "documents": [],
            }
            for row in rows
        ]

        message_ids = [int(message["id"]) for message in messages]
        if not message_ids:
            return messages

        placeholders = ",".join("?" for _ in message_ids)
        source_rows = self.conn.execute(
            f"""
            SELECT
                cmd.chat_message_id,
                d.id AS document_id,
                d.name AS document_name
            FROM chat_message_document cmd
            JOIN documents d ON d.id = cmd.document_id
            WHERE cmd.chat_message_id IN ({placeholders})
            ORDER BY cmd.chat_message_id ASC, d.name ASC
            """,
            tuple(message_ids),
        ).fetchall()

        docs_by_message_id: dict[int, list[dict[str, Any]]] = {}
        for row in source_rows:
            chat_message_id = int(row["chat_message_id"])
            docs_by_message_id.setdefault(chat_message_id, []).append(
                {
                    "document_id": int(row["document_id"]),
                    "document_name": row["document_name"],
                }
            )

        for message in messages:
            message["documents"] = docs_by_message_id.get(int(message["id"]), [])

        return messages

    def get_chat_for_user(self, chat_id: int, user_id: int) -> dict[str, Any]:
        chat_meta = self.get_chat_meta(chat_id)
        if chat_meta is None:
            return {"status": "not_found", "chat": None}
        if chat_meta["user_id"] != user_id:
            return {"status": "forbidden", "chat": None}

        return {
            "status": "ok",
            "chat": {
                "id": chat_meta["id"],
                "user_id": chat_meta["user_id"],
                "name": chat_meta["name"],
                "messages": self.get_chat(chat_id),
            },
        }

    def list_user_chats(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                c.id,
                c.name,
                c.user_id,
                MAX(cm.created_at) AS last_message_at,
                COUNT(cm.id) AS message_count
            FROM chat c
            LEFT JOIN chat_message cm ON cm.chat_id = c.id
            WHERE c.user_id = ?
            GROUP BY c.id, c.name, c.user_id
            ORDER BY c.id DESC
            """,
            (user_id,),
        ).fetchall()

        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "user_id": int(row["user_id"]),
                "last_message_at": row["last_message_at"],
                "message_count": int(row["message_count"]),
            }
            for row in rows
        ]

    def create_chat(self, user_id: int) -> int:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO chat(user_id) VALUES (?)",
                (user_id,),
            )
        return int(cursor.lastrowid)

    def set_chat_name(self, chat_id: int, name: str | None) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE chat SET name = ? WHERE id = ?",
                (name, chat_id),
            )

    def delete_chat(self, chat_id: int) -> bool:
        with self.conn:
            cursor = self.conn.execute("DELETE FROM chat WHERE id = ?", (chat_id,))
        return cursor.rowcount > 0

    def delete_chat_for_user(self, chat_id: int, user_id: int) -> str:
        owner_id = self.get_chat_owner_id(chat_id)
        if owner_id is None:
            return "not_found"
        if owner_id != user_id:
            return "forbidden"

        self.delete_chat(chat_id)
        return "deleted"

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

    def _apply_schema_migrations(self) -> None:
        # Backward-compatible migration for existing DBs created before chat.name existed.
        chat_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(chat)").fetchall()
        }
        if "name" not in chat_columns:
            with self.conn:
                self.conn.execute("ALTER TABLE chat ADD COLUMN name TEXT DEFAULT NULL")

        # Backward-compatible migration for RAG source mappings per assistant message.
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_message_document (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_message_id INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                UNIQUE(chat_message_id, document_id),
                FOREIGN KEY (chat_message_id) REFERENCES chat_message(id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_message_document_chat_message_id ON chat_message_document(chat_message_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_message_document_document_id ON chat_message_document(document_id)"
        )
