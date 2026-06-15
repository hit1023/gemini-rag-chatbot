#!/bin/bash
set -e

COMPOSE="docker compose"
ENV_FILE=".env"

# カラー定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

show_help() {
  echo "使い方: ./run.sh [コマンド]"
  echo ""
  echo "コマンド:"
  echo "  up       コンテナを起動（デフォルト）"
  echo "  down     コンテナを停止"
  echo "  restart  コンテナを再起動"
  echo "  logs     ログをリアルタイム表示"
  echo "  status   コンテナの状態確認"
  echo "  build    イメージを再ビルドして起動"
  echo "  reset    データを含めて完全リセット（⚠️ DB削除）"
  echo "  help     このヘルプを表示"
}

check_env() {
  if [ ! -f "$ENV_FILE" ]; then
    warn ".env ファイルが見つかりません。作成します。"
    read -rp "GEMINI_API_KEY を入力してください: " api_key
    echo "GEMINI_API_KEY=${api_key}" > "$ENV_FILE"
    info ".env を作成しました。"
  fi
  if ! grep -q "GEMINI_API_KEY" "$ENV_FILE" || grep -q "GEMINI_API_KEY=$" "$ENV_FILE"; then
    error "GEMINI_API_KEY が .env に設定されていません。"
  fi
}

get_local_ip() {
  ip a 2>/dev/null | grep -oP '(?<=inet )192\.\d+\.\d+\.\d+' | head -1 \
    || ipconfig getifaddr en0 2>/dev/null \
    || echo "localhost"
}

cmd_up() {
  check_env
  info "コンテナを起動します..."
  $COMPOSE up -d
  info "起動完了！"
  local ip
  ip=$(get_local_ip)
  echo ""
  echo -e "  アクセスURL: ${GREEN}http://${ip}:8031${NC}"
  echo ""
}

cmd_down() {
  info "コンテナを停止します..."
  $COMPOSE down
  info "停止しました。"
}

cmd_restart() {
  check_env
  info "コンテナを再起動します..."
  $COMPOSE restart
  info "再起動しました。"
}

cmd_logs() {
  info "ログを表示します（Ctrl+C で終了）"
  $COMPOSE logs -f
}

cmd_status() {
  $COMPOSE ps
}

cmd_build() {
  check_env
  info "イメージを再ビルドして起動します..."
  $COMPOSE build --no-cache api
  $COMPOSE up -d
  local ip
  ip=$(get_local_ip)
  info "起動完了！"
  echo ""
  echo -e "  アクセスURL: ${GREEN}http://${ip}:8031${NC}"
  echo ""
}

cmd_reset() {
  echo -e "${RED}⚠️  警告: DBのデータ（会話履歴・ドキュメント・アカウント）がすべて削除されます！${NC}"
  read -rp "本当に実行しますか？ (yes と入力して確認): " confirm
  if [ "$confirm" != "yes" ]; then
    info "キャンセルしました。"
    exit 0
  fi
  info "コンテナとボリュームを削除します..."
  $COMPOSE down -v
  check_env
  info "再起動します..."
  $COMPOSE up -d
  info "リセット完了！"
}

# メイン処理
case "${1:-up}" in
  up)      cmd_up ;;
  down)    cmd_down ;;
  restart) cmd_restart ;;
  logs)    cmd_logs ;;
  status)  cmd_status ;;
  build)   cmd_build ;;
  reset)   cmd_reset ;;
  help|--help|-h) show_help ;;
  *) error "不明なコマンド: $1  ( ./run.sh help で確認 )" ;;
esac
