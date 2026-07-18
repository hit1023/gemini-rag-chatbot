#!/bin/bash
# k3s版 管理メニュー（run.shのk3s版）
# このスクリプトは k3s が動いているホスト（h-1）上で実行してください:
#   ssh h-1
#   cd /home/hit/docker/gemini-rag-chatbot
#   ./run-k3s.sh

BLUE='\033[0;34m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GRAY='\033[0;90m'
BOLD='\033[1m'
RESET='\033[0m'

NS=ragchat
KUBECTL="sudo k3s kubectl"
POSTGRES_HOST_IP="192.168.0.20"
NODEPORT=30081

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
  echo -e "  ${GRAY}アクセスURL:${RESET} ${CYAN}http://${ip}:${NODEPORT}${RESET}  ${GRAY}(本番は https://ragchat.s-quad.com/)${RESET}"
}

build_and_import_api() {
  echo -e "${GRAY}  api イメージをビルド中...${RESET}"
  docker build -t ragchat-api:k3s ./app || return 1
  echo -e "${GRAY}  k3s（containerd）へ取り込み中...${RESET}"
  docker save ragchat-api:k3s | sudo k3s ctr images import - || return 1
}

update_webui_configmap() {
  $KUBECTL create configmap webui-html --from-file=index.html=webui/index.html -n "$NS" --dry-run=client -o yaml | $KUBECTL apply -f - >/dev/null
  $KUBECTL create configmap webui-nginx-conf --from-file=nginx.conf=webui/nginx.conf -n "$NS" --dry-run=client -o yaml | $KUBECTL apply -f - >/dev/null
}

recreate_secret() {
  local gemini_key
  gemini_key=$(grep '^GEMINI_API_KEY=' .env | cut -d= -f2-)
  $KUBECTL create secret generic ragchat-env -n "$NS" \
    --from-literal=GEMINI_API_KEY="$gemini_key" \
    --from-literal=POSTGRES_DSN="postgresql://raguser:ragpass@${POSTGRES_HOST_IP}:5432/ragdb" \
    --dry-run=client -o yaml | $KUBECTL apply -f - >/dev/null
}

show_menu() {
  clear
  echo -e "${CYAN}${BOLD}"
  echo "  ╔════════════════════════════════════════╗"
  echo "  ║   Gemini RAG Chatbot  k3s管理メニュー  ║"
  echo "  ╚════════════════════════════════════════╝"
  echo -e "${RESET}"
  echo -e "  ${GRAY}namespace: ${NS}${RESET}"
  echo ""
  echo -e "  ${BOLD}1.${RESET}  ${GREEN}更新 & 全体デプロイ${RESET}   ${GRAY}(pull → api再ビルド → webui更新 → 再起動)${RESET}"
  echo -e "  ${BOLD}2.${RESET}  ${GREEN}webuiだけ更新${RESET}         ${GRAY}(ConfigMap再生成 → rollout restart)${RESET}"
  echo -e "  ${BOLD}3.${RESET}  ${GREEN}apiだけ更新${RESET}           ${GRAY}(イメージ再ビルド&取込 → rollout restart)${RESET}"
  echo -e "  ${BOLD}4.${RESET}  ${YELLOW}再起動${RESET}                ${GRAY}(rollout restart api+webui、再ビルドなし)${RESET}"
  echo -e "  ${BOLD}5.${RESET}  ${RED}停止${RESET}                  ${GRAY}(replicas=0、postgresは無関係で継続稼働)${RESET}"
  echo -e "  ${BOLD}6.${RESET}  ${GREEN}起動${RESET}                  ${GRAY}(replicas=1)${RESET}"
  echo -e "  ${BOLD}7.${RESET}  ${BLUE}ログを見る${RESET}            ${GRAY}(api / webui 選択)${RESET}"
  echo -e "  ${BOLD}8.${RESET}  ${BLUE}状態を確認${RESET}            ${GRAY}(get all -n ${NS})${RESET}"
  echo -e "  ${BOLD}9.${RESET}  ${YELLOW}Secret再生成${RESET}          ${GRAY}(.envのGEMINI_API_KEYを変更した時)${RESET}"
  echo -e "  ${BOLD}0.${RESET}  終了"
  echo ""
  echo -ne "  番号を選択 → "
}

