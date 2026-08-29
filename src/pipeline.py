#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NEWS-YOUTUBE — PIPELINE COMPLETO

Fluxo:

1. Busca/atualiza as notícias
2. Gera os roteiros
3. Gera o próximo vídeo pendente
4. Mantém o controle da fila
5. Uma execução gera somente 1 vídeo

Estrutura esperada:

src/
    pipeline.py
    gerar_roteiro.py
    gerar_video.py
    [script de busca de notícias]

dados/
    noticias/
    roteiros/
    audios/
    imagens/
    videos/
    status/
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
DADOS_DIR = BASE_DIR / "dados"

ROTEIROS_DIR = DADOS_DIR / "roteiros"
AUDIOS_DIR = DADOS_DIR / "audios"
IMAGENS_DIR = DADOS_DIR / "imagens"
VIDEOS_DIR = DADOS_DIR / "videos"
STATUS_DIR = DADOS_DIR / "status"

STATUS_FILE = STATUS_DIR / "fila.json"


# ============================================================================
# CORES
# ============================================================================

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
WHITE = "\033[97m"
RESET = "\033[0m"


# ============================================================================
# UTILIDADES
# ============================================================================

def linha(char="=", tamanho=75):
    print(char * tamanho)


def titulo(texto):
    print()
    linha()
    print(texto)
    linha()


def executar(script, descricao):
    """
    Executa outro script Python usando o mesmo ambiente virtual.
    """

    caminho = SRC_DIR / script

    if not caminho.exists():
        print(
            f"{YELLOW}⚠️ Script não encontrado: {caminho}{RESET}"
        )
        return False

    titulo(descricao)

    print(f"▶️ Executando: {script}")
    print()

    resultado = subprocess.run(
        [sys.executable, str(caminho)],
        cwd=str(BASE_DIR)
    )

    if resultado.returncode != 0:
        print()
        print(
            f"{RED}❌ O script {script} terminou com erro.{RESET}"
        )
        return False

    print()
    print(
        f"{GREEN}✅ {script} concluído.{RESET}"
    )

    return True


# ============================================================================
# VERIFICAÇÃO DOS DIRETÓRIOS
# ============================================================================

def preparar_diretorios():

    diretorios = [
        DADOS_DIR,
        ROTEIROS_DIR,
        AUDIOS_DIR,
        IMAGENS_DIR,
        VIDEOS_DIR,
        STATUS_DIR,
    ]

    for diretorio in diretorios:
        diretorio.mkdir(parents=True, exist_ok=True)


# ============================================================================
# LEITURA DA FILA
# ============================================================================

def carregar_fila():

    if not STATUS_FILE.exists():
        return {}

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)

        if isinstance(dados, dict):
            return dados

        return {}

    except Exception as e:
        print(
            f"{YELLOW}⚠️ Não foi possível ler a fila: {e}{RESET}"
        )
        return {}


# ============================================================================
# STATUS
# ============================================================================

def mostrar_status():

    fila = carregar_fila()

    titulo("📊 STATUS DA FILA")

    if not fila:
        print("⚠️ Nenhuma notícia cadastrada na fila.")
        return

    concluidos = 0
    pendentes = 0
    erros = 0

    for noticia_id in sorted(
        fila.keys(),
        key=lambda x: int(
            "".join(c for c in str(x) if c.isdigit()) or 0
        )
    ):

        item = fila[noticia_id]

        if isinstance(item, str):
            status = item
            erro = ""

        else:
            status = item.get("status", "pendente")
            erro = item.get("erro", "")

        if status == "concluido":

            print(
                f"{GREEN}✅ {noticia_id}: concluido{RESET}"
            )
            concluidos += 1

        elif status == "erro":

            print(
                f"{RED}❌ {noticia_id}: erro{RESET}"
            )

            if erro:
                print(
                    f"   └─ {erro}"
                )

            erros += 1

        else:

            print(
                f"{YELLOW}⏳ {noticia_id}: pendente{RESET}"
            )
            pendentes += 1

    total = len(fila)

    print()
    print(f"Total: {total}")
    print(f"{GREEN}Concluídos: {concluidos}{RESET}")
    print(f"{YELLOW}Pendentes: {pendentes}{RESET}")
    print(f"{RED}Erros: {erros}{RESET}")


# ============================================================================
# VERIFICA SE EXISTEM ROTEIROS
# ============================================================================

def contar_roteiros():

    if not ROTEIROS_DIR.exists():
        return 0

    return len(
        list(ROTEIROS_DIR.glob("noticia_*.json"))
    )


# ============================================================================
# VERIFICA SE EXISTEM NOTÍCIAS
# ============================================================================

