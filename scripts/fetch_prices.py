#!/usr/bin/env python3
"""Повлекува моментални цени за телевизори и фрижидери од повеќе продавници и ги зачувува со датум.

Продавници:
  A1          – автоматски (a1.mk/webshop)
  Нептун      – автоматски (neptun.mk)
  Техномаркет – автоматски (tehnomarket.com.mk)
  Сетек       – полуавтоматски: setec.mk ги вчитува цените со JavaScript, па се собираат во
                прелистувач со scripts/setec_collect.js и се зачувуваат во data/manual/setec-*.tsv.
                Оваа скрипта ги спојува тие датотеки (со датумот запишан во нив).

Употреба:
    python3 scripts/fetch_prices.py                         # снимка за денес
    python3 scripts/fetch_prices.py --label "Black Friday"
    python3 scripts/fetch_prices.py --only a1,neptun        # само некои продавници

Резултат:
    data/snapshots/<датум>.json – сурова снимка за тој ден
    data/prices.json            – сите производи + историја на цени по датум (ја чита index.html)
Само стандардна Python библиотека.
"""
import argparse, datetime as dt, html, json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (price-tracker)"}
CAP = {"tv": 45000, "fridge": 50000}   # не чуваме поскапи производи (нема потреба)


def fetch(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # повтори при мрежна грешка
            if attempt == 2:
                raise
            time.sleep(2)


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).replace("\xa0", " ").strip()


# ---------- поврзување на ист модел меѓу продавници ----------
NOISE = re.compile(r"^\d+(HZ|MS|W|L|KWH|CM|MM|DB|DBA|GB|NIT|NITS|\")?$|^(DVB|HDR10|HDMI|USB|WIFI|4K|8K|UHD|FHD|QLED|OLED|LED|DLED|ANDROID\d*|WEBOS\d*|A\+\+\+?|DOLBY)", re.I)


def model_code(title, brand=""):
    t = clean(title).upper()
    for w in [brand or "", "ТЕЛЕВИЗОР", "ФРИЖИДЕР", "ЛАДИЛНИК", "КОМБИНИРАН", "SMART", "TV"]:
        if w:
            t = t.replace(w.upper(), " ")
    t = re.sub(r"\b(\d{2})\s*\"?\s+([A-Z]{1,4}\d[A-Z0-9]*)\b", r"\1\2", t)  # "85 P8L" -> "85P8L"
    t = re.sub(r"\b(\d{2})\s*\"?\s+(NANO)\s+(\d{2}[A-Z0-9]+)\b", r"\1\2\3", t)  # "55 NANO 81A3A" -> "55NANO81A3A"
    t = re.sub(r"\b(\d{2})\s*\"?\s+(8MB6C)\b", r"\1\2", t)                      # LG "55 8MB6C" -> "558MB6C"
    t = re.sub(r"\b(RDS[OA])\s+(\d{3})\s+(K40)\s?([A-Z]{2})\b", r"\1\2\3\4", t)      # Beko "RDSO 206 K40SN"
    toks = re.findall(r"[A-Z0-9][A-Z0-9/\-\.]*", t)
    for i, tok in enumerate(toks):
        tok = tok.split("/")[0].replace("-", "").replace(".", "")
        if len(tok) >= 5 and re.search(r"[A-Z]", tok) and re.search(r"\d", tok) and not NOISE.match(tok):
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            return tok + (nxt if nxt in ("PRO", "PLUS", "MAX", "ULTRA", "SE", "MINI", "I") else "")
    # резерва: „65 BIQ 8000, 65\"…“ -> 65BIQ8000 (делот пред првата запирка, без празни места)
    head = re.sub(r"[^A-Z0-9]", "", t.split(",")[0])
    return head if len(head) >= 5 and re.search(r"[A-Z]", head) and re.search(r"\d", head) else None


def group_codes(products):
    """Ист модел = ист код, или еден код е почеток на друг (>= 9 знаци), на пр. UE55U7022H ~ UE55U7022HUXXH."""
    codes = sorted({p["code"] for p in products if p["code"]}, key=len)
    canon = {}
    for c in codes:
        base = next((k for k in canon.values() if len(k) >= 9 and c.startswith(k)), None)
        canon[c] = base or c
    for p in products:
        p["group"] = canon.get(p["code"]) or f'{p["store"]}:{p["id"]}'


