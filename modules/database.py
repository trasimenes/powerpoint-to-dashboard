import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("database.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS extractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                filename TEXT,
                slide_start INTEGER,
                slide_end INTEGER,
                kpi TEXT,
                table_data TEXT
            )"""
        )


def insert_record(filename, slide_start, slide_end, kpi, table_data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO extractions (timestamp, filename, slide_start, slide_end, kpi, table_data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
                filename,
                slide_start,
                slide_end,
                json.dumps(kpi, ensure_ascii=False),
                json.dumps(table_data, ensure_ascii=False),
            ),
        )
        conn.commit()


def get_history():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT timestamp, filename, slide_start, slide_end, kpi FROM extractions ORDER BY id DESC"
        )
        rows = cursor.fetchall()
    history = [
        {
            "timestamp": r[0],
            "filename": r[1],
            "slide_start": r[2],
            "slide_end": r[3],
            "kpi": json.loads(r[4]),
        }
        for r in rows
    ]
    return history
