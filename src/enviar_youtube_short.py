#!/usr/bin/env python3

"""
Publica no YouTube o próximo Short concluído que ainda não
foi enviado. Mesmo padrão de enviar_youtube_video.py, mas
pra pipeline de Shorts — totalmente separado.
"""

import json
import sys
from pathlib import Path

from youtube_upload import autenticar, enviar_video


BASE_DIR = Path(__file__).resolve().parent.parent

SHORTS_DIR = BASE_DIR / "dados" / "shorts"

ROTEIROS_DIR = SHORTS_DIR / "roteiros"
VIDEOS_DIR = SHORTS_DIR / "videos"

STATUS_GERACAO_FILE = SHORTS_DIR / "status" / "fila.json"
STATUS_YOUTUBE_FILE = SHORTS_DIR / "status" / "youtube.json"

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

    status_geracao = carregar_json(STATUS_GERACAO_FILE)
    status_youtube = carregar_json(STATUS_YOUTUBE_FILE)

    arquivos = sorted(
        ROTEIROS_DIR.glob("resultado_*.json"),
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
    print("📤 NEWS-YOUTUBE — PUBLICAR SHORT NO YOUTUBE")
    print("=" * 75)

    chave, arquivo_roteiro, arquivo_video = encontrar_proximo()

    if not chave:

        print("⚠️ Nenhum short novo pra publicar.")
        return 2

    dados = carregar_json(arquivo_roteiro)
    roteiro = dados.get("roteiro", {})

    titulo = roteiro.get(
        "titulo_youtube",
        roteiro.get("titulo", "Resultado do dia"),
    )

    descricao = roteiro.get("descricao_youtube", "")
    tags = roteiro.get("tags_youtube", [])

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
