"""
gradio_app.py — Gradio 분석 UI (FastAPI에 /ui 로 마운트)
A+++ 심화: 단어 빈도, 감성 분석, 저자 통계, 태그 분포, 랜덤 추천, 길이 분포
"""

import collections
import random

import gradio as gr
import matplotlib
import matplotlib.pyplot as plt
import numpy as np

import db

matplotlib.use("Agg")  # 서버 환경 headless 렌더링 필수


# ── 분석 함수들 ──────────────────────────────────────────────────────
STOP_WORDS = {
    "the", "a", "an", "of", "and", "to", "in", "i", "it", "is", "that",
    "this", "was", "for", "on", "are", "with", "as", "at", "be", "by",
    "from", "or", "not", "you", "he", "she", "we", "they", "have", "do",
}


def word_freq_chart(top_n: int = 15):
    texts = db.get_all_texts()
    if not texts:
        return None, "DB에 데이터가 없습니다. 먼저 크롤링을 실행하세요."

    words = " ".join(texts).lower().split()
    freq = collections.Counter(w.strip(".,!?;:\"'") for w in words if w not in STOP_WORDS and len(w) > 2)
    top = freq.most_common(top_n)

    fig, ax = plt.subplots(figsize=(9, 5))
    labels, values = zip(*top)
    bars = ax.barh(labels[::-1], values[::-1], color="#4A6FA5")
    ax.set_xlabel("빈도수")
    ax.set_title(f"상위 {top_n}개 단어 빈도")
    ax.bar_label(bars, padding=3, fontsize=9)
    plt.tight_layout()
    return fig, f"총 {len(texts)}개 격언에서 {sum(freq.values())}개 단어 분석"


def author_chart():
    data = db.get_author_counts()
    if not data:
        return None, "데이터 없음"

    authors = [d["author"] for d in data]
    counts = [d["cnt"] for d in data]

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = plt.cm.Blues(np.linspace(0.4, 0.9, len(authors)))
    bars = ax.barh(authors[::-1], counts[::-1], color=colors[::-1])
    ax.set_xlabel("격언 수")
    ax.set_title("저자별 격언 수 (Top 15)")
    ax.bar_label(bars, padding=3, fontsize=9)
    plt.tight_layout()
    return fig, f"상위 저자: {authors[0]} ({counts[0]}개)"


def tag_chart():
    data = db.get_tag_counts()
    if not data:
        return None, "데이터 없음"

    tags = [d["tag"] for d in data[:15]]
    counts = [d["count"] for d in data[:15]]

    fig, ax = plt.subplots(figsize=(8, 8))
    wedges, texts, autotexts = ax.pie(
        counts,
        labels=tags,
        autopct="%1.1f%%",
        startangle=140,
        colors=plt.cm.Set3.colors,
    )
    ax.set_title("태그 분포 (Top 15)")
    plt.tight_layout()
    return fig, f"총 {len(data)}개 태그"


def length_distribution():
    texts = db.get_all_texts()
    if not texts:
        return None, "데이터 없음"

    lengths = [len(t) for t in texts]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 히스토그램
    axes[0].hist(lengths, bins=20, color="#4A6FA5", edgecolor="white")
    axes[0].axvline(np.mean(lengths), color="red", linestyle="--", label=f"평균 {np.mean(lengths):.0f}자")
    axes[0].axvline(np.median(lengths), color="orange", linestyle="--", label=f"중앙값 {np.median(lengths):.0f}자")
    axes[0].set_xlabel("격언 길이 (문자 수)")
    axes[0].set_ylabel("빈도")
    axes[0].set_title("격언 길이 분포")
    axes[0].legend()

    # 박스플롯
    axes[1].boxplot(lengths, vert=True)
    axes[1].set_ylabel("격언 길이 (문자 수)")
    axes[1].set_title("길이 박스플롯")
    axes[1].set_xticks([1])
    axes[1].set_xticklabels(["전체 격언"])

    plt.tight_layout()
    stats = f"평균 {np.mean(lengths):.0f}자 | 중앙값 {np.median(lengths):.0f}자 | 최단 {min(lengths)}자 | 최장 {max(lengths)}자"
    return fig, stats


def sentiment_chart():
    """TextBlob 감성 분석 (A+++ 심화)"""
    try:
        from textblob import TextBlob
    except ImportError:
        return None, "textblob 미설치: pip install textblob"

    texts = db.get_all_texts()
    if not texts:
        return None, "데이터 없음"

    scores = [TextBlob(t).sentiment.polarity for t in texts]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 히스토그램
    pos = sum(1 for s in scores if s > 0)
    neg = sum(1 for s in scores if s < 0)
    neu = len(scores) - pos - neg
    axes[0].hist(scores, bins=30, color="#4A6FA5", edgecolor="white")
    axes[0].axvline(0, color="red", linestyle="--", label="중립선")
    axes[0].set_xlabel("감성 점수 (-1: 부정, +1: 긍정)")
    axes[0].set_title("감성 점수 분포")
    axes[0].legend()

    # 파이차트
    axes[1].pie(
        [pos, neg, neu],
        labels=["긍정", "부정", "중립"],
        autopct="%1.1f%%",
        colors=["#4CAF50", "#F44336", "#9E9E9E"],
        startangle=90,
    )
    axes[1].set_title("감성 분류")

    plt.tight_layout()
    return fig, f"긍정 {pos}개 | 부정 {neg}개 | 중립 {neu}개 | 평균 점수 {sum(scores)/len(scores):.3f}"


