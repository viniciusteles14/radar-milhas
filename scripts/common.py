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


def telegram_send(text, preview=False):
    """Envia mensagem pro Telegram. Sem token configurado, só imprime (modo teste)."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("---- [Telegram simulado] ----\n" + text + "\n-----------------------------")
        return
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": "false" if preview else "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:  # não derruba o monitor por falha de envio
        print("Falha ao enviar Telegram:", e)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_pts(n):
    return f"{int(n):,}".replace(",", ".")
