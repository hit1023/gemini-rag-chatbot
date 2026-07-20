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
| 会話履歴の保存 | ユーザーごとにセッションをまたいで DB に保存 |
| 会話履歴一覧・再開 | 直近20件をAI要約タイトル付きで一覧表示し、クリックで再開 |
| ファイルアップロード | PDF / TXT のドラッグ＆ドロップ対応 |
| URL からのナレッジ追加 | 指定 URL（HTML / PDF）の本文を抽出して取り込み |
| URL クロール取り込み | 同一ドメイン内のリンクも辿って一括取り込み（ページ数・文字数に上限あり） |
| ドキュメント管理 | 登録済みファイルの一覧・個別削除・全削除 |
| ユーザー認証 | ログイン / 招待コード制の新規登録（JWT、30日有効） |
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
cp .env.example .env
```

`.env` に設定する項目は以下の4つです。**特に `REGISTER_CODE` と `SECRET_KEY` は、他人に勝手にアカウントを作られたり、なりすましログインされたりしないための重要な設定**なので、必ず値を入れてください（空のままでも動きますが、動くこと自体が問題です）。

| 変数名 | 必須 | 説明 |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Google Gemini API キー。取得方法は次項参照 |
| `POSTGRES_DSN` | ✅ | PostgreSQL接続文字列。`.env.example`の値をそのまま使えばOK（`docker-compose.yml`内で`postgres`コンテナ名解決に上書きされるため、ローカルからDBに直接繋ぐ時だけ使われます） |
| `REGISTER_CODE` | ✅ | **新規登録時に必要な招待コード**。好きな文字列を決めて入れてください（例: `mySecretInvite2026`）。**これを空にすると誰でも自由にアカウント登録できてしまうので、必ず設定してください** |
| `SECRET_KEY` | ✅ | JWT（ログイン用トークン）の署名に使う秘密鍵。以下のコマンドで生成した値を貼り付けてください |

`SECRET_KEY` の生成コマンド：

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

出力された64文字の文字列を `.env` の `SECRET_KEY=` の後に貼り付けます。

`.env` の記入例：

```env
GEMINI_API_KEY=AIzaSy...（自分のAPIキー）
POSTGRES_DSN=postgresql://raguser:ragpass@localhost:5432/ragdb
REGISTER_CODE=mySecretInvite2026
SECRET_KEY=8f3a1c9e2b7d4f6a0e5c8b1d3f7a9c2e4b6d8f0a1c3e5b7d9f1a3c5e7b9d1f3a
```

> **注意:**
> - `.env` ファイルは `.gitignore` に含まれており、GitHub にはアップロードされません
> - `REGISTER_CODE` は登録時に招待したい相手にだけ個別に伝えてください（例: Slack DMや口頭で）
> - `SECRET_KEY` を後から変更すると、**それまで発行済みのログイントークンが全て無効になり、全ユーザーが再ログインを求められます**。運用開始後は基本的に変更しないでください

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

### アカウント作成（招待コードが必要です）

1. ブラウザでアクセスすると、ログイン画面が表示されます
2. 「**新規登録**」タブをクリック
3. ユーザー名・パスワードに加えて、**「招待コード」欄に `.env` の `REGISTER_CODE` と同じ値**を入力
4. 「**アカウント作成**」をクリック

招待コードが間違っている（または未入力の）場合、`招待コードが正しくありません` というエラーが表示され、登録は失敗します。

他の人にアカウントを作ってもらいたい場合は、アプリのURLと一緒に `REGISTER_CODE` の値だけを個別に伝えてください。この値さえ知っていれば誰でも登録できてしまうため、ブログやREADMEなど不特定多数が見る場所には書かないでください。

> 同じユーザー名は登録できません。パスワードの最小文字数制限はありません。
>
> 招待コードを変更したい場合は、`.env` の `REGISTER_CODE` を書き換えてから `docker compose up -d --force-recreate api` を実行してください（`.env` を編集しただけではコンテナに反映されません）。

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

### URL からのナレッジ追加

1. 「**📄 ナレッジ追加**」エリア下の URL 入力欄に、取り込みたいページの URL を入力
2. 「**🔗 追加**」ボタンをクリック（Enter キーでも送信できます）
3. 指定した URL 1ページ分の本文（HTML の場合は `<script>` / `<style>` / `<nav>` / `<header>` / `<footer>` を除いたテキスト、PDF の場合は全文）が抽出され、チャンク化・ベクトル化されて登録されます

#### 関連ページも辿って取り込む（クロール機能）

「**関連ページも辿って取り込む（同一ドメイン内、最大5ページ）**」のチェックボックスをONにすると、指定したURLのページ内にある**同一ドメインへのリンク**も自動で辿って、まとめて取り込みます。

- 対象は**開始URL＋そのページ内のリンク（深さ1）のみ**。リンク先のさらに先（孫リンク）は辿りません
- 取得ページ数は**最大5ページ**（開始URL含む）
- 1ページあたりの本文は**最大20,000文字**で切り詰められます（巨大なページ1つで埋め込みAPIコストが暴走するのを防ぐため）
- リクエスト全体で**最大100チャンク**まで（ページ数・サイズに関わらず、埋め込みAPI呼び出し回数の絶対上限）
- リンクは**ページ内での出現順**に取得するため、目的のページ（例: 会社概要ページ）が5ページの中に入らない場合があります。その場合は、目的のページのURLを直接指定して個別に追加してください

> **コストに関する注意:** クロール機能自体（ページ取得・リンク抽出）はGeminiを使わず無料ですが、取り込んだテキストをチャンク単位でベクトル化する処理は毎回 Gemini Embedding API を呼びます。ページ数が多いほど、または本文が長いほど、Gemini API の呼び出し回数（＝コスト）が増える点に注意してください。

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

### 会話履歴の一覧・再開

左サイドバーの「**🧠 ユーザープロンプト**」の下に「**🕘 会話履歴**」セクションがあります。

- 直近**20件**のセッションが、新しい順に一覧表示されます
- 各セッションのタイトルは、**そのセッションの最初のユーザー発言をもとに Gemini が自動生成**します（10〜15文字程度、生成コストを抑えるため1セッションにつき1回だけ生成）
- タイトルを**クリックすると、そのセッションの会話をチャット画面に読み込んで再開**できます（自分のメッセージ入力欄はそのまま使えます）
- 現在表示中のセッションは枠が強調表示されます

> 会話履歴の一覧・再開はユーザーごとに分離されています。他のユーザーの会話は見えません。

---

## データの永続化

| データ | 保存先 |
|---|---|
| ドキュメント（ベクトル含む） | PostgreSQL（`documents` テーブル） |
| 会話履歴（メッセージ本文） | PostgreSQL（`conversations` テーブル） |
| 会話履歴（セッションタイトル） | PostgreSQL（`chat_sessions` テーブル） |
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
| URL取り込み・クロール | `requests`（HTTP取得） + `beautifulsoup4`（HTML解析・リンク抽出） |
| PDF解析 | `pypdf` |

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

# コード変更後の再ビルド・再起動（app/ 配下を編集した場合）
docker compose up -d --build api

# .env の環境変数を変更した場合（再ビルド不要、再作成のみ必要）
docker compose up -d --force-recreate api

# webui（index.html / nginx.conf）を編集した場合
docker compose up -d --force-recreate webui

# PostgreSQL に直接接続
docker exec -it gemini-rag-chatbot-postgres-1 psql -U raguser -d ragdb

# 全コンテナの状態確認
docker compose ps
```

