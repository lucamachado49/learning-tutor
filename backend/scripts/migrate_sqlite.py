"""
migrate_sqlite.py — Copia sessões, mensagens e memória do antigo tutor.db
(SQLite) para o banco configurado em DATABASE_URL. Idempotente: registros
já existentes (mesmo id) são ignorados.

Uso (na raiz do projeto, com o Postgres rodando):
    .venv\\Scripts\\python.exe backend\\scripts\\migrate_sqlite.py [caminho/tutor.db]
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from models import ChatSession, Message, Mistake  # noqa: E402


def _dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main(path: Path) -> None:
    if not path.exists():
        print(f"Arquivo não encontrado: {path}")
        return

    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts = {"sessions": 0, "messages": 0, "mistakes": 0}

    with db.session_scope() as s:
        for r in src.execute("SELECT * FROM sessions"):
            if s.get(ChatSession, r["id"]):
                continue
            keys = r.keys()
            s.add(ChatSession(
                id=r["id"], title=r["title"],
                domain=(r["domain"] if "domain" in keys and r["domain"] else r["language"]),
                level=r["level"],
                mode=(r["mode"] if "mode" in keys and r["mode"] else "conversation"),
                created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"]),
            ))
            counts["sessions"] += 1
        s.flush()

        seq: dict[str, int] = {}
        for r in src.execute("SELECT * FROM messages ORDER BY session_id, created_at"):
            seq[r["session_id"]] = seq.get(r["session_id"], 0) + 1
            if s.get(Message, r["id"]) or not s.get(ChatSession, r["session_id"]):
                continue
            s.add(Message(
                id=r["id"], session_id=r["session_id"], seq=seq[r["session_id"]],
                role=r["role"], content=r["content"],
                feedback=r["feedback"] or "", created_at=_dt(r["created_at"]),
            ))
            counts["messages"] += 1

        if "mistakes" in tables:
            for r in src.execute("SELECT * FROM mistakes"):
                if s.get(Mistake, r["id"]):
                    continue
                s.add(Mistake(
                    id=r["id"], domain=r["domain"], text=r["text"], norm=r["norm"], count=r["count"],
                    first_seen=_dt(r["first_seen"]), last_seen=_dt(r["last_seen"]),
                ))
                counts["mistakes"] += 1

    print("Migrados:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "tutor.db"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
