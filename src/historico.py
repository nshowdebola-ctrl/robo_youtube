#!/usr/bin/env python3

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ranking_noticias import normalizar_texto


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

HISTORICO_FILE = BASE_DIR / "dados" / "historico_noticias.json"

DIAS_RETENCAO = 30


# ============================================================
# CARREGAR / SALVAR
# ============================================================

def carregar_historico():

    if not HISTORICO_FILE.exists():
        return []

    try:

        with open(
            HISTORICO_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            dados = json.load(arquivo)

    except Exception as erro:

        print(
            f"⚠️ Não foi possível ler o histórico: {erro}"
        )

        return []

    if not isinstance(dados, list):
        return []

    return dados


def salvar_historico(historico):

    HISTORICO_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        HISTORICO_FILE,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            historico,
            arquivo,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# LIMPEZA DE ENTRADAS ANTIGAS
# ============================================================

def limpar_expirados(historico, dias=DIAS_RETENCAO):

    limite = datetime.now(timezone.utc) - timedelta(
        days=dias
    )

    resultado = []

    for item in historico:

        try:

            data_uso = datetime.fromisoformat(
                item.get("data_uso", "")
            )

            if data_uso.tzinfo is None:
                data_uso = data_uso.replace(
                    tzinfo=timezone.utc
                )

        except (ValueError, TypeError):
            continue

        if data_uso >= limite:
            resultado.append(item)

    return resultado


# ============================================================
# CONSULTA / REGISTRO
# ============================================================

def _link_noticia(noticia):

    return (
        noticia.get("link")
        or noticia.get("url")
        or ""
    ).strip()


def ja_usada(noticia, historico):

    titulo_normalizado = normalizar_texto(
        noticia.get("titulo", "")
    )

    link = _link_noticia(noticia)

    for item in historico:

        if (
            titulo_normalizado
            and item.get("titulo_normalizado") == titulo_normalizado
        ):
            return True

        if link and item.get("link") == link:
            return True

    return False


def registrar_uso(noticia, historico):

    historico = list(historico)

    historico.append({

        "titulo_normalizado": normalizar_texto(
            noticia.get("titulo", "")
        ),

        "titulo": noticia.get("titulo", ""),

        "link": _link_noticia(noticia),

        "data_uso": datetime.now(
            timezone.utc
        ).isoformat(),

    })

    return historico
