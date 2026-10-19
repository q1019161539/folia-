"""Offline, redacted guard for tracked source and all reachable Git history.

This supplements Gitleaks; it is not a proof that arbitrary secrets do not exist.
No file bodies, matched values, or credentials are ever printed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


PATTERNS = (
    ("ai-relay-key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}")),
    ("google-api-key", re.compile(rb"\bAIza[A-Za-z0-9_-]{30,}")),
    ("github-token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("url-password", re.compile(rb"https?://[^\s/:\"'<>]+:[^\s/@\"'<>]{8,}@")),
    ("bilibili-session", re.compile(rb"\bSESSDATA\s*[=:]\s*[\"']?[A-Za-z0-9%_,.-]{20,}")),
)
MEDIA_SUFFIXES = {".mp4", ".mov", ".mkv", ".mp3", ".wav", ".flac"}
ARCHIVE_SUFFIXES = {".bundle", ".tgz", ".zip", ".7z", ".tar", ".gz"}
RUNTIME_DIRS = {"data", "models", "work", "output", "media-view", "node_modules",
                "__pycache__", "backup", "backups", "stage", ".security-reports"}


def forbidden_path(name):
    parts = PurePosixPath(name.replace("\\", "/")).parts
    base = parts[-1] if parts else ""
    lower = base.lower()
    if base != ".env.example" and (base == ".env" or base.startswith(".env.")):
        return True
    return (any(part in RUNTIME_DIRS for part in parts[:-1])
            or lower in {".htpasswd", "id_rsa", "id_ed25519", "cookies.txt", "cookies.json"}
            or lower.endswith((".pem", ".key", ".db", ".sqlite", ".sqlite3", ".log", "-wal", "-shm"))
            or PurePosixPath(lower).suffix in MEDIA_SUFFIXES | ARCHIVE_SUFFIXES)


def scan_bytes(data, path, scope, revision=None):
    findings = []
    for rule, pattern in PATTERNS:
        for match in pattern.finditer(data):
            item = {"rule": rule, "path": path, "scope": scope,
                    "line": data.count(b"\n", 0, match.start()) + 1}
            if revision:
                item["revision"] = revision
            findings.append(item)
    return findings


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def current_scan(root):
    # No recursive filesystem crawl: ignored credentials and media stay unread.
    names = git(root, "ls-files", "-co", "--exclude-standard", "-z").split(b"\0")
    findings = []
    count = 0
    for raw in sorted(set(names)):
        if not raw:
            continue
        name = raw.decode("utf-8", errors="replace")
        path = root / name
        if not path.is_file():
            continue
        count += 1
        if forbidden_path(name):
            findings.append({"rule": "private-runtime-path", "path": name, "scope": "current"})
        findings.extend(scan_bytes(path.read_bytes(), name, "current"))
    return findings, count


def history_scan(root):
    findings = []
    entries = git(root, "rev-list", "--objects", "--all").splitlines()
    count = 0
    # Batch Git plumbing, not one subprocess per historical object.
    with subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as batch:
        for entry in entries:
            oid, _, raw_name = entry.partition(b" ")
            batch.stdin.write(oid + b"\n")
            batch.stdin.flush()
            header = batch.stdout.readline().split()
            if len(header) != 3:
                raise RuntimeError("Invalid Git object response")
            size = int(header[2])
            data = batch.stdout.read(size)
            if len(data) != size or batch.stdout.read(1) != b"\n":
                raise RuntimeError("Incomplete Git object response")
            kind = header[1]
            if kind not in (b"blob", b"commit", b"tag"):
                continue
            revision = oid.decode("ascii")
            path = raw_name.decode("utf-8", errors="replace") or "<" + kind.decode() + ">"
            if kind == b"blob":
                count += 1
                if forbidden_path(path):
                    findings.append({"rule": "private-runtime-path", "path": path,
                                     "scope": "history", "revision": revision})
            findings.extend(scan_bytes(data, path, "history", revision))
        batch.stdin.close()
        if batch.wait() != 0:
            raise RuntimeError("Git object read failed")
    return findings, count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    findings, count = current_scan(root)
    history_count = 0
    if args.history:
        extra, history_count = history_scan(root)
        findings.extend(extra)
    print(json.dumps({"current_files": count, "history_blobs": history_count,
                      "findings": findings}, ensure_ascii=True, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
