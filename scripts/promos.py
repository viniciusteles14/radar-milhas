"""Monitor de promoções: lê feeds RSS dos blogs de milhas, filtra Azul e avisa no Telegram."""
import os
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape

sys.path.insert(0, os.path.dirname(__file__))
from common import esc, http_get, load_config, load_json, now_iso, save_json, telegram_send  # noqa: E402

TAGS = [
    ("🌎 Internacional", r"internacion|europa|eua|estados unidos|lisboa|portugal|paris|orlando|miami|fort lauderdale|nova york|executiva|business"),
    ("💸 Desconto no resgate", r"desconto|% ?off|\boff\b|resgate"),
    ("🔁 Bônus transferência", r"b[ôo]nus|transfer[êe]ncia|livelo|esfera|inter loop|uau caixa"),
    ("🚨 Alerta de passagem", r"alerta|a partir de|trechos|passagens"),
    ("🛒 Compra de pontos", r"compr(a|e) de pontos|milheiro|clube azul"),
]


def strip_html(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_feed(xml_bytes, feed_url):
    items = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = strip_html(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        desc = strip_html(it.findtext("description"))[:400]
        pub = it.findtext("pubDate")
        try:
            pub = parsedate_to_datetime(pub).isoformat() if pub else now_iso()
        except Exception:
            pub = now_iso()
        source = re.sub(r"^https?://(www\.)?", "", feed_url).split("/")[0]
        items.append({"title": title, "link": link, "summary": desc, "published": pub, "source": source})
    return items


def classify(item):
    text = (item["title"] + " " + item["summary"]).lower()
    return [label for label, rx in TAGS if re.search(rx, text)]


def fetch_all(cfg):
    out = []
    for url in cfg["feeds"]:
        try:
            out += parse_feed(http_get(url), url)
        except Exception as e:
            print(f"[promos] falha em {url}: {e}")
    return out


def run(items=None):
    cfg = load_config()["promos"]
    items = items if items is not None else fetch_all(cfg)
    rx = [re.compile(p, re.I) for p in cfg["title_must_match"]]
    azul = [i for i in items if any(r.search(i["title"]) for r in rx)]

    state = load_json("promos_seen.json", None)
    first_run = state is None
    seen = set(state or [])
    db = load_json("promos.json", [])
    known = {d["link"] for d in db}

    new = []
    for it in azul:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        it["tags"] = classify(it)
        it["international"] = "🌎 Internacional" in it["tags"]
        it["found_at"] = now_iso()
        if it["link"] not in known:
            db.append(it)
        new.append(it)

    # internacionais primeiro, depois mais recentes
    new.sort(key=lambda i: (not i["international"], i["published"]), reverse=False)
    db.sort(key=lambda i: i["published"], reverse=True)
    save_json("promos.json", db[:300])
    save_json("promos_seen.json", sorted(seen)[-3000:])

    if first_run:
        top = new[:5]
        msg = "✈️ <b>Radar de Milhas Azul ativado!</b>\nÚltimas oportunidades encontradas:\n\n"
        msg += "\n\n".join(f"• <a href=\"{esc(i['link'])}\">{esc(i['title'])}</a>" for i in top) or "(nada no momento)"
        telegram_send(msg)
        print(f"[promos] primeira execução: {len(new)} itens registrados")
        return new

    for it in new[: cfg["max_alerts_per_run"]]:
        tags = " ".join(it["tags"]) or "📰 Novidade"
        telegram_send(
            f"{tags}\n<b>{esc(it['title'])}</b>\n{esc(it['summary'][:220])}…\n"
            f"<i>{esc(it['source'])}</i>\n{esc(it['link'])}",
            preview=True,
        )
    print(f"[promos] {len(azul)} itens da Azul nos feeds, {len(new)} novos")
    return new


if __name__ == "__main__":
    run()
