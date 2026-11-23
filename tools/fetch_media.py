"""Download every file in sources/media-manifest.json into the repo, then point all links at the local copies.

Usage:  python tools/fetch_media.py
Runs automatically through .github/workflows/fetch-media.yml.

For each file: skip if already present; otherwise try the original URL, then the Apify mirror.
After downloading, remote URLs in README.md and content/*.md are rewritten to relative local paths.
sources/SOURCES.md is left alone on purpose: it is the record of where everything came from.
"""
import json
import os
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "sources" / "media-manifest.json"
UA = {"User-Agent": "Mozilla/5.0 (archive-bot)"}


def download(url, dest):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return dest.stat().st_size


def fetch_all(files):
    ok, failed = 0, []
    for item in files:
        dest = ROOT / item["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            ok += 1
            continue
        for label in ("original", "mirror"):
            url = item.get(label)
            if not url:
                continue
            try:
                size = download(url, dest)
                note = "" if size == item.get("bytes") else f" (expected {item.get('bytes')} bytes)"
                print(f"  ✓ {item['path']} from {label}, {size:,} bytes{note}")
                ok += 1
                break
            except Exception as e:  # try the next source
                print(f"  · {item['path']}: {label} failed ({e})")
                dest.unlink(missing_ok=True)
        else:
            failed.append(item["path"])
    return ok, failed


def localize(files, cdn_base=""):
    """Images and PDFs link to the repo-relative copy; MP4s link to the CDN copy so they play in the browser
    (GitHub itself only plays videos uploaded through its web editor)."""
    targets = [ROOT / "README.md", *sorted((ROOT / "content").glob("*.md"))]
    for doc in targets:
        text = original = doc.read_text()
        for item in files:
            local = ROOT / item["path"]
            if not local.exists():
                continue
            if cdn_base and item["path"].endswith(".mp4"):
                target = cdn_base + item["path"]
            else:
                target = os.path.relpath(local, doc.parent).replace(os.sep, "/")
            text = text.replace(item["original"], target)
        if text != original:
            doc.write_text(text)
            print(f"  ↺ links localized in {doc.relative_to(ROOT)}")


def main():
    manifest = json.loads(MANIFEST.read_text())
    files = manifest["files"]
    print(f"Fetching {len(files)} files…")
    ok, failed = fetch_all(files)
    localize(files, manifest.get("cdn_base", ""))
    print(f"Done: {ok}/{len(files)} present.")
    if failed:
        print("Missing:", *failed, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
