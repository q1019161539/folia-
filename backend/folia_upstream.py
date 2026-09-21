"""Read-only stable release discovery for the pinned Folia renderer."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import httpx


RELEASES_URL = "https://api.github.com/repos/chthollyphile/folia-major/releases?per_page=20"
RAW_VERSION_URL = "https://raw.githubusercontent.com/chthollyphile/folia-major/{tag}/deploy/docker/VERSION"
DOCKER_TAG_URL = "https://hub.docker.com/v2/repositories/papersman/folia-web/tags/{version}-amd64"


def _version_tuple(value: str) -> tuple[int, ...]:
    clean = value.strip().lower().removeprefix("v")
    try:
        return tuple(int(part) for part in clean.split("."))
    except ValueError:
        return ()


def newest_stable_release(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    stable = [row for row in rows if not row.get("draft") and not row.get("prerelease") and _version_tuple(str(row.get("tag_name") or ""))]
    return max(stable, key=lambda row: _version_tuple(str(row.get("tag_name") or "")), default=None)


def check_upstream(current: dict[str, Any], client: httpx.Client | None = None) -> dict[str, Any]:
    owns_client = client is None
    client = client or httpx.Client(timeout=12, headers={"User-Agent": "folia-video-studio"}, follow_redirects=True)
    try:
        releases = client.get(RELEASES_URL)
        releases.raise_for_status()
        latest = newest_stable_release(releases.json())
        if not latest:
            raise RuntimeError("GitHub 没有返回稳定 Release")
        tag = str(latest["tag_name"])
        version_response = client.get(RAW_VERSION_URL.format(tag=tag))
        version_response.raise_for_status()
        stack = version_response.text.strip()
        image_response = client.get(DOCKER_TAG_URL.format(version=stack))
        image_ready = image_response.status_code == 200
        image_digest = ""
        if image_ready:
            image_digest = str((image_response.json() or {}).get("digest") or "")
        return {
            "ok": True,
            "checked_at": time.time(),
            "current_release": current["release"],
            "current_revision": current["revision"],
            "current_stack": current["docker_stack"],
            "current_digest": current["docker_amd64_digest"],
            "patch_profile": current["patch_profile"],
            "latest_release": tag,
            "latest_stack": stack,
            "latest_digest": image_digest,
            "release_url": str(latest.get("html_url") or ""),
            "published_at": latest.get("published_at"),
            "image_ready": image_ready,
            "update_available": _version_tuple(tag) > _version_tuple(str(current["release"])),
        }
    finally:
        if owns_client:
            client.close()


class UpstreamStatusStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(".partial")
        partial.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        partial.replace(self.path)

    def refresh(self, current: dict[str, Any], notify: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        previous = self.load()
        try:
            result = check_upstream(current)
        except Exception as exc:
            result = {**previous, "ok": False, "checked_at": time.time(), "error": str(exc)[:500]}
            self.save(result)
            return result
        if result.get("update_available") and result.get("image_ready"):
            latest = str(result.get("latest_release") or "")
            if latest and previous.get("notified_release") != latest and notify:
                notify(result)
                result["notified_release"] = latest
        elif previous.get("notified_release"):
            result["notified_release"] = previous["notified_release"]
        self.save(result)
        return result