# ---------- A1 ----------
def a1():
    urls = {"tv": "https://www.a1.mk/webshop/mk/tv/shop",
            "fridge": "https://www.a1.mk/webshop/mk/belatehnika/frizideri/shop"}
    out = []
    money = lambda b, f: (lambda m: round(float(m.group(1))) if m else None)(re.search(rf"\b{f}=MKD ([\d.]+)", b))
    attr = lambda b, n: (lambda m: html.unescape(m.group(1).strip()) if m else None)(re.search(rf'data-{n}="?([^"\n]*)"?', b))
    for cat, url in urls.items():
        for b in fetch(url).split('class="dvc-idtfr')[1:]:
            pid = attr(b, "productid")
            if not pid:
                continue
            link = re.search(r'class="device-link" href="([^"]+)"', b)
            inst = re.search(r'<div class="cena[^"]*">\s*([\d.]+) ден\. x (\d+) рати', b)
            brand, model = attr(b, "brand"), attr(b, "model")
            out.append(dict(store="a1", id=pid, category=cat, brand=brand, title=f"{brand} {model}",
                            code=model_code(model), url=html.unescape(link.group(1)) if link else None,
                            image=attr(b, "image"),
                            specs=[clean(s) for s in re.findall(r'<div class="icon"></div>(.*?)</div>', b, re.S) if clean(s)],
                            price=money(b, "fullPrice"), regular=money(b, "defaultBasePrice"),
                            monthly=int(inst.group(1).replace(".", "")) if inst else None,
                            installments=int(inst.group(2)) if inst else None, priceName="A1 цена"))
    return out


# ---------- Нептун ----------
def neptun():
    cats = {"tv": "televizori", "fridge": "KOMBINIRANI_FRIZIDERI"}
    out = []
    for cat, slug in cats.items():
        for page in range(1, 30):
            s = fetch(f"https://www.neptun.mk/{slug}.nspx?page={page}")
            m = re.search(r'data-categorydetails="([^"]*)"', s)
            prods = json.loads(html.unescape(m.group(1)))["Products"] if m else []
            if not prods:
                break
            for p in prods:
                brand = (p.get("Manufacturer") or {}).get("Name", "")
                curl = (p.get("Category") or {}).get("Url") or slug
                price = round(p.get("ActualPrice") or p.get("DiscountPrice") or p.get("RegularPrice"))
                out.append(dict(store="neptun", id=str(p["Id"]), category=cat, brand=brand.title(), title=p["Title"],
                                code=model_code(p["Title"], brand),
                                url=f"https://www.neptun.mk/categories/{curl}/{p['Url']}",
                                image="https://www.neptun.mk/" + p["Thumbnail"] if p.get("Thumbnail") else None,
                                specs=[], price=price, regular=round(p["RegularPrice"]),
                                monthly=round(p["RatePrice"]) if p.get("RatePrice") else None,
                                installments=p.get("NumberOfRates"),
                                priceName=(p.get("DiscountPriceName") or "") + " цена" if p.get("HasDiscount") else "Цена"))
            if len(prods) < 20:
                break
    return out


# ---------- Техномаркет ----------
def tehnomarket():
    cats = {"tv": ["4327/46-85-led-televizori", "4328/19-43-led-televizori"],
            "fridge": ["3885/ladilnici-so-dole-zamrznuvach", "3887/ladilnici-so-gore-zamrznuvach"]}
    out = []
    for cat, slugs in cats.items():
        for slug in slugs:
            seen = set()
            for page in range(1, 40):
                url = f"https://www.tehnomarket.com.mk/category/{slug}" + (f"/page/{page}" if page > 1 else "")
                # првиот производ во ред има класа „span4 span-first-child product-fix“
                blocks = re.split(r'<li class="span4[^"]*?product-fix', re.sub(r"<!--.*?-->", "", fetch(url), flags=re.S))[1:]
                ids = [re.search(r'data-id="(\d+)"', b).group(1) for b in blocks]
                if not blocks or set(ids) <= seen:   # нема нови производи = крај
                    break
                seen |= set(ids)
                for b in blocks:
                    pid = re.search(r'data-id="(\d+)"', b).group(1)
                    title = clean((re.search(r'class="product-name[^"]*"\s+title="([^"]*)"', b) or [None, ""])[1])
                    link = re.search(r'href="(https://www\.tehnomarket\.com\.mk/product/[^"]+)"', b)
                    img = re.search(r"background-image: url\('([^']+)'\)", b)
                    brand = clean((re.search(r"Производител:\s*<strong>([^<]*)", b) or [None, ""])[1])
                    prices = {clean(k).rstrip(":").strip(): int(v.replace(",", "")) for k, v in
                              re.findall(r'([А-Яа-яA-Za-z ]+:)\s*<strong><span class="nm">([\d,]+)</span>', b)}
                    regular = prices.get("Редовна Цена") or int(re.search(r'data-price="(\d+)"', b).group(1))
                    smart = prices.get("SMART цена")
                    out.append(dict(store="tehnomarket", id=pid, category=cat, brand=brand.title(), title=title,
                                    code=model_code(title, brand), url=link.group(1) if link else None,
                                    image=img.group(1) if img else None, specs=[],
                                    price=smart or regular, regular=regular, monthly=None, installments=None,
                                    priceName="SMART цена (со SMART картичка)" if smart else "Цена"))
    return out


