"""Build the knowledge hub: docs/ website, REPOS.md and the auto section of README.md.

Usage:  python tools/build_site.py      (needs: pip install markdown)
Driven entirely by sources/entries.json and sources/media-manifest.json,
so adding an X post = add its content file + an entry + its media rows, then push.
"""
import html
import json
import os
import pathlib
import re
import shutil
from collections import OrderedDict

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
HUB = json.loads((ROOT / "sources" / "entries.json").read_text())
MANIFEST = json.loads((ROOT / "sources" / "media-manifest.json").read_text())
CDN = MANIFEST.get("cdn_base", "")
ENTRIES = sorted(HUB["entries"], key=lambda e: e["date"], reverse=True)
MEDIA = MANIFEST["files"]

CSS = r"""
:root{--bg:#0a0c10;--panel:#11151b;--panel2:#171c24;--line:#252c37;--ink:#eef2f7;--muted:#9aa6b5;
--accent:#2dd4bf;--accent2:#8b5cf6;--mustard:#5eead4;--cream:#e2e8f0;--radius:16px}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:radial-gradient(1200px 600px at 80% -10%,#0f2f33 0%,transparent 60%),var(--bg);
color:var(--ink);font:17px/1.7 Inter,system-ui,-apple-system,Segoe UI,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--mustard);text-decoration:none}a:hover{text-decoration:underline}
.nav{position:sticky;top:0;z-index:10;backdrop-filter:blur(12px);background:rgba(14,10,9,.78);border-bottom:1px solid var(--line)}
.nav .in{max-width:1180px;margin:auto;display:flex;align-items:center;gap:22px;padding:14px 22px;flex-wrap:wrap}
.brand{font-family:'Bricolage Grotesque',Inter,sans-serif;font-weight:800;font-size:19px;color:var(--ink)}
.brand b{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
.nav a.l{color:var(--muted);font-size:15px;font-weight:500}.nav a.l.on,.nav a.l:hover{color:var(--ink);text-decoration:none}
.nav .sp{flex:1}
h1,h2,h3,h4{font-family:'Bricolage Grotesque',Inter,sans-serif;line-height:1.15;letter-spacing:-.015em}
h1{font-size:clamp(34px,5vw,56px);margin:.2em 0 .4em}
h2{font-size:30px;margin:2.2em 0 .6em;padding-top:.4em}
h3{font-size:22px;margin:1.8em 0 .5em;color:var(--cream)}h4{font-size:18px;margin:1.6em 0 .4em;color:var(--mustard)}
.grad{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
.wrap{max-width:1180px;margin:auto;padding:0 22px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:56px;max-width:1180px;margin:auto;padding:40px 22px 100px}
.doc{max-width:780px;min-width:0}
.toc{position:sticky;top:84px;align-self:start;max-height:calc(100vh - 110px);overflow:auto;font-size:14px;border-left:1px solid var(--line);padding-left:18px}
.toc b{display:block;color:var(--muted);font-size:12px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:10px}
.toc a{display:block;color:var(--muted);padding:4px 0;line-height:1.35}.toc a:hover{color:var(--ink);text-decoration:none}
@media(max-width:980px){.layout{grid-template-columns:1fr}.toc{display:none}}
p,li,td{color:#eadcc6;overflow-wrap:anywhere}strong{color:var(--ink)}
hr{border:0;height:1px;background:linear-gradient(90deg,transparent,var(--line),transparent);margin:48px 0}
blockquote{margin:22px 0;padding:14px 20px;border-left:3px solid var(--accent);background:var(--panel);border-radius:0 12px 12px 0;color:var(--muted)}
blockquote p{margin:.3em 0;color:#e2d3bd}
code{font-family:'JetBrains Mono',ui-monospace,Menlo,monospace;font-size:.88em;background:var(--panel2);border:1px solid var(--line);padding:.1em .4em;border-radius:6px}
pre{position:relative;background:#120d0c;border:1px solid var(--line);border-radius:var(--radius);padding:20px 22px;overflow:auto;line-height:1.55}
pre code{background:none;border:0;padding:0;font-size:13.5px;color:#f1e2cb;white-space:pre-wrap;word-break:break-word}
.copy{position:absolute;top:10px;right:10px;font:600 12px Inter,sans-serif;color:var(--ink);background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;cursor:pointer;opacity:.85}
.copy:hover{opacity:1;border-color:var(--accent)}
table{width:100%;border-collapse:separate;border-spacing:0;margin:22px 0;font-size:15px;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;display:block;overflow-x:auto}
th,td{padding:11px 14px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{background:var(--panel2);color:var(--cream);font-weight:600;white-space:nowrap}
tr:last-child td{border-bottom:0}tbody tr:nth-child(even) td{background:rgba(255,255,255,.015)}
img{max-width:100%;border-radius:12px}
figure{margin:30px 0}figure img{display:block;margin:auto;border:1px solid var(--line)}
figure.video video{display:block;width:100%;border-radius:var(--radius);border:1px solid var(--line);background:#000;box-shadow:0 20px 60px rgba(0,0,0,.45)}
figure.video.tall video{max-height:78vh;width:auto;max-width:100%;margin:auto}
figcaption{text-align:center;font-size:14px;color:var(--muted);margin-top:10px}
figcaption a{font-weight:600}
.hero{position:relative;border-radius:28px;overflow:hidden;margin:36px 0 18px;border:1px solid var(--line)}
.hero img{display:block;width:100%;border-radius:0}
.hero-copy{padding:40px 0 10px;max-width:820px}
.hero-copy p.lead{font-size:20px;color:var(--muted)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:30px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px}
.stat b{display:block;font:800 30px 'Bricolage Grotesque',Inter,sans-serif;color:var(--ink)}
.stat span{color:var(--muted);font-size:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;margin:26px 0 10px}
.card{display:block;background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:22px;padding:26px;color:var(--ink);transition:.2s}
.card:hover{transform:translateY(-3px);border-color:var(--accent);text-decoration:none}
.card .k{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.card h3{margin:.4em 0 .3em;color:var(--ink)}.card p{color:var(--muted);margin:0;font-size:15px}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:18px;margin-top:22px}
.gallery .g{background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden}
.gallery video{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#000}
.gallery .g.tall video{aspect-ratio:4/5}
.gallery .t{padding:12px 14px}.gallery .t b{display:block}.gallery .t span{font-size:13.5px;color:var(--muted)}
.foot{border-top:1px solid var(--line);color:var(--muted);font-size:13.5px;text-align:center;padding:30px 22px 50px}
.pill{display:inline-block;font-size:12.5px;padding:4px 10px;border-radius:999px;border:1px solid var(--line);color:var(--muted);margin:0 6px 6px 0}

.entry{display:grid;grid-template-columns:220px 1fr;gap:22px;background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:22px;padding:18px;color:var(--ink);margin-bottom:18px;transition:.2s}
.entry:hover{border-color:var(--accent);text-decoration:none;transform:translateY(-2px)}
.entry img{width:100%;height:150px;object-fit:cover;border-radius:14px}
.entry.nocover{grid-template-columns:1fr}
.entry .k{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.entry h3{margin:.3em 0 .4em;color:var(--ink)}.entry p{color:var(--muted);margin:.2em 0 .6em;font-size:15px}
@media(max-width:700px){.entry{grid-template-columns:1fr}.entry img{height:180px}}
.tag{display:inline-block;font-size:12px;padding:3px 9px;border-radius:999px;background:var(--panel2);border:1px solid var(--line);color:var(--muted);margin:0 6px 6px 0}
.hero-grad{border-radius:28px;border:1px solid var(--line);padding:56px 40px;margin:36px 0 10px;background:radial-gradient(600px 300px at 85% 20%,rgba(45,212,191,.28),transparent 70%),linear-gradient(180deg,var(--panel2),var(--panel))}
"""
JS = r"""
document.querySelectorAll('pre').forEach(pre=>{const b=document.createElement('button');b.className='copy';b.textContent='Copy';
b.onclick=()=>{navigator.clipboard.writeText(pre.innerText.replace(/^Copy\n?/,'')).then(()=>{b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1400)})};pre.prepend(b)});
"""
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">')


