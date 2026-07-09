#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="${SERVICE_NAME:-rpi-button-touch}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
APP_USER="${APP_USER:-}"
APP_GROUP="${APP_GROUP:-}"
INSTALL_SYSTEM_PACKAGES=1
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
  --user USER        systemd service user. Default: current user, or sudo caller.
  --group GROUP      systemd service group. Default: primary group of APP_USER.
  --no-system-packages
                    Skip apt-get update/install for system packages.
  --no-service       Install dependencies only; skip systemd service setup.
  --start            Start/restart the app service after installation.
  -h, --help         Show this help.

Environment overrides:
  HOST, PORT, SERVICE_NAME, APP_USER, APP_GROUP
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
    --user)
      APP_USER="${2:?--user requires a value}"
      shift 2
      ;;
    --group)
      APP_GROUP="${2:?--group requires a value}"
      shift 2
      ;;
    --no-system-packages)
      INSTALL_SYSTEM_PACKAGES=0
      shift
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
if [[ -z "${APP_USER}" ]]; then
  APP_USER="${DEFAULT_APP_USER}"
fi

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  echo "User '${APP_USER}' does not exist. Create it first or choose another user with --user." >&2
  exit 1
fi

if [[ -z "${APP_GROUP}" ]]; then
  if ! APP_GROUP="$(id -gn "${APP_USER}" 2>/dev/null)"; then
    echo "Unable to determine the primary group for user '${APP_USER}'. Set it with --group or APP_GROUP." >&2
    exit 1
  fi
fi

if ! getent group "${APP_GROUP}" >/dev/null 2>&1; then
  echo "Group '${APP_GROUP}' does not exist. Create it first or choose another group with --group." >&2
  exit 1
fi
APP_HOME="$(getent passwd "${APP_USER}" | cut -d: -f6)"

if [[ -z "${APP_HOME}" ]]; then
  echo "Unable to determine the home directory for user '${APP_USER}'." >&2
  exit 1
fi

if [[ "${EUID}" -eq 0 && "${APP_USER}" != "root" ]] && ! command -v runuser >/dev/null 2>&1; then
  echo "runuser is required when installing as root for a non-root app user." >&2
  exit 1
fi

run_as_app_user() {
  if [[ "${EUID}" -eq 0 && "${APP_USER}" != "root" ]]; then
    runuser -u "${APP_USER}" -g "${APP_GROUP}" -- env HOME="${APP_HOME}" "$@"
  else
    "$@"
  fi
}

fix_app_ownership() {
  if [[ "${EUID}" -ne 0 ]]; then
    return
  fi

  local paths=()
  [[ -e "${VENV_DIR}" ]] && paths+=("${VENV_DIR}")
  [[ -e "${PROJECT_DIR}/.env" ]] && paths+=("${PROJECT_DIR}/.env")
  [[ -e "${PROJECT_DIR}/data" ]] && paths+=("${PROJECT_DIR}/data")

  if [[ "${#paths[@]}" -gt 0 ]]; then
    chown -R "${APP_USER}:${APP_GROUP}" "${paths[@]}"
  fi
}

if [[ "${INSTALL_SYSTEM_PACKAGES}" -eq 1 ]] && ! command -v apt-get >/dev/null 2>&1; then
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
echo "App group: ${APP_GROUP}"
echo "Bind: ${HOST}:${PORT}"

if [[ "${INSTALL_SYSTEM_PACKAGES}" -eq 1 ]]; then
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
else
  echo "Skipping system package installation."
fi

echo "Ensuring app file ownership..."
fix_app_ownership

echo "Creating Python virtual environment..."
run_as_app_user python3 -m venv "${VENV_DIR}"
run_as_app_user "${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
run_as_app_user "${VENV_DIR}/bin/python" -m pip install --prefer-binary -r "${PROJECT_DIR}/requirements.txt"

if [[ ! -f "${PROJECT_DIR}/.env" && -f "${PROJECT_DIR}/.env.example" ]]; then
  echo "Creating .env from .env.example..."
  run_as_app_user cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
fi

run_as_app_user mkdir -p "${PROJECT_DIR}/data"

if [[ ! -f "${PROJECT_DIR}/data/app.json" ]]; then
  echo "Creating default data/app.json from data/app.example.json..."
  run_as_app_user cp "${PROJECT_DIR}/data/app.example.json" "${PROJECT_DIR}/data/app.json"
fi

if [[ ! -f "${PROJECT_DIR}/data/secrets.json" ]]; then
  echo "Creating default data/secrets.json from data/secrets.example.json..."
  run_as_app_user cp "${PROJECT_DIR}/data/secrets.example.json" "${PROJECT_DIR}/data/secrets.json"
fi

fix_app_ownership

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
Group=${APP_GROUP}
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
echo "  ${PROJECT_DIR}/data/app.json"
echo
echo "Manual run:"
echo "  ${VENV_DIR}/bin/python -m app.command.service --host ${HOST} --port ${PORT}"

if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
  echo
  echo "Service commands:"
  echo "  sudo systemctl status ${SERVICE_NAME}.service"
  echo "  sudo journalctl -u ${SERVICE_NAME}.service -f"
fi
