"""
main.py — FastAPI 메인 앱
A+++ 심화: Pydantic v2, 페이지네이션, 검색, 통계 엔드포인트, Gradio 마운트
실행: uvicorn main:app --reload
"""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

import gradio as gr
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import db
from crawler import run_crawl
from gradio_app import build_demo


# ── Lifespan: 앱 시작 시 DB 초기화 ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print("[DB] 초기화 완료")
    yield


app = FastAPI(
    title="Quotes Management API",
    description="quotes.toscrape.com 격언 수집·관리·분석 시스템",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Pydantic 모델 ────────────────────────────────────────────────────
class QuoteBase(BaseModel):
    text: str = Field(..., min_length=5, description="격언 본문")
    author: str = Field(..., min_length=1, description="저자 이름")
    tags: str = Field(default="", description="쉼표 구분 태그 (예: love,life)")


class QuoteCreate(QuoteBase):
    pass


class QuoteUpdate(BaseModel):
    text: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[str] = None


class QuoteResponse(QuoteBase):
    id: int
    sentiment: float
    created_at: str

    model_config = {"from_attributes": True}


# ── 헬퍼 ─────────────────────────────────────────────────────────────
def _get_quote_or_404(quote_id: int) -> dict:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id, text, author, tags, sentiment, created_at FROM quotes WHERE id = ?",
            (quote_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")
    return dict(row)


# ── CRUD 엔드포인트 ──────────────────────────────────────────────────
@app.get("/quotes", response_model=list[QuoteResponse], tags=["CRUD"])
def list_quotes(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """전체 격언 조회 (페이지네이션)"""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, text, author, tags, sentiment, created_at FROM quotes LIMIT ? OFFSET ?",
            (limit, skip),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/quotes/search", response_model=list[QuoteResponse], tags=["CRUD"])
def search_quotes(
    q: str = Query(..., description="검색 키워드 (본문 또는 저자)"),
    tag: Optional[str] = Query(None, description="태그 필터"),
):
    """키워드 + 태그 검색 (A+++ 심화)"""
    with db.get_conn() as conn:
        if tag:
            rows = conn.execute(
                "SELECT id, text, author, tags, sentiment, created_at FROM quotes "
                "WHERE (text LIKE ? OR author LIKE ?) AND tags LIKE ?",
                (f"%{q}%", f"%{q}%", f"%{tag}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, text, author, tags, sentiment, created_at FROM quotes "
                "WHERE text LIKE ? OR author LIKE ?",
                (f"%{q}%", f"%{q}%"),
            ).fetchall()
    return [dict(r) for r in rows]


@app.get("/quotes/random", response_model=QuoteResponse, tags=["CRUD"])
def random_quote(tag: Optional[str] = Query(None)):
    """랜덤 격언 추천 (태그 필터 선택)"""
    with db.get_conn() as conn:
        if tag:
            row = conn.execute(
                "SELECT id, text, author, tags, sentiment, created_at FROM quotes "
                "WHERE tags LIKE ? ORDER BY RANDOM() LIMIT 1",
                (f"%{tag}%",),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, text, author, tags, sentiment, created_at FROM quotes "
                "ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No quotes found")
    return dict(row)


@app.get("/quotes/{quote_id}", response_model=QuoteResponse, tags=["CRUD"])
def get_quote(quote_id: int):
    """단건 조회"""
    return _get_quote_or_404(quote_id)


@app.post("/quotes", response_model=QuoteResponse, status_code=201, tags=["CRUD"])
def create_quote(body: QuoteCreate):
    """격언 수동 추가"""
    with db.get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO quotes (text, author, tags) VALUES (?, ?, ?)",
                (body.text, body.author, body.tags),
            )
            return _get_quote_or_404(cur.lastrowid)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Duplicate quote text")


@app.put("/quotes/{quote_id}", response_model=QuoteResponse, tags=["CRUD"])
def update_quote(quote_id: int, body: QuoteUpdate):
    """격언 수정"""
    existing = _get_quote_or_404(quote_id)
    new_text = body.text or existing["text"]
    new_author = body.author or existing["author"]
    new_tags = body.tags if body.tags is not None else existing["tags"]

    with db.get_conn() as conn:
        conn.execute(
            "UPDATE quotes SET text = ?, author = ?, tags = ? WHERE id = ?",
            (new_text, new_author, new_tags, quote_id),
        )
    return _get_quote_or_404(quote_id)


@app.delete("/quotes/{quote_id}", tags=["CRUD"])
def delete_quote(quote_id: int):
    """격언 삭제"""
    _get_quote_or_404(quote_id)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    return {"detail": f"Quote {quote_id} deleted"}


# ── 크롤링 트리거 ─────────────────────────────────────────────────────
@app.post("/quotes/crawl", tags=["Crawl"])
async def trigger_crawl():
    """크롤링 실행 → DB 저장"""
    saved = await run_crawl()
    return {"message": "크롤링 완료", "saved_count": saved}


# ── 통계 엔드포인트 (A+++ 심화) ──────────────────────────────────────
@app.get("/stats", tags=["Analytics"])
def get_stats():
    """전체 통계 요약"""
    return db.get_stats_summary()


@app.get("/stats/authors", tags=["Analytics"])
def get_author_stats():
    """저자별 격언 수"""
    return db.get_author_counts()


@app.get("/stats/tags", tags=["Analytics"])
def get_tag_stats():
    """태그별 빈도"""
    return db.get_tag_counts()


# ── Gradio 마운트 ─────────────────────────────────────────────────────
demo = build_demo()
app = gr.mount_gradio_app(app, demo, path="/ui")

# ── 로컬 실행 ─────────────────────────────────────────────────────────
# uvicorn main:app --reload --port 8000
# Swagger: http://localhost:8000/docs
# Gradio:  http://localhost:8000/ui
