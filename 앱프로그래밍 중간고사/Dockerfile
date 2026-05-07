FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 설치 (Docker 레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 앱 시작 시 DB 초기화 + 자동 크롤링
ENV PORT=7860
EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
