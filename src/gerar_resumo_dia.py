#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NEWS-YOUTUBE — GERADOR DO "RESUMO DO DIA"

Vídeo longo HORIZONTAL (1920x1080) compilando várias notícias já
roteirizadas e narradas pelo pipeline principal (gerar_video.py /
gerar_roteiro.py). Não gera narração nova por notícia — reaproveita
o áudio e a imagem que já existem em dados/audios/ e dados/imagens/,
só monta um card visual horizontal novo e concatena tudo com uma
abertura e um encerramento.

Pipeline SEPARADA da principal e da de Shorts — só LÊ os arquivos
delas (dados/status/fila.json, dados/roteiros/, dados/audios/,
dados/imagens/), nunca escreve neles.

Controla quais notícias já apareceram em algum resumo em
dados/resumo/status/usados.json, pra nunca repetir a mesma notícia
em dois vídeos de resumo.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gerar_video import (
    gerar_audio,
    obter_duracao_audio,
    quebrar_por_largura,
)

# Tags: reaproveita a mesma função usada pelo pipeline principal
# (testada e usada com sucesso em dezenas de vídeos publicados) —
# uma lista de tags própria, feita à mão pro resumo, deu erro
# "invalid video keywords" da API do YouTube numa das palavras
# extraídas dos títulos (não foi possível isolar qual, e a cota
# diária de upload acabou no meio do diagnóstico). Mais seguro
# reaproveitar o que já é comprovado do que arriscar de novo.
from gerar_roteiro import gerar_tags as gerar_tags_roteiro


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

STATUS_PRINCIPAL_FILE = BASE_DIR / "dados" / "status" / "fila.json"
ROTEIROS_PRINCIPAL_DIR = BASE_DIR / "dados" / "roteiros"
AUDIOS_PRINCIPAL_DIR = BASE_DIR / "dados" / "audios"
IMAGENS_PRINCIPAL_DIR = BASE_DIR / "dados" / "imagens"

RESUMO_DIR = BASE_DIR / "dados" / "resumo"
RESUMO_ROTEIROS_DIR = RESUMO_DIR / "roteiros"
RESUMO_VIDEOS_DIR = RESUMO_DIR / "videos"
RESUMO_PARTES_DIR = RESUMO_DIR / "partes"
RESUMO_AUDIOS_DIR = RESUMO_DIR / "audios"
RESUMO_STATUS_DIR = RESUMO_DIR / "status"

RESUMO_FILA_FILE = RESUMO_STATUS_DIR / "fila.json"
RESUMO_USADOS_FILE = RESUMO_STATUS_DIR / "usados.json"

# Vídeo longo horizontal de verdade — diferente do pipeline
# principal, que hoje é vertical (Short).
W = 1920
H = 1080
FPS = 30

MARGEM_SEGURA_X = 70
MARGEM_SEGURA_Y = 50

FONT_BOLD = Path(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)
FONT_NORMAL = Path(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
)

MINIMO_NOTICIAS = 2
MAXIMO_NOTICIAS = 8

TEXTO_INTRO = (
    "Você está no resumo do dia do Show de Bola. "
    "Confira as principais notícias do futebol de hoje."
)

TEXTO_ENCERRAMENTO = (
    "Inscreva-se e acesse o canal para ver mais "
    "conteúdos como este."
)



# ============================================================================
# JSON
# ============================================================================

def carregar_json(path, padrao):
    path = Path(path)

    if not path.exists():
        return padrao

    try:
        with path.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        return dados

    except Exception as erro:
        print(f"⚠️ Erro lendo {path}: {erro}")
        return padrao


def salvar_json(path, dados):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporario = path.with_suffix(".tmp")

    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)

    temporario.replace(path)


# ============================================================================
# DIRETÓRIOS
# ============================================================================

def preparar_diretorios():
    for diretorio in (
        RESUMO_ROTEIROS_DIR,
        RESUMO_VIDEOS_DIR,
        RESUMO_PARTES_DIR,
        RESUMO_AUDIOS_DIR,
        RESUMO_STATUS_DIR,
    ):
        diretorio.mkdir(parents=True, exist_ok=True)


