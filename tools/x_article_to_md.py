"""Convert a scraped X Article (xquik/x-article-scraper item) into hub Markdown, verbatim.

Usage:
  python tools/x_article_to_md.py ARTICLE.json TWEETS.json PREFIX OUT.md MEDIA_ROWS.json [HEADER.md]

ARTICLE.json  one article item (needs `contents`, `title`)
TWEETS.json   list of tweet items for the embedded posts (xquik/x-tweet-scraper, fields incl. media, noteTweet, entities)
PREFIX        media file prefix, e.g. e04
HEADER.md     optional metadata block placed under the title

Writes the Markdown plus a JSON list of media rows (name, original, kind, title, poster) to add to
sources/media-manifest.json. Videos use the highest-quality MP4 that stays under ~40 MB.
"""
import json
import re
import sys
from datetime import datetime

MAX_BYTES = 40_000_000


def pick_mp4(variants, duration_ms):
    mp4s = sorted((v for v in variants if v.get("contentType") == "video/mp4"), key=lambda v: v.get("bitrate", 0), reverse=True)
    secs = (duration_ms or 0) / 1000
    for v in mp4s:
        if not secs or v.get("bitrate", 0) * secs / 8 < MAX_BYTES:
            return v["url"]
    return mp4s[-1]["url"] if mp4s else None


def res_of(url):
    m = re.search(r"/(\d+x\d+)/", url)
    return m.group(1) if m else ""


def styled(block):
    """Apply Bold/Italic ranges and links to a block's text (offsets are in UTF-16 code units in X's data;
    plain BMP text is assumed, which holds for these articles)."""
    text = block.get("text", "")
    marks = []
    for r in block.get("inlineStyleRanges", []):
        tag = {"Bold": "**", "Italic": "*"}.get(r.get("style"))
        if tag and r["length"] > 0:
            marks.append((r["offset"], r["offset"] + r["length"], tag, tag))
    for l in block.get("links", []) or []:
        marks.append((l["offset"], l["offset"] + l["length"], "[", f"]({l['url']})"))
    for start, end, open_, close in sorted(marks, key=lambda m: m[0], reverse=True):
        seg = text[start:end]
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg) - len(seg.rstrip())
        core = seg.strip()
        if not core:
            continue
        text = text[:start] + seg[:lead] + open_ + core + close + seg[len(seg) - trail:] + text[end:]
    return text.rstrip()


def clean_code(md):
    # X appends the copy button's label to the last line of each code block.
    return re.sub(r"copy(\n+)```\s*$", "\n```", md.rstrip())


def expand(text, entities, media):
    for u in (entities or {}).get("urls", []):
        text = text.replace(u["url"], u["expanded_url"])
    for m in media or []:
        text = text.replace(m.get("url", "@@"), "").rstrip()
    return re.sub(r"\s*https://t\.co/\S+\s*$", "", text).rstrip()


class Media:
    def __init__(self, prefix):
        self.prefix, self.rows, self.n = prefix, [], 0

    def add_video(self, mp4, poster, title, slug):
        self.n += 1
        name = f"{self.prefix}-v{self.n}-{slug}"
        self.rows.append({"name": f"{name}.mp4", "original": mp4, "kind": "video", "title": title, "poster": f"{name}-poster.jpg"})
        self.rows.append({"name": f"{name}-poster.jpg", "original": poster, "kind": "poster"})

    def add_image(self, url, title, slug):
        self.n += 1
        ext = url.rsplit(".", 1)[-1].split("?")[0]
        self.rows.append({"name": f"{self.prefix}-img{self.n}-{slug}.{ext}", "original": url, "kind": "image", "title": title})


def slugify(s, n=4):
    words = re.findall(r"[a-z0-9]+", s.lower())[:n]
    return "-".join(words) or "media"


def video_block(mp4, poster, caption, width):
    alt = caption.replace('"', "&quot;")
    return (f'<p align="center"><a href="{mp4}"><img src="{poster}" width="{width}" alt="{alt}"></a><br>\n'
            f'<sub>▶ {caption} · <a href="{mp4}">MP4</a></sub></p>')