def page_name(e):
    return f"{e['id']}.html"


def local_exists(path):
    return (ROOT / path).exists()


def media_src(item, for_html=True):
    """Local copy when downloaded, original URL otherwise."""
    if local_exists(item["path"]):
        return "media/" + pathlib.Path(item["path"]).name if for_html else item["path"]
    return item["original"]


def by_path(path):
    return next((m for m in MEDIA if m["path"] == path), None)


def shell(title, active, body):
    nav = [("index.html", "Home")] + [(page_name(e), e["id"].upper()) for e in sorted(ENTRIES, key=lambda x: x["id"])]
    nav += [("repos.html", "All repos"), ("sources.html", "Sources")]
    titles = {page_name(e): e["title"] for e in ENTRIES}
    links = "".join(f'<a class="l{" on" if active == href else ""}" href="{href}" title="{html.escape(titles.get(href, label))}">{html.escape(label)}</a>' for href, label in nav)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="robots" content="noindex">{FONTS}<style>{CSS}</style></head><body>
<nav class="nav"><div class="in"><a class="brand" href="index.html">Social Media <b>with AI</b></a><span class="sp"></span>{links}</div></nav>
{body}
<div class="foot">All archived content © its original authors. Captured from X for personal reference.</div>
<script>{JS}</script></body></html>"""


VID_BLOCK = re.compile(r'<p align="center"><a href="([^"]+)"><img src="([^"]+)" width="\d+" alt="([^"]*)"></a><br>\s*<sub>(.*?)</sub></p>', re.S)
IMG_BLOCK = re.compile(r'<p align="center"><img src="([^"]+)" width="\d+" alt="([^"]*)"></p>')
URL = re.compile(r'(?<![("<=\[/])(https?://[^\s)<>|`*]+[^\s)<>|`*.,])')


def linkify(text):
    out, fence = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            fence = not fence
        elif not fence and not line.lstrip().startswith("<"):
            line = URL.sub(r"<\1>", line)
        out.append(line)
    return "\n".join(out)


def is_tall(src):
    return any(k in src for k in ("1080x1920", "1440x1800", "1080x1350", "720x1280"))


def video_fig(m):
    mp4, poster, alt, cap = m.groups()
    item = next((x for x in MEDIA if x["original"] == mp4 or mp4.endswith(pathlib.Path(x["path"]).name)), None)
    tall = is_tall(item["original"] if item else mp4)
    cap = cap.replace("▶ ", "")
    return (f'<figure class="video{" tall" if tall else ""}"><video controls playsinline preload="none" poster="{poster}">'
            f'<source src="{mp4}" type="video/mp4"></video><figcaption>{cap}</figcaption></figure>')


def localize_html(out):
    if CDN:
        out = out.replace(CDN + "docs/media/", "media/")
    out = out.replace("../docs/media/", "media/").replace("docs/media/", "media/")
    for item in MEDIA:
        if local_exists(item["path"]):
            local = "media/" + pathlib.Path(item["path"]).name
            out = out.replace(item["original"], local).replace(item["original"].replace("&", "&amp;"), local)
    for e in ENTRIES:
        out = out.replace(f'href="{pathlib.Path(e["file"]).name}"', f'href="{page_name(e)}"')
    return out


def render_md(text):
    text = linkify(text)
    text = VID_BLOCK.sub(video_fig, text)
    text = IMG_BLOCK.sub(lambda m: f'<figure><img src="{m.group(1)}" alt="{m.group(2)}"></figure>', text)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2-3"}})
    out = md.convert(text)
    toks = md.toc_tokens
    flat = toks[0]["children"] if toks and toks[0].get("level") == 1 else toks
    return out, flat


def toc_html(tokens):
    items = []
    for t in tokens:
        items.append(f'<a href="#{t["id"]}">{t["name"]}</a>')
        for c in t.get("children", []):
            items.append(f'<a href="#{c["id"]}" style="padding-left:12px">{c["name"]}</a>')
    return "<b>On this page</b>" + "".join(items)


def write(path, text):
    path.write_text(localize_html(text))


# ---------- repo index ----------
GH = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


def collect_repos():
    repos = OrderedDict()
    for e in ENTRIES:
        if e.get("kind") == "GitHub topic":
            continue
        text = (ROOT / e["file"]).read_text()
        for owner, name in GH.findall(text):
            name = name.rstrip(".")
            key = f"{owner}/{name}".lower()
            r = repos.setdefault(key, {"full": f"{owner}/{name}", "entries": []})
            if e["id"] not in r["entries"]:
                r["entries"].append(e["id"])
    return sorted(repos.values(), key=lambda r: (-len(r["entries"]), r["full"].lower()))


def write_repos_md(repos):
    titles = {e["id"]: e for e in ENTRIES}
    lines = ["# Every GitHub repo in the hub", "",
             f"{len(repos)} unique repositories, collected automatically from all {len(ENTRIES)} entries. Repos mentioned in more than one entry come first.", "",
             "| Repository | Mentioned in |", "|---|---|"]
    for r in repos:
        refs = " · ".join(f"[{titles[i]['kind']} {i.upper()}]({titles[i]['file']})" for i in r["entries"])
        lines.append(f"| [{r['full']}](https://github.com/{r['full']}) | {refs} |")
    lines += ["", "<sub>Generated by tools/build_site.py. Do not edit by hand.</sub>", ""]
    (ROOT / "REPOS.md").write_text("\n".join(lines))


# ---------- README auto section ----------
def readme_auto(repos, videos):
    vids = [v for v in videos][:9]
    out = ["<!-- AUTO:START (generated by tools/build_site.py; edit sources/entries.json instead) -->", "",
           f"**{len(ENTRIES)} entries · {len(repos)} repos linked from entries · {sum(e.get('repo_count', 0) for e in ENTRIES):,} repos in topic catalogues**", "",
           "## Entries", "", "| | Entry | Type | Author | Date |", "|---|---|---|---|---|"]
    for e in ENTRIES:
        cover = by_path(e.get("cover", ""))
        img = f'<img src="{e["cover"] if cover and local_exists(cover["path"]) else (cover or {}).get("original", "")}" width="120">' if cover else ""
        out.append(f"| {img} | **[{e['title']}]({e['file']})**<br><sub>{e['summary']}</sub> | {e['kind']} | [@{e['handle']}](https://x.com/{e['handle']}) | {e['date']} |")
    if not vids:
        out += ["", f"<sub>The full list of {len(repos)} repos linked from entries is in [REPOS.md](REPOS.md).</sub>", "", "<!-- AUTO:END -->"]
        return "\n".join(out)
    out += ["", "## Watch", "", "| | | |", "|:---:|:---:|:---:|"]
    cells = []
    for v in vids:
        poster = by_path(v.get("poster", "")) or {}
        p = v["poster"] if poster and local_exists(poster["path"]) else poster.get("original", "")
        href = (CDN + v["path"]) if local_exists(v["path"]) and CDN else v["original"]
        cells.append(f'[![{v["title"]}]({p})]({href})<br><sub>{v["title"]}</sub>')
    while len(cells) % 3:
        cells.append("")
    for i in range(0, len(cells), 3):
        out.append("| " + " | ".join(cells[i:i + 3]) + " |")
    out += ["", f"<sub>Tap a thumbnail to play it. The full list of {len(repos)} repos is in [REPOS.md](REPOS.md).</sub>", "", "<!-- AUTO:END -->"]
    return "\n".join(out)


def update_readme(block):
    p = ROOT / "README.md"
    t = p.read_text()
    t = re.sub(r"<!-- AUTO:START.*?<!-- AUTO:END -->", lambda m: block, t, flags=re.S)
    p.write_text(t)


def build():
    DOCS.mkdir(exist_ok=True)
    repos = collect_repos()
    videos = [m for m in MEDIA if m["kind"] == "video" and m.get("title")]

    for e in ENTRIES:
        body, toc = render_md((ROOT / e["file"]).read_text())
        write(DOCS / page_name(e), shell(e["title"], page_name(e),
              f'<div class="layout"><article class="doc">{body}</article><aside class="toc">{toc_html(toc)}</aside></div>'))

    write_repos_md(repos)
    body, toc = render_md((ROOT / "REPOS.md").read_text().replace("(content/", "("))
    write(DOCS / "repos.html", shell("Every repo", "repos.html", f'<div class="layout"><article class="doc" style="max-width:100%">{body}</article><aside class="toc"></aside></div>'))

    body, toc = render_md((ROOT / "sources" / "SOURCES.md").read_text())
    write(DOCS / "sources.html", shell("Sources", "sources.html", f'<div class="layout"><article class="doc" style="max-width:100%">{body}</article><aside class="toc">{toc_html(toc)}</aside></div>'))

    cards = ""
    for e in ENTRIES:
        cover = by_path(e.get("cover", ""))
        img = f'<img src="{media_src(cover)}" alt="">' if cover else ""
        tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in e.get("tags", []))
        cards += (f'<a class="entry{"" if img else " nocover"}" href="{page_name(e)}">{img}<div><span class="k">{e["kind"]} · {e["date"]} · @{e["handle"]}</span>'
                  f'<h3>{html.escape(e["title"])}</h3><p>{html.escape(e["summary"])}</p>{tags}</div></a>')
    gallery = ""
    for v in videos:
        poster = by_path(v.get("poster", ""))
        shape = "tall" if is_tall(v["original"]) else "wide"
        gallery += (f'<div class="g {shape}"><video controls playsinline preload="none" poster="{media_src(poster) if poster else ""}">'
                    f'<source src="{media_src(v)}" type="video/mp4"></video><div class="t"><b>{html.escape(v["title"])}</b>'
                    f'<span>{v["entry"]}</span></div></div>')
    home = f"""<div class="wrap">