# ============================================================================
# SELEÇÃO DAS NOTÍCIAS
# ============================================================================

def proximo_indice_resumo():

    fila = carregar_json(RESUMO_FILA_FILE, {})

    maior = 0

    for chave in fila:

        try:
            numero = int(str(chave).split("_")[-1])

        except ValueError:
            continue

        maior = max(maior, numero)

    return maior + 1


def selecionar_noticias():
    """
    Devolve, em ordem cronológica (mais antiga primeiro), até
    MAXIMO_NOTICIAS notícias concluídas no pipeline principal que
    ainda não apareceram em nenhum resumo anterior.
    """

    status_principal = carregar_json(STATUS_PRINCIPAL_FILE, {})
    usados = set(carregar_json(RESUMO_USADOS_FILE, []))

    candidatas = []

    for chave, registro in status_principal.items():

        estado = (
            registro.get("status", "pendente")
            if isinstance(registro, dict)
            else registro
        )

        if estado != "concluido":
            continue

        try:
            numero = int(str(chave).split("_")[-1])

        except ValueError:
            continue

        if numero in usados:
            continue

        roteiro_path = ROTEIROS_PRINCIPAL_DIR / f"noticia_{numero}.json"
        audio_path = AUDIOS_PRINCIPAL_DIR / f"noticia_{numero}.mp3"
        imagem_path = IMAGENS_PRINCIPAL_DIR / f"noticia_{numero}.jpg"

        if not (
            roteiro_path.exists()
            and audio_path.exists()
            and imagem_path.exists()
        ):
            continue

        candidatas.append(numero)

    candidatas.sort()

    selecionadas = candidatas[-MAXIMO_NOTICIAS:]

    return selecionadas


def carregar_dados_noticia(numero):

    roteiro_path = ROTEIROS_PRINCIPAL_DIR / f"noticia_{numero}.json"

    dados = carregar_json(roteiro_path, {})

    roteiro = dados.get("roteiro", {})

    if not isinstance(roteiro, dict):
        roteiro = {}

    titulo = str(roteiro.get("titulo", "")).strip()

    # O título salvo no roteiro é o título do YouTube, que hoje
    # sempre termina em " #Shorts" (ver gerar_titulo_youtube em
    # gerar_roteiro.py) — não faz sentido nesse vídeo, que não é
    # um Short.
    if titulo.endswith(" #Shorts"):
        titulo = titulo[: -len(" #Shorts")].strip()

    if not titulo:
        titulo = "Notícia do futebol"

    fonte = str(roteiro.get("fonte", "")).strip() or "Google Notícias"

    return {
        "numero": numero,
        "titulo": titulo,
        "fonte": fonte,
        "audio": AUDIOS_PRINCIPAL_DIR / f"noticia_{numero}.mp3",
        "imagem": IMAGENS_PRINCIPAL_DIR / f"noticia_{numero}.jpg",
    }


# ============================================================================
# DESENHO — UTILITÁRIOS COMPARTILHADOS ENTRE OS CARDS
# ============================================================================

def _abrir_imagem_cortada_16_9(caminho_imagem):

    imagem = Image.open(caminho_imagem).convert("RGB")

    proporcao_desejada = W / H
    largura, altura = imagem.size
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

    return imagem.resize((W, H), Image.Resampling.LANCZOS)


def _fundo_gradiente():

    imagem = Image.new("RGB", (W, H), (7, 19, 29))
    draw = ImageDraw.Draw(imagem)

    topo = (10, 26, 40)
    base = (5, 10, 16)

    for y in range(H):

        t = y / (H - 1)

        cor = tuple(
            int(topo[c] + (base[c] - topo[c]) * t)
            for c in range(3)
        )

        draw.line([(0, y), (W, y)], fill=cor)

    return imagem


