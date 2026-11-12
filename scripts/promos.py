"""Monitor de promoções: lê feeds RSS dos blogs de milhas, filtra Azul e avisa no Telegram.

Avisos certeiros: o robô identifica DESTINO e PONTOS em cada promoção e só alerta na hora
quando bate numa regra do config.json (ex.: Europa até 50 mil). O resto vai num resumo diário.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

sys.path.insert(0, os.path.dirname(__file__))
from common import esc, fmt_pts, http_get, load_config, load_json, now_iso, save_json, telegram_send  # noqa: E402

REGIOES = {
    "Europa": r"europa|lisboa|portugal|porto\b|paris|fran[çc]a|madri|espanha|barcelona|roma|it[áa]lia|mil[ãa]o|londres|amsterd|frankfurt|zurique|munique|alemanha",
    "EUA": r"\beua\b|estados unidos|orlando|miami|fort lauderdale|nova york|new york|boston|chicago|los angeles|flórida|florida|disney",
    "América do Sul": r"buenos aires|argentina|santiago|chile|montevid|uruguai|lima\b|peru|bogot|col[ôo]mbia|assun[çc][ãa]o|bariloche|punta del este",
    "Caribe": r"caribe|canc[úu]n|punta cana|aruba|curaçao|cura[çc]ao",
}
PASSAGEM = r"passage|trecho|voo|v[ôo]os|resgate|emiss|executiva|ida e volta|ida\b|a partir de"
TAGS = [
    ("🔁 Bônus transferência", r"b[ôo]nus|transfer[êe]ncia|livelo|esfera|inter loop|uau caixa"),
    ("💸 Desconto no resgate", r"desconto|% ?off|\boff\b"),
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
        desc = strip_html(it.findtext("description"))[:600]
        pub = it.findtext("pubDate")
        try:
            pub = parsedate_to_datetime(pub).isoformat() if pub else now_iso()
        except Exception:
            pub = now_iso()
        source = re.sub(r"^https?://(www\.)?", "", feed_url).split("/")[0]
        items.append({"title": title, "link": link, "summary": desc, "published": pub, "source": source})
    return items


def extrair_pontos(texto):
    """Menor quantidade de pontos/milhas citada (ex.: '49 mil pontos', '3.540 pontos')."""
    vals = []
    rx = r"(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)\s*(mil)?\s*(?:pontos|milhas|pts)(?!\s*(?:por|a cada)\s*(?:real|r\$|d[óo]lar))"
    for num, mil in re.findall(rx, texto, re.I):
        n = float(num.replace(".", "").replace(",", "."))
        if mil:
            n *= 1000
        if n >= 1000:  # ignora "25 pontos por real" etc.
            vals.append(int(n))
    return min(vals) if vals else None


def analisar(item):
    t = item["title"].lower()
    full = (item["title"] + " " + item["summary"]).lower()
    regiao = next((r for r, rx in REGIOES.items() if re.search(rx, t)), None)
    if not regiao and re.search(PASSAGEM, t):
        regiao = next((r for r, rx in REGIOES.items() if re.search(rx, full)), None)
    eh_passagem = bool(re.search(PASSAGEM, t))
    if not regiao and eh_passagem and re.search(r"nacion|brasil|pelo pa[ií]s|dom[ée]stic", full):
        regiao = "Nacional"
    pontos = extrair_pontos(item["title"]) or (extrair_pontos(item["summary"]) if eh_passagem else None)
    cabine = "executiva" if re.search(r"executiva|business|primeira classe", full) else "economica"
    tags = [label for label, rx in TAGS if re.search(rx, full)]
    if regiao and regiao != "Nacional":
        tags.insert(0, "🌎 Internacional")
    return {"regiao": regiao, "pontos": pontos, "cabine": cabine, "tags": tags}


def bate_regra(item, regras):
    if item["pontos"] is None or not item["regiao"]:
        return None
    for r in regras:
        intl_ok = r["regiao"] == "Qualquer internacional" and item["regiao"] != "Nacional"
        if r["regiao"] != item["regiao"] and not intl_ok:
            continue
        if r.get("cabine", "qualquer") not in ("qualquer", item["cabine"]):
            continue
        if item["pontos"] <= r["max_pontos"]:
            return r
    return None


def parse_telegram(html, canal):
    """Lê a página pública t.me/s/<canal> e devolve itens no mesmo formato do RSS."""
    items = []
    for bloco in html.split("tgme_widget_message_wrap")[1:]:
        m_txt = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', bloco, re.S)
        if not m_txt:
            continue
        bruto = m_txt.group(1)
        linhas = [re.sub(r"https?://\S+", "", strip_html(x)).strip(" 👉🏼🔗:-") for x in re.split(r"<br\s*/?>", bruto)]
        linhas = [x for x in linhas if len(re.sub(r"\W", "", x)) >= 3]
        if not linhas:
            continue
        title = max(linhas, key=len)[:200]  # a linha mais longa costuma ser a manchete
        resumo = " ".join(x for x in linhas if x != title)[:400]
        links = [u for u in re.findall(r'href="(https?://[^"]+)"', bruto) if "t.me/" not in u and "telegram.org" not in u]
        post = re.search(r'data-post="([^"]+)"', bloco)
        link = links[0] if links else (f"https://t.me/{post.group(1)}" if post else "")
        t = re.search(r'<time datetime="([^"]+)"', bloco)
        items.append({"title": title, "link": link, "summary": resumo, "published": t.group(1) if t else now_iso(),
                      "source": f"t.me/{canal}"})
    return items


def fetch_all(cfg):
    out = []
    reserva = cfg.get("telegram_reserva", {})
    for url in cfg["feeds"]:
        try:
            out += parse_feed(http_get(url, timeout=15), url)
        except Exception as e:
            canal = reserva.get(url)
            if not canal:
                print(f"[promos] falha em {url}: {e}")
                continue
            try:
                itens = parse_telegram(http_get(f"https://t.me/s/{canal}", timeout=15).decode("utf-8", "ignore"), canal)
                out += itens
                print(f"[promos] {url} falhou ({e}); usei o Telegram t.me/{canal}: {len(itens)} posts")
            except Exception as e2:
                print(f"[promos] falha em {url} e no Telegram {canal}: {e2}")
    for canal in cfg.get("telegram_canais", []):
        try:
            out += parse_telegram(http_get(f"https://t.me/s/{canal}", timeout=15).decode("utf-8", "ignore"), canal)
        except Exception as e:
            print(f"[promos] falha no Telegram {canal}: {e}")
    return out


def chave_titulo(title):
    t = re.sub(r"[^a-z0-9 ]", "", unescape(title).lower())
    return "t:" + re.sub(r"\s+", " ", t).strip()[:70]


def run(items=None, force_digest=False):
    full_cfg = load_config()
    cfg = full_cfg["promos"]
    regras = full_cfg.get("alertas_certeiros", [])
    items = items if items is not None else fetch_all(cfg)
    rx = [re.compile(p, re.I) for p in cfg["title_must_match"]]
    azul = [i for i in items if any(r.search(i["title"]) for r in rx)]

    state = load_json("promos_seen.json", None)
    first_run = state is None
    seen = set(state or [])
    db = load_json("promos.json", [])
    known = {d["link"] for d in db}
    pending = load_json("promos_digest.json", [])

    new = []
    for it in azul:
        tk = chave_titulo(it["title"])
        if it["link"] in seen or tk in seen:
            continue
        seen.add(it["link"])
        seen.add(tk)
        it.update(analisar(it))
        it["international"] = it["regiao"] not in (None, "Nacional")
        it["found_at"] = now_iso()
        regra = bate_regra(it, regras)
        it["match"] = regra["nome"] if regra else None
        if it["link"] not in known:
            db.append(it)
        new.append(it)

    db.sort(key=lambda i: i["published"], reverse=True)
    save_json("promos.json", db[:300])
    save_json("promos_seen.json", sorted(seen)[-6000:])

    if first_run:
        hits = [i for i in new if i["match"]]
        msg = ("✈️ <b>Radar ajustado para avisos certeiros!</b>\n"
               "Vou te chamar na hora só quando bater numa destas regras:\n"
               + "\n".join(f"• {esc(r['nome'])}" for r in regras)
               + f"\n\nO resto das promoções da Azul vai num resumo por dia.\n"
               f"Agora nos blogs: {len(hits)} oferta(s) dentro das suas regras.")
        telegram_send(msg)
        for it in hits[:5]:
            enviar_certeiro(it)
        print(f"[promos] primeira execução: {len(new)} itens, {len(hits)} certeiros")
        return new

    hits = [i for i in new if i["match"]]
    enviados = 0
    for it in hits[: cfg["max_alerts_per_run"]]:
        enviar_certeiro(it)
        enviados += 1
    pending += [{"title": i["title"], "link": i["link"], "tags": i["tags"]} for i in new if not i["match"]]

    # resumo diário (por volta das 9h de Brasília = 12h UTC)
    hour = datetime.now(timezone.utc).hour
    if pending and (force_digest or (cfg.get("resumo_diario", True) and hour == 12)):
        linhas = [f"📰 <b>Resumo do dia — Azul</b> ({len(pending)} novidades)\n"]
        for p in pending[:15]:
            tag = p["tags"][0] if p["tags"] else "•"
            linhas.append(f"{tag} <a href=\"{esc(p['link'])}\">{esc(p['title'])}</a>")
        telegram_send("\n".join(linhas))
        enviados += 1
        pending = []
    if not enviados and cfg.get("avisar_sem_novidades", True):
        agora = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3))).strftime("%H:%M")
        telegram_send(f"✅ SEM NOVIDADES ({agora})", privado=True)
    save_json("promos_digest.json", pending[-100:])
    print(f"[promos] {len(azul)} itens da Azul, {len(new)} novos, {len(hits)} certeiros")
    return new


def enviar_certeiro(it):
    destino = it["regiao"].upper() if it["regiao"] != "EUA" else "OS EUA"
    cab = " EXECUTIVA" if it["cabine"] == "executiva" else ""
    telegram_send(
        f"🔥 <b>PASSAGEM{cab} PRA {esc(destino)} POR {fmt_pts(it['pontos'])} PONTOS</b>\n"
        f"Regra: {esc(it['match'])}\n\n"
        f"{esc(it['title'])}\n<i>{esc(it['source'])}</i>\n{esc(it['link'])}\n\n"
        "⚠️ Valor 'a partir de', confira datas e se é só ida ou ida e volta.",
        preview=True,
    )


if __name__ == "__main__":
    run()
