#!/usr/bin/env python3

import argparse
import asyncio
import html
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("❌ Pillow não está instalado.")
    print("Execute:")
    print("   pip install pillow")
    sys.exit(1)


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

ROTEIROS_DIR = BASE_DIR / "dados" / "roteiros"
AUDIOS_DIR = BASE_DIR / "dados" / "audios"
IMAGENS_DIR = BASE_DIR / "dados" / "imagens"
VIDEOS_DIR = BASE_DIR / "dados" / "videos"
STATUS_DIR = BASE_DIR / "dados" / "status"

STATUS_FILE = STATUS_DIR / "fila.json"

W = 1920
H = 1080
FPS = 30

# Margem de segurança pra nenhum texto/selo ficar cortado
# pelo zoom lento (Ken Burns) aplicado no vídeo final.
MARGEM_SEGURA_X = 100
MARGEM_SEGURA_Y = 55

VOICE_PREFERRED = "pt-BR-AntonioNeural"

FONT_BOLD = Path(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)

FONT_NORMAL = Path(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,image/svg+xml,image/*,*/*;q=0.8"
    ),
}

TIMEOUT = 25


# ============================================================================
# DIRETÓRIOS
# ============================================================================

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
        json.dump(
            data,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    temporario.replace(path)


# ============================================================================
# STATUS
# ============================================================================

def numero_noticia(path):
    try:
        return int(Path(path).stem.split("_")[-1])
    except Exception:
        return 999999


def carregar_status():
    data = carregar_json(STATUS_FILE)

    if not isinstance(data, dict):
        return {}

    return data


def atualizar_status(noticia_id, estado, erro=None):
    status = carregar_status()

    chave = f"noticia_{int(noticia_id)}"

    status[chave] = {
        "status": estado
    }

    if erro:
        status[chave]["erro"] = str(erro)

    salvar_json(STATUS_FILE, status)


def mostrar_status():
    arquivos = sorted(
        ROTEIROS_DIR.glob("noticia_*.json"),
        key=numero_noticia,
    )

    status = carregar_status()

    print()
    print("=" * 75)
    print("📊 STATUS DA FILA")
    print("=" * 75)

    total = len(arquivos)

    concluidos = 0
    pendentes = 0
    erros = 0
    processando = 0

    for arquivo in arquivos:

        chave = arquivo.stem

        registro = status.get(chave, {})

        if isinstance(registro, str):
            estado = registro
            erro_msg = ""
        else:
            estado = registro.get(
                "status",
                "pendente",
            )
            erro_msg = registro.get(
                "erro",
                "",
            )

        if estado == "concluido":

            print(
                f"✅ {chave}: concluido"
            )

            concluidos += 1

        elif estado == "erro":

            print(
                f"❌ {chave}: erro"
            )

            if erro_msg:
                print(
                    f"   └─ {erro_msg}"
                )

            erros += 1

        elif estado == "processando":

            print(
                f"🔄 {chave}: processando"
            )

            processando += 1

        else:

            print(
                f"⏳ {chave}: pendente"
            )

            pendentes += 1

    print()

    print(f"Total: {total}")
    print(f"Concluídos: {concluidos}")
    print(f"Pendentes: {pendentes}")
    print(f"Processando: {processando}")
    print(f"Erros: {erros}")

    print("=" * 75)

    return arquivos, status


def encontrar_proxima_noticia(repetir_erros=False):

    arquivos = sorted(
        ROTEIROS_DIR.glob("noticia_*.json"),
        key=numero_noticia,
    )

    status = carregar_status()

    # Primeiro tenta pendentes.
    for arquivo in arquivos:

        chave = arquivo.stem

        registro = status.get(
            chave,
            {},
        )

        if isinstance(registro, str):
            estado = registro
        else:
            estado = registro.get(
                "status",
                "pendente",
            )

        if estado == "pendente":
            return arquivo

    # Depois tenta erros, somente se solicitado.
    if repetir_erros:

        for arquivo in arquivos:

            chave = arquivo.stem

            registro = status.get(
                chave,
                {},
            )

            if isinstance(registro, str):
                estado = registro
            else:
                estado = registro.get(
                    "status",
                    "pendente",
                )

            if estado == "erro":
                return arquivo

    return None


# ============================================================================
# NOTÍCIA
# ============================================================================

def carregar_noticia(path):

    path = Path(path)

    dados = carregar_json(path)

    if not isinstance(dados, dict):
        raise RuntimeError(
            f"Formato inválido: {path}"
        )

    noticia = dados.get(
        "noticia",
        {},
    )

    roteiro = dados.get(
        "roteiro",
        {},
    )

    if not isinstance(noticia, dict):
        noticia = {}

    if not isinstance(roteiro, dict):
        roteiro = {}

    titulo = (
        noticia.get("titulo")
        or roteiro.get("titulo")
        or "Notícia do futebol"
    )

    fonte = (
        noticia.get("fonte")
        or roteiro.get("fonte")
        or "Google Notícias"
    )

    url = (
        noticia.get("url")
        or noticia.get("link")
        or ""
    )

    texto = (
        roteiro.get("roteiro")
        or roteiro.get("texto")
        or roteiro.get("gancho")
        or ""
    )

    return {
        "id": numero_noticia(path),

        "titulo": str(
            titulo
        ).strip(),

        "titulo_original": str(
            noticia.get(
                "titulo_original",
                titulo,
            )
        ).strip(),

        "fonte": str(
            fonte
        ).strip(),

        "url": str(
            url
        ).strip(),

        "texto": str(
            texto
        ).strip(),
    }


# ============================================================================
# EDGE TTS
# ============================================================================

def importar_edge_tts():

    try:
        import edge_tts
        return edge_tts

    except ImportError:
        raise RuntimeError(
            "edge-tts não está instalado.\n"
            "Execute:\n"
            "pip install edge-tts"
        )


async def obter_voz_valida():

    edge_tts = importar_edge_tts()

    vozes = await edge_tts.list_voices()

    nomes = []

    for voz in vozes:

        nome = voz.get(
            "ShortName",
            "",
        )

        if nome.lower().startswith(
            "pt-br-"
        ):
            nomes.append(nome)

    if VOICE_PREFERRED in nomes:
        return VOICE_PREFERRED

    for nome in nomes:

        if "Antonio" in nome:
            return nome

    for nome in nomes:

        if "Francisca" in nome:
            return nome

    if nomes:
        return sorted(nomes)[0]

    raise RuntimeError(
        "Nenhuma voz pt-BR disponível."
    )


async def gerar_audio_async(
    texto,
    destino,
):

    edge_tts = importar_edge_tts()

    voz = await obter_voz_valida()

    print()
    print("🎙️ GERANDO NARRAÇÃO")
    print("=" * 75)

    print(
        f"📝 Caracteres: {len(texto)}"
    )

    print(
        f"🗣️ Voz: {voz}"
    )

    destino = Path(destino)

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    comunicador = edge_tts.Communicate(
        texto,
        voz,
    )

    await comunicador.save(
        str(destino)
    )

    if (
        not destino.exists()
        or destino.stat().st_size < 1000
    ):
        raise RuntimeError(
            "Áudio não foi criado "
            "ou está inválido."
        )

    print(
        f"✅ Áudio criado: {destino}"
    )


def gerar_audio(
    texto,
    destino,
):

    asyncio.run(
        gerar_audio_async(
            texto,
            destino,
        )
    )


# ============================================================================
# IMAGENS
# ============================================================================

def imagem_valida(path):

    path = Path(path)

    if not path.exists():
        return False

    if path.stat().st_size < 12000:
        return False

    try:

        with Image.open(path) as imagem:

            largura, altura = imagem.size

            return (
                largura >= 700
                and altura >= 400
            )

    except Exception:
        return False


def baixar_imagem(
    url,
    destino,
    referer=None,
):

    destino = Path(destino)

    if not url:
        return False

    if not str(url).startswith(
        "http"
    ):
        return False

    headers = dict(
        HEADERS
    )

    if referer:
        headers["Referer"] = str(
            referer
        )

    temporario = destino.with_suffix(
        ".download"
    )

    try:

        resposta = requests.get(
            str(url),
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        resposta.raise_for_status()

        data = resposta.content

        content_type = resposta.headers.get(
            "content-type",
            "",
        ).lower()

        if (
            "text/html" in content_type
            or len(data) < 12000
        ):
            return False

        temporario.write_bytes(
            data
        )

        if not imagem_valida(
            temporario
        ):
            temporario.unlink(
                missing_ok=True
            )
            return False

        # Reabre e converte com Pillow.
        # Isso evita depender de comportamento
        # específico do FFmpeg para imagens.
        with Image.open(
            temporario
        ) as imagem:

            imagem = imagem.convert(
                "RGB"
            )

            imagem.save(
                destino,
                "JPEG",
                quality=94,
                optimize=True,
            )

        temporario.unlink(
            missing_ok=True
        )

        return imagem_valida(
            destino
        )

    except Exception:

        temporario.unlink(
            missing_ok=True
        )

        return False


def tokenizar(texto):

    texto = re.sub(
        r"[^a-z0-9áéíóúãõâêîôûçü\s]",
        " ",
        str(texto).lower(),
    )

    palavras = texto.split()

    stop = {
        "para",
        "como",
        "com",
        "por",
        "uma",
        "um",
        "do",
        "da",
        "de",
        "dos",
        "das",
        "no",
        "na",
        "nos",
        "nas",
        "e",
        "o",
        "a",
        "os",
        "as",
        "em",
        "ao",
        "aos",
        "que",
        "club",
        "clube",
        "futebol",
        "brasil",
        "brasileiro",
        "brasileira",
        "veja",
        "detalhes",
    }

    return [
        palavra
        for palavra in palavras
        if len(palavra) >= 4
        and palavra not in stop
    ]


def consultas_relevantes(titulo):

    tokens = tokenizar(
        titulo
    )

    consultas = []

    def adicionar(valor):

        valor = re.sub(
            r"\s+",
            " ",
            valor,
        ).strip()

        if (
            valor
            and valor not in consultas
        ):
            consultas.append(
                valor
            )

    adicionar(titulo)

    if len(tokens) >= 2:

        adicionar(
            " ".join(
                tokens[:6]
            )
            + " futebol"
        )

    if len(tokens) >= 3:

        adicionar(
            " ".join(
                tokens[:4]
            )
            + " jogador"
        )

    clubes = [
        "palmeiras",
        "flamengo",
        "corinthians",
        "santos",
        "vasco",
        "botafogo",
        "athletico",
        "grêmio",
        "gremio",
        "internacional",
        "cruzeiro",
        "bahia",
        "sport",
        "fortaleza",
        "fluminense",
        "atlético",
        "atletico",
    ]

    titulo_lower = titulo.lower()

    achados = [
        clube
        for clube in clubes
        if clube in titulo_lower
    ]

    if achados:

        adicionar(
            " ".join(achados)
            + " futebol"
        )

        if tokens:

            adicionar(
                " ".join(
                    achados
                    + tokens[:2]
                )
                + " jogador"
            )

    return consultas[:8]


def buscar_bing_images(
    consulta
):

    resultados = []

    try:

        resposta = requests.get(
            "https://www.bing.com/images/search",
            params={
                "q": consulta,
                "form": "HDRSC2",
                "first": "1",
                # Restringe a imagens que o Bing classifica como
                # livres pra modificar, compartilhar e usar
                # comercialmente (license-L6) — o vídeo recorta e
                # sobrepõe texto na imagem, então precisa também de
                # permissão de modificação, não só de uso.
                "qft": (
                    "+filterui:aspect-wide"
                    "+filterui:license-L6"
                ),
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        resposta.raise_for_status()

        soup = BeautifulSoup(
            resposta.text,
            "html.parser",
        )

        for elemento in soup.select(
            "a.iusc"
        ):

            raw = elemento.get(
                "m"
            )

            if not raw:
                continue

            try:

                meta = json.loads(
                    html.unescape(raw)
                )

            except Exception:
                continue

            url = meta.get(
                "murl"
            )

            titulo = (
                meta.get("t")
                or ""
            )

            pagina = (
                meta.get("purl")
                or ""
            )

            if (
                url
                and str(url).startswith(
                    "http"
                )
            ):

                resultados.append(
                    {
                        "url": str(url),
                        "texto": (
                            f"{titulo} {pagina}"
                        ),
                    }
                )

        print(
            f"   📷 Bing retornou "
            f"{len(resultados)} candidatas."
        )

    except Exception as erro:

        print(
            f"   ⚠️ Bing indisponível: {erro}"
        )

    return resultados[:35]


def pontuar_candidata(
    candidata,
    titulo,
):

    texto = (
        f"{candidata.get('texto', '')} "
        f"{candidata.get('url', '')}"
    ).lower()

    tokens = tokenizar(
        titulo
    )

    pontos = 0
    matches = 0

    for token in tokens:

        if token in texto:

            matches += 1
            pontos += 15

    dominio = urlparse(
        candidata.get(
            "url",
            "",
        )
    ).netloc.lower()

    if (
        "wikimedia.org"
        in dominio
    ):
        pontos -= 35

    if (
        "wikipedia.org"
        in dominio
    ):
        pontos -= 35

    fontes_esportivas = (
        "espn",
        "ge.globo",
        "globo",
        "lance",
        "terra",
        "gazetaesportiva",
        "uol",
        "365scores",
        "palmeiras.com.br",
        "flamengo.com.br",
        "internacional.com.br",
        "sportclubinternacional",
    )

    if any(
        item in dominio
        for item in fontes_esportivas
    ):
        pontos += 35

    if matches >= 3:
        pontos += 40

    elif matches == 2:
        pontos += 20

    elif matches == 0:
        pontos -= 80

    return pontos


def criar_fallback_noticia(
    destino,
    titulo,
):

    destino = Path(destino)

    print(
        "📰 Criando arte gráfica específica da notícia..."
    )

    imagem = Image.new(
        "RGB",
        (W, H),
        (7, 19, 29),
    )

    draw = ImageDraw.Draw(
        imagem
    )

    # Fundo.
    draw.rectangle(
        [0, 0, W, H],
        fill=(7, 19, 29),
    )

    # Faixa superior.
    draw.rectangle(
        [0, 0, W, 150],
        fill=(5, 11, 18),
    )

    # Barra vermelha.
    draw.rectangle(
        [0, 0, 18, H],
        fill=(233, 39, 39),
    )

    draw.rectangle(
        [0, 1010, W, H],
        fill=(3, 7, 11),
    )

    draw.rectangle(
        [0, 1010, W, 1015],
        fill=(233, 39, 39),
    )

    fonte_logo = ImageFont.truetype(
        str(FONT_BOLD),
        48,
    )

    fonte_categoria = ImageFont.truetype(
        str(FONT_BOLD),
        30,
    )

    fonte_titulo = ImageFont.truetype(
        str(FONT_BOLD),
        50,
    )

    fonte_rodape = ImageFont.truetype(
        str(FONT_NORMAL),
        24,
    )

    draw.text(
        (60, 35),
        "NOTÍCIA SHOW DE BOLA",
        font=fonte_logo,
        fill="white",
    )

    draw.text(
        (60, 100),
        "NOTÍCIA DO FUTEBOL",
        font=fonte_categoria,
        fill=(233, 39, 39),
    )

    linhas = textwrap.wrap(
        str(titulo),
        width=42,
    )

    y = 300

    for linha in linhas[:6]:

        draw.text(
            (80, y),
            linha,
            font=fonte_titulo,
            fill="white",
        )

        y += 75

    draw.text(
        (60, 1030),
        "NOTÍCIAS •  FUTEBOL  •  NOTÍCIAS  •  ANÁLISES",
        font=fonte_rodape,
        fill="white",
    )

    imagem.save(
        destino,
        "JPEG",
        quality=95,
    )

    if not imagem_valida(
        destino
    ):
        raise RuntimeError(
            "Fallback gráfico inválido."
        )

    return destino


def procurar_imagem(
    noticia
):

    noticia_id = int(
        noticia["id"]
    )

    titulo = str(
        noticia["titulo"]
    )

    destino = (
        IMAGENS_DIR
        / f"noticia_{noticia_id}.jpg"
    )

    destino.unlink(
        missing_ok=True
    )

    print()
    print("=" * 75)
    print(
        "🖼️ BUSCA DE IMAGEM RELEVANTE"
    )
    print("=" * 75)

    print(
        f"📰 {titulo}"
    )

    # ------------------------------------------------------------
    # 1. Imagem oficial da matéria — DESATIVADO.
    #
    # extrair_og_images() pegava a foto do próprio artigo
    # (og:image) direto, sem checar licença nenhuma — é a foto
    # editorial do veículo, normalmente licenciada de uma agência,
    # e usar sem permissão é risco de direitos autorais. Todas as
    # imagens agora vêm só do Bing (passo 2), já filtrado por
    # licença de reuso/modificação comercial.
    # ------------------------------------------------------------

    # ------------------------------------------------------------
    # 2. Bing
    # ------------------------------------------------------------

    candidatos = []

    print()
    print(
        "2️⃣ Buscando imagens específicas no Bing..."
    )

    for consulta in consultas_relevantes(
        titulo
    ):

        print(
            f"   🔎 {consulta}"
        )

        resultados = buscar_bing_images(
            consulta
        )

        for item in resultados:

            item[
                "pontuacao"
            ] = pontuar_candidata(
                item,
                titulo,
            )

            candidatos.append(
                item
            )

    # Deduplicação.
    unicos = {}

    for item in candidatos:

        imagem_url = item.get(
            "url",
            "",
        )

        if not imagem_url:
            continue

        anterior = unicos.get(
            imagem_url
        )

        if (
            anterior is None
            or item["pontuacao"]
            > anterior["pontuacao"]
        ):
            unicos[
                imagem_url
            ] = item

    candidatos = sorted(
        unicos.values(),
        key=lambda item: item[
            "pontuacao"
        ],
        reverse=True,
    )

    print()
    print(
        f"🧪 Candidatas únicas: "
        f"{len(candidatos)}"
    )

    limite = min(
        25,
        len(candidatos),
    )

    print(
        "🎯 Pontuação mínima para testar: 35"
    )

    for indice, item in enumerate(
        candidatos[:25],
        start=1,
    ):

        score = item[
            "pontuacao"
        ]

        imagem_url = item[
            "url"
        ]

        print()
        print(
            f"   📥 Candidata "
            f"{indice}/{limite}"
        )

        print(
            f"   ⭐ Relevância: {score}"
        )

        print(
            f"   🔗 {imagem_url}"
        )

        if score < 35:

            print(
                "   ⛔ Rejeitada por baixa relevância."
            )

            continue

        if baixar_imagem(
            imagem_url,
            destino,
        ):

            print(
                "   ✅ IMAGEM RELEVANTE ACEITA."
            )

            print(
                f"📷 Arquivo final da imagem:"
            )

            print(
                f"   {destino}"
            )

            return Path(
                destino
            )

    # ------------------------------------------------------------
    # 3. Fallback
    # ------------------------------------------------------------

    print()
    print(
        "⚠️ Nenhuma fotografia relevante foi confirmada."
    )

    print(
        "📰 Será usada uma arte específica com o título."
    )

    return Path(
        criar_fallback_noticia(
            destino,
            titulo,
        )
    )


# ============================================================================
# QUEBRA DE LINHA POR LARGURA EM PIXELS
# ============================================================================

def quebrar_por_largura(
    draw,
    texto,
    fonte,
    largura_maxima,
):
    """
    Quebra o texto em linhas que cabem em largura_maxima
    (em pixels), em vez de um número fixo de caracteres —
    garante que a linha nunca ultrapasse a área segura,
    mesmo com o zoom aplicado depois no vídeo.
    """

    palavras = texto.split()

    linhas = []
    linha_atual = ""

    for palavra in palavras:

        candidata = (
            f"{linha_atual} {palavra}".strip()
        )

        largura = draw.textlength(
            candidata,
            font=fonte,
        )

        if (
            largura <= largura_maxima
            or not linha_atual
        ):
            linha_atual = candidata

        else:
            linhas.append(linha_atual)
            linha_atual = palavra

    if linha_atual:
        linhas.append(linha_atual)

    return linhas


# ============================================================================
# PREPARAÇÃO DA IMAGEM PARA O VÍDEO
# ============================================================================

def preparar_frame_video(
    arquivo_imagem,
    noticia,
):

    arquivo_imagem = Path(
        arquivo_imagem
    )

    if not arquivo_imagem.exists():
        raise RuntimeError(
            f"Imagem não encontrada: "
            f"{arquivo_imagem}"
        )

    try:

        imagem = Image.open(
            arquivo_imagem
        ).convert("RGB")

    except Exception as erro:

        raise RuntimeError(
            f"Não foi possível abrir a imagem: {erro}"
        )

    # ------------------------------------------------------------
    # Crop para 16:9
    # ------------------------------------------------------------

    proporcao_desejada = W / H

    largura, altura = imagem.size

    proporcao_atual = (
        largura / altura
    )

    if proporcao_atual > proporcao_desejada:

        nova_largura = int(
            altura
            * proporcao_desejada
        )

        esquerda = (
            largura
            - nova_largura
        ) // 2

        imagem = imagem.crop(
            (
                esquerda,
                0,
                esquerda + nova_largura,
                altura,
            )
        )

    else:

        nova_altura = int(
            largura
            / proporcao_desejada
        )

        topo = (
            altura
            - nova_altura
        ) // 2

        imagem = imagem.crop(
            (
                0,
                topo,
                largura,
                topo + nova_altura,
            )
        )

    imagem = imagem.resize(
        (W, H),
        Image.Resampling.LANCZOS,
    )

    # ------------------------------------------------------------
    # Escurecimento
    # ------------------------------------------------------------

    escurecida = Image.new(
        "RGB",
        (W, H),
        (0, 0, 0),
    )

    escurecida.paste(
        imagem
    )

    imagem = escurecida

    draw = ImageDraw.Draw(
        imagem,
        "RGBA",
    )

    # ------------------------------------------------------------
    # Cabeçalho
    # ------------------------------------------------------------

    draw.rectangle(
        [0, 0, W, 155],
        fill=(3, 8, 14, 225),
    )

    draw.rectangle(
        [0, 150, W, 155],
        fill=(233, 39, 39, 255),
    )

    # ------------------------------------------------------------
    # Painel da notícia
    # ------------------------------------------------------------

    draw.rounded_rectangle(
        [55, 690, 1865, 965],
        radius=20,
        fill=(0, 0, 0, 205),
    )

    draw.rectangle(
        [55, 690, 73, 965],
        fill=(233, 39, 39, 255),
    )

    # ------------------------------------------------------------
    # Rodapé
    # ------------------------------------------------------------

    draw.rectangle(
        [0, 1010, W, H],
        fill=(3, 7, 11, 245),
    )

    draw.rectangle(
        [0, 1010, W, 1015],
        fill=(233, 39, 39, 255),
    )

    # ------------------------------------------------------------
    # Fontes
    # ------------------------------------------------------------

    fonte_logo = ImageFont.truetype(
        str(FONT_BOLD),
        42,
    )

    fonte_subtitulo = ImageFont.truetype(
        str(FONT_NORMAL),
        24,
    )

    fonte_titulo = ImageFont.truetype(
        str(FONT_BOLD),
        42,
    )

    fonte_fonte = ImageFont.truetype(
        str(FONT_NORMAL),
        23,
    )

    fonte_rodape = ImageFont.truetype(
        str(FONT_NORMAL),
        22,
    )

    # ------------------------------------------------------------
    # Logo
    # ------------------------------------------------------------

    draw.text(
        (MARGEM_SEGURA_X, MARGEM_SEGURA_Y),
        "NOTICIAS SHOW DE BOLA",
        font=fonte_logo,
        fill=(255, 255, 255, 255),
    )

    draw.text(
        (MARGEM_SEGURA_X, MARGEM_SEGURA_Y + 58),
        "FUTEBOL  •  NOTÍCIAS  •  ANÁLISES",
        font=fonte_subtitulo,
        fill=(233, 39, 39, 255),
    )

    # ------------------------------------------------------------
    # Selo "inscreva-se" — chamada pra atrair novos seguidores.
    # ------------------------------------------------------------

    fonte_selo = ImageFont.truetype(
        str(FONT_BOLD),
        30,
    )

    texto_selo = "INSCREVA-SE"

    caixa_selo = draw.textbbox(
        (0, 0),
        texto_selo,
        font=fonte_selo,
    )

    largura_selo = (
        caixa_selo[2] - caixa_selo[0] + 56
    )

    selo_x2 = W - MARGEM_SEGURA_X
    selo_x1 = selo_x2 - largura_selo
    selo_y1 = MARGEM_SEGURA_Y
    selo_y2 = selo_y1 + 60

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

    # ------------------------------------------------------------
    # Título
    # ------------------------------------------------------------

    titulo = str(
        noticia.get(
            "titulo",
            "Notícia do futebol",
        )
    )

    titulo_x = MARGEM_SEGURA_X + 40

    largura_titulo_maxima = (
        W - titulo_x - MARGEM_SEGURA_X
    )

    linhas = quebrar_por_largura(
        draw,
        titulo,
        fonte_titulo,
        largura_titulo_maxima,
    )

    y = 720

    for linha in linhas[:4]:

        draw.text(
            (titulo_x, y),
            linha,
            font=fonte_titulo,
            fill=(255, 255, 255, 255),
        )

        y += 52

    # ------------------------------------------------------------
    # Fonte
    # ------------------------------------------------------------

    fonte = str(
        noticia.get(
            "fonte",
            "Google Notícias",
        )
    )

    draw.text(
        (titulo_x, 900),
        f"Fonte: {fonte}",
        font=fonte_fonte,
        fill=(210, 220, 230, 255),
    )

    # ------------------------------------------------------------
    # Rodapé
    # ------------------------------------------------------------

    # O rodapé (faixa 1010-1080) fica perto da borda inferior,
    # que é justamente onde o zoom recorta — usa um respiro
    # pequeno a partir do topo da faixa, em vez da borda de
    # baixo, pra não ser cortado.
    draw.text(
        (MARGEM_SEGURA_X, 1018),
        "NEWS YOUTUBE  •  FUTEBOL  •  NOTÍCIAS  •  ANÁLISES",
        font=fonte_rodape,
        fill=(255, 255, 255, 255),
    )

    destino = (
        IMAGENS_DIR
        / f"noticia_{int(noticia['id'])}_frame.jpg"
    )

    imagem.convert(
        "RGB"
    ).save(
        destino,
        "JPEG",
        quality=95,
        optimize=True,
    )

    return Path(
        destino
    )


# ============================================================================
# VÍDEO
# ============================================================================

def obter_duracao_audio(
    arquivo_audio
):

    arquivo_audio = Path(
        arquivo_audio
    )

    comando = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(arquivo_audio),
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=20,
    )

    if resultado.returncode != 0:
        raise RuntimeError(
            "Não foi possível obter "
            "a duração do áudio."
        )

    try:

        duracao = float(
            resultado.stdout.strip()
        )

    except ValueError:

        raise RuntimeError(
            "Duração do áudio inválida."
        )

    if duracao <= 0:
        raise RuntimeError(
            "Áudio possui duração inválida."
        )

    return duracao


def gerar_video(
    noticia,
    arquivo_audio,
    arquivo_imagem,
):

    numero = int(
        noticia["id"]
    )

    arquivo_audio = Path(
        arquivo_audio
    )

    arquivo_imagem = Path(
        arquivo_imagem
    )

    destino = (
        VIDEOS_DIR
        / f"noticia_{numero}.mp4"
    )

    print()
    print(
        "🎬 MONTANDO VÍDEO"
    )
    print("=" * 75)

    if not arquivo_audio.exists():

        raise RuntimeError(
            f"Áudio não existe: "
            f"{arquivo_audio}"
        )

    if not arquivo_imagem.exists():

        raise RuntimeError(
            f"Imagem não existe: "
            f"{arquivo_imagem}"
        )

    # ------------------------------------------------------------
    # Cria frame completo com Pillow.
    # Nenhum drawtext será usado no FFmpeg.
    # ------------------------------------------------------------

    frame = preparar_frame_video(
        arquivo_imagem,
        noticia,
    )

    duracao = obter_duracao_audio(
        arquivo_audio
    )

    print(
        f"⏱️ Duração do áudio: "
        f"{duracao:.2f}s"
    )

    print(
        f"🖼️ Frame: {frame}"
    )

    # ------------------------------------------------------------
    # FFmpeg simples e robusto, com zoom lento (Ken Burns)
    # pra imagem não ficar parada o vídeo inteiro.
    # ------------------------------------------------------------

    frames_totais = int(
        duracao * FPS
    ) + FPS

    # x/y centralizam o corte do zoom (o padrão do zoompan é
    # ancorar no canto superior esquerdo, o que cortava o
    # rodapé e o selo em vez de manter tudo centralizado).
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

        # Imagem.
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(frame),

        # Áudio.
        "-i",
        str(arquivo_audio),

        # Zoom lento na imagem.
        "-vf",
        filtro_zoom,

        # Vídeo.
        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "21",

        "-pix_fmt",
        "yuv420p",

        # Áudio.
        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-ar",
        "44100",

        # Duração.
        "-t",
        f"{duracao:.3f}",

        "-shortest",

        # Compatibilidade web.
        "-movflags",
        "+faststart",

        str(destino),
    ]

    print()
    print(
        "🎞️ Executando FFmpeg..."
    )

    try:

        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=max(
                180,
                int(duracao * 8),
            ),
        )

    except subprocess.TimeoutExpired:

        raise RuntimeError(
            "FFmpeg excedeu o tempo limite."
        )

    except Exception as erro:

        raise RuntimeError(
            f"Erro executando FFmpeg: {erro}"
        )

    if resultado.returncode != 0:

        print()
        print(
            "❌ FFmpeg apresentou erro:"
        )

        print(
            resultado.stderr[-8000:]
        )

        raise RuntimeError(
            "FFmpeg falhou."
        )

    if not destino.exists():

        raise RuntimeError(
            "FFmpeg terminou, "
            "mas o vídeo não foi criado."
        )

    if destino.stat().st_size < 10000:

        raise RuntimeError(
            "Vídeo criado possui tamanho inválido."
        )

    print()
    print(
        f"✅ VÍDEO CRIADO: {destino}"
    )

    return Path(
        destino
    )


# ============================================================================
# PROCESSAMENTO
# ============================================================================

def processar(
    repetir_erros=False
):

    preparar_diretorios()

    arquivos, status = mostrar_status()

    arquivo = encontrar_proxima_noticia(
        repetir_erros=repetir_erros
    )

    if not arquivo:

        print()

        print(
            "⚠️ Nenhuma notícia disponível para processamento."
        )

        if not repetir_erros:

            print(
                "ℹ️ Notícias com erro não são repetidas automaticamente."
            )

            print(
                "ℹ️ Use --repetir-erros para tentar novamente."
            )

        return

    chave_id = numero_noticia(
        arquivo
    )

    noticia = carregar_noticia(
        arquivo
    )

    # Garante que o ID usado nos arquivos
    # seja sempre inteiro e nunca tuple.
    noticia["id"] = int(
        chave_id
    )

    print()
    print("=" * 75)
    print(
        f"📰 PRÓXIMA NOTÍCIA: noticia_{chave_id}"
    )
    print("=" * 75)

    print(
        f"📰 Título: {noticia['titulo']}"
    )

    print(
        f"🗞️ Fonte: {noticia['fonte']}"
    )

    print(
        f"🔗 URL: {noticia['url']}"
    )

    atualizar_status(
        chave_id,
        "processando",
    )

    try:

        # ========================================================
        # ÁUDIO
        # ========================================================

        print()
        print(
            "🎙️ Etapa 1/3 — Áudio"
        )

        texto = noticia[
            "texto"
        ]

        if not texto:

            raise RuntimeError(
                "Roteiro sem texto para narração."
            )

        arquivo_audio = (
            AUDIOS_DIR
            / f"noticia_{chave_id}.mp3"
        )

        gerar_audio(
            texto,
            arquivo_audio,
        )

        # ========================================================
        # IMAGEM
        # ========================================================

        print()
        print(
            "🖼️ Etapa 2/3 — Imagem"
        )

        arquivo_imagem = procurar_imagem(
            noticia
        )

        # Defesa contra o erro antigo:
        # expected str, bytes or os.PathLike object, not tuple
        if isinstance(
            arquivo_imagem,
            tuple,
        ):

            if not arquivo_imagem:

                raise RuntimeError(
                    "Busca de imagem retornou uma tupla vazia."
                )

            arquivo_imagem = (
                arquivo_imagem[0]
            )

        arquivo_imagem = Path(
            arquivo_imagem
        )

        if not arquivo_imagem.exists():

            raise RuntimeError(
                f"Imagem final não existe: "
                f"{arquivo_imagem}"
            )

        print(
            f"📷 Arquivo final da imagem:"
        )

        print(
            f"   {arquivo_imagem}"
        )

        # ========================================================
        # VÍDEO
        # ========================================================

        print()
        print(
            "🎬 Etapa 3/3 — Vídeo"
        )

        arquivo_video = gerar_video(
            noticia,
            arquivo_audio,
            arquivo_imagem,
        )

        atualizar_status(
            chave_id,
            "concluido",
        )

        print()
        print("=" * 75)
        print(
            "✅ PROCESSAMENTO CONCLUÍDO"
        )
        print("=" * 75)

        print(
            f"📰 Notícia: noticia_{chave_id}"
        )

        print(
            f"🖼️ Imagem: {arquivo_imagem}"
        )

        print(
            f"🎙️ Áudio: {arquivo_audio}"
        )

        print(
            f"🎬 Vídeo: {arquivo_video}"
        )

    except Exception as erro:

        atualizar_status(
            chave_id,
            "erro",
            str(erro),
        )

        print()
        print("=" * 75)
        print(
            "❌ PROCESSAMENTO INTERROMPIDO"
        )
        print("=" * 75)

        print(
            f"Notícia: noticia_{chave_id}"
        )

        print(
            f"Erro: {erro}"
        )

        print()

        print(
            "⚠️ Esta notícia continuará com status de erro."
        )


# ============================================================================
# ARGUMENTOS
# ============================================================================

def argumentos():

    parser = argparse.ArgumentParser(
        description=(
            "NEWS-YOUTUBE — "
            "Gerador de vídeos de notícias"
        )
    )

    parser.add_argument(
        "--repetir-erros",
        action="store_true",
        help=(
            "Tenta novamente notícias "
            "que estão com status de erro."
        ),
    )

    return parser.parse_args()


# ============================================================================
# MAIN
# ============================================================================

def main():

    args = argumentos()

    print()
    print("=" * 75)
    print(
        "🎬 NEWS-YOUTUBE — GERADOR DE VÍDEO"
    )
    print("=" * 75)

    print(
        f"📂 Projeto: {BASE_DIR}"
    )

    print(
        f"📂 Status: {STATUS_FILE}"
    )

    if args.repetir_erros:

        print(
            "🔁 Modo: REPETIR ERROS"
        )

    processar(
        repetir_erros=args.repetir_erros
    )

    print()
    print("=" * 75)
    print(
        "📊 STATUS APÓS EXECUÇÃO"
    )
    print("=" * 75)

    mostrar_status()


if __name__ == "__main__":
    main()