def tweet_block(t, media):
    a = t.get("author", {})
    when = datetime.strptime(t["createdAt"], "%a %b %d %H:%M:%S %z %Y").strftime("%a %d %b %Y")
    text = expand((t.get("noteTweet") or {}).get("text") or t.get("text", ""), t.get("entities"), t.get("media"))
    head = f"> **[Embedded post]** [@{a.get('username')}]({t['url']}) · {a.get('name', '')} · {when} · {t.get('viewCount', 0):,} views · {t.get('likeCount', 0):,} likes"
    body = "\n".join("> " + ln if ln else ">" for ln in text.split("\n"))
    out = [head, ">", body]
    q = t.get("quoted_tweet")
    if q and q.get("text"):
        qa = (q.get("author") or {}).get("username", "")
        qtext = expand(q["text"], q.get("entities"), q.get("media"))
        out += [">", f"> > **Quoting** [@{qa}]({q.get('url')}):", "> >"] + ["> > " + ln if ln else "> >" for ln in qtext.split("\n")]
    for m in t.get("media") or []:
        if m.get("type") == "video":
            mp4 = pick_mp4(m.get("videoVariants", []), m.get("durationMillis"))
            secs = round((m.get("durationMillis") or 0) / 1000)
            title = f"@{a.get('username')}: {text.splitlines()[0][:60]}".strip()
            media.add_video(mp4, m["mediaUrl"], title, slugify(a.get("username", "post"), 1))
            out += ["", video_block(mp4, m["mediaUrl"], f"@{a.get('username')} video, {secs} s, {res_of(mp4)}", 560)]
        elif m.get("type") == "photo":
            media.add_image(m["mediaUrl"], f"@{a.get('username')} image", slugify(a.get("username", "post"), 1))
            out += ["", f'<p align="center"><img src="{m["mediaUrl"]}" width="560" alt="@{a.get("username")} image"></p>']
    return "\n".join(out)


def convert(article, tweets, prefix, header=""):
    media = Media(prefix)
    tweets = {t["id"]: t for t in tweets}
    lines = [f"# {article['title']}", ""]
    if article.get("coverImageUrl"):
        media.rows.append({"name": f"{prefix}-cover.{article['coverImageUrl'].rsplit('.', 1)[-1]}", "original": article["coverImageUrl"], "kind": "image", "title": "Cover"})
        lines += [f'<p align="center"><img src="{article["coverImageUrl"]}" width="860" alt="Cover"></p>', ""]
    if header:
        lines += [header.rstrip(), "", "---", ""]
    list_kind = None
    last_heading = "intro"
    for i, b in enumerate(article["contents"]):
        t = b["type"]
        if t not in ("unordered-list-item", "ordered-list-item") and list_kind:
            lines.append("")
            list_kind = None
        if t == "paragraph":
            txt = styled(b)
            if txt:
                lines += [txt, ""]
        elif t in ("header-one", "header-two"):
            last_heading = b["text"].strip()
            lines += [("## " if t == "header-one" else "### ") + last_heading, ""]
        elif t == "unordered-list-item":
            list_kind = "ul"
            lines.append("- " + styled(b))
        elif t == "ordered-list-item":
            list_kind = "ol"
            lines.append("1. " + styled(b))
        elif t == "blockquote":
            lines += ["> " + styled(b).replace("\n", "\n> "), ""]
        elif t == "markdown":
            lines += [clean_code(b["text"]), ""]
        elif t == "divider":
            lines += ["---", ""]
        elif t == "tweet":
            tw = tweets.get(b["tweetId"])
            if tw:
                lines += [tweet_block(tw, media), ""]
            else:
                lines += [f"> **[Embedded post, not captured]** https://x.com/i/status/{b['tweetId']}", ""]
        elif t == "media":
            if b.get("mediaType") == "video":
                mp4 = pick_mp4(b.get("variants", []), b.get("durationMs"))
                secs = round((b.get("durationMs") or 0) / 1000)
                title = f"{last_heading[:50]} (video)"
                media.add_video(mp4, b["previewUrl"], title, slugify(last_heading))
                lines += [video_block(mp4, b["previewUrl"], f"{title}, {secs} s, {res_of(mp4)}", 640), ""]
            else:
                url = b.get("url") or b.get("previewUrl")
                media.add_image(url, last_heading[:60], slugify(last_heading))
                lines += [f'<p align="center"><img src="{url}" width="860" alt="{last_heading.replace(chr(34), "&quot;")}"></p>', ""]
        else:
            lines += [b.get("text", ""), ""]
    md = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).rstrip() + "\n"
    return md, media.rows


if __name__ == "__main__":
    art = json.load(open(sys.argv[1]))
    tw = json.load(open(sys.argv[2]))
    header = open(sys.argv[6]).read() if len(sys.argv) > 6 else ""
    md, rows = convert(art, tw, sys.argv[3], header)
    open(sys.argv[4], "w").write(md)
    json.dump(rows, open(sys.argv[5], "w"), indent=2)
    print(f"{len(md.split()):,} words, {len(rows)} media rows")
