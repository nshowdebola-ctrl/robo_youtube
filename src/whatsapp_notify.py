#!/usr/bin/env python3
"""
NEWS-YOUTUBE - NOTIFICAÇÃO WHATSAPP (CallMeBot)

Reaproveita as mesmas credenciais CallMeBot já configuradas no
projeto crypto-radar (.callmebot.env lá) em vez de pedir pro
usuário configurar de novo aqui.

Falha de envio (rede fora, key inválida, serviço fora do ar) nunca
deve derrubar quem chamou - só retorna False.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from pathlib import Path

ENV_FILE = Path("/home/alex/projetos/crypto-radar/.callmebot.env")

TIMEOUT_SECONDS = 10


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def send_whatsapp(message: str) -> bool:
    """True se a mensagem foi enfileirada com sucesso. Nunca lança
    exceção."""
    env = load_env()
    phone = env.get("CALLMEBOT_PHONE", "")
    apikey = env.get("CALLMEBOT_APIKEY", "")
    if not phone or not apikey:
        return False

    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode({
        "phone": phone,
        "text": message,
        "apikey": apikey,
    })
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status == 200 and "queued" in body.lower()
    except Exception:
        return False


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) or "Teste do news-youtube."
    ok = send_whatsapp(text)
    print("Enviado." if ok else "Falhou.")
    raise SystemExit(0 if ok else 1)
