#!/usr/bin/env python3

"""
Autenticação e upload de vídeo pra YouTube Data API v3.

Módulo genérico, reaproveitado pelas duas pipelines (vídeo
principal e Shorts) — cada uma só monta título/descrição/tags
e chama enviar_video().

CREDENCIAIS:

Coloque o arquivo baixado do Google Cloud Console (tipo "App
para computador") em:

    credenciais/client_secret.json

Na primeira execução, uma janela do navegador vai abrir pra
você autorizar o acesso à conta do canal. Depois disso, o
token fica salvo em credenciais/token.json e as próximas
execuções não pedem autorização de novo (a menos que o
token seja revogado).
"""

import time
from datetime import datetime
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from whatsapp_notify import send_whatsapp


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

CREDENCIAIS_DIR = BASE_DIR / "credenciais"

CLIENT_SECRET_FILE = CREDENCIAIS_DIR / "client_secret.json"
TOKEN_FILE = CREDENCIAIS_DIR / "token.json"

# force-ssl é superset de "youtube" (cobre upload/gestão) e é o
# único scope aceito por commentThreads.insert — precisamos dele
# pro comentário automático com o link afiliado.
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

# 17 = Sports, categoria padrão do YouTube.
CATEGORIA_ESPORTES = "17"

# Marca quando o último alerta de token expirado foi mandado, pra
# não spammar WhatsApp a cada execução do cron (roda várias vezes
# por dia) enquanto o usuário não reautentica.
MARCADOR_ALERTA_TOKEN = CREDENCIAIS_DIR / ".alerta_token_expirado"
INTERVALO_MINIMO_ALERTA_SEGUNDOS = 6 * 60 * 60


def _avisar_token_expirado(erro):

    try:
        if MARCADOR_ALERTA_TOKEN.exists():
            ultimo = float(MARCADOR_ALERTA_TOKEN.read_text().strip() or 0)
            if time.time() - ultimo < INTERVALO_MINIMO_ALERTA_SEGUNDOS:
                return
    except (OSError, ValueError):
        pass

    send_whatsapp(
        "⚠️ news-youtube: o token do YouTube expirou/foi revogado "
        "e parou de publicar vídeo. Rode "
        "'python3 src/reautenticar_youtube.py' pra renovar."
    )

    try:
        MARCADOR_ALERTA_TOKEN.write_text(str(time.time()))
    except OSError:
        pass


def _limpar_alerta_token():
    try:
        MARCADOR_ALERTA_TOKEN.unlink(missing_ok=True)
    except OSError:
        pass


def gerado_hoje(caminho_video):
    """
    True se o arquivo de vídeo foi gerado (mtime) na mesma data
    local de hoje.

    Usado pelos 3 scripts de publicação pra não sair, com atraso
    de um dia (ex.: quando esbarra na cota diária de upload do
    YouTube), vídeo/Short/resumo com conteúdo datado ("notícia de
    hoje", "Resumo do dia — 06/09") que já ficou velho.
    """
    try:
        mtime = datetime.fromtimestamp(Path(caminho_video).stat().st_mtime)
    except OSError:
        return False
    return mtime.date() == datetime.now().date()


# ============================================================
# AUTENTICAÇÃO
# ============================================================

def autenticar():
    """
    Retorna um cliente autenticado da YouTube Data API v3.

    Reaproveita o token salvo se ainda for válido; renova
    automaticamente se estiver expirado; só pede autorização
    de novo (abre o navegador) se não existir token nenhum.
    """

    if not CLIENT_SECRET_FILE.exists():

        raise RuntimeError(
            f"Credenciais não encontradas em "
            f"{CLIENT_SECRET_FILE}. Baixe o client_secret.json "
            f"do Google Cloud Console e coloque nesse caminho."
        )

    credenciais = None

    if TOKEN_FILE.exists():

        credenciais = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            SCOPES,
        )

    if not credenciais or not credenciais.valid:

        if (
            credenciais
            and credenciais.expired
            and credenciais.refresh_token
        ):

            try:
                credenciais.refresh(Request())
            except RefreshError as erro:
                _avisar_token_expirado(erro)
                raise

        else:

            fluxo = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE),
                SCOPES,
            )

            credenciais = fluxo.run_local_server(
                port=0,
                open_browser=False,
            )

        _limpar_alerta_token()

        CREDENCIAIS_DIR.mkdir(parents=True, exist_ok=True)

        TOKEN_FILE.write_text(
            credenciais.to_json(),
            encoding="utf-8",
        )

    return build(
        "youtube",
        "v3",
        credentials=credenciais,
    )


# ============================================================
# UPLOAD
# ============================================================

# O YouTube limita as tags pela soma dos caracteres de todas
# juntas (separadas por vírgula), não pela quantidade de tags.
# 495 (quase no limite oficial de 500) já deu "invalid video
# keywords" na prática (resumo_1, 2026-09-05/06) mesmo contando
# em bytes UTF-8 — o limite real parece mais apertado do que o
# documentado. Usando 350 com boa margem de segurança.
LIMITE_CARACTERES_TAGS = 350

# Limite real de título do YouTube.
LIMITE_CARACTERES_TITULO = 100


def _truncar_titulo(titulo, limite=LIMITE_CARACTERES_TITULO):
    """
    Corta o título respeitando o limite do YouTube sem quebrar
    no meio de uma palavra (ex.: "...da Grécia. O jo").
    """

    titulo = titulo.strip()

    if len(titulo) <= limite:
        return titulo

    reticencias = "…"

    corte = titulo[: limite - len(reticencias)]
    corte = corte.rsplit(" ", 1)[0].rstrip(" ,;:-")

    return corte + reticencias


def _limitar_tags_por_caracteres(tags, limite=LIMITE_CARACTERES_TAGS):
    """
    O limite do YouTube é em bytes UTF-8 da string final (separada
    por vírgulas), não em caracteres — acentos/cedilha ocupam 2
    bytes cada, então contar por len() subestima o tamanho real e
    deixa passar listas que o YouTube rejeita (invalidTags).
    """

    selecionadas = []
    total = 0

    for tag in tags:

        acrescimo = len(tag.encode("utf-8")) + (1 if selecionadas else 0)

        if total + acrescimo > limite:
            break

        selecionadas.append(tag)
        total += acrescimo

    return selecionadas


def enviar_video(
    youtube,
    caminho_video,
    titulo,
    descricao,
    tags,
    privacy_status="public",
    category_id=CATEGORIA_ESPORTES,
):
    """
    Sobe um vídeo pro canal autenticado. Retorna o ID do
    vídeo no YouTube.
    """

    corpo = {

        "snippet": {
            "title": _truncar_titulo(titulo),
            "description": descricao[:5000],
            "tags": _limitar_tags_por_caracteres(tags),
            "categoryId": category_id,
        },

        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(caminho_video),
        chunksize=-1,
        resumable=True,
        mimetype="video/mp4",
    )

    requisicao = youtube.videos().insert(
        part="snippet,status",
        body=corpo,
        media_body=media,
    )

    resposta = None

    while resposta is None:

        status, resposta = requisicao.next_chunk()

        if status:

            print(
                f"   ⬆️ Enviando... "
                f"{int(status.progress() * 100)}%"
            )

    return resposta["id"]
