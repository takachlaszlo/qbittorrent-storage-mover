#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALL_DIR="/usr/local/lib/qbit-mover"
readonly CONFIG_DIR="/etc/qbit-mover"
readonly CONFIG_FILE="${CONFIG_DIR}/qbit-mover.env"
readonly SERVICE_FILE="/etc/systemd/system/qbit-mover.service"
readonly EMERGENCY_SERVICE_FILE="/etc/systemd/system/qbit-mover-emergency.service"
readonly TIMER_FILE="/etc/systemd/system/qbit-mover.timer"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root, for example: sudo ./install.sh" >&2
  exit 1
fi

if [[ ! -x /usr/bin/python3 ]]; then
  echo "python3 is required." >&2
  exit 1
fi

prompt_default() {
  local prompt=$1
  local default=$2
  local result
  read -r -p "${prompt} [${default}]: " result
  printf '%s' "${result:-$default}"
}

env_quote() {
  /usr/bin/python3 -c '
import sys
value = sys.stdin.read()
value = value.replace("\\", "\\\\").replace("\"", "\\\"")
value = value.replace("`", "\\`").replace("$", "\\$")
sys.stdout.write("\"" + value + "\"")
'
}

write_env() {
  local key=$1
  local value=$2
  printf '%s=' "$key"
  printf '%s' "$value" | env_quote
  printf '\n'
}

default_user="${SUDO_USER:-}"
if [[ -z "$default_user" || "$default_user" == "root" ]]; then
  default_user="qbittorrent"
fi

service_user=$(prompt_default "Linux user running qBittorrent" "$default_user")
if ! id "$service_user" >/dev/null 2>&1; then
  echo "Linux user does not exist: ${service_user}" >&2
  exit 1
fi

qb_scheme=$(prompt_default "qBittorrent Web UI protocol" "http")
qb_host=$(prompt_default "qBittorrent Web UI host/address" "127.0.0.1")
qb_port=$(prompt_default "qBittorrent Web UI port" "8080")
if [[ ! "$qb_port" =~ ^[0-9]+$ ]] || ((qb_port < 1 || qb_port > 65535)); then
  echo "Invalid TCP port: ${qb_port}" >&2
  exit 1
fi

read -r -p "qBittorrent Web UI username: " qb_username
read -r -s -p "qBittorrent Web UI password: " qb_password
printf '\n'
if [[ -z "$qb_username" || -z "$qb_password" ]]; then
  echo "The Web UI username and password cannot be empty." >&2
  exit 1
fi

source_path=$(prompt_default "qBittorrent default download directory" "/srv/downloads")
target_path=$(prompt_default "Storage target directory" "/srv/storage")
source_path=$(realpath -e -- "$source_path")
target_path=$(realpath -e -- "$target_path")

