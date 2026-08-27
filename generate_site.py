#!/usr/bin/env python3
"""求職者向けEntrance Book（Notion）→ HP（静的HTML）生成
usage: python3 generate_site.py <output_dir>
NOTION_TOKEN は Keychain(notion-hayfield) または環境変数 NOTION_TOKEN から取得
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

CANDIDATE_ROOT = "3c9b68c2-5038-81f9-88aa-c18633efdd2f"

EN_LABELS = {
    "はじめに": "Introduction", "会社概要": "Company", "事業内容": "Business",
    "仕事内容": "Work", "数字で見るヘイフィールド": "Data", "MVV・カルチャー": "Culture",
    "評価制度・報酬": "Evaluation & Reward", "キャリア形成環境": "Career",
    "教育・成長環境": "Growth", "福利厚生・働き方": "Benefits", "福利厚生・子育てサポート": "Benefits",
    "ギャラリー": "Gallery", "募集要項": "Positions", "選考について": "Selection",
    "よくある質問": "FAQ", "採用広報コンテンツ": "Media",
}
BASE = "https://api.notion.com/v1"

def get_token():
    t = os.environ.get("NOTION_TOKEN")
    if t: return t
    return subprocess.run(["security", "find-generic-password", "-s", "notion-hayfield",
                           "-a", "entrance", "-w"], capture_output=True, text=True, check=True).stdout.strip()
TOKEN = get_token()

def api(method, path):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Notion-Version", "2022-06-28")
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 * (attempt + 1)); continue
            raise
        except Exception as e:
            print(f"  api retry {attempt+1}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(path)

def children(block_id):
    out, cursor = [], None
    while True:
        path = f"/blocks/{block_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        res = api("GET", path)
        out += res["results"]
        if not res.get("has_more"): break
        cursor = res["next_cursor"]
    return out

# ---------- rendering ----------
IMG_DIR = None
img_count = 0
page_images = {}

def save_image(url, page_slug):
    global img_count
    img_count += 1
    fname = f"{page_slug}_{img_count:02d}.jpg"
    dest = os.path.join(IMG_DIR, fname)
    if os.path.exists(dest) and os.path.getsize(dest) > 5000:
        page_images.setdefault(page_slug, []).append(f"assets/{fname}")
        return f"assets/{fname}"  # キャッシュ再利用（再実行時）
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
                f.write(r.read())
            page_images.setdefault(page_slug, []).append(f"assets/{fname}")
            return f"assets/{fname}"
        except Exception as e:
            print(f"  image retry {attempt+1}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"image download failed: {fname}")

def rich(rts):
    out = []
    for t in rts:
        s = html.escape(t.get("plain_text", ""))
        ann = t.get("annotations", {})
        if ann.get("bold"): s = f"<strong>{s}</strong>"
        if ann.get("color") == "gray": s = f'<span class="muted">{s}</span>'
        href = t.get("href")
        if href: s = f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{s}</a>'
        out.append(s)
    return "".join(out).replace("\n", "<br>")

def yt_embed(url):
    m = re.search(r"(?:v=|youtu\.be/)([\w-]+)", url)
    if not m: return f'<p><a href="{url}">{url}</a></p>'
    return (f'<div class="video"><iframe src="https://www.youtube.com/embed/{m.group(1)}" '
            'title="YouTube" allowfullscreen loading="lazy"></iframe></div>')

def render_blocks(blocks, page_slug, depth=0):
    out, i = [], 0
    while i < len(blocks):
        b = blocks[i]
        t = b["type"]
        data = b.get(t, {})
        rt = data.get("rich_text", [])
        if t in ("bulleted_list_item", "numbered_list_item"):
            tag = "ul" if t == "bulleted_list_item" else "ol"
            items = []
            while i < len(blocks) and blocks[i]["type"] == t:
                items.append(f"<li>{rich(blocks[i][t]['rich_text'])}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        if t == "heading_1": out.append(f"<h2>{rich(rt)}</h2>")
        elif t == "heading_2": out.append(f"<h3>{rich(rt)}</h3>")
        elif t == "heading_3": out.append(f"<h4>{rich(rt)}</h4>")
        elif t == "paragraph":
            if rt: out.append(f"<p>{rich(rt)}</p>")
        elif t == "callout":
            emoji = (data.get("icon") or {}).get("emoji", "")
            color = data.get("color", "")
            cls = "callout"
            if "blue" in color: cls += " c-blue"
            elif "green" in color: cls += " c-green"
            elif "yellow" in color: cls += " c-yellow"
            out.append(f'<div class="{cls}"><span class="ic">{emoji}</span><div>{rich(rt)}</div></div>')
        elif t == "quote": out.append(f"<blockquote>{rich(rt)}</blockquote>")
        elif t == "divider": out.append("<hr>")
        elif t == "toggle":
            inner = render_blocks(children(b["id"]), page_slug, depth+1)
            out.append(f"<details><summary>{rich(rt)}</summary><div class='dbody'>{inner}</div></details>")
        elif t == "table":
            rows = children(b["id"])
            has_header = data.get("has_column_header")
            trs = []
            for ri, r in enumerate(rows):
                cells = r["table_row"]["cells"]
                tag = "th" if (has_header and ri == 0) else "td"
                trs.append("<tr>" + "".join(f"<{tag}>{rich(c)}</{tag}>" for c in cells) + "</tr>")
            out.append(f"<div class='tablewrap'><table>{''.join(trs)}</table></div>")
        elif t == "column_list":
            cols = []
            for col in children(b["id"]):
                cols.append(f"<div class='col'>{render_blocks(children(col['id']), page_slug, depth+1)}</div>")
            out.append(f"<div class='cols'>{''.join(cols)}</div>")
        elif t == "image":
            src_info = data.get(data.get("type"), {})
            url = src_info.get("url", "")
            if url:
                local = save_image(url, page_slug)
                out.append(f'<img src="{local}" alt="" loading="lazy">')
        elif t == "video":
            url = data.get("external", {}).get("url", "")
            if url: out.append(yt_embed(url))
        elif t == "embed":
            url = data.get("url", "")
            out.append(f'<p><a href="{html.escape(url)}" target="_blank" rel="noopener">▶ 資料を見る（外部リンク）</a></p>')
        elif t == "child_page":
            pass
        i += 1
    return "\n".join(out)

# ---------- main ----------
def main():
    global IMG_DIR
    outdir = sys.argv[1] if len(sys.argv) > 1 else "site"
    IMG_DIR = os.path.join(outdir, "assets")
    os.makedirs(IMG_DIR, exist_ok=True)

    kids = children(CANDIDATE_ROOT)
    pages = [(b["child_page"]["title"], b["id"]) for b in kids if b["type"] == "child_page"]
    print(f"{len(pages)} pages found", flush=True)

    sections, nav = [], []
    gallery_slug = None
    for idx, (title, pid) in enumerate(pages):
        slug = f"s{idx:02d}"
        if "ギャラリー" in title: gallery_slug = slug
        body = render_blocks(children(pid), slug)
        nav.append(f'<a href="#{slug}">{html.escape(title)}</a>')
        en = EN_LABELS.get(title.strip(), "")
        head = (f'<div class="sec-head"><span class="en">{html.escape(en)}</span>'
                f'<span class="jp">{html.escape(title)}</span></div>') if en else \
               f'<div class="sec-head"><span class="en">{html.escape(title)}</span></div>'
        sections.append(f'<section id="{slug}"><div class="wrap">{head}\n{body}</div></section>')
        print("rendered:", title, flush=True)

    # ヒーローコラージュ: ギャラリーの写真から6枚
    collage_imgs = (page_images.get(gallery_slug) or [])[:6]
    collage = "".join(f'<img src="{u}" alt="" loading="lazy">' for u in collage_imgs)

    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "site_template.html")).read()
    page_html = (tpl.replace("<!--NAV-->", "".join(nav))
                    .replace("<!--COLLAGE-->", collage)
                    .replace("<!--SECTIONS-->", "\n".join(sections)))
    with open(os.path.join(outdir, "index.html"), "w") as f:
        f.write(page_html)
    print("DONE ->", os.path.join(outdir, "index.html"))

if __name__ == "__main__":
    main()
