import os
import json
import uuid
import psycopg2
import requests
from urllib.parse import urlparse, urljoin
from google import genai
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
from pypdf import PdfReader
from bs4 import BeautifulSoup
from passlib.context import CryptContext
from jose import jwt, JWTError
import io
from datetime import datetime, timedelta

load_dotenv()

api_key = os.environ["GEMINI_API_KEY"]
embed_client = genai.Client(api_key=api_key, http_options={"api_version": "v1"})
chat_client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-please")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

app = FastAPI()

DEFAULT_PROMPT = """あなたは親切なアシスタントです。
以下の「ユーザー情報」はチャット相手のユーザー自身に関する登録情報です。
「あなた」という言葉が出た場合はチャット相手のユーザーを指します。
この情報と会話履歴を踏まえて質問に答えてください。"""


def get_db():
    return psycopg2.connect(os.environ["POSTGRES_DSN"])


# ===== 認証 =====

def create_token(user_id: int, username: str) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "username": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {"id": int(payload["sub"]), "username": payload["username"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="トークンが無効です")


REGISTER_CODE = os.environ.get("REGISTER_CODE", "")


class AuthRequest(BaseModel):
    username: str
    password: str
    invite_code: str = ""


@app.post("/auth/register")
def register(req: AuthRequest):
    if REGISTER_CODE and req.invite_code != REGISTER_CODE:
        raise HTTPException(status_code=403, detail="招待コードが正しくありません")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = %s", (req.username,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="このユーザー名は既に使われています")
    hashed = pwd_context.hash(req.password)
    cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id", (req.username, hashed))
    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"token": create_token(user_id, req.username), "username": req.username}


@app.post("/auth/login")
def login(req: AuthRequest):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (req.username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row or not pwd_context.verify(req.password, row[1]):
        raise HTTPException(status_code=401, detail="ユーザー名またはパスワードが違います")
    return {"token": create_token(row[0], req.username), "username": req.username}


# ===== Embedding =====

def get_embedding(text: str) -> list[float]:
    result = embed_client.models.embed_content(model="gemini-embedding-001", contents=text)
    return result.embeddings[0].values


# ===== 会話履歴 =====

def get_history(session_id: str, user_id: int, limit: int = 10) -> list[dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM conversations WHERE session_id = %s AND user_id = %s ORDER BY created_at DESC LIMIT %s",
        (session_id, user_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def save_message(session_id: str, user_id: int, role: str, content: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conversations (session_id, user_id, role, content) VALUES (%s, %s, %s, %s)",
        (session_id, user_id, role, content),
    )
    conn.commit()
    cur.close()
    conn.close()


def search_docs(embedding: list[float], user_id: int, top_k: int = 3) -> list[str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT content FROM documents WHERE user_id = %s ORDER BY embedding <=> %s::vector LIMIT %s",
        (user_id, embedding, top_k),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]


def chunk_text(text: str, size: int = 300, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size].strip())
        start += size - overlap
    return [c for c in chunks if len(c) > 20]


# ===== チャット =====

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    system_prompt: str = DEFAULT_PROMPT


@app.post("/chat")
def chat(req: ChatRequest, user=Depends(get_current_user)):
    session_id = req.session_id or str(uuid.uuid4())
    user_id = user["id"]

    embedding = get_embedding(req.message)
    contexts = search_docs(embedding, user_id)
    context_text = "\n".join(f"- {c}" for c in contexts)
    history = get_history(session_id, user_id, limit=5)
    history_text = "\n".join(
        f"{'ユーザー' if h['role'] == 'user' else 'アシスタント'}: {h['content']}"
        for h in history
    )
    prompt = f"""{req.system_prompt}

ユーザー情報:
{context_text}

会話履歴:
{history_text}

ユーザー: {req.message}
"""
    try:
        from google.genai import types
        response = chat_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=3000,
                )
            ),
        )
        # 思考内容と回答を分離
        thinking = ""
        answer = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, "thought") and part.thought:
                thinking += part.text
            else:
                answer += part.text
    except Exception as e:
        err = str(e)
        thinking = ""
        if "429" in err:
            answer = "ごめんね、今ちょっと混んでて返事できないんだ。少し待ってからもう一度話しかけてね。(ERR429)"
        elif "503" in err or "UNAVAILABLE" in err:
            answer = "ごめんね、今サービスが不安定みたい。少し待ってからもう一度試してね。(ERR503)"
        else:
            answer = "ごめんね、うまく返事できなかったよ。もう一度試してみて。(ERR000)"

    save_message(session_id, user_id, "user", req.message)
    save_message(session_id, user_id, "assistant", answer)
    ensure_chat_session(session_id, user_id, req.message)

    return {"answer": answer, "thinking": thinking, "contexts": contexts, "session_id": session_id}