# ---------- Сетек (од data/manual/setec-*.tsv) ----------
def setec():
    out, dates = [], set()
    for cat in ("tv", "fridge"):
        f = DATA / "manual" / f"setec-{cat}.tsv"
        if not f.exists():
            continue
        lines = f.read_text(encoding="utf-8").splitlines()
        dates.add(lines[0].lstrip("# ").split("\t")[0])
        for ln in lines[1:]:
            if not ln.strip():
                continue
            slug, model, price, regular = ln.split("\t")
            brand = model.split()[0].title() if " " in model else model.split("-")[0].title()
            out.append(dict(store="setec", id=slug, category=cat, brand=brand, title=model,
                            code=model_code(model, brand), url=f"https://setec.mk/products/{slug}", image=None,
                            specs=[], price=int(price), regular=int(regular), monthly=None, installments=None,
                            priceName="Клуб цена (со Сетек клуб картичка)"))
    return out, dates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--label", default="", help='на пр. "Black Friday"')
    ap.add_argument("--only", default="a1,neptun,tehnomarket,setec")
    a = ap.parse_args()
    only = a.only.split(",")

    products = []
    for name, fn in [("a1", a1), ("neptun", neptun), ("tehnomarket", tehnomarket)]:
        if name in only:
            got = fn()
            print(f"{name}: {len(got)} производи", file=sys.stderr)
            if not got:
                sys.exit(f"Нема производи од {name} – можеби страницата е сменета. Ништо не е зачувано.")
            products += got
    if "setec" in only:
        got, dates = setec()
        print(f"setec: {len(got)} производи (од TSV, датум {', '.join(sorted(dates)) or '–'})", file=sys.stderr)
        if dates and dates != {a.date}:
            print(f"  ВНИМАНИЕ: цените од Сетек се од {dates}, не од {a.date}. Повлечи ги пак со setec_collect.js.",
                  file=sys.stderr)
        products += got

    # веќе следените производи ги чуваме и над CAP, инаку поскапувањата би исчезнале
    kp = DATA / "prices.json"
    known = set(json.loads(kp.read_text(encoding="utf-8"))["products"]) if kp.exists() else set()
    products = [p for p in products if p["price"] and
                (p["price"] <= CAP[p["category"]] or f'{p["store"]}:{p["id"]}' in known)]
    group_codes(products)

    (DATA / "snapshots").mkdir(parents=True, exist_ok=True)
    (DATA / "snapshots" / f"{a.date}.json").write_text(
        json.dumps({"date": a.date, "label": a.label, "products": products}, ensure_ascii=False, indent=1), encoding="utf-8")

    db_path = DATA / "prices.json"
    db = json.loads(db_path.read_text(encoding="utf-8")) if db_path.exists() else {"snapshots": [], "products": {}}
    snaps = {s["date"]: s for s in db["snapshots"]}
    snaps[a.date] = {"date": a.date, "label": a.label or snaps.get(a.date, {}).get("label", ""),
                     "stores": sorted({p["store"] for p in products} | set(snaps.get(a.date, {}).get("stores", [])))}
    db["snapshots"] = sorted(snaps.values(), key=lambda s: s["date"])
    for p in products:
        key = f'{p["store"]}:{p["id"]}'
        cur = db["products"].setdefault(key, {"history": []})
        hist = [h for h in cur["history"] if h["date"] != a.date]
        hist.append({"date": a.date, "price": p["price"], "regular": p["regular"], "monthly": p["monthly"]})
        info = {k: v for k, v in p.items() if k not in ("price", "regular", "monthly")}
        cur.update(info, key=key, lastSeen=a.date, history=sorted(hist, key=lambda h: h["date"]))
    db["updated"] = a.date
    db_path.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    multi = {}
    for p in products:
        multi.setdefault(p["group"], set()).add(p["store"])
    print(f"Зачувано: {a.date} – {len(products)} производи, {sum(len(v) > 1 for v in multi.values())} модели во 2+ продавници",
          file=sys.stderr)


if __name__ == "__main__":
    main()
