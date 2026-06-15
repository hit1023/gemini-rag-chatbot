#!/bin/bash

BLUE='\033[0;34m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GRAY='\033[0;90m'
BOLD='\033[1m'
RESET='\033[0m'

get_local_ip() {
  ip a 2>/dev/null | grep -oP '(?<=inet )192\.\d+\.\d+\.\d+' | head -1 \
    || ipconfig getifaddr en0 2>/dev/null \
    || echo "localhost"
}

check_env() {
  if [ ! -f ".env" ]; then
    echo -e "\n${YELLOW}⚠  .env が見つかりません。作成します。${RESET}"
    read -rp "  GEMINI_API_KEY を入力してください: " api_key
    echo "GEMINI_API_KEY=${api_key}" > .env
    echo -e "${GREEN}✓ .env を作成しました${RESET}"
  fi
  if grep -q "GEMINI_API_KEY=$" .env 2>/dev/null; then
    echo -e "${RED}✗ GEMINI_API_KEY が未設定です。.env を確認してください。${RESET}"
    sleep 2
    return 1
  fi
}

show_url() {
  local ip
  ip=$(get_local_ip)
  echo -e "  ${GRAY}アクセスURL:${RESET} ${CYAN}http://${ip}:8031${RESET}"
}

show_menu() {
  clear
  echo -e "${CYAN}${BOLD}"
  echo "  ╔════════════════════════════════════════╗"
  echo "  ║     Gemini RAG Chatbot  管理メニュー  ║"
  echo "  ╚════════════════════════════════════════╝"
  echo -e "${RESET}"
  echo -e "  ${BOLD}1.${RESET}  ${GREEN}更新 & 起動${RESET}       ${GRAY}(pull → down → build → up)${RESET}"
  echo -e "  ${BOLD}2.${RESET}  ${GREEN}ビルド & 起動${RESET}     ${GRAY}(down → build → up)${RESET}"
  echo -e "  ${BOLD}3.${RESET}  ${GREEN}起動${RESET}              ${GRAY}(up -d)${RESET}"
  echo -e "  ${BOLD}4.${RESET}  ${YELLOW}再起動${RESET}            ${GRAY}(restart)${RESET}"
  echo -e "  ${BOLD}5.${RESET}  ${RED}停止${RESET}              ${GRAY}(down)${RESET}"
  echo -e "  ${BOLD}6.${RESET}  ${BLUE}ログを見る${RESET}        ${GRAY}(logs -f)${RESET}"
  echo -e "  ${BOLD}7.${RESET}  ${BLUE}状態を確認${RESET}        ${GRAY}(ps)${RESET}"
  echo -e "  ${BOLD}8.${RESET}  ${RED}完全リセット${RESET}      ${GRAY}(down -v → up) ⚠️  DB削除${RESET}"
  echo -e "  ${BOLD}0.${RESET}  終了"
  echo ""
  echo -ne "  番号を選択 → "
}

while true; do
  show_menu
  read -r choice

  case $choice in
    1)
      echo -e "\n${GREEN}▶ 更新 & 起動${RESET}"
      git pull
      check_env || { read -r; continue; }
      docker compose down
      docker compose up -d --build
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    2)
      echo -e "\n${GREEN}▶ ビルド & 起動${RESET}"
      check_env || { read -r; continue; }
      docker compose down
      docker compose up -d --build
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    3)
      echo -e "\n${GREEN}▶ 起動${RESET}"
      check_env || { read -r; continue; }
      docker compose up -d
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    4)
      echo -e "\n${YELLOW}▶ 再起動${RESET}"
      docker compose restart
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    5)
      echo -e "\n${RED}▶ 停止${RESET}"
      docker compose down
      echo -e "${GREEN}✓ 停止しました${RESET}"
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    6)
      echo -e "\n${BLUE}▶ ログ表示 ${GRAY}(Ctrl+C で戻る)${RESET}\n"
      docker compose logs -f
      ;;
    7)
      echo -e "\n${BLUE}▶ 状態確認${RESET}\n"
      docker compose ps
      echo ""
      show_url
      echo -e "\n${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    8)
      echo -e "\n${RED}⚠️  警告: DB のデータ（会話履歴・ドキュメント・アカウント）が全て削除されます！${RESET}"
      echo -ne "  本当に実行しますか？ (yes と入力して確認): "
      read -r confirm
      if [ "$confirm" = "yes" ]; then
        docker compose down -v
        check_env || { read -r; continue; }
        docker compose up -d
        echo -e "${GREEN}✓ リセット完了${RESET}"
        show_url
      else
        echo -e "${GRAY}キャンセルしました${RESET}"
      fi
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    0)
      echo -e "\n${GRAY}終了します${RESET}\n"
      exit 0
      ;;
    *)
      echo -e "\n${RED}無効な番号です${RESET}"
      sleep 1
      ;;
  esac
done
