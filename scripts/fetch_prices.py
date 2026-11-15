#!/usr/bin/env python3
"""Повлекува моментални цени од A1.mk (телевизори + фрижидери) и ги зачувува со датум.

Употреба:
    python3 scripts/fetch_prices.py              # снимка за денес
    python3 scripts/fetch_prices.py --date 2026-11-27 --label "Black Friday"

Резултат:
    data/snapshots/<датум>.json   – сурова снимка за тој ден
    data/prices.json              – сите производи + историја на цени по датум (ја чита index.html)
Само стандардна Python библиотека, без зависности.
"""
import argparse, datetime as dt, html, json, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATEGORIES = {
    "tv": "https://www.a1.mk/webshop/mk/tv/shop",
    "fridge": "https://www.a1.mk/webshop/mk/belatehnika/frizideri/shop",
}
UA = {"User-Agent": "Mozilla/5.0 (price-tracker)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def money(block, field):
    m = re.search(rf"\b{field}=MKD ([\d.]+)", block)
    return round(float(m.group(1))) if m else None


def attr(block, name):
    m = re.search(rf'data-{name}="?([^"\n]*)"?', block)
    return html.unescape(m.group(1).strip()) if m else None


def parse(page, category):
    items = []
    for block in page.split('class="dvc-idtfr')[1:]:
        pid = attr(block, "productid")
        if not pid:
            continue
        link = re.search(r'class="device-link" href="([^"]+)"', block)
        specs = [html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").strip()
                 for s in re.findall(r'<div class="icon"></div>(.*?)</div>', block, re.S)]
        inst = re.search(r'<div class="cena[^"]*">\s*([\d.]+) ден\. x (\d+) рати', block)
        badge = re.findall(r'<span class="text-\d">([^<]+)</span>', block)
        items.append({
            "id": pid,
            "category": category,
            "brand": attr(block, "brand"),
            "model": attr(block, "model"),
            "image": attr(block, "image"),
            "url": html.unescape(link.group(1)) if link else None,
            "specs": [s for s in specs if s],
            "badge": " ".join(b.strip() for b in badge) or None,
            "a1Price": money(block, "fullPrice"),        # цена прикажана на A1 картичката
            "basePrice": money(block, "defaultBasePrice"),  # основна/редовна цена
            "monthly": int(inst.group(1).replace(".", "")) if inst else None,
            "installments": int(inst.group(2)) if inst else None,
            "availableOnline": attr(block, "availableonline") == "true",
        })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--label", default="", help='на пр. "Black Friday"')
    a = ap.parse_args()

    snapshot = {"date": a.date, "label": a.label, "products": []}
    for cat, url in CATEGORIES.items():
        got = parse(fetch(url), cat)
        print(f"{cat}: {len(got)} производи", file=sys.stderr)
        if not got:
            sys.exit(f"Нема производи за {cat} – можеби A1 ја сменил страницата.")
        snapshot["products"] += got

    (DATA / "snapshots").mkdir(parents=True, exist_ok=True)
    (DATA / "snapshots" / f"{a.date}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    db_path = DATA / "prices.json"
    db = json.loads(db_path.read_text(encoding="utf-8")) if db_path.exists() else {"snapshots": [], "products": {}}
    db["snapshots"] = sorted({s["date"]: s for s in db["snapshots"] + [{"date": a.date, "label": a.label}]}.values(),
                             key=lambda s: s["date"])
    for p in snapshot["products"]:
        cur = db["products"].setdefault(p["id"], {"history": []})
        hist = [h for h in cur["history"] if h["date"] != a.date]
        hist.append({"date": a.date, "a1Price": p["a1Price"], "basePrice": p["basePrice"], "monthly": p["monthly"]})
        info = {k: v for k, v in p.items() if k not in ("a1Price", "basePrice", "monthly")}
        cur.update(info, lastSeen=a.date, history=sorted(hist, key=lambda h: h["date"]))
    db["updated"] = a.date
    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Зачувано: {a.date} ({len(snapshot['products'])} производи)", file=sys.stderr)


if __name__ == "__main__":
    main()
