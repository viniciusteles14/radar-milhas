"""Funções compartilhadas: HTTP, JSON, Telegram. Só biblioteca padrão do Python."""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
DATA.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (RadarMilhas; +https://github.com)"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def load_json(name, default):
    p = DATA / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def save_json(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def telegram_send(text, preview=False, privado=False):
    """Envia mensagem pro Telegram. privado=True manda só pro dono (TELEGRAM_CHAT_ID);
    senão vai pro canal definido em config.json (telegram_canal), se houver.
    Sem token configurado, só imprime (modo teste)."""
    import re
    import urllib.error
    token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    canal = str(load_config().get("telegram_canal") or "").strip()
    if canal and not privado:
        chat = canal
    if not token or not chat:
        print("---- [Telegram simulado] ----\n" + text + "\n-----------------------------")
        return

    def post(payload):
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode(payload).encode())
        urllib.request.urlopen(req, timeout=30).read()

    payload = {
        "chat_id": chat,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": "false" if preview else "true",
    }
    try:
        post(payload)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        print(f"Falha ao enviar Telegram ({e.code}): {detail}")
        if e.code == 400:  # tenta de novo em texto puro (sem formatação)
            plain = re.sub(r"<[^>]+>", "", text)
            plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            payload.pop("parse_mode")
            payload["text"] = plain[:4000]
            try:
                post(payload)
                print("Reenviado em texto puro: OK")
            except urllib.error.HTTPError as e2:
                print(f"Falha de novo ({e2.code}): {e2.read().decode('utf-8', 'ignore')}")
    except Exception as e:  # não derruba o monitor por falha de envio
        print("Falha ao enviar Telegram:", e)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_pts(n):
    return f"{int(n):,}".replace(",", ".")
