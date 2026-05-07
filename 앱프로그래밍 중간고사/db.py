"""
db.py — SQLite3 데이터베이스 설계 및 헬퍼 함수
A+++ 심화: UNIQUE 제약, length 자동 계산, sentiment 컬럼 포함
"""

import sqlite3
from datetime import datetime

DB_PATH = "quotes.db"


def init_db():
    """앱 시작 시 1회 호출 — 테이블 생성"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quotes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT    NOT NULL UNIQUE,
                author      TEXT    NOT NULL,
                tags        TEXT    DEFAULT '',
                length      INTEGER GENERATED ALWAYS AS (LENGTH(text)) VIRTUAL,
                sentiment   REAL    DEFAULT 0.0,
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def get_conn() -> sqlite3.Connection:
    """Row 팩토리 적용된 커넥션 반환"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


async def save_quotes(quotes: list[dict]) -> int:
    """크롤링 결과 벌크 저장 (중복 무시)"""
    with get_conn() as conn:
        result = conn.executemany(
            "INSERT OR IGNORE INTO quotes (text, author, tags) VALUES (:text, :author, :tags)",
            quotes,
        )
        return result.rowcount


def update_sentiment(quote_id: int, score: float):
    """TextBlob 분석 후 감성 점수 업데이트"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE quotes SET sentiment = ? WHERE id = ?",
            (score, quote_id),
        )


# ── 통계 쿼리 (Gradio 분석 탭에서 사용) ────────────────────────────
def get_all_texts() -> list[str]:
    with get_conn() as conn:
        return [r["text"] for r in conn.execute("SELECT text FROM quotes")]


def get_author_counts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT author, COUNT(*) as cnt FROM quotes GROUP BY author ORDER BY cnt DESC LIMIT 15"
        ).fetchall()
        return [dict(r) for r in rows]


def get_tag_counts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT tags FROM quotes WHERE tags != ''").fetchall()
    counter: dict[str, int] = {}
    for r in rows:
        for tag in r["tags"].split(","):
            tag = tag.strip()
            if tag:
                counter[tag] = counter.get(tag, 0) + 1
    return sorted(
        [{"tag": k, "count": v} for k, v in counter.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:20]


def get_sentiment_distribution() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, text, author, sentiment FROM quotes"
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats_summary() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        avg_len = conn.execute("SELECT AVG(LENGTH(text)) FROM quotes").fetchone()[0]
        authors = conn.execute("SELECT COUNT(DISTINCT author) FROM quotes").fetchone()[0]
        avg_sent = conn.execute("SELECT AVG(sentiment) FROM quotes").fetchone()[0]
    return {
        "total_quotes": total,
        "avg_length": round(avg_len or 0, 1),
        "unique_authors": authors,
        "avg_sentiment": round(avg_sent or 0, 3),
    }
