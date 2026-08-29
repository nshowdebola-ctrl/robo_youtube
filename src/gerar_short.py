#!/usr/bin/env python3

"""
NEWS-YOUTUBE — GERADOR DE SHORT (RESULTADO)

Pipeline SEPARADA da principal (gerar_video.py). Vídeo vertical
e curto, com o placar de um jogo. Fila, roteiros e vídeos ficam
em dados/shorts/ — não compartilha nada com o pipeline principal.

Reaproveita (só importa, não modifica) funções utilitárias já
prontas e testadas de gerar_video.py: geração de áudio (TTS),
busca de imagem no Bing já filtrada por licença de reuso, e
pontuação de candidatas.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gerar_video import (
    FONT_BOLD,
    FONT_NORMAL,
    FPS,
    gerar_audio,
    obter_duracao_audio,
    consultas_relevantes,
    buscar_bing_images,
    pontuar_candidata,
    baixar_imagem,
)


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

SHORTS_DIR = BASE_DIR / "dados" / "shorts"

ROTEIROS_DIR = SHORTS_DIR / "roteiros"
AUDIOS_DIR = SHORTS_DIR / "audios"
IMAGENS_DIR = SHORTS_DIR / "imagens"
VIDEOS_DIR = SHORTS_DIR / "videos"
STATUS_DIR = SHORTS_DIR / "status"

STATUS_FILE = STATUS_DIR / "fila.json"

W = 1080
H = 1920

MARGEM_SEGURA_X = 60
MARGEM_SEGURA_Y = 55

CANAL = "Noticias Show de Bola"


def preparar_diretorios():

    for diretorio in (
        ROTEIROS_DIR,
        AUDIOS_DIR,
        IMAGENS_DIR,
        VIDEOS_DIR,
        STATUS_DIR,
    ):
        diretorio.mkdir(parents=True, exist_ok=True)


# ============================================================================
# PRÓXIMO ÍNDICE
# ============================================================================

def proximo_indice_short():

    ROTEIROS_DIR.mkdir(parents=True, exist_ok=True)

    maior = 0

    for arquivo in ROTEIROS_DIR.glob("resultado_*.json"):

        try:
            numero = int(arquivo.stem.split("_")[-1])

        except ValueError:
            continue

        maior = max(maior, numero)

    return maior + 1


# ============================================================================
# QUEBRA DE LINHA POR LARGURA (mesma técnica do vídeo principal)
# ============================================================================

def quebrar_por_largura(draw, texto, fonte, largura_maxima):

    palavras = texto.split()

    linhas = []
    linha_atual = ""

    for palavra in palavras:

        candidata = f"{linha_atual} {palavra}".strip()

        largura = draw.textlength(candidata, font=fonte)

        if largura <= largura_maxima or not linha_atual:
            linha_atual = candidata

        else:
            linhas.append(linha_atual)
            linha_atual = palavra

    if linha_atual:
        linhas.append(linha_atual)

    return linhas


# ============================================================================
# MONTAR ROTEIRO (texto determinístico, sem IA — é só o placar)
# ============================================================================

def montar_roteiro_short(resultado, indice):

    time_a = resultado["time_a"]
    time_b = resultado["time_b"]
    placar_a = int(resultado["placar_a"])
    placar_b = int(resultado["placar_b"])
    competicao = resultado.get("competicao", "")

    abertura = "Mais um resultado do futebol brasileiro."

    corpo = (
        f"{time_a} {placar_a} x {placar_b} {time_b}"
        + (f", pela {competicao}" if competicao else "")
        + "."
    )

    if placar_a > placar_b:

        desenvolvimento = (
            f"O {time_a} leva a melhor sobre o {time_b} "
            f"nessa partida."
        )

    elif placar_b > placar_a:

        desenvolvimento = (
            f"O {time_b} leva a melhor sobre o {time_a} "
            f"nessa partida."
        )

    else:

        desenvolvimento = (
            f"{time_a} e {time_b} não saíram do empate "
            f"nessa partida."
        )

    contexto = (
        "O resultado pode pesar na tabela e já repercute "
        "entre os torcedores das duas equipes."
    )

    fechamento = (
        "Inscreva-se no canal para acompanhar todos os "
        "resultados do dia."
    )

    texto = (
        f"{abertura} {corpo} {desenvolvimento} "
        f"{contexto} {fechamento}"
    )

    titulo_tela = (
        f"{time_a} {placar_a} x {placar_b} {time_b}"
    )

    # --------------------------------------------------------
    # Metadados pro YouTube (upload automático).
    # --------------------------------------------------------

    titulo_youtube = f"{titulo_tela} | Resultado #Shorts"

    descricao_youtube = (
        f"{corpo} "
        f"Confira o resultado no Noticias Show de Bola. "
        f"Inscreva-se para acompanhar todos os resultados do dia.\n\n"
        f"#Shorts #futebol #resultados"
    )

    tags_youtube = [
        "futebol", "resultados", "shorts", "futebol brasileiro",
        "Noticias Show de Bola", time_a, time_b,
    ]

    if competicao:
        tags_youtube.append(competicao)

    dados = {

        "resultado": resultado,

        "roteiro": {

            "titulo": titulo_tela,
            "roteiro": texto,
            "competicao": competicao,
            "canal": CANAL,

            "titulo_youtube": titulo_youtube,
            "descricao_youtube": descricao_youtube,
            "tags_youtube": tags_youtube,

        },
    }

    ROTEIROS_DIR.mkdir(parents=True, exist_ok=True)

    destino = ROTEIROS_DIR / f"resultado_{indice}.json"

    with open(destino, "w", encoding="utf-8") as arquivo:

        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    print(f"✅ Roteiro do short salvo: {destino}")

    return destino


# ============================================================================
# JSON
# ============================================================================

def carregar_json(path):

    path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo)

    except FileNotFoundError:
        return {}

    except Exception as erro:
        print(f"❌ Erro lendo {path}: {erro}")
        return {}


def salvar_json(path, data):

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporario = path.with_suffix(".tmp")

    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(data, arquivo, ensure_ascii=False, indent=2)

    temporario.replace(path)


# ============================================================================
# STATUS (fila própria, separada da fila do vídeo principal)
# ============================================================================

def numero_resultado(path):

    try:
        return int(Path(path).stem.split("_")[-1])

    except Exception:
        return 999999


def carregar_status():

    data = carregar_json(STATUS_FILE)

    if not isinstance(data, dict):
        return {}

    return data


def atualizar_status(indice, estado, erro=None):

    status = carregar_status()

    chave = f"resultado_{int(indice)}"

    status[chave] = {"status": estado}

    if erro:
        status[chave]["erro"] = str(erro)

    salvar_json(STATUS_FILE, status)


def mostrar_status():

    arquivos = sorted(
        ROTEIROS_DIR.glob("resultado_*.json"),
        key=numero_resultado,
    )

    status = carregar_status()

    print()
    print("=" * 75)
    print("📊 STATUS DA FILA DE SHORTS")
    print("=" * 75)

    concluidos = pendentes = erros = 0

    for arquivo in arquivos:

        chave = arquivo.stem
        registro = status.get(chave, {})

        estado = (
            registro.get("status", "pendente")
            if isinstance(registro, dict)
            else registro
        )

        if estado == "concluido":
            print(f"✅ {chave}: concluido")
            concluidos += 1

        elif estado == "erro":
            print(f"❌ {chave}: erro")
            erros += 1

        else:
            print(f"⏳ {chave}: pendente")
            pendentes += 1

    print()
    print(f"Total: {len(arquivos)}")
    print(f"Concluídos: {concluidos}")
    print(f"Pendentes: {pendentes}")
    print(f"Erros: {erros}")
    print("=" * 75)

    return arquivos, status


def encontrar_proximo_pendente(repetir_erros=False):

    arquivos = sorted(
        ROTEIROS_DIR.glob("resultado_*.json"),
        key=numero_resultado,
    )

    status = carregar_status()

    for arquivo in arquivos:

        registro = status.get(arquivo.stem, {})

        estado = (
            registro.get("status", "pendente")
            if isinstance(registro, dict)
            else registro
        )

        if estado == "pendente":
            return arquivo

    if repetir_erros:

        for arquivo in arquivos:

            registro = status.get(arquivo.stem, {})

            estado = (
                registro.get("status", "pendente")
                if isinstance(registro, dict)
                else registro
            )

            if estado == "erro":
                return arquivo

    return None


# ============================================================================
# IMAGEM DO JOGO
# ============================================================================

def procurar_imagem_short(resultado, indice):

    titulo_busca = (
        f"{resultado['time_a']} x {resultado['time_b']} futebol"
    )

    destino = IMAGENS_DIR / f"resultado_{indice}.jpg"
    destino.unlink(missing_ok=True)

    print()
    print("🖼️ Buscando imagem do jogo no Bing...")

    candidatos = []

    for consulta in consultas_relevantes(titulo_busca):

        print(f"   🔎 {consulta}")

        for item in buscar_bing_images(consulta):

            item["pontuacao"] = pontuar_candidata(
                item,
                titulo_busca,
            )

            candidatos.append(item)

    candidatos.sort(
        key=lambda item: item["pontuacao"],
        reverse=True,
    )

    for item in candidatos[:20]:

        if item["pontuacao"] < 20:
            continue

        if baixar_imagem(item["url"], destino):

            print(f"   ✅ Imagem aceita: {item['url']}")

            return destino

    print(
        "   ⚠️ Nenhuma foto relevante encontrada — "
        "usando card só com o placar."
    )

    return None


# ============================================================================
# FRAME (vertical, estilo card de placar)
# ============================================================================

def preparar_frame_short(arquivo_imagem, resultado, indice):

    if arquivo_imagem and Path(arquivo_imagem).exists():

        imagem = Image.open(arquivo_imagem).convert("RGB")

        largura, altura = imagem.size
        proporcao_desejada = W / H
        proporcao_atual = largura / altura

        if proporcao_atual > proporcao_desejada:

            nova_largura = int(altura * proporcao_desejada)
            esquerda = (largura - nova_largura) // 2

            imagem = imagem.crop(
                (esquerda, 0, esquerda + nova_largura, altura)
            )

        else:

            nova_altura = int(largura / proporcao_desejada)
            topo = (altura - nova_altura) // 2

            imagem = imagem.crop(
                (0, topo, largura, topo + nova_altura)
            )

        imagem = imagem.resize(
            (W, H),
            Image.Resampling.LANCZOS,
        )

    else:

        imagem = Image.new("RGB", (W, H), (10, 12, 18))

    fundo = Image.new("RGB", (W, H), (0, 0, 0))
    fundo.paste(imagem)
    imagem = fundo

    draw = ImageDraw.Draw(imagem, "RGBA")

    # Escurece o quadro todo, pra qualquer texto ficar legível
    # em cima de qualquer foto.
    draw.rectangle([0, 0, W, H], fill=(0, 0, 0, 110))

    # Cabeçalho.
    draw.rectangle([0, 0, W, 190], fill=(3, 8, 14, 235))
    draw.rectangle([0, 185, W, 190], fill=(233, 39, 39, 255))

    # Selo "inscreva-se".
    fonte_selo = ImageFont.truetype(str(FONT_BOLD), 30)
    texto_selo = "INSCREVA-SE"

    caixa_selo = draw.textbbox((0, 0), texto_selo, font=fonte_selo)
    largura_selo = caixa_selo[2] - caixa_selo[0] + 56

    selo_x1 = MARGEM_SEGURA_X
    selo_x2 = selo_x1 + largura_selo
    selo_y1 = MARGEM_SEGURA_Y + 62
    selo_y2 = selo_y1 + 58

    draw.rounded_rectangle(
        [selo_x1, selo_y1, selo_x2, selo_y2],
        radius=(selo_y2 - selo_y1) // 2,
        fill=(233, 39, 39, 255),
    )

    draw.text(
        (selo_x1 + 28, selo_y1 + 12),
        texto_selo,
        font=fonte_selo,
        fill=(255, 255, 255, 255),
    )

    fonte_logo = ImageFont.truetype(str(FONT_BOLD), 40)

    draw.text(
        (MARGEM_SEGURA_X, MARGEM_SEGURA_Y),
        "NOTICIAS SHOW DE BOLA",
        font=fonte_logo,
        fill=(255, 255, 255, 255),
    )

    # Card central com o placar.
    card_y1 = 780
    card_y2 = 1180

    draw.rounded_rectangle(
        [MARGEM_SEGURA_X, card_y1, W - MARGEM_SEGURA_X, card_y2],
        radius=24,
        fill=(0, 0, 0, 210),
    )

    draw.rectangle(
        [MARGEM_SEGURA_X, card_y1, W - MARGEM_SEGURA_X, card_y1 + 6],
        fill=(233, 39, 39, 255),
    )

    fonte_time = ImageFont.truetype(str(FONT_BOLD), 46)
    fonte_placar = ImageFont.truetype(str(FONT_BOLD), 90)

    time_a = resultado["time_a"]
    time_b = resultado["time_b"]
    placar_texto = (
        f"{resultado['placar_a']}  x  {resultado['placar_b']}"
    )

    largura_max_time = W - 2 * (MARGEM_SEGURA_X + 40)

    def texto_centralizado(texto, fonte, y):

        caixa = draw.textbbox((0, 0), texto, font=fonte)
        largura_texto = caixa[2] - caixa[0]
        x = (W - largura_texto) // 2

        draw.text((x, y), texto, font=fonte, fill=(255, 255, 255, 255))

    linhas_a = quebrar_por_largura(
        draw, time_a, fonte_time, largura_max_time
    )[:1]

    linhas_b = quebrar_por_largura(
        draw, time_b, fonte_time, largura_max_time
    )[:1]

    texto_centralizado(linhas_a[0] if linhas_a else time_a, fonte_time, card_y1 + 40)
    texto_centralizado(placar_texto, fonte_placar, card_y1 + 130)
    texto_centralizado(linhas_b[0] if linhas_b else time_b, fonte_time, card_y1 + 260)

    # Competição (se detectada).
    competicao = resultado.get("competicao", "")

    if competicao:

        fonte_competicao = ImageFont.truetype(str(FONT_NORMAL), 30)

        texto_centralizado(
            competicao.upper(),
            fonte_competicao,
            card_y2 + 30,
        )

    # Rodapé.
    draw.rectangle([0, H - 110, W, H], fill=(3, 7, 11, 245))
    draw.rectangle([0, H - 110, W, H - 105], fill=(233, 39, 39, 255))

    fonte_rodape = ImageFont.truetype(str(FONT_NORMAL), 26)

    draw.text(
        (MARGEM_SEGURA_X, H - 80),
        "NEWS YOUTUBE • FUTEBOL • RESULTADOS",
        font=fonte_rodape,
        fill=(255, 255, 255, 255),
    )

    destino = IMAGENS_DIR / f"resultado_{indice}_frame.jpg"

    imagem.convert("RGB").save(
        destino,
        "JPEG",
        quality=95,
        optimize=True,
    )

    return destino


# ============================================================================
# VÍDEO
# ============================================================================

def gerar_video_short(resultado, indice, arquivo_audio, arquivo_imagem):

    frame = preparar_frame_short(arquivo_imagem, resultado, indice)

    duracao = obter_duracao_audio(arquivo_audio)

    print(f"⏱️ Duração do áudio: {duracao:.2f}s")

    destino = VIDEOS_DIR / f"resultado_{indice}.mp4"

    frames_totais = int(duracao * FPS) + FPS

    # x/y centralizam o corte do zoom — sem isso o zoompan
    # ancora no canto superior esquerdo por padrão e corta
    # o card/selo/rodapé.
    filtro_zoom = (
        "scale=1620:2880,"
        "zoompan="
        "z='min(zoom+0.0003,1.05)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={frames_totais}:"
        f"s={W}x{H}:"
        f"fps={FPS}"
    )

    comando = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(frame),
        "-i", str(arquivo_audio),
        "-vf", filtro_zoom,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-t", f"{duracao:.3f}",
        "-shortest",
        "-movflags", "+faststart",
        str(destino),
    ]

    print()
    print("🎞️ Executando FFmpeg...")

    resultado_ffmpeg = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=max(180, int(duracao * 8)),
    )

    if resultado_ffmpeg.returncode != 0:

        print(resultado_ffmpeg.stderr[-4000:])

        raise RuntimeError("FFmpeg falhou.")

    if not destino.exists():
        raise RuntimeError("Vídeo não foi criado.")

    print(f"✅ SHORT CRIADO: {destino}")

    return destino


# ============================================================================
# FALLBACK — SHORT A PARTIR DA NOTÍCIA DO VÍDEO LONGO
#
# Quando não há resultado de jogo com placar identificável, em vez de
# não publicar nada nesse horário, reaproveitamos a notícia mais recente
# já publicada pelo pipeline principal (áudio e imagem já prontos) num
# card vertical de manchete. Só LÊ arquivos que o vídeo longo já gerou —
# não mexe em nada do pipeline principal nem no timing/render do Short
# de placar (gerar_video_short fica intocado; o ffmpeg abaixo é uma
# cópia dele, só trocando o frame de entrada).
# ============================================================================

NOTICIAS_ROTEIROS_DIR = BASE_DIR / "dados" / "roteiros"
NOTICIAS_AUDIOS_DIR = BASE_DIR / "dados" / "audios"
NOTICIAS_IMAGENS_DIR = BASE_DIR / "dados" / "imagens"
NOTICIAS_STATUS_YOUTUBE_FILE = BASE_DIR / "dados" / "status" / "youtube.json"


def _ultima_noticia_publicada():
    """
    Maior índice de notícia_N já publicado no vídeo longo, com
    áudio e imagem disponíveis pra reaproveitar no Short.
    """

    status_youtube = carregar_json(NOTICIAS_STATUS_YOUTUBE_FILE)

    indices = []

    for chave in status_youtube:

        try:
            indices.append(int(chave.split("_")[-1]))

        except ValueError:
            continue

    for n in sorted(indices, reverse=True):

        roteiro_path = NOTICIAS_ROTEIROS_DIR / f"noticia_{n}.json"
        audio_path = NOTICIAS_AUDIOS_DIR / f"noticia_{n}.mp3"
        imagem_path = NOTICIAS_IMAGENS_DIR / f"noticia_{n}.jpg"

        if (
            roteiro_path.exists()
            and audio_path.exists()
            and imagem_path.exists()
        ):
            return n, roteiro_path, audio_path, imagem_path

    return None, None, None, None


def _noticia_ja_usada_no_fallback(indice_noticia):

    for arquivo in ROTEIROS_DIR.glob("resultado_*.json"):

        if carregar_json(arquivo).get("origem_noticia") == indice_noticia:
            return True

    return False


def preparar_frame_noticia(arquivo_imagem, titulo, indice):
    """
    Card vertical de manchete (mesmo estilo visual do card de
    placar), pra quando não há resultado de jogo pra publicar
    nesse horário.
    """

    if arquivo_imagem and Path(arquivo_imagem).exists():

        imagem = Image.open(arquivo_imagem).convert("RGB")

        largura, altura = imagem.size
        proporcao_desejada = W / H
        proporcao_atual = largura / altura

        if proporcao_atual > proporcao_desejada:

            nova_largura = int(altura * proporcao_desejada)
            esquerda = (largura - nova_largura) // 2

            imagem = imagem.crop(
                (esquerda, 0, esquerda + nova_largura, altura)
            )

        else:

            nova_altura = int(largura / proporcao_desejada)
            topo = (altura - nova_altura) // 2

            imagem = imagem.crop(
                (0, topo, largura, topo + nova_altura)
            )

        imagem = imagem.resize(
            (W, H),
            Image.Resampling.LANCZOS,
        )

    else:

        imagem = Image.new("RGB", (W, H), (10, 12, 18))

    fundo = Image.new("RGB", (W, H), (0, 0, 0))
    fundo.paste(imagem)
    imagem = fundo

    draw = ImageDraw.Draw(imagem, "RGBA")

    draw.rectangle([0, 0, W, H], fill=(0, 0, 0, 110))

    # Cabeçalho (igual ao card de placar).
    draw.rectangle([0, 0, W, 190], fill=(3, 8, 14, 235))
    draw.rectangle([0, 185, W, 190], fill=(233, 39, 39, 255))

    fonte_selo = ImageFont.truetype(str(FONT_BOLD), 30)
    texto_selo = "INSCREVA-SE"

    caixa_selo = draw.textbbox((0, 0), texto_selo, font=fonte_selo)
    largura_selo = caixa_selo[2] - caixa_selo[0] + 56

    selo_x1 = MARGEM_SEGURA_X
    selo_x2 = selo_x1 + largura_selo
    selo_y1 = MARGEM_SEGURA_Y + 62
    selo_y2 = selo_y1 + 58

    draw.rounded_rectangle(
        [selo_x1, selo_y1, selo_x2, selo_y2],
        radius=(selo_y2 - selo_y1) // 2,
        fill=(233, 39, 39, 255),
    )

    draw.text(
        (selo_x1 + 28, selo_y1 + 12),
        texto_selo,
        font=fonte_selo,
        fill=(255, 255, 255, 255),
    )

    fonte_logo = ImageFont.truetype(str(FONT_BOLD), 40)

    draw.text(
        (MARGEM_SEGURA_X, MARGEM_SEGURA_Y),
        "NOTICIAS SHOW DE BOLA",
        font=fonte_logo,
        fill=(255, 255, 255, 255),
    )

    # Card central com a manchete (em vez do placar).
    card_y1 = 700
    card_y2 = 1260

    draw.rounded_rectangle(
        [MARGEM_SEGURA_X, card_y1, W - MARGEM_SEGURA_X, card_y2],
        radius=24,
        fill=(0, 0, 0, 210),
    )

    draw.rectangle(
        [MARGEM_SEGURA_X, card_y1, W - MARGEM_SEGURA_X, card_y1 + 6],
        fill=(233, 39, 39, 255),
    )

    fonte_manchete = ImageFont.truetype(str(FONT_BOLD), 56)

    largura_max_texto = W - 2 * (MARGEM_SEGURA_X + 50)

    linhas = quebrar_por_largura(
        draw, titulo, fonte_manchete, largura_max_texto
    )[:5]

    altura_linha = 74
    altura_bloco = altura_linha * len(linhas)
    y_inicial = card_y1 + ((card_y2 - card_y1) - altura_bloco) // 2

    for i, linha in enumerate(linhas):

        caixa = draw.textbbox((0, 0), linha, font=fonte_manchete)
        largura_linha = caixa[2] - caixa[0]
        x = (W - largura_linha) // 2

        draw.text(
            (x, y_inicial + i * altura_linha),
            linha,
            font=fonte_manchete,
            fill=(255, 255, 255, 255),
        )

    fonte_rotulo = ImageFont.truetype(str(FONT_NORMAL), 30)
    texto_rotulo = "NOTÍCIA DO DIA"

    caixa_rotulo = draw.textbbox((0, 0), texto_rotulo, font=fonte_rotulo)
    largura_rotulo = caixa_rotulo[2] - caixa_rotulo[0]

    draw.text(
        ((W - largura_rotulo) // 2, card_y2 + 30),
        texto_rotulo,
        font=fonte_rotulo,
        fill=(255, 255, 255, 255),
    )

    # Rodapé (igual ao card de placar).
    draw.rectangle([0, H - 110, W, H], fill=(3, 7, 11, 245))
    draw.rectangle([0, H - 110, W, H - 105], fill=(233, 39, 39, 255))

    fonte_rodape = ImageFont.truetype(str(FONT_NORMAL), 26)

    draw.text(
        (MARGEM_SEGURA_X, H - 80),
        "NEWS YOUTUBE • FUTEBOL • NOTÍCIAS",
        font=fonte_rodape,
        fill=(255, 255, 255, 255),
    )

    destino = IMAGENS_DIR / f"resultado_{indice}_frame.jpg"

    imagem.convert("RGB").save(
        destino,
        "JPEG",
        quality=95,
        optimize=True,
    )

    return destino


def gerar_video_noticia_short(frame, indice, arquivo_audio):
    """
    Monta o vídeo com o MESMO timing/render de gerar_video_short
    (zoompan, FPS, codecs) — função duplicada de propósito, sem
    tocar na original, só trocando o frame de entrada (manchete
    em vez de placar).
    """

    duracao = obter_duracao_audio(arquivo_audio)

    print(f"⏱️ Duração do áudio: {duracao:.2f}s")

    destino = VIDEOS_DIR / f"resultado_{indice}.mp4"

    frames_totais = int(duracao * FPS) + FPS

    filtro_zoom = (
        "scale=1620:2880,"
        "zoompan="
        "z='min(zoom+0.0003,1.05)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={frames_totais}:"
        f"s={W}x{H}:"
        f"fps={FPS}"
    )

    comando = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(frame),
        "-i", str(arquivo_audio),
        "-vf", filtro_zoom,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-t", f"{duracao:.3f}",
        "-shortest",
        "-movflags", "+faststart",
        str(destino),
    ]

    print()
    print("🎞️ Executando FFmpeg...")

    resultado_ffmpeg = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=max(180, int(duracao * 8)),
    )

    if resultado_ffmpeg.returncode != 0:

        print(resultado_ffmpeg.stderr[-4000:])

        raise RuntimeError("FFmpeg falhou.")

    if not destino.exists():
        raise RuntimeError("Vídeo não foi criado.")

    print(f"✅ SHORT (fallback de notícia) CRIADO: {destino}")

    return destino


def gerar_fallback_de_noticia():
    """
    Quando não há resultado de jogo com placar pra publicar,
    reaproveita a notícia mais recente já publicada no vídeo
    longo (áudio e imagem já prontos) e gera um Short de
    manchete a partir dela, em vez de não publicar nada nesse
    horário.

    Retorna o índice do resultado_N gerado, ou None se não
    havia notícia nova disponível pra reaproveitar.
    """

    indice_noticia, roteiro_path, audio_path, imagem_path = (
        _ultima_noticia_publicada()
    )

    if indice_noticia is None:

        print(
            "⚠️ Nenhuma notícia do vídeo longo disponível "
            "pra reaproveitar no fallback."
        )

        return None

    if _noticia_ja_usada_no_fallback(indice_noticia):

        print(
            f"ℹ️ noticia_{indice_noticia} já virou Short de "
            f"fallback antes — nada novo pra gerar agora."
        )

        return None

    dados_noticia = carregar_json(roteiro_path)
    roteiro_noticia = dados_noticia.get("roteiro", {})

    titulo = roteiro_noticia.get(
        "titulo", "Notícia do futebol"
    )
    descricao_base = roteiro_noticia.get("descricao", "")
    tags_base = roteiro_noticia.get("tags", [])

    preparar_diretorios()

    indice = proximo_indice_short()

    print()
    print("=" * 75)
    print(
        f"📰 SHORT DE FALLBACK: notícia_{indice_noticia} "
        f"→ resultado_{indice}"
    )
    print("=" * 75)
    print(titulo)

    atualizar_status(indice, "processando")

    try:

        frame = preparar_frame_noticia(
            imagem_path, titulo, indice
        )

        gerar_video_noticia_short(
            frame, indice, audio_path
        )

        titulo_youtube = f"{titulo} #Shorts"

        descricao_youtube = (
            f"{descricao_base}\n\n#Shorts #futebol #noticias"
        )

        tags_youtube = list(tags_base)[:15]

        dados = {

            "origem_noticia": indice_noticia,

            "roteiro": {

                "titulo": titulo,
                "canal": CANAL,

                "titulo_youtube": titulo_youtube,
                "descricao_youtube": descricao_youtube,
                "tags_youtube": tags_youtube,

            },
        }

        destino = ROTEIROS_DIR / f"resultado_{indice}.json"

        with open(destino, "w", encoding="utf-8") as arquivo:
            json.dump(
                dados, arquivo, ensure_ascii=False, indent=2
            )

        atualizar_status(indice, "concluido")

        print(f"✅ Roteiro do short (fallback) salvo: {destino}")

        return indice

    except Exception as erro:

        atualizar_status(indice, "erro", str(erro))

        print()
        print(
            f"❌ Falha ao gerar fallback de notícia: {erro}"
        )

        return None


# ============================================================================
# PROCESSAR
# ============================================================================

def processar(repetir_erros=False):

    preparar_diretorios()

    mostrar_status()

    arquivo = encontrar_proximo_pendente(repetir_erros)

    if not arquivo:

        print()
        print("⚠️ Nenhum short pendente pra processar.")

        return

    indice = numero_resultado(arquivo)

    dados = carregar_json(arquivo)
    resultado = dados.get("resultado", {})
    texto = dados.get("roteiro", {}).get("roteiro", "")

    print()
    print("=" * 75)
    print(f"📰 PRÓXIMO SHORT: resultado_{indice}")
    print("=" * 75)

    print(texto)

    atualizar_status(indice, "processando")

    try:

        if not texto:
            raise RuntimeError("Roteiro sem texto para narração.")

        arquivo_audio = AUDIOS_DIR / f"resultado_{indice}.mp3"

        gerar_audio(texto, arquivo_audio)

        arquivo_imagem = procurar_imagem_short(resultado, indice)

        gerar_video_short(
            resultado,
            indice,
            arquivo_audio,
            arquivo_imagem,
        )

        atualizar_status(indice, "concluido")

    except Exception as erro:

        atualizar_status(indice, "erro", str(erro))

        print()
        print(f"❌ Falha ao processar resultado_{indice}: {erro}")


# ============================================================================
# MAIN
# ============================================================================

def argumentos():

    parser = argparse.ArgumentParser(
        description="NEWS-YOUTUBE — Gerador de Shorts de resultado"
    )

    parser.add_argument(
        "--repetir-erros",
        action="store_true",
    )

    parser.add_argument(
        "--fallback-noticia",
        action="store_true",
        help=(
            "Sem resultado de jogo com placar: gera um Short "
            "de manchete a partir da notícia mais recente do "
            "vídeo longo, em vez de não publicar nada."
        ),
    )

    return parser.parse_args()


def main():

    args = argumentos()

    print()
    print("=" * 75)
    print("🎬 NEWS-YOUTUBE — GERADOR DE SHORT")
    print("=" * 75)

    if args.fallback_noticia:
        gerar_fallback_de_noticia()
        return

    processar(repetir_erros=args.repetir_erros)


if __name__ == "__main__":
    main()