def random_quote_fn(tag_filter: str):
    """랜덤 격언 추천"""
    with db.get_conn() as conn:
        if tag_filter.strip():
            row = conn.execute(
                "SELECT text, author, tags FROM quotes WHERE tags LIKE ? ORDER BY RANDOM() LIMIT 1",
                (f"%{tag_filter.strip()}%",),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT text, author, tags FROM quotes ORDER BY RANDOM() LIMIT 1"
            ).fetchone()

    if not row:
        return "격언을 찾을 수 없습니다. 크롤링 먼저 실행하세요.", "", ""
    return f'"{row["text"]}"', f"— {row["author"]}", f"태그: {row['tags']}"


def get_summary():
    stats = db.get_stats_summary()
    return (
        f"총 격언 수: {stats['total_quotes']}개",
        f"평균 길이: {stats['avg_length']}자",
        f"저자 수: {stats['unique_authors']}명",
        f"평균 감성: {stats['avg_sentiment']:.3f}",
    )


# ── Gradio UI 구성 ────────────────────────────────────────────────────
def build_demo() -> gr.Blocks:
    with gr.Blocks(title="격언 분석 대시보드", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 격언 분석 대시보드\nquotes.toscrape.com 데이터 기반 분석 시스템")

        # 요약 통계 카드
        with gr.Row():
            total_box = gr.Textbox(label="총 격언 수", interactive=False)
            len_box = gr.Textbox(label="평균 길이", interactive=False)
            author_box = gr.Textbox(label="저자 수", interactive=False)
            sent_box = gr.Textbox(label="평균 감성", interactive=False)
        refresh_btn = gr.Button("📊 통계 새로고침", variant="secondary")
        refresh_btn.click(get_summary, outputs=[total_box, len_box, author_box, sent_box])

        gr.Markdown("---")

        with gr.Tabs():
            # ─ 탭 1: 단어 빈도 ─
            with gr.Tab("단어 빈도 분석"):
                top_n = gr.Slider(5, 30, value=15, step=1, label="표시할 단어 수")
                run_btn = gr.Button("분석 실행", variant="primary")
                word_plot = gr.Plot(label="단어 빈도 차트")
                word_info = gr.Textbox(label="분석 요약", interactive=False)
                run_btn.click(word_freq_chart, inputs=top_n, outputs=[word_plot, word_info])

            # ─ 탭 2: 저자 통계 ─
            with gr.Tab("저자별 통계"):
                author_btn = gr.Button("저자 분석", variant="primary")
                author_plot = gr.Plot()
                author_info = gr.Textbox(interactive=False)
                author_btn.click(author_chart, outputs=[author_plot, author_info])

            # ─ 탭 3: 태그 분포 ─
            with gr.Tab("태그 분포"):
                tag_btn = gr.Button("태그 분석", variant="primary")
                tag_plot = gr.Plot()
                tag_info = gr.Textbox(interactive=False)
                tag_btn.click(tag_chart, outputs=[tag_plot, tag_info])

            # ─ 탭 4: 길이 분포 (심화) ─
            with gr.Tab("📏 길이 분포"):
                len_btn = gr.Button("길이 분석", variant="primary")
                len_plot = gr.Plot()
                len_info = gr.Textbox(interactive=False)
                len_btn.click(length_distribution, outputs=[len_plot, len_info])

            # ─ 탭 5: 감성 분석 (심화) ─
            with gr.Tab("감성 분석"):
                gr.Markdown("TextBlob 기반 긍정/부정/중립 분류")
                sent_btn = gr.Button("감성 분석 실행", variant="primary")
                sent_plot = gr.Plot()
                sent_info = gr.Textbox(interactive=False)
                sent_btn.click(sentiment_chart, outputs=[sent_plot, sent_info])

            # ─ 탭 6: 랜덤 추천 (심화) ─
            with gr.Tab("🎲 랜덤 추천"):
                tag_input = gr.Textbox(label="태그 필터 (선택, 예: love)", placeholder="비워두면 전체 랜덤")
                rand_btn = gr.Button("격언 추천", variant="primary")
                quote_text = gr.Textbox(label="격언", interactive=False)
                quote_author = gr.Textbox(label="저자", interactive=False)
                quote_tags = gr.Textbox(label="태그", interactive=False)
                rand_btn.click(random_quote_fn, inputs=tag_input, outputs=[quote_text, quote_author, quote_tags])

    return demo
