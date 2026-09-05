#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NEWS-YOUTUBE — PIPELINE DO RESUMO DO DIA

Pipeline SEPARADA da principal (pipeline.py) e da de Shorts
(pipeline_shorts.py). Só chama gerar_resumo_dia.py, que reaproveita
áudio/imagem já gerados pelo pipeline principal.
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

    titulo("🎬 NEWS-YOUTUBE — PIPELINE DO RESUMO DO DIA")

    print(f"📂 Projeto: {BASE_DIR}")

    caminho_gerador = SRC_DIR / "gerar_resumo_dia.py"

    if not caminho_gerador.exists():

        print(f"{RED}❌ src/gerar_resumo_dia.py não encontrado.{RESET}")
        return 1

    resultado = subprocess.run(
        [sys.executable, str(caminho_gerador)],
        cwd=str(BASE_DIR),
    )

    if resultado.returncode == 2:

        print()
        print(
            f"{YELLOW}ℹ️ Notícias novas insuficientes pra montar "
            f"um resumo nesta execução. Nada a gerar.{RESET}"
        )

        return 0

    if resultado.returncode != 0:

        print()
        print(
            f"{RED}❌ A geração do resumo do dia terminou com erro.{RESET}"
        )

        return 1

    fim = datetime.now()

    titulo("🏁 PIPELINE DO RESUMO DO DIA FINALIZADO")

    print(f"⏱️ Tempo total: {fim - inicio}")

    return 0


if __name__ == "__main__":

    try:
        sys.exit(main())

    except KeyboardInterrupt:

        print()
        print(f"{YELLOW}⚠️ Execução interrompida pelo usuário.{RESET}")
        sys.exit(130)
