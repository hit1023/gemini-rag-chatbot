import os
import uuid
import psycopg2
from google import genai
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
from pypdf import PdfReader
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


class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/register")
def register(req: AuthRequest):
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
        response = chat_client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
        answer = response.text
    except Exception as e:
        err = str(e)
        if "429" in err:
            answer = "ごめんね、今ちょっと混んでて返事できないんだ。少し待ってからもう一度話しかけてね。(ERR429)"
        elif "503" in err or "UNAVAILABLE" in err:
            answer = "ごめんね、今サービスが不安定みたい。少し待ってからもう一度試してね。(ERR503)"
        else:
            answer = f"ごめんね、うまく返事できなかったよ。もう一度試してみて。(ERR000)"

    save_message(session_id, user_id, "user", req.message)
    save_message(session_id, user_id, "assistant", answer)

    return {"answer": answer, "contexts": contexts, "session_id": session_id}


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


@app.get("/health")
def health():
    return {"status": "ok"}
