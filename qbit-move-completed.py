#!/usr/bin/env python3
"""Queue completed qBittorrent torrents for relocation to slower storage."""

from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


QB_URL = os.environ["QB_URL"].rstrip("/")
QB_USERNAME = os.environ["QB_USERNAME"]
QB_PASSWORD = os.environ["QB_PASSWORD"]
SOURCE_PATH = Path(os.environ["SOURCE_PATH"]).resolve()
TARGET_PATH = Path(os.environ["TARGET_PATH"]).resolve()
MIN_AGE_SECONDS = int(os.environ.get("MIN_AGE_SECONDS", "7200"))
MIN_FREE_BYTES = int(os.environ.get("MIN_FREE_BYTES", str(10 * 1024**3)))
DRY_RUN = os.environ.get("DRY_RUN", "1").lower() in {"1", "yes", "true", "on"}
INCLUDE_TAGS = {
    tag.strip()
    for tag in os.environ.get("INCLUDE_TAGS", "").split(",")
    if tag.strip()
}


def log(message: str) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z"), message, flush=True)


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class QBClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies)
        )

    def request(self, endpoint: str, data: dict[str, str] | None = None) -> bytes:
        encoded = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=encoded,
            headers={
                "Referer": f"{self.base_url}/",
                "Origin": self.base_url,
                "User-Agent": "qbittorrent-storage-mover/1.0",
            },
            method="POST" if data is not None else "GET",
        )
        with self.opener.open(request, timeout=30) as response:
            return response.read()

    def authenticate(self) -> None:
        try:
            self.request("/api/v2/app/version")
            return
        except urllib.error.HTTPError as error:
            if error.code != 403:
                raise

        result = self.request(
            "/api/v2/auth/login",
            {"username": QB_USERNAME, "password": QB_PASSWORD},
        ).decode("utf-8", errors="replace").strip()
        if result != "Ok.":
            raise RuntimeError("qBittorrent Web API login failed.")


def validate_paths() -> None:
    if not SOURCE_PATH.is_dir():
        raise RuntimeError(f"Source directory does not exist: {SOURCE_PATH}")
    if not TARGET_PATH.is_dir():
        raise RuntimeError(f"Target directory does not exist: {TARGET_PATH}")
    if SOURCE_PATH == TARGET_PATH:
        raise RuntimeError("Source and target directories are identical.")
    if SOURCE_PATH.stat().st_dev == TARGET_PATH.stat().st_dev:
        raise RuntimeError(
            "Source and target are on the same filesystem. "
            "The storage may not be mounted."
        )


def main() -> int:
    validate_paths()
    client = QBClient(QB_URL)
    client.authenticate()
    torrents = json.loads(client.request("/api/v2/torrents/info?filter=completed"))

    now = int(time.time())
    eligible: list[dict] = []
    for torrent in torrents:
        completion_on = int(torrent.get("completion_on") or 0)
        amount_left = int(torrent.get("amount_left") or 0)
        save_path = Path(torrent.get("save_path") or "/").resolve()

        if completion_on <= 0 or now - completion_on < MIN_AGE_SECONDS:
            continue
        if amount_left != 0 or not is_under(save_path, SOURCE_PATH):
            continue
        torrent_tags = {
            tag.strip()
            for tag in (torrent.get("tags") or "").split(",")
            if tag.strip()
        }
        if INCLUDE_TAGS and not INCLUDE_TAGS.intersection(torrent_tags):
            continue
        if torrent.get("state") in {
            "moving",
            "checkingUP",
            "checkingResumeData",
            "allocating",
            "unknown",
        }:
            continue
        eligible.append(torrent)

    eligible.sort(key=lambda item: int(item.get("completion_on") or 0))
    if not eligible:
        tag_note = (
            f" matching tags: {', '.join(sorted(INCLUDE_TAGS))}"
            if INCLUDE_TAGS
            else ""
        )
        log(
            "No completed torrents are currently eligible for relocation"
            f"{tag_note}."
        )
        return 0

    selected: list[dict] = []
    selected_bytes = 0
    free_bytes = shutil.disk_usage(TARGET_PATH).free
    usable_bytes = max(0, free_bytes - MIN_FREE_BYTES)

    for torrent in eligible:
        name = torrent.get("name", torrent.get("hash", "unknown"))
        content_path = Path(torrent.get("content_path") or name)
        target_content = TARGET_PATH / content_path.name
        if target_content.exists():
            log(
                "Target already contains an item with the same name; "
                "qBittorrent will handle merging and any required recheck: "
                f"{name!r} -> {target_content}"
            )

        size = int(torrent.get("size") or torrent.get("total_size") or 0)
        if selected_bytes + size > usable_bytes:
            log(
                f"SKIPPED, insufficient target space: {name!r}; "
                f"torrent={size}, batch={selected_bytes}, usable={usable_bytes}"
            )
            continue

        age = now - int(torrent["completion_on"])
        if DRY_RUN:
            log(
                f"DRY RUN: eligible: {name!r}; age={age}s; "
                f"source={torrent.get('save_path')}; target={TARGET_PATH}"
            )
        selected.append(torrent)
        selected_bytes += size

    if not selected:
        log("Eligible torrents were found, but none could be queued.")
        return 0

    if DRY_RUN:
        log(
            f"Dry run complete: {len(selected)} torrent(s), "
            f"{selected_bytes} bytes; no data was moved."
        )
        return 0

    client.request(
        "/api/v2/torrents/setLocation",
        {
            "hashes": "|".join(torrent["hash"] for torrent in selected),
            "location": str(TARGET_PATH),
        },
    )
    log(
        f"Queued {len(selected)} torrent(s) in qBittorrent's relocation queue; "
        f"bytes={selected_bytes}; target={TARGET_PATH}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        KeyError,
        OSError,
        ValueError,
        RuntimeError,
        urllib.error.URLError,
    ) as error:
        log(f"ERROR: {error}")
        raise SystemExit(1)