<div class="hero-grad"><span class="pill">Knowledge hub</span><span class="pill">topic catalogues refresh weekly</span><span class="pill">{len(ENTRIES)} entries</span><span class="pill">updated automatically</span>
<h1>Social media research and content, <span class="grad">run by AI agents</span>.</h1>
<p class="lead" style="font-size:20px;color:var(--muted);max-width:760px">{html.escape(HUB["hub"]["tagline"])}</p></div>
<div class="stats">
<div class="stat"><b>{len(ENTRIES)}</b><span>entries archived</span></div>
<div class="stat"><b>{sum(e.get("repo_count", 0) for e in ENTRIES):,}</b><span>repos in topic catalogues</span></div>
<div class="stat"><b>{sum(1 for e in ENTRIES if e.get("kind") == "GitHub topic")}</b><span>GitHub topics catalogued</span></div>
<div class="stat"><b>{len(repos)}</b><span>repos linked from entries</span></div>
</div>
<h2>Entries</h2>{cards}
{"<h2>Watch</h2><div class=gallery>" + gallery + "</div>" if gallery else ""}
<p style="margin-top:36px"><a href="repos.html">Browse all {len(repos)} repos →</a> · <a href="sources.html">Sources and capture log →</a></p>
</div>"""
    write(DOCS / "index.html", shell(HUB["hub"]["title"], "index.html", home))
    update_readme(readme_auto(repos, videos))
    (DOCS / ".nojekyll").write_text("")
    print(f"built {len(ENTRIES)} entries, {len(repos)} repos, {len(videos)} videos")


if __name__ == "__main__":
    build()
