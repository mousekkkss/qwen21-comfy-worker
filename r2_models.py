"""Hydrate optional Qwen 2.1 models from signed Cloudflare R2 GET URLs.

The website signs each object; the worker holds no storage credential. Every
file is checked against the manifest size and SHA-256 before ComfyUI sees it,
then reused for later jobs on the same worker.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit
import hashlib
import json
import os
import re
import shutil
import threading
import time
import requests

MODEL_ROOT = Path(os.environ.get("QWEN21_MODEL_ROOT", "/comfyui/models"))
ALLOWED_ROOTS = ("diffusion_models", "text_encoders", "loras")
ALLOWED_BUCKETS = tuple(filter(None, os.environ.get("QWEN21_R2_BUCKETS", "rat-image-ai-models").split(",")))
HOST_SUFFIX = ".r2.cloudflarestorage.com"
MARKER_SUFFIX = ".r2-verified.json"
MAX_FILES = 12
CHUNK = 64 * 1024 * 1024
RANGE_THRESHOLD = 256 * 1024 * 1024
_LOCK = threading.Lock()


def _relative_path(value):
    raw = str(value or "").replace("\\", "/").strip().strip("/")
    path = PurePosixPath(raw)
    parts = path.parts
    if len(parts) < 2 or parts[0] not in ALLOWED_ROOTS or any(p in ("", ".", "..") or "\0" in p for p in parts):
        raise ValueError(f"Model path is not allowed: {raw!r}")
    if path.suffix.lower() != ".safetensors":
        raise ValueError(f"Only .safetensors models can be hydrated: {raw!r}")
    return path.as_posix()


def validate_plan(plan):
    """Return normalized rows; reject anything that is not a signed R2 GET for an allowed model folder."""
    if not isinstance(plan, dict) or str(plan.get("provider", "")).lower() != "cloudflare-r2":
        raise ValueError("qwen21_model_plan must be a cloudflare-r2 plan")
    bucket = str(plan.get("bucket", "")).strip()
    prefix = str(plan.get("prefix", "")).strip().strip("/")
    if bucket not in ALLOWED_BUCKETS:
        raise ValueError("qwen21_model_plan bucket is not allowed")
    rows = plan.get("required")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_FILES:
        raise ValueError(f"qwen21_model_plan must list 1-{MAX_FILES} files")
    result, seen = [], set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"qwen21_model_plan item {index} must be an object")
        relative = _relative_path(row.get("relativePath"))
        size = int(row.get("sizeBytes") or 0)
        sha256 = str(row.get("sha256", "")).strip().lower()
        if size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError(f"{relative} requires manifest size and SHA-256")
        url = str(row.get("url", "")).strip()
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host.endswith(HOST_SUFFIX):
            raise ValueError(f"{relative} must use an HTTPS Cloudflare R2 URL")
        expected = "/" + "/".join(filter(None, [bucket, prefix, relative]))
        if unquote(parsed.path) != expected:
            raise ValueError(f"{relative} URL does not address its bucket object")
        if "X-Amz-Signature" not in parse_qs(parsed.query):
            raise ValueError(f"{relative} URL is not signed")
        if relative.lower() in seen:
            continue
        seen.add(relative.lower())
        result.append({"relativePath": relative, "url": url, "sizeBytes": size, "sha256": sha256})
    return result


def _marker(target):
    return target.with_name(target.name + MARKER_SUFFIX)


def _cached(target, row):
    try:
        info = json.loads(_marker(target).read_text())
        return info.get("sha256") == row["sha256"] and target.stat().st_size == row["sizeBytes"]
    except (OSError, ValueError):
        return False


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_range(url, path, start, end):
    for attempt in range(4):
        try:
            with requests.get(url, headers={"Range": f"bytes={start}-{end}"}, stream=True, timeout=(30, 300)) as response:
                if response.status_code != 206:
                    raise RuntimeError(f"R2 range request returned HTTP {response.status_code}")
                with open(path, "r+b") as file:
                    file.seek(start)
                    written = 0
                    for block in response.iter_content(4 * 1024 * 1024):
                        file.write(block)
                        written += len(block)
                if written != end - start + 1:
                    raise RuntimeError("R2 range ended early")
                return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def _download(row, temporary):
    size, url = row["sizeBytes"], row["url"]
    with open(temporary, "wb") as file:
        file.truncate(size)
    if size < RANGE_THRESHOLD:
        _download_range(url, temporary, 0, size - 1)
        return
    ranges = [(start, min(size, start + CHUNK) - 1) for start in range(0, size, CHUNK)]
    workers = max(1, int(os.environ.get("QWEN21_R2_CONCURRENCY", "8")))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for future in [executor.submit(_download_range, url, temporary, a, b) for a, b in ranges]:
            future.result()


def _free_space(rows, root):
    """Evict earlier R2 files that this job does not use when the disk is short."""
    needed = sum(r["sizeBytes"] for r in rows if not _cached(root / r["relativePath"], r))
    keep = {(root / r["relativePath"]).resolve() for r in rows}
    margin = 4 * 1024 ** 3
    if shutil.disk_usage(root).free >= needed + margin:
        return
    for marker in sorted(root.rglob("*" + MARKER_SUFFIX), key=lambda p: p.stat().st_mtime):
        target = marker.with_name(marker.name[: -len(MARKER_SUFFIX)])
        if target.resolve() in keep:
            continue
        target.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
        print("qwen21: evicted", target.relative_to(root), flush=True)
        if shutil.disk_usage(root).free >= needed + margin:
            return
    if shutil.disk_usage(root).free < needed + margin:
        raise RuntimeError(f"Not enough worker disk for Qwen 2.1 models ({needed / 1024 ** 3:.1f} GiB needed)")


def hydrate(plan, root=None):
    """Download and verify every planned file; return one summary per file."""
    rows = validate_plan(plan)
    root = Path(root or MODEL_ROOT)
    summaries = []
    with _LOCK:
        _free_space(rows, root)
        for row in rows:
            target = root / row["relativePath"]
            if _cached(target, row):
                os.utime(_marker(target))
                summaries.append({"relativePath": row["relativePath"], "sizeBytes": row["sizeBytes"], "cached": True})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.r2-part")
            started = time.monotonic()
            print("qwen21: hydrating", row["relativePath"], row["sizeBytes"], flush=True)
            try:
                _download(row, temporary)
                if temporary.stat().st_size != row["sizeBytes"]:
                    raise RuntimeError(f"R2 size mismatch for {row['relativePath']}")
                if _sha256(temporary) != row["sha256"]:
                    raise RuntimeError(f"R2 SHA-256 mismatch for {row['relativePath']}")
                os.replace(temporary, target)
                _marker(target).write_text(json.dumps({"sha256": row["sha256"], "sizeBytes": row["sizeBytes"]}))
            finally:
                temporary.unlink(missing_ok=True)
            seconds = round(time.monotonic() - started, 1)
            print("qwen21: hydrated", row["relativePath"], f"{seconds}s", flush=True)
            summaries.append({"relativePath": row["relativePath"], "sizeBytes": row["sizeBytes"], "cached": False, "seconds": seconds})
    return summaries
