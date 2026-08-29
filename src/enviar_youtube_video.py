#!/usr/bin/env python3

"""
Publica no YouTube o próximo vídeo concluído do pipeline
principal que ainda não foi enviado.

Lê status/metadados de dados/roteiros/ e dados/status/fila.json
(SÓ LEITURA — nunca escreve nesses arquivos). O controle de
quem já foi publicado fica em dados/status/youtube.json,
separado, pra não mexer em nada do pipeline de geração.
"""

import json
import sys
from pathlib import Path

from youtube_upload import autenticar, enviar_video


BASE_DIR = Path(__file__).resolve().parent.parent

ROTEIROS_DIR = BASE_DIR / "dados" / "roteiros"
VIDEOS_DIR = BASE_DIR / "dados" / "videos"

STATUS_GERACAO_FILE = BASE_DIR / "dados" / "status" / "fila.json"
STATUS_YOUTUBE_FILE = BASE_DIR / "dados" / "status" / "youtube.json"

PRIVACY_STATUS = "public"


def carregar_json(path):

    path = Path(path)

    if not path.exists():
        return {}

    try:

        with path.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)

    except Exception:
        return {}


def salvar_json(path, dados):

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)


def numero(path):

    try:
        return int(Path(path).stem.split("_")[-1])

    except Exception:
        return 999999


def encontrar_proximo():
    """
    Primeiro vídeo (em ordem) que está concluído na geração
    e ainda não tem registro de publicação.
    """

    status_geracao = carregar_json(STATUS_GERACAO_FILE)
    status_youtube = carregar_json(STATUS_YOUTUBE_FILE)

    arquivos = sorted(
        ROTEIROS_DIR.glob("noticia_*.json"),
        key=numero,
    )

    for arquivo in arquivos:

        chave = arquivo.stem

        registro_geracao = status_geracao.get(chave, {})

        estado = (
            registro_geracao.get("status", "pendente")
            if isinstance(registro_geracao, dict)
            else registro_geracao
        )

        if estado != "concluido":
            continue

        if chave in status_youtube:
            continue

        video = VIDEOS_DIR / f"{chave}.mp4"

        if not video.exists():
            continue

        return chave, arquivo, video

    return None, None, None


def main():

    print()
    print("=" * 75)
    print("📤 NEWS-YOUTUBE — PUBLICAR VÍDEO NO YOUTUBE")
    print("=" * 75)

    chave, arquivo_roteiro, arquivo_video = encontrar_proximo()

    if not chave:

        print("⚠️ Nenhum vídeo novo pra publicar.")
        return 2

    dados = carregar_json(arquivo_roteiro)
    roteiro = dados.get("roteiro", {})

    titulo = roteiro.get("titulo", "Notícia do futebol")
    descricao = roteiro.get("descricao", "")
    tags = roteiro.get("tags", [])

    print(f"📰 {chave}")
    print(f"🎬 {arquivo_video}")
    print(f"📝 Título: {titulo}")

    try:

        youtube = autenticar()

        video_id = enviar_video(
            youtube,
            arquivo_video,
            titulo,
            descricao,
            tags,
            privacy_status=PRIVACY_STATUS,
        )

    except Exception as erro:

        print(f"❌ Falha ao publicar: {erro}")
        return 1

    url = f"https://youtu.be/{video_id}"

    print()
    print(f"✅ Publicado: {url}")

    status_youtube = carregar_json(STATUS_YOUTUBE_FILE)

    status_youtube[chave] = {
        "status": "publicado",
        "video_id": video_id,
        "url": url,
    }

    salvar_json(STATUS_YOUTUBE_FILE, status_youtube)

    return 0


if __name__ == "__main__":
    sys.exit(main())
