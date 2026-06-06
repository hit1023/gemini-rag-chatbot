import os
import psycopg2
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])


def get_embedding(text: str) -> list[float]:
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document",
    )
    return result["embedding"]


def ingest(texts: list[str]):
    conn = psycopg2.connect(os.environ["POSTGRES_DSN"])
    cur = conn.cursor()
    for text in texts:
        embedding = get_embedding(text)
        cur.execute(
            "INSERT INTO documents (content, embedding) VALUES (%s, %s)",
            (text, embedding),
        )
        print(f"登録: {text[:40]}...")
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    sample_docs = [
        "Pythonはシンプルで読みやすいプログラミング言語です。",
        "Dockerはコンテナベースのアプリケーションデプロイツールです。",
        "PostgreSQLはオープンソースのリレーショナルデータベースです。",
        "RAGとはRetrieval-Augmented Generationの略で、検索と生成を組み合わせた手法です。",
        "pgvectorはPostgreSQLでベクトル検索を実現する拡張機能です。",
    ]
    ingest(sample_docs)
    print("登録完了")
