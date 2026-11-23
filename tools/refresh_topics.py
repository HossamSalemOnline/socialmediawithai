"""Refresh the GitHub topic catalogues listed in sources/topics.json.

Usage:  python tools/refresh_topics.py            (needs the `gh` CLI, authenticated; GH_TOKEN in Actions)
For each topic it pulls every public repository (GitHub search returns at most 1,000 per query, so the
date range is split in half until each slice fits), then writes:
  sources/topics/<topic>.json   raw data, sorted by stars
  content/topic-<topic>.md      the readable catalogue
"""
import datetime as dt
import hashlib
import json
import re
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIELDS = "fullName,description,stargazersCount,forksCount,language,updatedAt,createdAt,url,isArchived"


def gh(args, tries=6):
    """Run gh, waiting out GitHub's search rate limit (about 30 searches a minute) when it hits."""
    for attempt in range(1, tries + 1):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0:
            time.sleep(2)  # stay well under the per-minute search limit
            return r.stdout
        wait = 20 * attempt
        print(f"  gh failed (attempt {attempt}): {r.stderr.strip()[:160]} — retrying in {wait}s", file=sys.stderr)
        time.sleep(wait)
    raise SystemExit(f"gh kept failing: {' '.join(args)}")


def count(topic, lo, hi):
    q = f"topic:{topic} created:{lo}..{hi}"
    return json.loads(gh(["api", "-X", "GET", "search/repositories", "-f", f"q={q}", "-f", "per_page=1", "--jq", "{total_count}"]))["total_count"]


def fetch(topic, lo, hi):
    out = gh(["search", "repos", "--topic", topic, "--created", f"{lo}..{hi}", "--limit", "1000", "--json", FIELDS])
    return json.loads(out or "[]")


def collect(topic, lo=dt.date(2008, 1, 1), hi=None):
    hi = hi or dt.date.today() + dt.timedelta(days=1)
    n = count(topic, lo, hi)
    if n == 0:
        return []
    if n < 1000 or (hi - lo).days < 2:
        return fetch(topic, lo, hi)
    mid = lo + (hi - lo) / 2
    return collect(topic, lo, mid) + collect(topic, mid + dt.timedelta(days=1), hi)


NON_LATIN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")
PENDING = "(Description not in English; translation pending. See the repo.)"


def englishify(repos):
    """English-only catalogue: swap non-English descriptions for stored translations or a placeholder.
    Returns the names still needing a translation."""
    tpath = ROOT / "sources" / "translations.json"
    tr = json.loads(tpath.read_text())["translations"] if tpath.exists() else {}
    pending = []
    for r in repos:
        d = r.get("description") or ""
        if not NON_LATIN.search(d):
            continue
        t = tr.get(r["fullName"])
        if t and t.get("source_sha1") == hashlib.sha1(d.encode()).hexdigest():
            r["description"] = t["en"]
        else:
            r["description"] = PENDING
            pending.append(r["fullName"])
        r["descriptionTranslated"] = True
    return pending


def md(topic, repos, note):
    today = dt.date.today().isoformat()
    langs = {}
    for r in repos:
        langs[r.get("language") or "Not set"] = langs.get(r.get("language") or "Not set", 0) + 1
    top_langs = ", ".join(f"{k} ({v})" for k, v in sorted(langs.items(), key=lambda x: -x[1])[:6])
    lines = [f"# GitHub topic: {topic}", "",
             f"- **Source:** https://github.com/topics/{topic}",
             f"- **Repositories:** {len(repos):,} public repos (refreshed {today})",
             f"- **Most common languages:** {top_langs}",
             f"- **Captured via:** GitHub search API, every repo tagged `{topic}`, refreshed weekly by `tools/refresh_topics.py`. Descriptions are the authors' own; {sum(1 for r in repos if r.get('descriptionTranslated'))} non-English ones are shown in English translation.",
             ""]
    if note:
        lines += [note, ""]
    lines += ["## Top 25 by stars", "", "| # | Repository | Stars | Language | Updated | Description |", "|---|---|---|---|---|---|"]
    def row(i, r):
        d = (r.get("description") or "").replace("|", "\\|").replace("\n", " ").strip()
        arch = " (archived)" if r.get("isArchived") else ""
        return f"| {i} | [{r['fullName']}]({r['url']}){arch} | {r['stargazersCount']:,} | {r.get('language') or ''} | {r['updatedAt'][:10]} | {d} |"
    lines += [row(i, r) for i, r in enumerate(repos[:25], 1)]
    lines += ["", f"## All {len(repos):,} repositories", "", "| # | Repository | Stars | Language | Updated | Description |", "|---|---|---|---|---|---|"]
    lines += [row(i, r) for i, r in enumerate(repos, 1)]
    return "\n".join(lines) + "\n"


def main():
    cfg = json.loads((ROOT / "sources" / "topics.json").read_text())
    (ROOT / "sources" / "topics").mkdir(parents=True, exist_ok=True)
    for t in cfg["topics"]:
        name = t["topic"]
        found = {r["fullName"].lower(): r for r in collect(name)}
        repos = sorted(found.values(), key=lambda r: (-r["stargazersCount"], r["fullName"].lower()))
        pending = englishify(repos)
        if pending:
            print(f"  {len(pending)} non-English descriptions awaiting translation: {', '.join(pending[:10])}")
        (ROOT / "sources" / "topics" / f"{name}.json").write_text(json.dumps(repos, indent=1))
        (ROOT / "content" / f"topic-{name}.md").write_text(md(name, repos, t.get("note", "")))
        print(f"{name}: {len(repos)} repos")


if __name__ == "__main__":
    main()