# ===== 会話履歴（セッション一覧） =====

def generate_session_title(user_message: str) -> str:
    try:
        prompt = (
            "次のユーザー発言の内容を表す、10〜15文字程度の短い日本語タイトルを1つだけ出力してください。"
            "タイトル以外の説明・記号・引用符は出力しないでください。\n\n"
            f"発言: {user_message[:500]}"
        )
        response = chat_client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
        title = (response.text or "").strip().splitlines()[0].strip()
        return title[:30] if title else user_message[:20]
    except Exception:
        return user_message[:20]


def ensure_chat_session(session_id: str, user_id: int, first_message: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM chat_sessions WHERE session_id = %s", (session_id,))
    if cur.fetchone():
        cur.execute("UPDATE chat_sessions SET updated_at = NOW() WHERE session_id = %s", (session_id,))
    else:
        # chat_sessions未登録のまま既存の会話履歴がある場合（本機能導入前のセッション）は、
        # 本当の最初の発言をタイトル生成に使う
        cur.execute(
            "SELECT content FROM conversations WHERE session_id = %s AND role = 'user' ORDER BY created_at ASC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
        basis = row[0] if row else first_message
        title = generate_session_title(basis)
        cur.execute(
            "INSERT INTO chat_sessions (session_id, user_id, title, updated_at) VALUES (%s, %s, %s, NOW())",
            (session_id, user_id, title),
        )
    conn.commit()
    cur.close()
    conn.close()


@app.get("/sessions")
def list_sessions(user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, title, updated_at FROM chat_sessions WHERE user_id = %s ORDER BY updated_at DESC LIMIT 20",
        (user["id"],),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"sessions": [{"session_id": r[0], "title": r[1], "updated_at": r[2].isoformat()} for r in rows]}


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM conversations WHERE session_id = %s AND user_id = %s ORDER BY created_at ASC",
        (session_id, user["id"]),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"messages": [{"role": r[0], "content": r[1]} for r in rows]}


# ===== ファイルアップロード =====

@app.post("/upload")
async def upload(file: UploadFile = File(...), user=Depends(get_current_user)):
    content = await file.read()
    filename = file.filename or ""
    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif filename.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="PDF または TXT ファイルのみ対応しています")
    chunks = chunk_text(text)
    conn = get_db()
    cur = conn.cursor()
    for chunk in chunks:
        emb = get_embedding(chunk)
        cur.execute(
            "INSERT INTO documents (content, embedding, metadata, user_id) VALUES (%s, %s, %s, %s)",
            (chunk, emb, f'{{"filename": "{filename}"}}', user["id"]),
        )
    conn.commit()
    cur.close()
    conn.close()
    return {"message": f"{len(chunks)} チャンクを登録しました", "filename": filename}


# ===== URL取り込み =====

MAX_CRAWL_PAGES = 5  # クロール時の最大取得ページ数
MAX_PAGE_CHARS = 20000  # 1ページあたりの最大文字数（巨大ページによるコスト暴走を防止。超過分は切り捨て）
MAX_TOTAL_CHUNKS = 100  # 1回のURL取り込みリクエストで埋め込みAPIを呼ぶ最大チャンク数（コストの絶対上限）