def _desenhar_cabecalho_rodape(draw, badge_direita=None):

    # Cabeçalho.
    draw.rectangle([0, 0, W, 130], fill=(3, 8, 14, 235))
    draw.rectangle([0, 125, W, 130], fill=(233, 39, 39, 255))

    fonte_logo = ImageFont.truetype(str(FONT_BOLD), 44)

    draw.text(
        (MARGEM_SEGURA_X, MARGEM_SEGURA_Y),
        "NOTICIAS SHOW DE BOLA",
        font=fonte_logo,
        fill=(255, 255, 255, 255),
    )

    if badge_direita:

        fonte_badge = ImageFont.truetype(str(FONT_BOLD), 32)

        caixa = draw.textbbox((0, 0), badge_direita, font=fonte_badge)
        largura_badge = caixa[2] - caixa[0] + 50

        badge_x2 = W - MARGEM_SEGURA_X
        badge_x1 = badge_x2 - largura_badge
        badge_y1 = MARGEM_SEGURA_Y - 6
        badge_y2 = badge_y1 + 56

        draw.rounded_rectangle(
            [badge_x1, badge_y1, badge_x2, badge_y2],
            radius=(badge_y2 - badge_y1) // 2,
            fill=(233, 39, 39, 255),
        )

        draw.text(
            (badge_x1 + 25, badge_y1 + 12),
            badge_direita,
            font=fonte_badge,
            fill=(255, 255, 255, 255),
        )

    # Rodapé.
    draw.rectangle([0, H - 80, W, H], fill=(3, 7, 11, 245))
    draw.rectangle([0, H - 80, W, H - 75], fill=(233, 39, 39, 255))

    fonte_rodape = ImageFont.truetype(str(FONT_NORMAL), 26)

    draw.text(
        (MARGEM_SEGURA_X, H - 58),
        "RESUMO DO DIA  •  FUTEBOL  •  NOTÍCIAS  •  ANÁLISES",
        font=fonte_rodape,
        fill=(255, 255, 255, 255),
    )


def _texto_centralizado(draw, texto, fonte, y, fill=(255, 255, 255, 255)):

    caixa = draw.textbbox((0, 0), texto, font=fonte)
    largura_texto = caixa[2] - caixa[0]
    x = (W - largura_texto) // 2

    draw.text((x, y), texto, font=fonte, fill=fill)


# ============================================================================
# CARD DE CADA NOTÍCIA
# ============================================================================

def preparar_frame_noticia(dados_noticia, indice, total, destino):

    imagem = _abrir_imagem_cortada_16_9(dados_noticia["imagem"])

    draw = ImageDraw.Draw(imagem, "RGBA")

    draw.rectangle([0, 0, W, H], fill=(0, 0, 0, 120))

    _desenhar_cabecalho_rodape(
        draw,
        badge_direita=f"NOTÍCIA {indice}/{total}",
    )

    # Painel da manchete, no terço inferior (acima do rodapé).
    card_y1 = H - 460
    card_y2 = H - 100

    draw.rounded_rectangle(
        [MARGEM_SEGURA_X, card_y1, W - MARGEM_SEGURA_X, card_y2],
        radius=24,
        fill=(0, 0, 0, 210),
    )

    draw.rectangle(
        [MARGEM_SEGURA_X, card_y1, W - MARGEM_SEGURA_X, card_y1 + 6],
        fill=(233, 39, 39, 255),
    )

    fonte_titulo = ImageFont.truetype(str(FONT_BOLD), 56)

    largura_maxima = W - 2 * (MARGEM_SEGURA_X + 60)

    linhas = quebrar_por_largura(
        draw,
        dados_noticia["titulo"],
        fonte_titulo,
        largura_maxima,
    )[:4]

    altura_linha = 70
    altura_bloco = altura_linha * len(linhas)
    y_inicial = card_y1 + 40

    for i, linha in enumerate(linhas):

        _texto_centralizado(
            draw,
            linha,
            fonte_titulo,
            y_inicial + i * altura_linha,
        )

    fonte_fonte = ImageFont.truetype(str(FONT_NORMAL), 30)

    _texto_centralizado(
        draw,
        f"Fonte: {dados_noticia['fonte']}",
        fonte_fonte,
        min(
            y_inicial + altura_bloco + 20,
            card_y2 - 50,
        ),
        fill=(210, 220, 230, 255),
    )

    imagem.convert("RGB").save(destino, "JPEG", quality=95, optimize=True)

    return destino


