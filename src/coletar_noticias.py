import re
import feedparser
import requests

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


# ============================================================
# FEEDS
# ============================================================

FEEDS = {
    "Google Notícias - Futebol": (
        "https://news.google.com/rss/search?"
        "q=futebol&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    ),

    "Google Notícias - Mercado da Bola": (
        "https://news.google.com/rss/search?"
        "q=mercado+da+bola&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    ),

    "UOL Esporte": (
        "https://rss.uol.com.br/feed/esporte.xml"
    ),
}


# ============================================================
# DATAS EM PORTUGUÊS (ex.: feed do UOL)
# ============================================================

_DIAS_PT_EN = {
    "dom": "Sun", "seg": "Mon", "ter": "Tue", "qua": "Wed",
    "qui": "Thu", "sex": "Fri", "sab": "Sat", "sáb": "Sat",
}

_MESES_PT_EN = {
    "jan": "Jan", "fev": "Feb", "mar": "Mar", "abr": "Apr",
    "mai": "May", "jun": "Jun", "jul": "Jul", "ago": "Aug",
    "set": "Sep", "out": "Oct", "nov": "Nov", "dez": "Dec",
}


def _traduzir_data_pt_en(texto):
    """
    Troca abreviações de dia/mês em português (ex.: "Qui, 27 Ago 2026")
    pelas equivalentes em inglês, pra dar pra usar parsedate_to_datetime
    (formato RFC 2822, que só reconhece nomes em inglês).
    """

    def substituir(match):

        palavra = match.group(0)

        chave = palavra.lower().rstrip(".")

        return (
            _DIAS_PT_EN.get(chave)
            or _MESES_PT_EN.get(chave)
            or palavra
        )

    return re.sub(
        r"[A-Za-zÀ-ÿ]+",
        substituir,
        texto,
    )


# ============================================================
# NORMALIZAR DATA
# ============================================================

def normalizar_data(item):
    """
    Converte a data do RSS para datetime UTC.

    Prioriza os campos *_parsed do feedparser.
    Depois tenta published/updated como texto.

    Retorna:
        datetime com timezone UTC
        ou None se não conseguir identificar a data.
    """

    # --------------------------------------------------------
    # published_parsed
    # --------------------------------------------------------

    if item.get("published_parsed"):

        try:
            return datetime(
                *item["published_parsed"][:6],
                tzinfo=timezone.utc
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # updated_parsed
    # --------------------------------------------------------

    if item.get("updated_parsed"):

        try:
            return datetime(
                *item["updated_parsed"][:6],
                tzinfo=timezone.utc
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # published como texto
    # --------------------------------------------------------

    texto = item.get("published")

    if texto:

        try:
            data = parsedate_to_datetime(texto)

            if data.tzinfo is None:
                data = data.replace(
                    tzinfo=timezone.utc
                )

            return data.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # updated como texto
    # --------------------------------------------------------

    texto = item.get("updated")

    if texto:

        try:
            data = parsedate_to_datetime(texto)

            if data.tzinfo is None:
                data = data.replace(
                    tzinfo=timezone.utc
                )

            return data.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # published/updated com dia/mês em português
    # (ex.: feed do UOL: "Qui, 27 Ago 2026 22:35:00 -0300")
    # --------------------------------------------------------

    texto = (
        item.get("published")
        or item.get("updated")
    )

    if texto:

        try:
            data = parsedate_to_datetime(
                _traduzir_data_pt_en(texto)
            )

            if data.tzinfo is None:
                data = data.replace(
                    tzinfo=timezone.utc
                )

            return data.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    return None


# ============================================================
# FORMATAR DATA PARA EXIBIÇÃO
# ============================================================

def formatar_data(data):

    if not data:
        return "Data desconhecida"

    if isinstance(data, datetime):

        data_local = data.astimezone()

        return data_local.strftime(
            "%d/%m/%Y %H:%M"
        )

    return str(data)


# ============================================================
# COLETAR UM FEED
# ============================================================

def extrair_publicador(item):
    """
    Nome do veículo original de uma entrada de RSS (ex.:
    "ESPN Brasil", "ge"). O Google Notícias expõe isso no
    campo <source> de cada item; feeds diretos (ex.: UOL) não
    têm esse campo, e nesse caso retorna "".
    """

    fonte = item.get("source")

    if isinstance(fonte, dict):
        return str(fonte.get("title", "") or "").strip()

    return ""


def coletar_feed(nome, url):

    print(
        f"\n🔎 Consultando: {nome}"
    )

    try:

        resposta = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"
                )
            },
            timeout=20
        )

        print(
            f"   HTTP: {resposta.status_code}"
        )

        if resposta.status_code != 200:

            print(
                f"   ❌ Erro HTTP: "
                f"{resposta.status_code}"
            )

            return []

        feed = feedparser.parse(
            resposta.content
        )

        if feed.bozo:

            print(
                "   ⚠️ Feed retornou um aviso "
                "de interpretação."
            )

        print(
            f"   Notícias encontradas: "
            f"{len(feed.entries)}"
        )

        noticias = []

        for item in feed.entries:

            data = normalizar_data(
                item
            )

            noticia = {

                "titulo": item.get(
                    "title",
                    "Sem título"
                ),

                "link": item.get(
                    "link",
                    ""
                ),

                # IMPORTANTE:
                # Mantemos datetime aqui.
                "data": data,

                "fonte": nome,

                # Nome do veículo original (ex.: "ESPN Brasil",
                # "ge"). O Google Notícias sempre acrescenta
                # " - Veículo" no final do título — guardamos
                # esse nome à parte pra poder tirar o sufixo do
                # título usado no YouTube (senão o vídeo parece
                # ser do veículo, não do canal).
                "publicador": extrair_publicador(
                    item
                ),

                "resumo": item.get(
                    "summary",
                    ""
                ),
            }

            noticias.append(
                noticia
            )

        return noticias

    except requests.RequestException as erro:

        print(
            f"   ❌ Erro de conexão: "
            f"{erro}"
        )

        return []

    except Exception as erro:

        print(
            f"   ❌ Erro inesperado: "
            f"{erro}"
        )

        return []


# ============================================================
# COLETAR TODOS OS FEEDS
# ============================================================

def coletar_noticias():

    noticias = []

    for nome, url in FEEDS.items():

        noticias.extend(
            coletar_feed(
                nome,
                url
            )
        )

    return noticias


# ============================================================
# MOSTRAR NOTÍCIAS
# ============================================================

def mostrar_noticias(noticias):

    print(
        "\n" + "=" * 70
    )

    print(
        f"📰 TOTAL: "
        f"{len(noticias)} NOTÍCIAS"
    )

    print(
        "=" * 70
    )

    for i, noticia in enumerate(
        noticias,
        1
    ):

        print(
            f"\n[{i}] "
            f"{noticia['titulo']}"
        )

        print(
            f"    Data:  "
            f"{formatar_data(noticia['data'])}"
        )

        print(
            f"    Fonte: "
            f"{noticia['fonte']}"
        )

        print(
            f"    Link:  "
            f"{noticia['link']}"
        )


# ============================================================
# TESTE DIRETO
# ============================================================

if __name__ == "__main__":

    noticias = coletar_noticias()

    mostrar_noticias(
        noticias
    )