def fetch_page_content(url: str) -> tuple[str, str]:
    """(抽出テキスト, 生HTML) を返す。PDFの場合はリンクを持たないため生HTMLは空文字。
    テキストは MAX_PAGE_CHARS で切り詰める（巨大ページによる埋め込みAPIコスト暴走を防ぐため）。"""
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(resp.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text[:MAX_PAGE_CHARS], ""
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return text[:MAX_PAGE_CHARS], html


def fetch_url_text(url: str) -> str:
    text, _ = fetch_page_content(url)
    return text


def extract_same_domain_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        link = urljoin(base_url, a["href"])
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or parsed.netloc != base_domain:
            continue
        clean = parsed._replace(fragment="").geturl()
        if clean not in seen:
            seen.add(clean)
            links.append(clean)
    return links


def crawl_urls(start_url: str, max_pages: int = MAX_CRAWL_PAGES) -> list[tuple[str, str]]:
    """開始URLと、そこから同一ドメインへ張られたリンク（深さ1）を最大max_pagesページ取得する"""
    results = []
    visited = {start_url}

    text, html = fetch_page_content(start_url)
    if text.strip():
        results.append((start_url, text))

    if html and len(results) < max_pages:
        for link in extract_same_domain_links(html, start_url):
            if len(results) >= max_pages:
                break
            if link in visited:
                continue
            visited.add(link)
            try:
                page_text, _ = fetch_page_content(link)
                if page_text.strip():
                    results.append((link, page_text))
            except Exception:
                continue  # 個別ページの取得失敗はスキップして続行

    return results


class UrlIngestRequest(BaseModel):
    url: str
    crawl: bool = False


@app.post("/upload-url")
def upload_url(req: UrlIngestRequest, user=Depends(get_current_user)):
    try:
        if req.crawl:
            pages = crawl_urls(req.url)
        else:
            pages = [(req.url, fetch_url_text(req.url))]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"URLの取得に失敗しました: {e}")

    conn = get_db()
    cur = conn.cursor()
    total_chunks = 0
    truncated = False
    for page_url, text in pages:
        if not text.strip():
            continue
        metadata = json.dumps({"filename": page_url, "source_url": page_url})
        for chunk in chunk_text(text):
            if total_chunks >= MAX_TOTAL_CHUNKS:
                truncated = True
                break
            emb = get_embedding(chunk)
            cur.execute(
                "INSERT INTO documents (content, embedding, metadata, user_id) VALUES (%s, %s, %s, %s)",
                (chunk, emb, metadata, user["id"]),
            )
            total_chunks += 1
        if truncated:
            break
    conn.commit()
    cur.close()
    conn.close()

    if total_chunks == 0:
        raise HTTPException(status_code=400, detail="URLからテキストを抽出できませんでした")

    message = f"{len(pages)}ページ・{total_chunks}チャンクを登録しました"
    if truncated:
        message += f"（上限{MAX_TOTAL_CHUNKS}チャンクに達したため一部は取り込んでいません）"

    return {
        "message": message,
        "url": req.url,
        "pages_fetched": len(pages),
    }


# ===== ドキュメント管理 =====

@app.get("/documents")
def list_documents(user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT metadata->>'filename', COUNT(*) FROM documents WHERE user_id = %s GROUP BY metadata->>'filename' ORDER BY 1",
        (user["id"],),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"documents": [{"filename": r[0] or "（直接登録）", "chunks": r[1]} for r in rows]}


@app.delete("/documents")
def delete_documents(user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM documents WHERE user_id = %s", (user["id"],))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "全ドキュメントを削除しました"}


@app.delete("/documents/{filename}")
def delete_document_by_filename(filename: str, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM documents WHERE metadata->>'filename' = %s AND user_id = %s",
        (filename, user["id"]),
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return {"message": f"{deleted}チャンクを削除しました"}


@app.get("/settings")
def get_settings(user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT system_prompt, user_profile FROM user_settings WHERE user_id = %s", (user["id"],))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {"system_prompt": row[0], "user_profile": row[1]}
    return {"system_prompt": DEFAULT_PROMPT, "user_profile": ""}


class SettingsRequest(BaseModel):
    system_prompt: str = ""
    user_profile: str = ""


@app.put("/settings")
def save_settings(req: SettingsRequest, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_settings (user_id, system_prompt, user_profile, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE
        SET system_prompt = EXCLUDED.system_prompt,
            user_profile = EXCLUDED.user_profile,
            updated_at = NOW()
    """, (user["id"], req.system_prompt, req.user_profile))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "保存しました"}


@app.get("/user-profile")
def generate_user_profile(user=Depends(get_current_user)):
    """会話履歴を分析してユーザープロファイルを生成する"""
    user_id = user["id"]
    conn = get_db()
    cur = conn.cursor()
    # 全会話履歴を取得（最大200件）
    cur.execute(
        "SELECT role, content FROM conversations WHERE user_id = %s ORDER BY created_at DESC LIMIT 200",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return {"profile": "まだ会話履歴がありません。チャットしてから再度お試しください。"}

    history_text = "\n".join(
        f"{'ユーザー' if r[0] == 'user' else 'AI'}: {r[1]}"
        for r in reversed(rows)
    )

    prompt = f"""以下はユーザーとAIの会話履歴です。この会話を分析して、ユーザーの人物像をまとめてください。

会話履歴:
{history_text}

以下の形式で日本語でまとめてください。箇条書きで簡潔に記述してください：

## 長所
（会話から読み取れるユーザーの良い点・強み）

## 短所・課題
（会話から読み取れる改善点や苦手な傾向）

## 接し方・コミュニケーションのコツ
（このユーザーと上手く接するためのポイント）

※会話履歴から読み取れる範囲でのみ記述し、推測が強い場合はその旨を記述してください。"""

    try:
        response = chat_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        profile = response.text
    except Exception as e:
        err = str(e)
        if "429" in err:
            profile = "レート制限中です。少し待ってから再試行してください。"
        else:
            profile = f"プロファイル生成に失敗しました: {err}"

    return {"profile": profile}


@app.get("/health")
def health():
    return {"status": "ok"}