def contar_noticias():

    arquivo_historico = (
        DADOS_DIR / "historico_noticias.json"
    )

    if not arquivo_historico.exists():
        return 0

    try:

        with open(
            arquivo_historico,
            "r",
            encoding="utf-8"
        ) as f:

            dados = json.load(f)

        if isinstance(dados, list):
            return len(dados)

    except Exception:
        pass

    return 0


# ============================================================================
# VERIFICA SE EXISTE ALGUM VÍDEO
# ============================================================================

def contar_videos():

    if not VIDEOS_DIR.exists():
        return 0

    return len(
        list(VIDEOS_DIR.glob("noticia_*.mp4"))
    )


# ============================================================================
# EXECUTA O PIPELINE
# ============================================================================

def main():

    inicio = datetime.now()

    titulo("🎬 NEWS-YOUTUBE — PIPELINE COMPLETO")

    print(f"📂 Projeto: {BASE_DIR}")
    print()

    preparar_diretorios()

    # ------------------------------------------------------------------------
    # ETAPA 1 — BUSCAR E SELECIONAR A NOTÍCIA
    # ------------------------------------------------------------------------

    titulo("📰 ETAPA 1 — BUSCANDO E SELECIONANDO A NOTÍCIA")

    print(
        f"🕘 Notícias já usadas (histórico): {contar_noticias()}"
    )

    print(
        f"📝 Roteiros existentes: {contar_roteiros()}"
    )

    print(
        f"🎬 Vídeos existentes: {contar_videos()}"
    )

    print()

    caminho_busca = SRC_DIR / "buscar_noticia.py"

    if not caminho_busca.exists():

        print(
            f"{RED}❌ src/buscar_noticia.py não encontrado.{RESET}"
        )

        return 1

    resultado_busca = subprocess.run(
        [sys.executable, str(caminho_busca)],
        cwd=str(BASE_DIR),
    )

    if resultado_busca.returncode == 2:

        print()
        print(
            f"{YELLOW}ℹ️ Nenhuma notícia nova relevante nas "
            f"últimas 12 horas. Nada a gerar nesta execução.{RESET}"
        )

        return 0

    if resultado_busca.returncode != 0:

        print()
        print(
            f"{RED}❌ Pipeline interrompido na busca/seleção da notícia.{RESET}"
        )

        return 1

    # ------------------------------------------------------------------------
    # ETAPA 2 — GERAR O VÍDEO
    # ------------------------------------------------------------------------

    titulo("📊 FILA ANTES DA GERAÇÃO DO VÍDEO")

    mostrar_status()

    titulo(
        "🎬 ETAPA 2 — GERANDO O VÍDEO"
    )

    print(
        "ℹ️ Apenas UMA notícia será processada nesta execução."
    )

    print(
        "ℹ️ A fila controla o que já foi concluído."
    )

    print(
        "ℹ️ Execute novamente o pipeline para gerar o próximo."
    )

    print()

    gerar_video = SRC_DIR / "gerar_video.py"

    if not gerar_video.exists():

        print(
            f"{RED}❌ src/gerar_video.py não encontrado.{RESET}"
        )

        return 1

    sucesso = executar(
        "gerar_video.py",
        "🎬 GERADOR DE VÍDEO"
    )

    if not sucesso:

        print()
        print(
            f"{YELLOW}⚠️ A execução do vídeo terminou com erro.{RESET}"
        )

    # ------------------------------------------------------------------------
    # STATUS FINAL
    # ------------------------------------------------------------------------

    titulo("📊 STATUS FINAL")

    mostrar_status()

    # ------------------------------------------------------------------------
    # RESUMO
    # ------------------------------------------------------------------------

    fim = datetime.now()
    duracao = fim - inicio

    titulo("🏁 PIPELINE FINALIZADO")

    print(
        f"⏱️ Tempo total: {duracao}"
    )

    print(
        f"🎬 Vídeos existentes: {contar_videos()}"
    )

    print()

    print(
        f"{GREEN}Próximo passo:{RESET}"
    )

    print(
        "Execute novamente:"
    )

    print()

    print(
        f"{CYAN}python src/pipeline.py{RESET}"
    )

    print()

    print(
        "O sistema vai buscar/atualizar as notícias, "
        "manter os roteiros e processar somente o próximo "
        "vídeo da fila."
    )

    return 0


# ============================================================================
# EXECUÇÃO
# ============================================================================

if __name__ == "__main__":

    try:

        sys.exit(main())

    except KeyboardInterrupt:

        print()
        print(
            f"{YELLOW}⚠️ Execução interrompida pelo usuário.{RESET}"
        )

        sys.exit(130)

    except Exception as e:

        print()
        print(
            f"{RED}❌ ERRO INESPERADO{RESET}"
        )

        print(
            f"{RED}{e}{RESET}"
        )

        sys.exit(1)