seed_hours=$(prompt_default "Move torrents this many hours after completion" "2")
if [[ ! "$seed_hours" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "Invalid hour value: ${seed_hours}" >&2
  exit 1
fi
min_age_seconds=$(
  /usr/bin/python3 -c \
    'import sys; print(round(float(sys.argv[1]) * 3600))' "$seed_hours"
)
if ((min_age_seconds < 1)); then
  echo "The completion age must be greater than zero." >&2
  exit 1
fi

check_interval_hours=$(prompt_default "Run the check every N hours" "1")
if [[ ! "$check_interval_hours" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "Invalid hour value: ${check_interval_hours}" >&2
  exit 1
fi
check_interval_seconds=$(
  /usr/bin/python3 -c \
    'import sys; print(round(float(sys.argv[1]) * 3600))' "$check_interval_hours"
)
if ((check_interval_seconds < 1)); then
  echo "The check interval must be greater than zero." >&2
  exit 1
fi
run_interval="${check_interval_seconds}s"

move_scope=$(prompt_default "Move all torrents or only selected tags? (all/tags)" "all")
case "${move_scope,,}" in
  all|a)
    include_tags=""
    ;;
  tags|tag|t)
    read -r -p "Included qBittorrent tags (comma-separated, match any): " include_tags
    include_tags=$(
      /usr/bin/python3 -c '
import sys
tags = [tag.strip() for tag in sys.argv[1].split(",") if tag.strip()]
print(",".join(dict.fromkeys(tags)))
' "$include_tags"
    )
    if [[ -z "$include_tags" ]]; then
      echo "At least one tag is required when tag filtering is selected." >&2
      exit 1
    fi
    ;;
  *)
    echo "Choose either all or tags." >&2
    exit 1
    ;;
esac

if [[ ! -d "$source_path" || ! -d "$target_path" ]]; then
  echo "Source and target must both be existing directories." >&2
  exit 1
fi
if [[ "$source_path" == "$target_path" ]]; then
  echo "Source and target directories cannot be identical." >&2
  exit 1
fi
if [[ $(stat -c '%d' -- "$source_path") == $(stat -c '%d' -- "$target_path") ]]; then
  echo "Source and target are on the same filesystem; is storage mounted?" >&2
  exit 1
fi
if ! runuser -u "$service_user" -- test -w "$target_path"; then
  echo "${service_user} cannot write to ${target_path}." >&2
  exit 1
fi

install -d -o root -g root -m 0755 "$INSTALL_DIR"
install -d -o root -g root -m 0700 "$CONFIG_DIR"
install -o root -g root -m 0755 \
  "${SCRIPT_DIR}/qbit-move-completed.py" \
  "${INSTALL_DIR}/qbit-move-completed.py"
install -o root -g root -m 0755 \
  "${SCRIPT_DIR}/qbit-mover-emergency" \
  /usr/local/sbin/qbit-mover-emergency

temp_config=$(mktemp "${CONFIG_DIR}/qbit-mover.env.XXXXXX")
trap 'rm -f -- "${temp_config:-}"' EXIT
{
  write_env QB_URL "${qb_scheme}://${qb_host}:${qb_port}"
  write_env QB_USERNAME "$qb_username"
  write_env QB_PASSWORD "$qb_password"
  write_env SOURCE_PATH "$source_path"
  write_env TARGET_PATH "$target_path"
  write_env MIN_AGE_SECONDS "$min_age_seconds"
  write_env MIN_FREE_BYTES "10737418240"
  write_env INCLUDE_TAGS "$include_tags"
  write_env DRY_RUN "1"
} >"$temp_config"
chown root:root "$temp_config"
chmod 0600 "$temp_config"
mv -f -- "$temp_config" "$CONFIG_FILE"
trap - EXIT
unset qb_password

sed "s/@SERVICE_USER@/${service_user}/g" \
  "${SCRIPT_DIR}/systemd/qbit-mover.service.in" >"$SERVICE_FILE"
chmod 0644 "$SERVICE_FILE"
sed "s/@SERVICE_USER@/${service_user}/g" \
  "${SCRIPT_DIR}/systemd/qbit-mover-emergency.service.in" \
  >"$EMERGENCY_SERVICE_FILE"
chmod 0644 "$EMERGENCY_SERVICE_FILE"
sed "s/@RUN_INTERVAL@/${run_interval}/g" \
  "${SCRIPT_DIR}/systemd/qbit-mover.timer" >"$TIMER_FILE"
chmod 0644 "$TIMER_FILE"

systemctl daemon-reload
systemctl disable --now qbit-mover.timer >/dev/null 2>&1 || true

echo
echo "Running a safe dry run..."
if ! systemctl start qbit-mover.service; then
  journalctl -u qbit-mover.service -n 50 --no-pager
  echo "Dry run failed. The timer was not enabled." >&2
  exit 1
fi
journalctl -u qbit-mover.service -n 30 --no-pager

echo
read -r -p "Enable real moves and the configured timer now? [y/N]: " enable_now
if [[ "$enable_now" =~ ^[Yy]$ ]]; then
  sed -i 's/^DRY_RUN=.*/DRY_RUN="0"/' "$CONFIG_FILE"
  systemctl enable --now qbit-mover.timer
  systemctl start qbit-mover.service
  echo "Installed and enabled. qBittorrent now owns the relocation queue."
else
  echo "Installed in dry-run mode. The timer remains disabled."
  echo "Re-run sudo ./install.sh when you are ready to activate it."
fi
echo "Emergency command: sudo qbit-mover-emergency"
