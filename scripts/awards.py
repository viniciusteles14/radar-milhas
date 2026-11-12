"""Monitor de assentos-prêmio Azul via API do Seats.aero.

Para cada rota (origem BR -> destino) e cabine, guarda o menor preço visto por dia
(histórico) e alerta quando:
  1) o preço fica abaixo do teto configurado em config.json, ou
  2) o preço fica X% abaixo da mediana histórica daquela rota.
"""
import json
import os
import statistics
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from common import esc, fmt_pts, http_get, load_config, load_json, now_iso, save_json, telegram_send  # noqa: E402

API = "https://seats.aero/partnerapi/availability"
CABINS = {"economy": "Y", "premium": "W", "business": "J"}
CABIN_PT = {"economy": "Econômica", "premium": "Premium", "business": "Executiva"}

BR_AIRPORTS = set(
    "GRU CGH VCP GIG SDU CNF PLU BSB REC FOR SSA POA CWB BEL MAO FLN NAT VIX GYN CGB MCZ "
    "JPA AJU THE SLZ CGR IGU NVT JOI LDB MGF RAO SJP UDI MOC IOS BPS PMW PVH RBR MCP BVB "
    "CXJ PNZ JDO CPV IMP STM UBA GVR VDC".split()
)


def fetch_region(cfg, dest_region, key):
    start = date.today()
    end = start + timedelta(days=cfg["days_ahead"])
    rows, cursor, skip = [], None, 0
    for _ in range(10):  # no máx. 10 páginas por região
        q = {
            "source": cfg["source"], "origin_region": cfg["origin_region"],
            "destination_region": dest_region, "start_date": start.isoformat(),
            "end_date": end.isoformat(), "take": 1000, "skip": skip,
        }
        if cursor:
            q["cursor"] = cursor
        raw = http_get(f"{API}?{urllib.parse.urlencode(q)}",
                       headers={"Partner-Authorization": key, "accept": "application/json"})
        body = json.loads(raw)
        page = body.get("data", []) if isinstance(body, dict) else body
        rows += page
        if not isinstance(body, dict) or not body.get("hasMore"):
            break
        cursor, skip = body.get("cursor"), skip + len(page)
    return rows


def normalize(rows, cfg, region):
    """Transforma objetos da API em ofertas simples: rota, data, cabine, pontos."""
    offers = []
    for r in rows:
        route = r.get("Route") or {}
        o, d = route.get("OriginAirport"), route.get("DestinationAirport")
        if not o or not d:
            continue
        if cfg.get("brazil_airports_only_origin") and o not in BR_AIRPORTS:
            continue
        for cabin, k in CABINS.items():
            if not r.get(f"{k}Available"):
                continue
            try:
                cost = int(float(r.get(f"{k}MileageCost") or 0))
            except ValueError:
                continue
            if cost <= 0:
                continue
            offers.append({
                "origin": o, "dest": d, "region": route.get("DestinationRegion") or region,
                "date": (r.get("Date") or "")[:10], "cabin": cabin, "points": cost,
                "direct": bool(r.get(f"{k}Direct")), "airlines": r.get(f"{k}Airlines") or "",
                "updated": r.get("UpdatedAt"),
            })
    return offers


def median_of(hist):
    vals = [h["min"] for h in hist]
    return statistics.median(vals) if vals else None


def run(offers=None):
    full = load_config()["awards"]
    key = os.environ.get("SEATS_AERO_KEY")
    if offers is None:
        if not key:
            print("[awards] SEATS_AERO_KEY não configurada — pulando monitor de rotas.")
            return []
        offers = []
        for reg in full["destination_regions"]:
            try:
                offers += normalize(fetch_region(full, reg, key), full, reg)
            except Exception as e:
                print(f"[awards] falha na região {reg}: {e}")

    today = date.today().isoformat()
    history = load_json("history.json", {})      # "GRU-LIS-business" -> [{day, min, flight_date}]
    alerted = load_json("alerted.json", {})       # "GRU-LIS-business-2027-01-10" -> {points, at}

    # melhor oferta por rota/cabine hoje
    best = {}
    for of in offers:
        k = f"{of['origin']}-{of['dest']}-{of['cabin']}"
        if k not in best or of["points"] < best[k]["points"]:
            best[k] = of

    alerts = []
    for k, of in best.items():
        hist = history.setdefault(k, [])
        med = median_of(hist)
        enough = len(hist) >= full["min_history_points"]
        limit = full["thresholds_points_one_way"].get(of["region"], {}).get(of["cabin"])
        reasons = []
        if limit and of["points"] <= limit:
            reasons.append(f"abaixo do seu teto de {fmt_pts(limit)}")
        if enough and med and of["points"] <= med * (1 - full["drop_vs_median_pct"] / 100):
            reasons.append(f"{round(100 * (1 - of['points'] / med))}% abaixo da mediana ({fmt_pts(med)})")
        of["median"] = med
        of["reasons"] = reasons

        # atualiza histórico (1 ponto por dia, guarda o menor)
        if hist and hist[-1]["day"] == today:
            if of["points"] < hist[-1]["min"]:
                hist[-1].update(min=of["points"], flight_date=of["date"])
        else:
            hist.append({"day": today, "min": of["points"], "flight_date": of["date"]})
        history[k] = hist[-120:]

        if not reasons:
            continue
        ak = f"{k}-{of['date']}"
        prev = alerted.get(ak)
        if prev:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(prev["at"])).days
            if age < full["realert_after_days"] and of["points"] >= prev["points"]:
                continue
        alerted[ak] = {"points": of["points"], "at": now_iso()}
        alerts.append(of)

    # ordena: executiva internacional primeiro, depois maior desconto
    def score(of):
        intl = of["region"] != "South America"
        disc = 1 - of["points"] / of["median"] if of.get("median") else 0
        return (not intl, of["cabin"] != "business", -disc)

    alerts.sort(key=score)
    top = alerts[: full["max_alerts_per_run"]]
    if top:
        lines = ["🎯 <b>Oportunidades Azul Fidelidade</b> (só ida)\n"]
        for of in top:
            d = datetime.fromisoformat(of["date"]).strftime("%d/%m/%Y") if of["date"] else "?"
            lines.append(
                f"✈️ <b>{of['origin']} → {of['dest']}</b> · {CABIN_PT[of['cabin']]}\n"
                f"   {fmt_pts(of['points'])} pts · {d}{' · direto' if of['direct'] else ''}\n"
                f"   <i>{esc('; '.join(of['reasons']))}</i>"
            )
        lines.append("\nConfira e emita em voeazul.com.br (disponibilidade muda rápido).")
        telegram_send("\n".join(lines))

    # dados para o painel
    current = sorted(best.values(), key=lambda o: (o["region"] == "South America", o["points"]))
    save_json("awards.json", {"updated": now_iso(), "offers": current[:1500], "alerts": top})
    save_json("history.json", history)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    save_json("alerted.json", {k: v for k, v in alerted.items() if v["at"] > cutoff})
    print(f"[awards] {len(offers)} ofertas, {len(best)} rotas/cabines, {len(alerts)} alertas")
    return alerts


if __name__ == "__main__":
    run()
