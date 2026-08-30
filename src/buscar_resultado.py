#!/usr/bin/env python3

"""
NEWS-YOUTUBE — BUSCA DE RESULTADO PARA SHORTS

Pipeline SEPARADA da principal (buscar_noticia.py). Roda junto,
mas não compartilha arquivos/histórico com ela.

1. Coleta e filtra notícias (mesmos filtros do pipeline principal).
2. Fica só com notícias do tipo "resultado" (vitória/derrota/empate)
   de um clube conhecido, excluindo categorias de base/amistoso.
3. Rankeia por relevância e remove as já usadas (histórico próprio).
4. Pra cada candidata, tenta extrair time A, time B e placar —
   do corpo da matéria (o título quase nunca tem o placar).
5. Gera o roteiro do Short pra primeira que der certo.

Códigos de saída:
    0 = short (roteiro) gerado com sucesso
    2 = nenhum resultado extraível nesta janela (não é erro)
    1 = falha real
"""

import re
import sys

from coletar_noticias import coletar_noticias
from filtrar_noticias import (
    filtrar_ultimas_24h,
    filtrar_conteudo_editorial,
    filtrar_apenas_futebol,
    remover_duplicadas,
)
from ranking_noticias import (
    ranquear_noticias,
    normalizar_texto,
    CLUBES_IMPORTANTES,
)
from gerar_roteiro import detectar_tipo, extrair_texto_materia
from historico_resultados import (
    carregar_historico,
    salvar_historico,
    limpar_expirados,
    ja_usada,
    registrar_uso,
)
from gerar_short import (
    montar_roteiro_short,
    proximo_indice_short,
)


# ============================================================
# CATEGORIAS QUE NÃO SÃO O TIME PRINCIPAL
# ============================================================

CATEGORIAS_EXCLUIDAS = [
    "sub-20", "sub-17", "sub-15", "sub-23", "sub-13", "sub-11",
    "sub20", "sub17", "sub15", "sub23",
    "amistoso", "amistosos", "pré-temporada", "pre-temporada",
    "categoria de base", "categorias de base",
    "reservas", "time b", "sub-9",
]


def eh_categoria_excluida(titulo):

    titulo_normalizado = normalizar_texto(titulo)

    return any(
        normalizar_texto(termo) in titulo_normalizado
        for termo in CATEGORIAS_EXCLUIDAS
    )


def tem_clube_importante(titulo):

    titulo_normalizado = normalizar_texto(titulo)

    return any(
        normalizar_texto(clube) in titulo_normalizado
        for clube in CLUBES_IMPORTANTES
    )


# Não mantemos uma lista de times da Série B (o elenco muda a
# cada temporada por acesso/rebaixamento — arriscado de ficar
# desatualizado). Em vez disso, identificamos pela própria
# competição sendo citada na notícia.
TERMOS_SERIE_B = [
    "série b", "serie b", "segunda divisão", "segunda divisao",
    "segundona",
]


def eh_serie_b(titulo):

    titulo_normalizado = normalizar_texto(titulo)

    return any(
        normalizar_texto(termo) in titulo_normalizado
        for termo in TERMOS_SERIE_B
    )


# ============================================================
# EXTRAIR TIME A, TIME B E PLACAR
# ============================================================

_ARTIGO = re.compile(
    r"^(o|a|os|as)\s+",
    re.IGNORECASE,
)

_TIME = (
    r"([A-ZÀ-Ú][\wÀ-ÿ\-]*"
    r"(?:\s+(?:[a-zà-ÿ]{1,3}\s+)?[A-ZÀ-Ú][\wÀ-ÿ\-]*){0,2})"
)

_VERBOS_VITORIA = (
    r"venceu|vence|derrotou|derrota|bateu|bate|"
    r"superou|supera|atropelou|atropela|goleou|goleia"
)