> `docker compose restart <service>` は環境変数の再読み込みやマウントの再設定を行わないため、`.env` の変更やファイルの丸ごと置き換え後は上記の `--force-recreate` を使ってください。

---

## トラブルシューティング

### ブラウザに古い画面が表示される

nginx がキャッシュを返している可能性があります。

```
Mac: Cmd + Shift + R
Windows/Linux: Ctrl + Shift + R
```

それでも解決しない場合（特に `scp` 等でファイルを丸ごと置き換えた場合）：

```bash
docker compose up -d --force-recreate webui
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
- `SECRET_KEY` を変更した直後は、それ以前に発行済みのトークンが全て無効になります。全ユーザーが再ログインすれば解決します

### 新規登録で「招待コードが正しくありません」と出る

- 入力した招待コードが `.env` の `REGISTER_CODE` の値と一致しているか確認してください（大文字小文字も区別されます）
- `.env` の `REGISTER_CODE` を編集した場合、コンテナに反映するには再作成が必要です：
  ```bash
  docker compose up -d --force-recreate api
  ```

### 招待コードなしで誰でも登録できてしまう

`.env` に `REGISTER_CODE` を設定していない（空のまま）と、招待コードチェックが無効になり誰でも登録できてしまいます。`.env` に値を設定し、上記コマンドで `api` を再作成してください。

### `.env` を編集したのに反映されない

`docker compose up -d` だけでは、既に起動中のコンテナは環境変数を再読み込みしません。`.env` を編集した後は、必ずコンテナを再作成してください。

```bash
docker compose up -d --force-recreate api
```

### フロントエンド（`webui/index.html`）を編集したのに画面が変わらない

`webui` は `nginx:alpine` イメージに `index.html` をそのままマウントしているため、通常はファイルを書き換えるだけで即時反映されます。ただし、ファイルを `scp` 等で**丸ごと置き換えた**場合（元のファイルとは別の実体になるコピー方法）、Docker のマウントが古い実体を掴んだままになり反映されないことがあります。その場合は `webui` コンテナ自体を再作成してください。

```bash
docker compose up -d --force-recreate webui
```

それでも直らない場合は、ブラウザのハードリロード（Mac: `Cmd + Shift + R` / Windows: `Ctrl + Shift + R`）も試してください。

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
