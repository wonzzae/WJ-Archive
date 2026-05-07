"""
crawler.py — 비동기 크롤러 (HTTPX + BeautifulSoup4)
A+++ 심화: asyncio 비동기, 카테고리별 분류, 전 페이지 순회
"""

import asyncio
import httpx
from bs4 import BeautifulSoup
from db import save_quotes

BASE_URL = "https://quotes.toscrape.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (quotes-study-crawler/1.0)"}


async def fetch_page(client: httpx.AsyncClient, url: str) -> BeautifulSoup:
    """단일 페이지 fetch → BeautifulSoup 반환"""
    response = await client.get(url, headers=HEADERS, follow_redirects=True)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_quotes(soup: BeautifulSoup) -> list[dict]:
    """HTML에서 격언 파싱"""
    results = []
    for q in soup.select(".quote"):
        text = q.select_one(".text").get_text(strip=True).strip("\u201c\u201d")
        author = q.select_one(".author").get_text(strip=True)
        tags = ",".join(t.get_text(strip=True) for t in q.select(".tag"))
        results.append({"text": text, "author": author, "tags": tags})
    return results


async def crawl_all_pages() -> list[dict]:
    """quotes.toscrape.com 전 페이지 순회 크롤링"""
    all_quotes: list[dict] = []
    page_path = "/page/1/"

    async with httpx.AsyncClient(timeout=30.0) as client:
        while page_path:
            soup = await fetch_page(client, BASE_URL + page_path)
            page_quotes = parse_quotes(soup)
            all_quotes.extend(page_quotes)
            print(f"  페이지 {page_path}: {len(page_quotes)}개 수집")

            next_btn = soup.select_one(".next a")
            page_path = next_btn["href"] if next_btn else None

    return all_quotes


async def crawl_by_tag(tag: str) -> list[dict]:
    """특정 태그 카테고리만 크롤링 (심화 기능)"""
    all_quotes: list[dict] = []
    page_path = f"/tag/{tag}/page/1/"

    async with httpx.AsyncClient(timeout=30.0) as client:
        while page_path:
            try:
                soup = await fetch_page(client, BASE_URL + page_path)
                page_quotes = parse_quotes(soup)
                if not page_quotes:
                    break
                all_quotes.extend(page_quotes)
                next_btn = soup.select_one(".next a")
                page_path = next_btn["href"] if next_btn else None
            except httpx.HTTPStatusError:
                break

    return all_quotes


async def run_crawl() -> int:
    """메인 크롤링 실행 → DB 저장 → 저장 건수 반환"""
    print("[크롤러] 시작...")
    quotes = await crawl_all_pages()
    print(f"[크롤러] 총 {len(quotes)}개 수집 완료, DB 저장 중...")
    saved = await save_quotes(quotes)
    print(f"[크롤러] {saved}개 신규 저장 (중복 제외)")
    return saved


if __name__ == "__main__":
    # 단독 실행 테스트: python crawler.py
    asyncio.run(run_crawl())
