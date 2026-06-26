#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-rpi-button-touch}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
INSTALL_SERVICE=1
AUTO_START=0

usage() {
  cat <<USAGE
Usage: ./install.sh [options]

Install Button Touch on Raspberry Pi OS.

Options:
  --host HOST        Uvicorn bind host. Default: ${HOST}
  --port PORT        Uvicorn bind port. Default: ${PORT}
  --service-name N   systemd service name. Default: ${SERVICE_NAME}
  --no-service       Install dependencies only; skip systemd service setup.
  --start            Start/restart the app service after installation.
  -h, --help         Show this help.

Environment overrides:
  HOST, PORT, SERVICE_NAME, APP_USER
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:?--host requires a value}"
      shift 2
      ;;
    --port)
      PORT="${2:?--port requires a value}"
      shift 2
      ;;
    --service-name)
      SERVICE_NAME="${2:?--service-name requires a value}"
      shift 2
      ;;
    --no-service)
      INSTALL_SERVICE=0
      shift
      ;;
    --start)
      AUTO_START=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
  DEFAULT_APP_USER="${SUDO_USER:-root}"
else
  SUDO=(sudo)
  DEFAULT_APP_USER="$(id -un)"
fi
APP_USER="${APP_USER:-${DEFAULT_APP_USER}}"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer is intended for Raspberry Pi OS or another apt-based Debian system." >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl is required on Raspberry Pi OS." >&2
  exit 1
fi

echo "Project: ${PROJECT_DIR}"
echo "Service: ${SERVICE_NAME}"
echo "App user: ${APP_USER}"
echo "Bind: ${HOST}:${PORT}"

echo "Installing system packages..."
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y \
  build-essential \
  libffi-dev \
  libssl-dev \
  pigpio \
  pkg-config \
  python3 \
  python3-dev \
  python3-pip \
  python3-venv

echo "Enabling pigpio daemon..."
"${SUDO[@]}" systemctl enable pigpiod.service
"${SUDO[@]}" systemctl restart pigpiod.service

echo "Creating Python virtual environment..."
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install --prefer-binary -r "${PROJECT_DIR}/requirements.txt"

if [[ ! -f "${PROJECT_DIR}/.env" && -f "${PROJECT_DIR}/.env.example" ]]; then
  echo "Creating .env from .env.example..."
  cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
fi

mkdir -p "${PROJECT_DIR}/data"

if [[ ! -f "${PROJECT_DIR}/data/rpi.json" ]]; then
  echo "Creating default data/rpi.json..."
  cat >"${PROJECT_DIR}/data/rpi.json" <<'JSON'
{
  "product_code": "S-T-DAI-00001-RPI-1",
  "function": {
    "PFN-MIRAICHANKWI": {
      "jobs": ["touch"],
      "order": "sequence"
    },
    "PFN-SHIZUKAKAWAI": {
      "jobs": ["turn-on"],
      "order": "sequence"
    },
    "PFN-TSUBASAKAWAI": {
      "jobs": ["turn-off"],
      "order": "sequence"
    }
  },
  "job": {
    "touch": {
      "uses": [
        {
          "name": "GPIO 18",
          "type": "GPIO",
          "value": 18
        }
      ],
      "action": [
        {"GPIO 18": "high"},
        {"wait": 0.3},
        {"GPIO 18": "low"},
        {"wait": 0.5}
      ]
    },
    "turn-on": {
      "uses": [
        {
          "name": "GPIO 19",
          "type": "GPIO",
          "value": 19
        }
      ],
      "action": [
        {"GPIO 19": "high"}
      ]
    },
    "turn-off": {
      "uses": [
        {
          "name": "GPIO 19",
          "type": "GPIO",
          "value": 19
        }
      ],
      "action": [
        {"GPIO 19": "low"}
      ]
    }
  },
  "GPIO": {
    "18": {
      "mode": "output",
      "state": "low"
    },
    "19": {
      "mode": "output",
      "state": "low"
    }
  }
}
JSON
fi

if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
  echo "Installing systemd service..."
  TMP_SERVICE="$(mktemp)"
  cat >"${TMP_SERVICE}" <<SERVICE
[Unit]
Description=Raspberry Pi Button Touch API
After=network-online.target pigpiod.service
Wants=network-online.target pigpiod.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${VENV_DIR}/bin/python -m app.command.service --host ${HOST} --port ${PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

  "${SUDO[@]}" install -m 0644 "${TMP_SERVICE}" "${SERVICE_FILE}"
  rm -f "${TMP_SERVICE}"
  "${SUDO[@]}" systemctl daemon-reload
  "${SUDO[@]}" systemctl enable "${SERVICE_NAME}.service"

  if [[ "${AUTO_START}" -eq 1 ]]; then
    echo "Starting ${SERVICE_NAME}.service..."
    "${SUDO[@]}" systemctl restart "${SERVICE_NAME}.service"
  else
    echo "Service installed but not started. Start it with:"
    echo "  sudo systemctl start ${SERVICE_NAME}.service"
  fi
fi

echo
echo "Installation complete."
echo "Edit configuration before first production run:"
echo "  ${PROJECT_DIR}/.env"
echo "  ${PROJECT_DIR}/data/rpi.json"
echo
echo "Manual run:"
echo "  ${VENV_DIR}/bin/python -m app.command.service --host ${HOST} --port ${PORT}"

if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
  echo
  echo "Service commands:"
  echo "  sudo systemctl status ${SERVICE_NAME}.service"
  echo "  sudo journalctl -u ${SERVICE_NAME}.service -f"
fi
