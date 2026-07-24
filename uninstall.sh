#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this uninstaller as root, for example: sudo ./uninstall.sh" >&2
  exit 1
fi

systemctl disable --now qbit-mover.timer >/dev/null 2>&1 || true
systemctl stop qbit-mover.service >/dev/null 2>&1 || true
systemctl stop qbit-mover-emergency.service >/dev/null 2>&1 || true

rm -f -- /etc/systemd/system/qbit-mover.service
rm -f -- /etc/systemd/system/qbit-mover-emergency.service
rm -f -- /etc/systemd/system/qbit-mover.timer
rm -f -- /usr/local/lib/qbit-mover/qbit-move-completed.py
rm -f -- /usr/local/sbin/qbit-mover-emergency
rm -f -- /etc/qbit-mover/qbit-mover.env
rmdir -- /usr/local/lib/qbit-mover 2>/dev/null || true
rmdir -- /etc/qbit-mover 2>/dev/null || true

systemctl daemon-reload
systemctl reset-failed
echo "qBittorrent storage mover has been removed."
