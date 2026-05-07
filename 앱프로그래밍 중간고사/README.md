---
title: Quotes Analysis System
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "4.44.0"
app_file: main.py
pinned: false
---

# FastAPI 격언 관리 & 분석 시스템 — A+++ 심화 버전

## 프로젝트 구조

```
quotes_project/
├── main.py          # FastAPI 앱 (CRUD + Gradio 마운트)
├── db.py            # SQLite3 DB 설계 & 쿼리 함수
├── crawler.py       # HTTPX + BeautifulSoup4 비동기 크롤러
├── gradio_app.py    # Gradio 분석 UI (6개 탭)
├── requirements.txt # 의존성
├── Dockerfile       # Railway 배포용
└── README.md        # 이 파일 (HF Spaces 설정 포함)
```

## 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --reload --port 8000

# 접속
# Swagger UI : http://localhost:8000/docs
# Gradio UI  : http://localhost:8000/ui

# 크롤링 실행 (API 호출 or 직접 실행)
python crawler.py
```

## 주요 기능

### API 엔드포인트 (`/docs` 에서 확인)
| Method | Path | 설명 |
|--------|------|------|
| POST | /quotes/crawl | 크롤링 트리거 |
| GET | /quotes | 전체 조회 (페이지네이션) |
| GET | /quotes/search?q= | 키워드 검색 |
| GET | /quotes/random | 랜덤 추천 |
| GET | /quotes/{id} | 단건 조회 |
| POST | /quotes | 수동 추가 |
| PUT | /quotes/{id} | 수정 |
| DELETE | /quotes/{id} | 삭제 |
| GET | /stats | 통계 요약 |
| GET | /stats/authors | 저자별 통계 |
| GET | /stats/tags | 태그별 빈도 |

### Gradio UI (`/ui`)
- 단어 빈도 분석 (Top N 바 차트)
- 저자별 격언 수 (수평 바 차트)
- 태그 분포 (파이 차트)
- 격언 길이 분포 (히스토그램 + 박스플롯)
- 감성 분석 (TextBlob — 긍정/부정/중립)
- 랜덤 격언 추천 (태그 필터)

## 배포

### Hugging Face Spaces
1. `README.md` 상단 YAML 메타데이터 그대로 유지
2. 모든 파일 업로드 → 자동 배포

### Railway
1. `railway.toml` 불필요 — `Dockerfile` 자동 감지
2. `railway up` 명령 또는 GitHub 연동

### ngrok (발표 당일 임시 배포)
```bash
pip install pyngrok
python -c "from pyngrok import ngrok; t = ngrok.connect(8000); print(t.public_url)"
```

## A+++ 차별화 포인트
- asyncio + httpx 비동기 크롤링
- Pydantic v2 검증 + 중복 방지 (UNIQUE 제약)
- 6개 분석 탭 (기본 요구사항 + 감성분석, 길이분포, 랜덤추천)
- FastAPI Lifespan 이벤트로 DB 자동 초기화
- 페이지네이션 + 키워드/태그 복합 검색
