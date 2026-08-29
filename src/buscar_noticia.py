#!/usr/bin/env python3

"""
NEWS-YOUTUBE — BUSCA E SELEÇÃO DA NOTÍCIA

Executado a cada rodada do pipeline (ex.: de hora em hora).

1. Coleta notícias dos feeds RSS.
2. Filtra pelas últimas 12 horas.
3. Aplica o filtro editorial, garante que é sobre futebol
   (fontes genéricas de esporte) e remove duplicadas.
4. Rankeia por relevância (pontuação + assuntos repetidos).
5. Remove as que já estão no histórico (não repetir notícia).
6. A IA (Ollama) escolhe a mais relevante entre as candidatas.
   Se a IA falhar, usa a #1 do ranking determinístico.
7. Gera o roteiro dessa notícia e registra no histórico.

Códigos de saída:
    0 = roteiro gerado com sucesso
    2 = nenhuma notícia nova relevante nesta janela (não é erro)
    1 = falha real
"""

import sys

from coletar_noticias import coletar_noticias
from filtrar_noticias import (
    filtrar_ultimas_12h,
    filtrar_conteudo_editorial,
    filtrar_apenas_futebol,
    remover_duplicadas,
)
from ranking_noticias import ranquear_noticias
from historico import (
    carregar_historico,
    salvar_historico,
    limpar_expirados,
    ja_usada,
    registrar_uso,
)
from gerar_roteiro import (
    gerar_roteiro_para_noticia,
    proximo_indice_roteiro,
)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print("📰 NEWS-YOUTUBE — BUSCA E SELEÇÃO DA NOTÍCIA")
    print("=" * 75)

    noticias = coletar_noticias()

    print(
        f"\n📥 Total coletado: {len(noticias)}"
    )

    noticias = filtrar_ultimas_12h(noticias)
    noticias = filtrar_conteudo_editorial(noticias)
    noticias = filtrar_apenas_futebol(noticias)
    noticias = remover_duplicadas(noticias)

    ranking = ranquear_noticias(
        noticias,
        limite=30,
    )

    if not ranking:

        print()
        print(
            "⚠️ Nenhuma notícia relevante "
            "nas últimas 12 horas."
        )

        return 2

    historico = limpar_expirados(
        carregar_historico()
    )

    candidatas = [
        noticia
        for noticia in ranking
        if not ja_usada(noticia, historico)
    ]

    print()
    print(
        f"🕘 Notícias já usadas (histórico): "
        f"{len(historico)}"
    )

    print(
        f"🎯 Candidatas novas: {len(candidatas)}"
    )

    if not candidatas:

        print()
        print(
            "⚠️ Nenhuma notícia nova relevante "
            "nas últimas 12 horas."
        )

        print(
            "ℹ️ Todas as candidatas já foram "
            "usadas recentemente."
        )

        return 2

    # A #1 do ranking já é a mais relevante entre as
    # candidatas novas (pontuação + assuntos repetidos
    # removidos por ranking_noticias.ranquear_noticias).
    escolhida = candidatas[0]

    print()
    print("=" * 75)
    print("📰 NOTÍCIA ESCOLHIDA")
    print("=" * 75)

    print(
        f"📰 {escolhida.get('titulo', '')}"
    )

    print(
        f"🗞️ {escolhida.get('fonte', '')}"
    )

    indice = proximo_indice_roteiro()

    caminho = gerar_roteiro_para_noticia(
        escolhida,
        indice,
    )

    historico = registrar_uso(
        escolhida,
        historico,
    )

    salvar_historico(historico)

    print()
    print("=" * 75)
    print("✅ BUSCA E SELEÇÃO FINALIZADAS")
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
