#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NEWS-YOUTUBE — PIPELINE DE SHORTS (RESULTADOS)

Pipeline SEPARADA da principal (pipeline.py). Pode rodar no
mesmo cron horário, em outra linha — não compartilha roteiros,
fila, histórico ou vídeos com o pipeline principal.

Fluxo:
1. Busca um resultado de jogo ainda não usado (buscar_resultado.py).
2. Gera o Short vertical (gerar_short.py).
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


def linha(char="=", tamanho=75):
    print(char * tamanho)


def titulo(texto):
    print()
    linha()
    print(texto)
    linha()


def main():

    inicio = datetime.now()

    titulo("🎬 NEWS-YOUTUBE — PIPELINE DE SHORTS")

    print(f"📂 Projeto: {BASE_DIR}")

    # --------------------------------------------------------------------
    # ETAPA 1 — BUSCAR RESULTADO
    # --------------------------------------------------------------------

    titulo("🏆 ETAPA 1 — BUSCANDO RESULTADO DO DIA")

    caminho_busca = SRC_DIR / "buscar_resultado.py"

    if not caminho_busca.exists():

        print(f"{RED}❌ src/buscar_resultado.py não encontrado.{RESET}")
        return 1

    resultado_busca = subprocess.run(
        [sys.executable, str(caminho_busca)],
        cwd=str(BASE_DIR),
    )

    if resultado_busca.returncode == 2:

        print()
        print(
            f"{YELLOW}ℹ️ Nenhum resultado novo identificável "
            f"nesta janela. Tentando fallback com a notícia "
            f"do vídeo longo...{RESET}"
        )

        caminho_video = SRC_DIR / "gerar_short.py"

        subprocess.run(
            [
                sys.executable,
                str(caminho_video),
                "--fallback-noticia",
            ],
            cwd=str(BASE_DIR),
        )

        return 0

    if resultado_busca.returncode != 0:

        print()
        print(
            f"{RED}❌ Pipeline de shorts interrompido na "
            f"busca do resultado.{RESET}"
        )

        return 1

    # --------------------------------------------------------------------
    # ETAPA 2 — GERAR O SHORT
    # --------------------------------------------------------------------

    titulo("🎬 ETAPA 2 — GERANDO O SHORT")

    caminho_video = SRC_DIR / "gerar_short.py"

    if not caminho_video.exists():

        print(f"{RED}❌ src/gerar_short.py não encontrado.{RESET}")
        return 1

    resultado_video = subprocess.run(
        [sys.executable, str(caminho_video)],
        cwd=str(BASE_DIR),
    )

    if resultado_video.returncode != 0:

        print()
        print(
            f"{YELLOW}⚠️ A geração do short terminou com erro.{RESET}"
        )

    fim = datetime.now()

    titulo("🏁 PIPELINE DE SHORTS FINALIZADO")

    print(f"⏱️ Tempo total: {fim - inicio}")

    print()

    print(f"{CYAN}python src/pipeline_shorts.py{RESET}")

    print()

    return 0


if __name__ == "__main__":

    try:
        sys.exit(main())

    except KeyboardInterrupt:

        print()
        print(f"{YELLOW}⚠️ Execução interrompida pelo usuário.{RESET}")
        sys.exit(130)
