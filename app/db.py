from __future__ import annotations

import os
import sqlite3
from typing import Iterator

from sqlmodel import SQLModel, Session, create_engine

# Персистентный путь к БД (маппится на /data в docker-compose)
DB_PATH = os.environ.get("DB_PATH", "/data/people.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


def _pragma_foreign_keys(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    SQLModel.metadata.create_all(engine)

    # Ленивая миграция: добавляем недостающие колонки в person
    with engine.begin() as conn:
        raw = conn.connection
        if isinstance(raw, sqlite3.Connection):
            _pragma_foreign_keys(raw)

        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(person)")}

        desired = [
            ("favorite_movies", "TEXT"),
            ("favorite_color", "TEXT"),
            ("favorite_flowers", "TEXT"),
            ("marital_status", "TEXT"),
            ("partner_name", "TEXT"),
            ("handedness", "TEXT"),
            ("smokes", "INTEGER"),
            ("avatar_path", "TEXT"),

            ("food_prefs", "TEXT"),
            ("alcohol_prefs", "TEXT"),
            ("places_to_go", "TEXT"),
            ("traits_positive", "TEXT"),
            ("traits_negative", "TEXT"),

            ("occupation", "TEXT"),
            ("job_title", "TEXT"),
            ("workplace", "TEXT"),  # новое поле «Где работает»

            ("wishlist", "TEXT"),

            ("telegram_username", "TEXT"),
            ("instagram_username", "TEXT"),
            ("vk_username", "TEXT"),

            ("apartment", "TEXT"),

            ("notify_year_7d", "INTEGER"),
            ("notify_year_1d", "INTEGER"),
        ]
        for col, typ in desired:
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE person ADD COLUMN {col} {typ}")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