# ============================================================================
# CARDS DE ABERTURA E ENCERRAMENTO
# ============================================================================

def preparar_frame_intro(data_str, quantidade, destino):

    imagem = _fundo_gradiente()
    draw = ImageDraw.Draw(imagem, "RGBA")

    draw.rectangle([0, 0, 18, H], fill=(233, 39, 39, 255))

    _desenhar_cabecalho_rodape(draw)

    fonte_titulo = ImageFont.truetype(str(FONT_BOLD), 90)
    fonte_sub = ImageFont.truetype(str(FONT_NORMAL), 42)

    _texto_centralizado(draw, "RESUMO DO DIA", fonte_titulo, H // 2 - 140)
    _texto_centralizado(
        draw,
        f"Futebol — {data_str}",
        fonte_sub,
        H // 2 - 20,
        fill=(210, 220, 230, 255),
    )
    _texto_centralizado(
        draw,
        f"{quantidade} principais notícias do dia",
        fonte_sub,
        H // 2 + 40,
        fill=(210, 220, 230, 255),
    )

    imagem.convert("RGB").save(destino, "JPEG", quality=95, optimize=True)

    return destino


def preparar_frame_outro(destino):

    imagem = _fundo_gradiente()
    draw = ImageDraw.Draw(imagem, "RGBA")

    draw.rectangle([0, 0, 18, H], fill=(233, 39, 39, 255))

    _desenhar_cabecalho_rodape(draw)

    fonte_selo = ImageFont.truetype(str(FONT_BOLD), 80)
    fonte_sub = ImageFont.truetype(str(FONT_NORMAL), 40)

    texto_selo = "INSCREVA-SE"

    caixa_selo = draw.textbbox((0, 0), texto_selo, font=fonte_selo)
    largura_selo = caixa_selo[2] - caixa_selo[0] + 100
    altura_selo = 130

    selo_x1 = (W - largura_selo) // 2
    selo_y1 = H // 2 - 150

    draw.rounded_rectangle(
        [
            selo_x1,
            selo_y1,
            selo_x1 + largura_selo,
            selo_y1 + altura_selo,
        ],
        radius=altura_selo // 2,
        fill=(233, 39, 39, 255),
    )

    _texto_centralizado(
        draw,
        texto_selo,
        fonte_selo,
        selo_y1 + 25,
    )

    _texto_centralizado(
        draw,
        "Noticias Show de Bola",
        fonte_sub,
        selo_y1 + altura_selo + 60,
        fill=(210, 220, 230, 255),
    )

    imagem.convert("RGB").save(destino, "JPEG", quality=95, optimize=True)

    return destino


# ============================================================================
# RENDERIZAÇÃO DE UM CLIPE (FRAME + ÁUDIO → MP4)
# ============================================================================

def renderizar_clipe(frame, audio, destino):

    duracao = obter_duracao_audio(audio)

    frames_totais = int(duracao * FPS) + FPS

    filtro_zoom = (
        "scale=2880:1620,"
        "zoompan="
        f"z='min(zoom+0.0003,1.05)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={frames_totais}:"
        f"s={W}x{H}:"
        f"fps={FPS}"
    )

    comando = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(frame),
        "-i", str(audio),
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

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=max(180, int(duracao * 8)),
    )

    if resultado.returncode != 0:

        print("❌ FFmpeg apresentou erro:")
        print(resultado.stderr[-4000:])

        raise RuntimeError(f"FFmpeg falhou renderizando {destino}.")

    return duracao


def concatenar_clipes(clipes, destino):

    lista_path = destino.with_suffix(".txt")

    with lista_path.open("w", encoding="utf-8") as arquivo:

        for clipe in clipes:
            arquivo.write(f"file '{Path(clipe).resolve()}'\n")

    comando = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(lista_path),
        "-c", "copy",
        "-movflags", "+faststart",
        str(destino),
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if resultado.returncode != 0:

        print("❌ FFmpeg apresentou erro ao concatenar:")
        print(resultado.stderr[-4000:])

        raise RuntimeError("FFmpeg falhou concatenando os clipes.")


