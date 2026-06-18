#!/usr/bin/env bash
# 서버에서 실행하는 배포 스크립트 (GitHub Actions SSH 단계 또는 수동 실행).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
APP_PORT="${E2E_APP_PORT:-8001}"
PYTHON_BIN="${E2E_PYTHON_BIN:-python3.11}"

echo "[deploy] app dir: $APP_DIR (port $APP_PORT)"

if [[ ! -f requirements.txt ]]; then
  echo "[deploy] requirements.txt not found — wrong directory?" >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[deploy] $PYTHON_BIN not found — installing python3.11"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.11 python3.11-venv curl
fi

if ! command -v curl >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl
fi

if [[ ! -f .env ]]; then
  echo "[deploy] WARNING: .env 없음 — cp .env.example .env 후 값을 채워 주세요."
fi

if [[ ! -d .venv ]] || ! .venv/bin/python -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo "[deploy] creating venv with $PYTHON_BIN"
  rm -rf .venv
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[deploy] installing Python dependencies"
python -m pip install -U pip wheel
python -m pip install -r requirements.txt

if ! python -c "import playwright" 2>/dev/null; then
  echo "[deploy] playwright import failed" >&2
  exit 1
fi

if ! dpkg -s libnss3 >/dev/null 2>&1; then
  echo "[deploy] installing Playwright OS dependencies (sudo)"
  sudo python -m playwright install-deps chromium
fi

echo "[deploy] installing Playwright Chromium"
python -m playwright install chromium

mkdir -p data artifacts

PUBLIC_PORT="${E2E_PUBLIC_PORT:-2222}"
echo "[deploy] ensuring OS firewall allows tcp/${PUBLIC_PORT}"
if ! sudo iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport "$PUBLIC_PORT" -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport "$PUBLIC_PORT" -j ACCEPT
fi
if ! sudo grep -q "dport ${PUBLIC_PORT}" /etc/iptables/rules.v4; then
  sudo sed -i "/dport 8000/a -A INPUT -p tcp -m state --state NEW -m tcp --dport ${PUBLIC_PORT} -j ACCEPT" /etc/iptables/rules.v4
fi

echo "[deploy] installing systemd unit"
sudo cp deploy/e2eTester.service /etc/systemd/system/e2eTester.service
sudo systemctl daemon-reload
sudo systemctl enable e2eTester

echo "[deploy] installing nginx site (https://pilotchat.kr:2222)"
if ! command -v nginx >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx
fi
sudo cp deploy/nginx-e2etester-upgrade.conf /etc/nginx/conf.d/e2etester-upgrade.conf
sudo cp deploy/nginx-e2etester.conf /etc/nginx/sites-available/e2etester
sudo ln -sf /etc/nginx/sites-available/e2etester /etc/nginx/sites-enabled/e2etester
sudo nginx -t
sudo systemctl reload nginx

echo "[deploy] restarting e2eTester"
sudo systemctl restart e2eTester

sleep 5
if ! systemctl is-active --quiet e2eTester; then
  echo "[deploy] service failed to start" >&2
  sudo journalctl -u e2eTester -n 30 --no-pager
  exit 1
fi

if curl -sf "http://127.0.0.1:${APP_PORT}/login" >/dev/null; then
  echo "[deploy] app health check OK (http://127.0.0.1:${APP_PORT}/login)"
else
  echo "[deploy] app health check failed" >&2
  sudo journalctl -u e2eTester -n 30 --no-pager
  exit 1
fi

if curl -sf --resolve pilotchat.kr:2222:127.0.0.1 "https://pilotchat.kr:2222/login" >/dev/null; then
  echo "[deploy] nginx health check OK (https://pilotchat.kr:2222/login)"
else
  echo "[deploy] nginx health check failed" >&2
  sudo journalctl -u nginx -n 20 --no-pager
  exit 1
fi

echo "[deploy] done"
