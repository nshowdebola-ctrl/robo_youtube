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

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

CREDENCIAIS_DIR = BASE_DIR / "credenciais"

CLIENT_SECRET_FILE = CREDENCIAIS_DIR / "client_secret.json"
TOKEN_FILE = CREDENCIAIS_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/youtube"]

# 17 = Sports, categoria padrão do YouTube.
CATEGORIA_ESPORTES = "17"


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

            credenciais.refresh(Request())

        else:

            fluxo = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE),
                SCOPES,
            )

            credenciais = fluxo.run_local_server(
                port=0,
                open_browser=False,
            )

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
            "title": titulo[:100],
            "description": descricao[:5000],
            "tags": tags[:500],
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
