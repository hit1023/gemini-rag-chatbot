import os
import psycopg2
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options={"api_version": "v1"},
)


def get_embedding(text: str) -> list[float]:
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
    )
    return result.embeddings[0].values


def ingest(texts: list[str]):
    conn = psycopg2.connect(os.environ["POSTGRES_DSN"])
    cur = conn.cursor()
    for text in texts:
        embedding = get_embedding(text)
        cur.execute(
            "INSERT INTO documents (content, embedding) VALUES (%s, %s)",
            (text, embedding),
        )
        print(f"登録: {text[:40]}")
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    sample_docs = [
        "ユーザーの名前はkuroです。",
        "ユーザーは55歳です。",
        "ユーザーは現在転職活動中です。転職候補先はAA株式会社とBB株式会社です。",
    ]
    ingest(sample_docs)
    print("登録完了")
