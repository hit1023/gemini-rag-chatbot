# Gemini RAG Chatbot

Google Gemini と PostgreSQL（pgvector）を使った RAG（検索拡張生成）チャットボットです。  
PDF / TXT ファイルをアップロードしてナレッジベースを構築し、会話履歴を記憶しながら回答します。  
マルチユーザー対応・ユーザーごとのデータ分離・Gemini Thinking（CoT）表示機能を備えています。

---

## 機能一覧

| 機能 | 概要 |
|---|---|
| RAG チャット | アップロードしたドキュメントを参照して回答 |
| Gemini Thinking | 回答生成中の思考内容をステータスバーに表示 |
| 会話履歴 | ユーザーごとにセッションをまたいで保存 |
| ファイルアップロード | PDF / TXT のドラッグ＆ドロップ対応 |
| ドキュメント管理 | 登録済みファイルの一覧・個別削除・全削除 |
| ユーザー認証 | ログイン / 新規登録（JWT、30日有効） |
| システムプロンプト | UI 上から編集・DB に永続保存 |
| ユーザープロファイル | 会話履歴から長所・短所・接し方を AI が自動分析 |

---

## システム構成

```
┌─────────────────────────────────────────┐
│  ブラウザ  http://localhost:8031         │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│  webui（nginx:alpine）  port 8031       │
│  /api/* → FastAPI へリバースプロキシ    │
│  /      → index.html 配信              │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│  api（FastAPI + Uvicorn）  port 8030    │
│  RAG パイプライン                       │
│  Gemini API（Embedding / Chat）         │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│  postgres（pgvector/pgvector:pg16）     │
│  ベクトル検索（3072次元）               │
└─────────────────────────────────────────┘
```

---

## 必要なもの

- Docker Desktop（または Docker Engine + Docker Compose）
- Google Gemini API キー（有料プラン推奨）

### Gemini API キーの取得

