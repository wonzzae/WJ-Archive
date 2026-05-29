"""
📚 도서관리시스템 - 파일 1개로 끝
실행: python app.py
접속: http://localhost:7860
"""

# ══════════════════════════════════════════════
# 0. 의존성 자동 설치
# ══════════════════════════════════════════════
import subprocess, sys

REQUIRED = ["fastapi", "uvicorn", "sqlalchemy", "gradio", "requests"]

def install_if_missing():
    import importlib.util
    missing = [p for p in REQUIRED if not importlib.util.find_spec(p.split("[")[0])]
    if missing:
        print(f"📦 설치 중: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing + ["--quiet"])
        print("✅ 설치 완료\n")

install_if_missing()

# ══════════════════════════════════════════════
# 1. MODEL  (SQLAlchemy ORM)
# ══════════════════════════════════════════════
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, ForeignKey, or_
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, joinedload
from datetime import datetime, timedelta

Base = declarative_base()
engine = create_engine("sqlite:///library.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Book(Base):
    __tablename__ = "books"
    id             = Column(Integer, primary_key=True, index=True)
    title          = Column(String(200), nullable=False)
    author         = Column(String(100), nullable=False)
    isbn           = Column(String(20), unique=True, nullable=False)
    publisher      = Column(String(100), default="")
    published_year = Column(Integer, nullable=True)
    genre          = Column(String(50), default="")
    is_available   = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    loans          = relationship("Loan", back_populates="book")


class Member(Base):
    __tablename__ = "members"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    email      = Column(String(150), unique=True, nullable=False)
    phone      = Column(String(20), default="")
    address    = Column(String(300), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    loans      = relationship("Loan", back_populates="member")


class Loan(Base):
    __tablename__ = "loans"
    id          = Column(Integer, primary_key=True, index=True)
    book_id     = Column(Integer, ForeignKey("books.id"), nullable=False)
    member_id   = Column(Integer, ForeignKey("members.id"), nullable=False)
    loaned_at   = Column(DateTime, default=datetime.utcnow)
    due_date    = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=14))
    returned_at = Column(DateTime, nullable=True)
    is_returned = Column(Boolean, default=False)
    book        = relationship("Book", back_populates="loans")
    member      = relationship("Member", back_populates="loans")

    @property
    def is_overdue(self):
        return not self.is_returned and datetime.utcnow() > self.due_date


Base.metadata.create_all(bind=engine)


# ══════════════════════════════════════════════
# 2. CONTROLLER  (비즈니스 로직)
# ══════════════════════════════════════════════

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class BookCtrl:
    @staticmethod
    def all(db):
        return db.query(Book).order_by(Book.id.desc()).all()

    @staticmethod
    def search(db, kw):
        return db.query(Book).filter(or_(
            Book.title.ilike(f"%{kw}%"), Book.author.ilike(f"%{kw}%"),
            Book.isbn.ilike(f"%{kw}%"),  Book.genre.ilike(f"%{kw}%"),
        )).all()

    @staticmethod
    def create(db, title, author, isbn, publisher="", published_year=None, genre=""):
        if db.query(Book).filter(Book.isbn == isbn).first():
            raise ValueError(f"ISBN '{isbn}' 이미 등록된 도서입니다.")
        b = Book(title=title, author=author, isbn=isbn,
                 publisher=publisher, published_year=published_year, genre=genre)
        db.add(b); db.commit(); db.refresh(b)
        return b

    @staticmethod
    def update(db, book_id, **kw):
        b = db.query(Book).filter(Book.id == book_id).first()
        if not b: raise ValueError(f"ID {book_id} 도서 없음")
        for k, v in kw.items():
            if v is not None: setattr(b, k, v)
        db.commit(); db.refresh(b); return b

    @staticmethod
    def delete(db, book_id):
        b = db.query(Book).filter(Book.id == book_id).first()
        if not b: raise ValueError(f"ID {book_id} 도서 없음")
        if not b.is_available: raise ValueError("대출 중인 도서는 삭제 불가")
        db.delete(b); db.commit()


class MemberCtrl:
    @staticmethod
    def all(db):
        return db.query(Member).order_by(Member.id.desc()).all()

    @staticmethod
    def search(db, kw):
        return db.query(Member).filter(or_(
            Member.name.ilike(f"%{kw}%"), Member.email.ilike(f"%{kw}%"),
            Member.phone.ilike(f"%{kw}%"),
        )).all()

    @staticmethod
    def create(db, name, email, phone="", address=""):
        if db.query(Member).filter(Member.email == email).first():
            raise ValueError(f"이메일 '{email}' 이미 등록된 회원입니다.")
        m = Member(name=name, email=email, phone=phone, address=address)
        db.add(m); db.commit(); db.refresh(m); return m

    @staticmethod
    def delete(db, member_id):
        m = db.query(Member).filter(Member.id == member_id).first()
        if not m: raise ValueError(f"ID {member_id} 회원 없음")
        if any(not l.is_returned for l in m.loans):
            raise ValueError("미반납 도서가 있는 회원은 삭제 불가")
        db.delete(m); db.commit()


class LoanCtrl:
    @staticmethod
    def _q(db): return db.query(Loan).options(joinedload(Loan.book), joinedload(Loan.member))

    @staticmethod
    def all(db):     return LoanCtrl._q(db).order_by(Loan.id.desc()).all()

    @staticmethod
    def active(db):  return LoanCtrl._q(db).filter(Loan.is_returned == False).all()  # noqa

    @staticmethod
    def overdue(db):
        return LoanCtrl._q(db).filter(
            Loan.is_returned == False, Loan.due_date < datetime.utcnow()  # noqa
        ).all()

    @staticmethod
    def loan(db, book_id, member_id):
        b = db.query(Book).filter(Book.id == book_id).first()
        if not b:              raise ValueError(f"ID {book_id} 도서 없음")
        if not b.is_available: raise ValueError(f"'{b.title}' 현재 대출 중")
        m = db.query(Member).filter(Member.id == member_id).first()
        if not m: raise ValueError(f"ID {member_id} 회원 없음")
        if any(l.member_id == member_id for l in LoanCtrl.overdue(db)):
            raise ValueError(f"'{m.name}' 연체 중 → 신규 대출 불가")
        l = Loan(book_id=book_id, member_id=member_id)
        b.is_available = False
        db.add(l); db.commit(); db.refresh(l); return l

    @staticmethod
    def ret(db, loan_id):
        l = LoanCtrl._q(db).filter(Loan.id == loan_id).first()
        if not l:           raise ValueError(f"ID {loan_id} 대출 기록 없음")
        if l.is_returned:   raise ValueError("이미 반납된 도서")
        l.is_returned = True
        l.returned_at = datetime.utcnow()
        l.book.is_available = True
        db.commit(); db.refresh(l); return l


# ══════════════════════════════════════════════
# 3. VIEW  (FastAPI REST API)
# ══════════════════════════════════════════════
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

api = FastAPI(title="도서관리 API", docs_url="/docs")
api.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# ── Pydantic 스키마 ─────────────────────────
class BCreate(BaseModel):
    title: str; author: str; isbn: str
    publisher: str = ""; published_year: Optional[int] = None; genre: str = ""

class BUpdate(BaseModel):
    title: Optional[str]=None; author: Optional[str]=None
    publisher: Optional[str]=None; published_year: Optional[int]=None; genre: Optional[str]=None

class MCreate(BaseModel):
    name: str; email: str; phone: str = ""; address: str = ""

class LCreate(BaseModel):
    book_id: int; member_id: int


def db_ctx():
    return next(get_db())

def ok(data=None, msg="success"):
    return {"ok": True, "data": data, "msg": msg}

def to_book(b):
    return {"id":b.id,"title":b.title,"author":b.author,"isbn":b.isbn,
            "publisher":b.publisher,"published_year":b.published_year,
            "genre":b.genre,"is_available":b.is_available,
            "created_at":str(b.created_at)[:10]}

def to_member(m):
    return {"id":m.id,"name":m.name,"email":m.email,
            "phone":m.phone,"created_at":str(m.created_at)[:10]}

def to_loan(l):
    return {"id":l.id,"book_id":l.book_id,"member_id":l.member_id,
            "book_title": l.book.title if l.book else "",
            "member_name": l.member.name if l.member else "",
            "loaned_at":str(l.loaned_at)[:10],
            "due_date":str(l.due_date)[:10],
            "returned_at":str(l.returned_at)[:10] if l.returned_at else "",
            "is_returned":l.is_returned, "is_overdue":l.is_overdue}


# ── 도서 ────────────────────────────────────
@api.get("/books")
def list_books(q: str = ""):
    db = db_ctx()
    items = BookCtrl.search(db, q) if q else BookCtrl.all(db)
    return ok([to_book(b) for b in items])

@api.post("/books")
def create_book(body: BCreate):
    db = db_ctx()
    try:    return ok(to_book(BookCtrl.create(db, **body.dict())))
    except ValueError as e: raise HTTPException(400, str(e))

@api.put("/books/{book_id}")
def update_book(book_id: int, body: BUpdate):
    db = db_ctx()
    try:    return ok(to_book(BookCtrl.update(db, book_id, **body.dict(exclude_none=True))))
    except ValueError as e: raise HTTPException(400, str(e))

@api.delete("/books/{book_id}")
def delete_book(book_id: int):
    db = db_ctx()
    try:    BookCtrl.delete(db, book_id); return ok(msg="삭제 완료")
    except ValueError as e: raise HTTPException(400, str(e))


# ── 회원 ────────────────────────────────────
@api.get("/members")
def list_members(q: str = ""):
    db = db_ctx()
    items = MemberCtrl.search(db, q) if q else MemberCtrl.all(db)
    return ok([to_member(m) for m in items])

@api.post("/members")
def create_member(body: MCreate):
    db = db_ctx()
    try:    return ok(to_member(MemberCtrl.create(db, **body.dict())))
    except ValueError as e: raise HTTPException(400, str(e))

@api.delete("/members/{member_id}")
def delete_member(member_id: int):
    db = db_ctx()
    try:    MemberCtrl.delete(db, member_id); return ok(msg="삭제 완료")
    except ValueError as e: raise HTTPException(400, str(e))


# ── 대출/반납 ────────────────────────────────
@api.get("/loans")
def list_loans(active_only: bool = False):
    db = db_ctx()
    items = LoanCtrl.active(db) if active_only else LoanCtrl.all(db)
    return ok([to_loan(l) for l in items])

@api.post("/loans")
def create_loan(body: LCreate):
    db = db_ctx()
    try:    return ok(to_loan(LoanCtrl.loan(db, body.book_id, body.member_id)))
    except ValueError as e: raise HTTPException(400, str(e))

@api.post("/loans/{loan_id}/return")
def return_loan(loan_id: int):
    db = db_ctx()
    try:    return ok(to_loan(LoanCtrl.ret(db, loan_id)))
    except ValueError as e: raise HTTPException(400, str(e))


# ── 통계 ────────────────────────────────────
@api.get("/stats")
def stats():
    db = db_ctx()
    total  = db.query(Book).count()
    avail  = db.query(Book).filter(Book.is_available == True).count()  # noqa
    return ok({
        "total_books":    total,
        "available_books": avail,
        "loaned_books":   total - avail,
        "total_members":  db.query(Member).count(),
        "active_loans":   db.query(Loan).filter(Loan.is_returned == False).count(),  # noqa
        "overdue_loans":  len(LoanCtrl.overdue(db)),
    })


# ══════════════════════════════════════════════
# 4. VIEW  (Gradio UI)  —  API 호출로 백엔드 사용
# ══════════════════════════════════════════════
import gradio as gr, requests as req, threading, time, uvicorn

BASE = "http://127.0.0.1:8000"

def call(method, path, **kw):
    try:
        r = getattr(req, method)(BASE + path, **kw)
        r.raise_for_status()
        body = r.json()
        return body.get("data"), None
    except req.exceptions.HTTPError as e:
        try:    msg = e.response.json().get("detail", str(e))
        except: msg = str(e)
        return None, msg
    except Exception as e:
        return None, f"서버 오류: {e}"


# ── 도서 ────────────────────────────────────
def books_load(kw=""):
    data, err = call("get", "/books", params={"q": kw})
    if err: return [], f"❌ {err}"
    rows = [[b["id"],b["title"],b["author"],b["isbn"],
             b["genre"],b["published_year"] or "",
             "✅ 가능" if b["is_available"] else "❌ 대출중",
             b["created_at"]] for b in (data or [])]
    return rows, f"✅ {len(rows)}권"

def book_add(title, author, isbn, publisher, year, genre):
    if not (title.strip() and author.strip() and isbn.strip()):
        return "❌ 제목·저자·ISBN 필수"
    _, err = call("post", "/books", json={"title":title,"author":author,"isbn":isbn,
                  "publisher":publisher,"published_year":int(year) if year else None,"genre":genre})
    return f"❌ {err}" if err else f"✅ '{title}' 등록 완료"

def book_update(bid, title, author, publisher, year, genre):
    if not bid: return "❌ 도서 ID 필요"
    body = {k:v for k,v in {"title":title,"author":author,"publisher":publisher,
            "published_year":int(year) if year else None,"genre":genre}.items() if v}
    if not body: return "❌ 수정 항목 없음"
    _, err = call("put", f"/books/{int(bid)}", json=body)
    return f"❌ {err}" if err else f"✅ ID {int(bid)} 수정 완료"

def book_del(bid):
    if not bid: return "❌ 도서 ID 필요"
    _, err = call("delete", f"/books/{int(bid)}")
    return f"❌ {err}" if err else f"✅ ID {int(bid)} 삭제 완료"


# ── 회원 ────────────────────────────────────
def members_load(kw=""):
    data, err = call("get", "/members", params={"q": kw})
    if err: return [], f"❌ {err}"
    rows = [[m["id"],m["name"],m["email"],m["phone"],m["created_at"]] for m in (data or [])]
    return rows, f"✅ {len(rows)}명"

def member_add(name, email, phone, address):
    if not (name.strip() and email.strip()): return "❌ 이름·이메일 필수"
    _, err = call("post", "/members", json={"name":name,"email":email,"phone":phone,"address":address})
    return f"❌ {err}" if err else f"✅ '{name}' 등록 완료"

def member_del(mid):
    if not mid: return "❌ 회원 ID 필요"
    _, err = call("delete", f"/members/{int(mid)}")
    return f"❌ {err}" if err else f"✅ ID {int(mid)} 삭제 완료"


# ── 대출/반납 ────────────────────────────────
def loans_load(active_only=False):
    data, err = call("get", "/loans", params={"active_only": active_only})
    if err: return [], f"❌ {err}"
    rows = [[l["id"],l["book_title"],l["member_name"],
             l["loaned_at"],l["due_date"],
             "⚠️ 연체" if l["is_overdue"] else ("✅ 반납" if l["is_returned"] else "📖 대출중")]
            for l in (data or [])]
    return rows, f"✅ {len(rows)}건"

def loan_create(bid, mid):
    if not (bid and mid): return "❌ 도서 ID·회원 ID 필요"
    data, err = call("post", "/loans", json={"book_id":int(bid),"member_id":int(mid)})
    if err: return f"❌ {err}"
    return f"✅ 대출 완료 (대출번호 {data['id']} | 반납기한 {data['due_date']})"

def loan_return(lid):
    if not lid: return "❌ 대출 ID 필요"
    _, err = call("post", f"/loans/{int(lid)}/return")
    return f"❌ {err}" if err else f"✅ ID {int(lid)} 반납 처리 완료"


# ── 통계 ────────────────────────────────────
def load_stats():
    data, err = call("get", "/stats")
    if err: return f"❌ {err}"
    return (
        f"📚 전체 도서     : {data['total_books']}권\n"
        f"✅ 대출 가능     : {data['available_books']}권\n"
        f"📖 대출 중       : {data['loaned_books']}권\n"
        f"👥 전체 회원     : {data['total_members']}명\n"
        f"📋 진행 중 대출  : {data['active_loans']}건\n"
        f"⚠️ 연체          : {data['overdue_loans']}건"
    )


# ── Gradio 레이아웃 ──────────────────────────
BOOK_H   = ["ID","제목","저자","ISBN","장르","출판연도","상태","등록일"]
MEMBER_H = ["ID","이름","이메일","전화번호","가입일"]
LOAN_H   = ["대출ID","도서명","회원명","대출일","반납기한","상태"]

with gr.Blocks(title="📚 도서관리시스템") as ui:
    gr.Markdown("# 📚 도서관리시스템\n> 파일 1개 · `python app.py` 한 방 실행")

    with gr.Tabs():

        # ── 도서 ──────────────────────────────
        with gr.Tab("📖 도서 관리"):
            with gr.Row():
                bkw = gr.Textbox(label="🔍 검색", scale=5)
                gr.Button("검색").click(lambda k: books_load(k), bkw, [
                    bt := gr.Dataframe(headers=BOOK_H, interactive=False, wrap=True),
                    bs := gr.Textbox(label="상태", interactive=False)
                ])
                gr.Button("전체").click(lambda: books_load(), [], [bt, bs])

            with gr.Accordion("➕ 등록", open=False):
                with gr.Row():
                    bti=gr.Textbox(label="제목 *"); bau=gr.Textbox(label="저자 *"); bis=gr.Textbox(label="ISBN *")
                with gr.Row():
                    bpu=gr.Textbox(label="출판사"); byr=gr.Number(label="출판연도",precision=0); bge=gr.Textbox(label="장르")
                gr.Button("등록",variant="primary").click(book_add,[bti,bau,bis,bpu,byr,bge],
                    ar:=gr.Textbox(label="결과",interactive=False))

            with gr.Accordion("✏️ 수정", open=False):
                with gr.Row():
                    uid=gr.Number(label="도서 ID *",precision=0); uti=gr.Textbox(label="제목"); uau=gr.Textbox(label="저자")
                with gr.Row():
                    upu=gr.Textbox(label="출판사"); uyr=gr.Number(label="출판연도",precision=0); uge=gr.Textbox(label="장르")
                gr.Button("수정",variant="primary").click(book_update,[uid,uti,uau,upu,uyr,uge],
                    ur:=gr.Textbox(label="결과",interactive=False))

            with gr.Accordion("🗑️ 삭제", open=False):
                did=gr.Number(label="도서 ID *",precision=0)
                gr.Button("삭제",variant="stop").click(book_del,did,
                    dr:=gr.Textbox(label="결과",interactive=False))

        # ── 회원 ──────────────────────────────
        with gr.Tab("👥 회원 관리"):
            with gr.Row():
                mkw=gr.Textbox(label="🔍 검색",scale=5)
                gr.Button("검색").click(lambda k: members_load(k), mkw, [
                    mt:=gr.Dataframe(headers=MEMBER_H,interactive=False,wrap=True),
                    ms:=gr.Textbox(label="상태",interactive=False)
                ])
                gr.Button("전체").click(lambda: members_load(),[],[mt,ms])

            with gr.Accordion("➕ 등록", open=False):
                with gr.Row():
                    mna=gr.Textbox(label="이름 *"); mem=gr.Textbox(label="이메일 *")
                with gr.Row():
                    mph=gr.Textbox(label="전화번호"); mad=gr.Textbox(label="주소")
                gr.Button("등록",variant="primary").click(member_add,[mna,mem,mph,mad],
                    mr:=gr.Textbox(label="결과",interactive=False))

            with gr.Accordion("🗑️ 삭제", open=False):
                dmi=gr.Number(label="회원 ID *",precision=0)
                gr.Button("삭제",variant="stop").click(member_del,dmi,
                    dmr:=gr.Textbox(label="결과",interactive=False))

        # ── 대출/반납 ─────────────────────────
        with gr.Tab("📋 대출 / 반납"):
            with gr.Row():
                gr.Button("전체 조회").click(lambda: loans_load(False),[],[
                    lt:=gr.Dataframe(headers=LOAN_H,interactive=False,wrap=True),
                    ls:=gr.Textbox(label="상태",interactive=False)
                ])
                gr.Button("대출중만",variant="secondary").click(lambda: loans_load(True),[],[lt,ls])

            with gr.Accordion("📤 대출 처리", open=True):
                with gr.Row():
                    lbi=gr.Number(label="도서 ID *",precision=0); lmi=gr.Number(label="회원 ID *",precision=0)
                gr.Button("대출",variant="primary").click(loan_create,[lbi,lmi],
                    lrr:=gr.Textbox(label="결과",interactive=False))

            with gr.Accordion("📥 반납 처리", open=True):
                rlid=gr.Number(label="대출 ID *",precision=0)
                gr.Button("반납",variant="primary").click(loan_return,rlid,
                    rrr:=gr.Textbox(label="결과",interactive=False))

        # ── 통계 ──────────────────────────────
        with gr.Tab("📊 통계"):
            gr.Button("새로고침",variant="primary").click(load_stats,[],
                so:=gr.Textbox(label="현황",lines=8,interactive=False))

    ui.load(lambda: books_load(), [], [bt, bs])


# ══════════════════════════════════════════════
# 5. 실행 — FastAPI 백그라운드 + Gradio 포그라운드
# ══════════════════════════════════════════════

def run_api():
    uvicorn.run(api, host="127.0.0.1", port=8000, log_level="warning")

if __name__ == "__main__":
    print("🚀 FastAPI 백엔드 시작 중...")
    t = threading.Thread(target=run_api, daemon=True)
    t.start()
    time.sleep(1.5)          # API 뜰 때까지 잠깐 대기
    print("🎨 Gradio UI 시작 중...")
    print("━" * 40)
    print("  접속 주소 : http://localhost:7860")
    print("  API 문서  : http://localhost:8000/docs")
    print("━" * 40)
    ui.launch(server_port=7860)