# ============================================================================
# TÍTULO / DESCRIÇÃO / TAGS
# ============================================================================

def formatar_tempo(segundos):

    segundos = int(segundos)
    m, s = divmod(segundos, 60)
    h, m = divmod(m, 60)

    if h:
        return f"{h}:{m:02d}:{s:02d}"

    return f"{m}:{s:02d}"


def gerar_titulo(edicao, data_str):

    return f"Resumo do dia — Futebol (Edição das {edicao}) — {data_str}"


def gerar_descricao(edicao, data_str, capitulos):

    linhas = [
        f"Resumo das notícias do futebol de hoje ({data_str}) — "
        f"Edição das {edicao}, direto do Noticias Show de Bola.",
        "",
    ]

    for tempo, titulo_capitulo in capitulos:
        linhas.append(f"{tempo} {titulo_capitulo}")

    linhas.append("")
    linhas.append(
        "Inscreva-se no canal para acompanhar todas as "
        "notícias do futebol."
    )
    linhas.append("")
    linhas.append("#futebol #noticias #resumo")

    return "\n".join(linhas)


def gerar_tags(titulos):
    """
    Reaproveita gerar_tags() de gerar_roteiro.py (base fixa do
    canal + palavras extraídas do texto, já testada e usada com
    sucesso todo dia pelo pipeline principal), alimentando com
    todos os títulos incluídos no resumo de uma vez.
    """

    return gerar_tags_roteiro(" ".join(titulos), "")


# ============================================================================
# PROCESSAMENTO
# ============================================================================

