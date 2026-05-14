"""
Инициализация схемы из gzu_database.sql при первом подключении к PostgreSQL.
"""
from __future__ import annotations

from pathlib import Path

import psycopg


def schema_sql_path() -> Path:
    return Path(__file__).resolve().parent / "gzu_database.sql"


def split_postgres_statements(sql: str) -> list[str]:
    """Делит скрипт по «;» вне одинарных кавычек и вне тела $$ ... $$ (как в plpgsql)."""
    stmts: list[str] = []
    buf_start = 0
    i = 0
    n = len(sql)
    in_single = False
    in_dollar = False

    while i < n:
        ch = sql[i]
        if in_dollar:
            if i + 1 < n and sql[i : i + 2] == "$$":
                in_dollar = False
                i += 2
                continue
            i += 1
            continue
        if in_single:
            if ch == "'" and i + 1 < n and sql[i + 1] == "'":
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if i + 1 < n and sql[i : i + 2] == "$$":
            in_dollar = True
            i += 2
            continue
        if ch == ";":
            piece = sql[buf_start : i + 1].strip()
            if piece:
                stmts.append(piece)
            buf_start = i + 1
        i += 1

    tail = sql[buf_start:].strip()
    if tail:
        stmts.append(tail)
    return stmts


def _has_executable_sql(stmt: str) -> bool:
    for line in stmt.splitlines():
        t = line.strip()
        if not t or t.startswith("--"):
            continue
        return True
    return False


def schema_tables_present(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'services'
            )
            """
        )
        row = cur.fetchone()
        return bool(row and row[0])


def apply_schema_file(conn: psycopg.Connection, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for stmt in split_postgres_statements(text):
        if not _has_executable_sql(stmt):
            continue
        conn.execute(stmt)


def ensure_schema_on_connection(conn: psycopg.Connection, path: Path | None = None) -> None:
    """
    Если в public ещё нет таблицы services, выполняет gzu_database.sql (схема + демо-данные).
    Вызывать на уже открытом соединении (autocommit=True для DDL).
    """
    p = path or schema_sql_path()
    if not p.is_file():
        raise FileNotFoundError(f"Не найден файл схемы: {p}")
    if schema_tables_present(conn):
        return
    apply_schema_file(conn, p)