# NOTA: nenhum destes padrões usa re.IGNORECASE global — isso
# anularia a exigência de maiúscula em _TIME e deixaria qualquer
# palavra minúscula (ex.: apelido de time usado em minúsculo no
# corpo da notícia) ser capturada como nome de time. A
# insensibilidade a caixa fica só nos grupos (?i:...) abaixo,
# em cima de verbos/conectores — nunca em _TIME.

_PADRAO_VENCEDOR = re.compile(
    _TIME
    + r"\s+(?i:"
    + _VERBOS_VITORIA
    + r")\s+(?i:o|a)?\s*"
    + _TIME
    + r"\s+(?i:por)\s+(\d+)\s*(?i:[ax])\s*(\d+)"
)

_PADRAO_PERDEDOR = re.compile(
    _TIME
    + r"\s+(?i:perde[u]?\s+para)\s+(?i:o|a)?\s*"
    + _TIME
    + r"\s+(?i:por)\s+(\d+)\s*(?i:[ax])\s*(\d+)"
)

_PADRAO_EMPATE_SEM_GOLS = re.compile(
    _TIME
    + r"\s+(?i:e)\s+"
    + _TIME
    + r"\s+(?i:empata(?:ram|m)?\s+sem\s+gols)"
)

_PADRAO_EMPATE_PLACAR = re.compile(
    _TIME
    + r"\s+(?i:e)\s+"
    + _TIME
    + r"\s+(?i:empata(?:ram|m)?\s+(?:em|por))\s+(\d+)\s*(?i:[ax])\s*(\d+)"
)


def _limpar_nome_time(nome):

    return _ARTIGO.sub(
        "",
        nome.strip(),
    ).strip()


def extrair_placar(texto):
    """
    Tenta extrair time_a, time_b e o placar de um texto em
    português (título ou corpo da matéria). Retorna um dict
    ou None se não conseguir reconhecer o padrão.
    """

    if not texto:
        return None

    m = _PADRAO_VENCEDOR.search(texto)

    if m:
        return {
            "time_a": _limpar_nome_time(m.group(1)),
            "time_b": _limpar_nome_time(m.group(2)),
            "placar_a": m.group(3),
            "placar_b": m.group(4),
        }

    m = _PADRAO_PERDEDOR.search(texto)

    if m:
        # Quem "perde para" fica com o placar menor (grupo 4).
        return {
            "time_a": _limpar_nome_time(m.group(2)),
            "time_b": _limpar_nome_time(m.group(1)),
            "placar_a": m.group(3),
            "placar_b": m.group(4),
        }

    m = _PADRAO_EMPATE_SEM_GOLS.search(texto)

    if m:
        return {
            "time_a": _limpar_nome_time(m.group(1)),
            "time_b": _limpar_nome_time(m.group(2)),
            "placar_a": "0",
            "placar_b": "0",
        }

    m = _PADRAO_EMPATE_PLACAR.search(texto)

    if m:
        return {
            "time_a": _limpar_nome_time(m.group(1)),
            "time_b": _limpar_nome_time(m.group(2)),
            "placar_a": m.group(3),
            "placar_b": m.group(4),
        }

    return None


# ============================================================
# COMPETIÇÃO (melhor esforço)
# ============================================================

COMPETICOES_CONHECIDAS = [
    "Brasileirão", "Campeonato Brasileiro", "Copa do Brasil",
    "Libertadores", "Sul-Americana", "Champions League",
    "Copa do Mundo", "Mundial de Clubes", "Copa Verde",
    "Campeonato Paulista", "Campeonato Carioca",
    "Campeonato Mineiro", "Campeonato Gaúcho",
]


def detectar_competicao(texto):

    if not texto:
        return ""

    for competicao in COMPETICOES_CONHECIDAS:

        if normalizar_texto(competicao) in normalizar_texto(texto):
            return competicao

    return ""


