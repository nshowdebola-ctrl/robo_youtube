#!/usr/bin/env python3

"""
Histórico de RESULTADOS já usados nos Shorts.

Módulo separado de historico.py (que controla o histórico de
notícias do pipeline principal) — propositalmente independente,
pra não mexer em nada do que já funciona.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ranking_noticias import normalizar_texto


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

HISTORICO_FILE = BASE_DIR / "dados" / "historico_resultados.json"

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
            f"⚠️ Não foi possível ler o histórico de resultados: {erro}"
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

def _chave_resultado(resultado):

    return (
        normalizar_texto(resultado.get("time_a", ""))
        + "|"
        + normalizar_texto(resultado.get("time_b", ""))
        + "|"
        + str(resultado.get("placar_a", ""))
        + "-"
        + str(resultado.get("placar_b", ""))
    )


def ja_usada(resultado, historico):

    chave = _chave_resultado(resultado)

    for item in historico:

        if item.get("chave") == chave:
            return True

    return False


def registrar_uso(resultado, historico):

    historico = list(historico)

    historico.append({

        "chave": _chave_resultado(resultado),

        "time_a": resultado.get("time_a", ""),
        "time_b": resultado.get("time_b", ""),
        "placar_a": resultado.get("placar_a", ""),
        "placar_b": resultado.get("placar_b", ""),

        "data_uso": datetime.now(
            timezone.utc
        ).isoformat(),

    })

    return historico
