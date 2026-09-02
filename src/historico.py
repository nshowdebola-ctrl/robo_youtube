#!/usr/bin/env python3

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ranking_noticias import normalizar_texto, similaridade


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

HISTORICO_FILE = BASE_DIR / "dados" / "historico_noticias.json"

DIAS_RETENCAO = 30

# Mesmo limiar usado em ranking_noticias.py pra assunto repetido
# dentro de uma rodada — aqui aplicado contra o histórico, pra
# pegar o mesmo assunto vindo de fontes diferentes (títulos com
# palavras distintas) em execuções separadas do robô.
LIMIAR_SIMILARIDADE = 0.70

# Só compara similaridade contra notícias usadas recentemente —
# não faz sentido barrar um assunto novo só porque ele parece
# com algo publicado há semanas.
JANELA_SIMILARIDADE_HORAS = 48


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


def _usada_ha_menos_de(item, horas):

    try:

        data_uso = datetime.fromisoformat(
            item.get("data_uso", "")
        )

        if data_uso.tzinfo is None:
            data_uso = data_uso.replace(
                tzinfo=timezone.utc
            )

    except (ValueError, TypeError):
        return False

    limite = datetime.now(timezone.utc) - timedelta(
        hours=horas
    )

    return data_uso >= limite


def ja_usada(noticia, historico):

    titulo = noticia.get("titulo", "")

    titulo_normalizado = normalizar_texto(
        titulo
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

        # Mesmo assunto contado por um veículo diferente (título
        # com palavras distintas) numa execução anterior recente
        # — sem isso, "Arthur é reforço do Santos" e "Santos
        # anuncia contratação de Arthur" passavam como notícias
        # diferentes e geravam vídeos duplicados.
        if (
            titulo
            and item.get("titulo")
            and _usada_ha_menos_de(item, JANELA_SIMILARIDADE_HORAS)
            and similaridade(titulo, item["titulo"]) >= LIMIAR_SIMILARIDADE
        ):
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