def processar():

    preparar_diretorios()

    numeros = selecionar_noticias()

    if len(numeros) < MINIMO_NOTICIAS:

        print(
            f"⚠️ Só há {len(numeros)} notícia(s) nova(s) desde o "
            f"último resumo (mínimo: {MINIMO_NOTICIAS})."
        )
        print(
            "ℹ️ Não é bug — o resumo pula a execução até acumular "
            "notícias suficientes."
        )

        return 2

    indice = proximo_indice_resumo()
    chave = f"resumo_{indice}"

    agora = datetime.now()
    data_str = agora.strftime("%d/%m")
    edicao = "12h" if agora.hour < 17 else "22h"

    print(f"📰 Notícias selecionadas: {numeros}")
    print(f"🎬 Gerando {chave} — edição das {edicao}, {data_str}")

    noticias = [carregar_dados_noticia(n) for n in numeros]

    clipes = []
    capitulos = []
    tempo_acumulado = 0.0

    try:

        # ------------------------------------------------------------
        # ABERTURA
        # ------------------------------------------------------------

        print()
        print("🎙️ Gerando narração de abertura...")

        audio_intro = RESUMO_AUDIOS_DIR / f"{chave}_intro.mp3"
        gerar_audio(TEXTO_INTRO, audio_intro)

        frame_intro = RESUMO_PARTES_DIR / f"{chave}_intro.jpg"
        preparar_frame_intro(data_str, len(noticias), frame_intro)

        clipe_intro = RESUMO_PARTES_DIR / f"{chave}_intro.mp4"
        duracao_intro = renderizar_clipe(
            frame_intro, audio_intro, clipe_intro
        )

        clipes.append(clipe_intro)
        capitulos.append((formatar_tempo(tempo_acumulado), "Abertura"))
        tempo_acumulado += duracao_intro

        # ------------------------------------------------------------
        # NOTÍCIAS
        # ------------------------------------------------------------

        total = len(noticias)

        for posicao, dados_noticia in enumerate(noticias, start=1):

            print()
            print(
                f"🎬 Notícia {posicao}/{total}: "
                f"{dados_noticia['titulo']}"
            )

            frame_path = (
                RESUMO_PARTES_DIR
                / f"{chave}_noticia_{dados_noticia['numero']}.jpg"
            )

            preparar_frame_noticia(
                dados_noticia, posicao, total, frame_path
            )

            clipe_path = (
                RESUMO_PARTES_DIR
                / f"{chave}_noticia_{dados_noticia['numero']}.mp4"
            )

            duracao = renderizar_clipe(
                frame_path, dados_noticia["audio"], clipe_path
            )

            clipes.append(clipe_path)

            capitulo_titulo = dados_noticia["titulo"]

            if len(capitulo_titulo) > 90:
                capitulo_titulo = capitulo_titulo[:87].rstrip() + "..."

            capitulos.append(
                (formatar_tempo(tempo_acumulado), capitulo_titulo)
            )

            tempo_acumulado += duracao

        # ------------------------------------------------------------
        # ENCERRAMENTO
        # ------------------------------------------------------------

        print()
        print("🎙️ Gerando narração de encerramento...")

        audio_outro = RESUMO_AUDIOS_DIR / f"{chave}_outro.mp3"
        gerar_audio(TEXTO_ENCERRAMENTO, audio_outro)

        frame_outro = RESUMO_PARTES_DIR / f"{chave}_outro.jpg"
        preparar_frame_outro(frame_outro)

        clipe_outro = RESUMO_PARTES_DIR / f"{chave}_outro.mp4"
        duracao_outro = renderizar_clipe(
            frame_outro, audio_outro, clipe_outro
        )

        clipes.append(clipe_outro)
        capitulos.append(
            (formatar_tempo(tempo_acumulado), "Inscreva-se no canal")
        )
        tempo_acumulado += duracao_outro

        # ------------------------------------------------------------
        # CONCATENAÇÃO
        # ------------------------------------------------------------

        print()
        print("🎞️ Concatenando os clipes...")

        destino_final = RESUMO_VIDEOS_DIR / f"{chave}.mp4"

        concatenar_clipes(clipes, destino_final)

        print(f"✅ Vídeo final: {destino_final}")
        print(f"⏱️ Duração total: {formatar_tempo(tempo_acumulado)}")

        # ------------------------------------------------------------
        # METADADOS
        # ------------------------------------------------------------

        titulos = [n["titulo"] for n in noticias]

        titulo_youtube = gerar_titulo(edicao, data_str)
        descricao = gerar_descricao(edicao, data_str, capitulos)
        tags = gerar_tags(titulos)

        roteiro_final = {
            "criado_em": agora.isoformat(),
            "edicao": edicao,
            "noticias_incluidas": numeros,
            "titulo": titulo_youtube,
            "descricao": descricao,
            "tags": tags,
        }

        salvar_json(
            RESUMO_ROTEIROS_DIR / f"{chave}.json",
            roteiro_final,
        )

        # ------------------------------------------------------------
        # STATUS
        # ------------------------------------------------------------

        fila = carregar_json(RESUMO_FILA_FILE, {})
        fila[chave] = {"status": "concluido"}
        salvar_json(RESUMO_FILA_FILE, fila)

        usados = carregar_json(RESUMO_USADOS_FILE, [])
        usados = sorted(set(usados) | set(numeros))
        salvar_json(RESUMO_USADOS_FILE, usados)

        print()
        print("=" * 75)
        print("✅ RESUMO DO DIA CONCLUÍDO")
        print("=" * 75)
        print(f"📰 Notícias incluídas: {numeros}")
        print(f"🎬 Vídeo: {destino_final}")

        return 0

    except Exception as erro:

        fila = carregar_json(RESUMO_FILA_FILE, {})
        fila[chave] = {"status": "erro", "erro": str(erro)}
        salvar_json(RESUMO_FILA_FILE, fila)

        print()
        print("=" * 75)
        print("❌ FALHA GERANDO O RESUMO DO DIA")
        print("=" * 75)
        print(f"Erro: {erro}")

        return 1


# ============================================================================
# MAIN
# ============================================================================

def main():

    print()
    print("=" * 75)
    print("🎬 NEWS-YOUTUBE — GERADOR DO RESUMO DO DIA")
    print("=" * 75)
    print(f"📂 Projeto: {BASE_DIR}")

    return processar()


if __name__ == "__main__":
    sys.exit(main())