1. [Google AI Studio](https://aistudio.google.com/) にアクセス
2. 「Get API key」→「Create API key」でキーを発行
3. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトに課金を紐付け（無料枠は 1 日あたりのリクエスト数が少ないため）

---

## セットアップ手順

### 1. リポジトリをクローン

```bash
git clone git@github.com:hit1023/gemini-rag-chatbot.git
cd gemini-rag-chatbot
```

### 2. 環境変数ファイルを作成

プロジェクトルートに `.env` ファイルを作成します。

```bash
cp .env.example .env   # サンプルがある場合
# または直接作成
```

`.env` の内容：

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

> **注意:** `.env` ファイルは `.gitignore` に含まれており、GitHub にはアップロードされません。

### 3. コンテナを起動

```bash
docker compose up -d
```

初回起動時は Docker イメージのビルドとライブラリのインストールが行われます（数分かかります）。

### 4. 起動確認

```bash
docker compose ps
```

3 つのサービス（`postgres`・`api`・`webui`）が `running` になっていれば OK です。

```bash
docker compose logs api   # API のログを確認
```

### 5. ブラウザでアクセス

```
http://localhost:8031
```

---

## 初期設定（ブラウザ）

### アカウント作成

1. ブラウザでアクセスすると、ログイン画面が表示されます
2. 「**新規登録**」タブをクリック
3. ユーザー名・パスワードを入力して「**アカウント作成**」

> 同じユーザー名は登録できません。パスワードの最小文字数制限はありません。

### ログイン

1. 「**ログイン**」タブでユーザー名・パスワードを入力
2. 「**ログイン**」ボタンをクリック

JWT トークンは `localStorage` に保存されます（30日間有効）。

---

## 使い方

### ドキュメントのアップロード

1. 左サイドバーの「**📄 ナレッジ追加**」エリアにファイルをドラッグ＆ドロップ
2. または、エリアをクリックしてファイルを選択
3. 対応形式：**PDF**・**TXT**

アップロードされたドキュメントはテキストを 300 文字ずつチャンクに分割し、Gemini Embedding でベクトル化して PostgreSQL に保存されます。

### チャット

1. 画面右下の入力欄にメッセージを入力
2. 「**送信**」ボタンをクリック（Enter キーは日本語 IME との干渉を避けるため無効）
3. 回答生成中は入力欄上部に **Thinking ステータスバー**が表示されます（30 秒間表示）

### システムプロンプトの編集

1. 左サイドバーの「**✏️ システムプロンプト**」テキストエリアを編集
2. 「**✅ プロンプトを保存**」ボタンをクリック
3. 保存内容は DB に記録され、次回ログイン時も復元されます

### ユーザープロファイルの生成

1. 左サイドバーの「**🧠 ユーザープロンプト**」セクションの「**✨ 生成**」ボタンをクリック
2. これまでの会話履歴（最大 200 件）を AI が分析し、以下を自動生成します
   - **長所**
   - **短所・課題**
   - **接し方・コミュニケーションのコツ**
3. 生成後は自動で DB に保存されます（次回ログイン時も復元）

### 登録済みドキュメントの管理

- サイドバーの「**📋 登録済みドキュメント**」でファイル名・チャンク数を確認できます
- **🗑** ボタンで個別削除
- 「**🗑️ 全て削除**」ボタンで一括削除

### 新しい会話の開始

「**＋ 新しい会話を始める**」ボタンをクリックすると、新しいセッション ID が発行されます。  
過去の会話はサーバー上に保存されたままです。

---

## データの永続化

| データ | 保存先 |
|---|---|
| ドキュメント（ベクトル含む） | PostgreSQL（`documents` テーブル） |
| 会話履歴 | PostgreSQL（`conversations` テーブル） |
| ユーザーアカウント | PostgreSQL（`users` テーブル） |
| システムプロンプト | PostgreSQL（`user_settings` テーブル） |
| ユーザープロファイル | PostgreSQL（`user_settings` テーブル） |
| JWT トークン | ブラウザの `localStorage` |
| セッション ID | ブラウザの `localStorage` |

PostgreSQL のデータは Docker ボリューム（`postgres_data`）に永続化されます。  
`docker compose down` してもデータは消えません。  
データを完全に削除するには：

```bash
docker compose down -v   # ボリュームごと削除（データ完全消去）
```

---

## 技術スタック

| レイヤー | 使用技術 |
|---|---|
| フロントエンド | HTML / CSS / Vanilla JavaScript（SPA） |
| リバースプロキシ | nginx:alpine |
| バックエンド | FastAPI + Uvicorn（Python 3.11） |
| AI / Embedding | Google Gemini API（`google-genai` SDK） |
| 生成モデル | `gemini-2.5-flash-lite`（Thinking 有効） |
| Embedding モデル | `gemini-embedding-001`（3072 次元） |
| ベクトル DB | PostgreSQL + pgvector（`pgvector/pgvector:pg16`） |
| 認証 | JWT（`python-jose`）+ bcrypt（`passlib`） |

---

## Gemini API について

### 使用するモデル

| 用途 | モデル | API バージョン |
|---|---|---|
| テキスト生成（チャット） | `gemini-2.5-flash-lite` | v1beta |
| Embedding（ベクトル化） | `gemini-embedding-001` | v1 |

### レート制限

- 無料プランは 1 日あたりのリクエスト数が少なく、すぐに制限に達します
- 有料プランでの利用を推奨します
- 429 エラー時はフレンドリーなメッセージを表示します

---

## 主なコマンド

```bash
# 起動
docker compose up -d

# 停止
docker compose down

# ログ確認
docker compose logs -f api
docker compose logs -f webui

# API の再起動
docker compose restart api

# webui の再起動（HTML 更新後）
docker compose restart webui

# PostgreSQL に直接接続
docker exec -it gemini-rag-chatbot-postgres-1 psql -U raguser -d ragdb

# 全コンテナの状態確認
docker compose ps
```

---

## トラブルシューティング

### ブラウザに古い画面が表示される

nginx がキャッシュを返している可能性があります。

```
Mac: Cmd + Shift + R
Windows/Linux: Ctrl + Shift + R
```

それでも解決しない場合：

```bash
docker compose restart webui
```

### API が起動しない

```bash
docker compose logs api
```

よくある原因：
- `.env` に `GEMINI_API_KEY` が設定されていない
- PostgreSQL の起動完了前に API が起動しようとしている（`depends_on` の `healthcheck` で対策済みですが、初回は時間がかかることがあります）

### 429 エラー（レート制限）

Gemini API の無料枠を超えています。

- 有料プランへの切り替え
- Google Cloud Console でプロジェクトへの課金を紐付け

### ログインできない

- ユーザー名・パスワードを確認
- ブラウザの `localStorage` をクリアして再試行：
  ```
  DevTools（F12）→ Application → Local Storage → 全削除 → リロード
  ```

---

## ディレクトリ構成

```
gemini-rag-chatbot/
├── docker-compose.yml       # Docker Compose 定義
├── .env                     # 環境変数（要作成・Git 管理外）
├── .env.example             # 環境変数サンプル
├── app/
│   ├── Dockerfile           # FastAPI コンテナ定義
│   ├── main.py              # FastAPI アプリ本体
│   ├── requirements.txt     # Python 依存ライブラリ
│   └── ingest.py            # ドキュメント直接投入スクリプト
├── webui/
│   ├── nginx.conf           # nginx 設定
│   └── index.html           # フロントエンド SPA
└── postgres/
    └── init.sql             # DB 初期化 SQL
```

---

## ライセンス

MIT
