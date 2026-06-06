import os
import psycopg2
import google.generativeai as genai
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

app = FastAPI()


class ChatRequest(BaseModel):
    message: str


def get_embedding(text: str) -> list[float]:
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_query",
    )
    return result["embedding"]


def search_docs(embedding: list[float], top_k: int = 3) -> list[str]:
    conn = psycopg2.connect(os.environ["POSTGRES_DSN"])
    cur = conn.cursor()
    cur.execute(
        """SELECT content FROM documents
           ORDER BY embedding <=> %s::vector
           LIMIT %s""",
        (embedding, top_k),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]


@app.post("/chat")
def chat(req: ChatRequest):
    embedding = get_embedding(req.message)
    contexts = search_docs(embedding)
    context_text = "\n".join(f"- {c}" for c in contexts)

    prompt = f"""以下の情報を参考に質問に答えてください。

参考情報:
{context_text}

質問: {req.message}
"""
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return {"answer": response.text, "contexts": contexts}


@app.get("/")
def health():
    return {"status": "ok"}