def tentar_resultado(candidatas, historico, rotulo):
    """
    Tenta, em ordem de relevância, extrair um placar válido
    e ainda não usado de uma lista de candidatas. Retorna
    (noticia, resultado) ou (None, None).
    """

    if not candidatas:
        return None, None

    ranking = ranquear_noticias(
        candidatas,
        limite=30,
    )

    print(
        f"\n🔎 Tentando entre {len(ranking)} candidatas ({rotulo})..."
    )

    for noticia in ranking:

        print(
            f"   • {noticia['titulo']}"
        )

        texto_materia = extrair_texto_materia(
            noticia.get("link", "")
        )

        candidato = extrair_placar(
            texto_materia
        ) or extrair_placar(
            noticia["titulo"]
        )

        if not candidato:

            print(
                "     ⚠️ Não foi possível identificar o placar."
            )

            continue

        if ja_usada(candidato, historico):

            print(
                "     ⚠️ Resultado já usado recentemente."
            )

            continue

        candidato["competicao"] = detectar_competicao(
            texto_materia or noticia["titulo"]
        )

        candidato["link"] = noticia.get("link", "")
        candidato["fonte"] = noticia.get("fonte", "")

        return noticia, candidato

    return None, None


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print("🎬 NEWS-YOUTUBE — BUSCA DE RESULTADO (SHORTS)")
    print("=" * 75)

    noticias = coletar_noticias()

    print(
        f"\n📥 Total coletado: {len(noticias)}"
    )

    noticias = filtrar_ultimas_24h(noticias)
    noticias = filtrar_conteudo_editorial(noticias)
    noticias = filtrar_apenas_futebol(noticias)
    noticias = remover_duplicadas(noticias)

    base = [
        n for n in noticias
        if detectar_tipo(n["titulo"]) in {
            "vitoria", "derrota", "empate",
        }
        and not eh_categoria_excluida(n["titulo"])
    ]

    candidatas_grandes = [
        n for n in base
        if tem_clube_importante(n["titulo"])
    ]

    candidatas_serie_b = [
        n for n in base
        if eh_serie_b(n["titulo"])
        and not tem_clube_importante(n["titulo"])
    ]

    print(
        f"🏆 Candidatas de times grandes: {len(candidatas_grandes)}"
    )

    print(
        f"🥈 Candidatas de Série B: {len(candidatas_serie_b)}"
    )

    if not candidatas_grandes and not candidatas_serie_b:

        print(
            "⚠️ Nenhuma notícia de resultado nas últimas 24h."
        )

        return 2

    historico = limpar_expirados(
        carregar_historico()
    )

    print(
        f"🕘 Resultados já usados (histórico): {len(historico)}"
    )

    # ------------------------------------------------------------
    # Primeiro tenta times grandes; se não achar nenhum com
    # placar identificável (ou já usados), cai pra Série B.
    # ------------------------------------------------------------

    escolhida, resultado = tentar_resultado(
        candidatas_grandes,
        historico,
        "times grandes",
    )

    if not resultado:

        escolhida, resultado = tentar_resultado(
            candidatas_serie_b,
            historico,
            "Série B",
        )

    if not resultado:

        print()
        print(
            "⚠️ Nenhum resultado com placar identificável "
            "nesta janela."
        )

        return 2

    print()
    print("=" * 75)
    print("🏆 RESULTADO ESCOLHIDO")
    print("=" * 75)

    print(
        f"{resultado['time_a']} {resultado['placar_a']} x "
        f"{resultado['placar_b']} {resultado['time_b']}"
    )

    indice = proximo_indice_short()

    caminho = montar_roteiro_short(
        resultado,
        indice,
    )

    historico = registrar_uso(
        resultado,
        historico,
    )

    salvar_historico(historico)

    print()
    print("=" * 75)
    print("✅ BUSCA DE RESULTADO FINALIZADA")
    print("=" * 75)

    print(
        f"📄 Roteiro: {caminho}"
    )

    return 0


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