while true; do
  show_menu
  read -r choice

  case $choice in
    1)
      echo -e "\n${GREEN}▶ 更新 & 全体デプロイ${RESET}"
      git pull
      check_env || { read -r; continue; }
      build_and_import_api || { echo -e "${RED}✗ apiビルド失敗${RESET}"; read -r; continue; }
      update_webui_configmap
      $KUBECTL apply -f k8s/namespace.yaml -f k8s/api.yaml -f k8s/webui.yaml
      $KUBECTL rollout restart deployment api webui -n "$NS"
      $KUBECTL rollout status deployment api -n "$NS"
      $KUBECTL rollout status deployment webui -n "$NS"
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    2)
      echo -e "\n${GREEN}▶ webuiだけ更新${RESET}"
      update_webui_configmap
      $KUBECTL rollout restart deployment webui -n "$NS"
      $KUBECTL rollout status deployment webui -n "$NS"
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    3)
      echo -e "\n${GREEN}▶ apiだけ更新${RESET}"
      check_env || { read -r; continue; }
      build_and_import_api || { echo -e "${RED}✗ apiビルド失敗${RESET}"; read -r; continue; }
      $KUBECTL rollout restart deployment api -n "$NS"
      $KUBECTL rollout status deployment api -n "$NS"
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    4)
      echo -e "\n${YELLOW}▶ 再起動${RESET}"
      $KUBECTL rollout restart deployment api webui -n "$NS"
      $KUBECTL rollout status deployment api -n "$NS"
      $KUBECTL rollout status deployment webui -n "$NS"
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    5)
      echo -e "\n${RED}▶ 停止${RESET}  ${GRAY}(postgresはDocker側なので影響なし)${RESET}"
      $KUBECTL scale deployment api webui -n "$NS" --replicas=0
      echo -e "${GREEN}✓ 停止しました${RESET}"
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    6)
      echo -e "\n${GREEN}▶ 起動${RESET}"
      $KUBECTL scale deployment api webui -n "$NS" --replicas=1
      $KUBECTL rollout status deployment api -n "$NS"
      $KUBECTL rollout status deployment webui -n "$NS"
      echo -e "${GREEN}✓ 完了${RESET}"
      show_url
      echo -e "${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    7)
      echo -ne "\n  ${BLUE}どちらのログ？${RESET} [1]api [2]webui → "
      read -r target
      case $target in
        1) echo -e "\n${BLUE}▶ api ログ ${GRAY}(Ctrl+C で戻る)${RESET}\n"; $KUBECTL logs -f deployment/api -n "$NS" ;;
        2) echo -e "\n${BLUE}▶ webui ログ ${GRAY}(Ctrl+C で戻る)${RESET}\n"; $KUBECTL logs -f deployment/webui -n "$NS" ;;
        *) echo -e "${RED}無効な選択${RESET}"; sleep 1 ;;
      esac
      ;;
    8)
      echo -e "\n${BLUE}▶ 状態確認${RESET}\n"
      $KUBECTL get all -n "$NS"
      echo ""
      show_url
      echo -e "\n${GRAY}Enterで戻る...${RESET}"
      read -r
      ;;
    9)
      echo -e "\n${YELLOW}▶ Secret再生成${RESET}  ${GRAY}(.envのGEMINI_API_KEYを読み込み直します)${RESET}"
      check_env || { read -r; continue; }
      recreate_secret
      echo -e "${YELLOW}  Secretは更新されましたが、Podは再起動しないと新しい値を読み込みません${RESET}"
      echo -ne "  今すぐ再起動しますか？ (y/N): "
      read -r yn
      [ "$yn" = "y" ] && $KUBECTL rollout restart deployment api webui -n "$NS"
      echo -e "${GREEN}✓ 完了${RESET}"
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
