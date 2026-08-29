from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re

from ranking_noticias import CLUBES_IMPORTANTES


# ============================================================
# CONFIGURAÇÃO
# ============================================================

HORAS_JANELA = 12


# ============================================================
# CONVERSÃO DE DATAS
# ============================================================

def converter_data(data):
    """
    Converte diferentes formatos de data para datetime UTC.

    Aceita:
    - datetime
    - string ISO
    - string RFC 2822
    - string brasileira: DD/MM/YYYY HH:MM
    """

    if not data:
        return None

    # Já é datetime
    if isinstance(data, datetime):

        dt = data

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    # Não é string
    if not isinstance(data, str):
        return None

    data = data.strip()

    if not data:
        return None

    # --------------------------------------------------------
    # ISO 8601
    # --------------------------------------------------------

    try:

        texto = data.replace("Z", "+00:00")

        dt = datetime.fromisoformat(texto)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError):
        pass

    # --------------------------------------------------------
    # RFC 2822
    # Exemplo:
    # Wed, 24 Aug 2026 03:00:00 GMT
    # --------------------------------------------------------

    try:

        dt = parsedate_to_datetime(data)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError, IndexError):
        pass

    # --------------------------------------------------------
    # Formato brasileiro
    # DD/MM/YYYY HH:MM
    # --------------------------------------------------------

    formatos = [
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]

    for formato in formatos:

        try:

            dt = datetime.strptime(
                data,
                formato
            )

            dt = dt.replace(
                tzinfo=timezone.utc
            )

            return dt

        except ValueError:
            continue

    return None


# ============================================================
# ÚLTIMAS 12 HORAS
# ============================================================

def filtrar_ultimas_12h(noticias):
    """
    Mantém somente notícias publicadas nas últimas 12 horas.
    """

    agora = datetime.now(timezone.utc)

    limite = agora - timedelta(
        hours=HORAS_JANELA
    )

    recentes = []
    antigas = 0
    invalidas = 0

    for noticia in noticias:

        data_original = noticia.get(
            "data"
        )

        data = converter_data(
            data_original
        )

        if data is None:

            invalidas += 1
            continue

        # Salva a data normalizada
        noticia["data"] = data

        if data >= limite:

            recentes.append(
                noticia
            )

        else:

            antigas += 1

    print()
    print(
        f"📅 Últimas {HORAS_JANELA} horas"
    )

    print(
        f"   Agora UTC: "
        f"{agora.strftime('%d/%m/%Y %H:%M')}"
    )

    print(
        f"   Limite: "
        f"{limite.strftime('%d/%m/%Y %H:%M')}"
    )

    print(
        f"   ✅ Notícias recentes: "
        f"{len(recentes)}"
    )

    print(
        f"   🗑️ Notícias antigas: "
        f"{antigas}"
    )

    print(
        f"   ⚠️ Sem data/ inválidas: "
        f"{invalidas}"
    )

    return recentes


# ============================================================
# COMPATIBILIDADE
# ============================================================

def filtrar_ultimas_24h(noticias):
    """
    Mantido para compatibilidade com arquivos antigos.

    Atualmente o projeto trabalha com 12 horas.
    """

    agora = datetime.now(timezone.utc)

    limite = agora - timedelta(
        hours=24
    )

    recentes = []
    antigas = 0
    invalidas = 0

    for noticia in noticias:

        data = converter_data(
            noticia.get("data")
        )

        if data is None:

            invalidas += 1
            continue

        noticia["data"] = data

        if data >= limite:

            recentes.append(
                noticia
            )

        else:

            antigas += 1

    print()
    print("📅 Últimas 24 horas")
    print(
        f"   Agora UTC: "
        f"{agora.strftime('%d/%m/%Y %H:%M')}"
    )

    print(
        f"   Limite: "
        f"{limite.strftime('%d/%m/%Y %H:%M')}"
    )

    print(
        f"   ✅ Notícias recentes: "
        f"{len(recentes)}"
    )

    print(
        f"   🗑️ Notícias antigas: "
        f"{antigas}"
    )

    print(
        f"   ⚠️ Sem data/ inválidas: "
        f"{invalidas}"
    )

    return recentes


# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================

def normalizar_texto(texto):
    """
    Normaliza texto para comparação de duplicadas.
    """

    if not texto:
        return ""

    texto = str(texto).lower()

    # Remove acentos de forma simples
    substituicoes = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "ä": "a",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "í": "i",
        "ì": "i",
        "î": "i",
        "ï": "i",
        "ó": "o",
        "ò": "o",
        "õ": "o",
        "ô": "o",
        "ö": "o",
        "ú": "u",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ç": "c",
    }

    for origem, destino in substituicoes.items():

        texto = texto.replace(
            origem,
            destino
        )

    # Remove pontuação
    texto = re.sub(
        r"[^a-z0-9\s]",
        " ",
        texto
    )

    # Remove espaços duplicados
    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# ============================================================
# DUPLICADAS
# ============================================================

def remover_duplicadas(noticias):
    """
    Remove notícias com títulos exatamente iguais
    após normalização.
    """

    resultado = []
    titulos_vistos = set()

    duplicadas = 0

    for noticia in noticias:

        titulo = noticia.get(
            "titulo",
            ""
        )

        titulo_normalizado = normalizar_texto(
            titulo
        )

        if not titulo_normalizado:
            continue

        if titulo_normalizado in titulos_vistos:

            duplicadas += 1
            continue

        titulos_vistos.add(
            titulo_normalizado
        )

        resultado.append(
            noticia
        )

    print()
    print(
        f"🧹 Duplicadas removidas: "
        f"{duplicadas}"
    )

    print(
        f"   Notícias restantes: "
        f"{len(resultado)}"
    )

    return resultado


# ============================================================
# FILTRO EDITORIAL
# ============================================================

PALAVRAS_BLOQUEADAS = [

    # Onde assistir
    "onde assistir",
    "onde assistir ao vivo",
    "onde ver",
    "como assistir",
    "veja onde",
    "veja como assistir",

    # Horários
    "horário",
    "horarios",
    "horários",
    "que horas",

    # Programação
    "programação",
    "programacao",
    "na tv",
    "na televisão",
    "na televisao",
    "futebol hoje na tv",

    # Jogos do dia
    "jogos de hoje",
    "jogo de hoje",
    "jogos hoje",
    "jogos de amanhã",
    "jogo de amanhã",
    "jogos de amanha",
    "jogo de amanha",

    # Transmissões
    "ao vivo",
    "transmissão ao vivo",
    "transmissao ao vivo",
    "transmissão",
    "transmissões",

    # Escalações
    "escalação",
    "escalacao",
    "escalações",
    "escalacoes",
    "provável escalação",

    # Agenda
    "agenda de jogos",
    "agenda do futebol",

]

# Gols isolados relatados minuto a minuto
# (ex.: "aos 23 min, fulano marca...").
PALAVRAS_GOL_ISOLADO = [
    f"aos {minuto} min"
    for minuto in range(1, 52)
]


def eh_conteudo_indesejado(noticia):
    """
    Verifica se o título é inadequado para o nosso canal.
    """

    titulo = noticia.get(
        "titulo",
        ""
    )

    titulo_normalizado = normalizar_texto(
        titulo
    )

    for palavra in PALAVRAS_BLOQUEADAS:

        palavra_normalizada = normalizar_texto(
            palavra
        )

        if palavra_normalizada in titulo_normalizado:

            return True

    for palavra in PALAVRAS_GOL_ISOLADO:

        if palavra in titulo_normalizado:

            return True

    return False


def filtrar_conteudo_editorial(noticias):
    """
    Remove conteúdos que não queremos transformar
    em vídeos.
    """

    aprovadas = []
    removidas = 0

    for noticia in noticias:

        if eh_conteudo_indesejado(
            noticia
        ):

            removidas += 1

            continue

        aprovadas.append(
            noticia
        )

    print()
    print(
        f"🚫 Conteúdo editorial removido: "
        f"{removidas}"
    )

    print(
        f"📰 Notícias após filtro editorial: "
        f"{len(aprovadas)}"
    )

    return aprovadas


# ============================================================
# FILTRO — SOMENTE FUTEBOL
# ============================================================

# Fontes cuja busca já é restrita a futebol (a própria consulta
# do feed já é "futebol"/"mercado da bola" — não precisa
# checar o título de novo).
FONTES_JA_ESCOPADAS_FUTEBOL = (
    "Google Notícias - Futebol",
    "Google Notícias - Mercado da Bola",
)

TERMOS_FUTEBOL = {
    "futebol", "gol", "gols", "artilheiro", "zagueiro",
    "atacante", "meia", "volante", "lateral", "goleiro",
    "técnico", "tecnico", "escalação", "escalacao", "elenco",
    "zaga", "meio-campo", "brasileirão", "brasileirao",
    "libertadores", "sul-americana", "sulamericana",
    "champions league", "liga dos campeões",
    "liga dos campeoes", "premier league", "la liga",
    "bundesliga", "copa do mundo", "copa do brasil",
    "mundial de clubes", "seleção brasileira",
    "selecao brasileira", "cbf", "fifa", "uefa", "conmebol",
    "var", "mercado da bola", "transfer ban", "camisa 10",
}

# Termos fortes de OUTROS esportes. Tem prioridade sobre
# qualquer coincidência de nome de clube (ex.: o atleta
# "Alison dos Santos", de atletismo, não pode passar só
# porque "Santos" também é nome de clube de futebol).
TERMOS_OUTROS_ESPORTES = {
    "tênis", "tenis", "vôlei", "volei", "basquete", "nba",
    "atletismo", "corrida", "maratona", "salto", "arremesso",
    "natação", "natacao", "surfe", "surf", "judô", "judo",
    "ginástica", "ginastica", "mma", "ufc", "boxe",
    "fórmula 1", "formula 1", "f1", "automobilismo", "nfl",
    "beisebol", "handebol", "rúgbi", "rugby", "hipismo",
    "esgrima", "badminton", "squash", "golfe", "ciclismo",
    "triatlo", "copa davis", "wimbledon", "roland garros",
    "us open", "recorde mundial", "olimpíadas", "olimpiadas",
    "paralimpíadas", "paralimpiadas",
}


def eh_sobre_futebol(noticia):
    """
    Verifica se o título menciona futebol de alguma forma
    (termo genérico, clube ou competição).

    Usado só pra fontes que não são exclusivas de futebol
    (ex.: um feed geral de esportes), pra não deixar passar
    notícia de tênis, vôlei, etc.
    """

    titulo = normalizar_texto(
        noticia.get("titulo", "")
    )

    # Um termo forte de outro esporte descarta de cara,
    # mesmo que o título coincida com um nome de clube.
    if any(
        termo in titulo
        for termo in TERMOS_OUTROS_ESPORTES
    ):
        return False

    if any(
        termo in titulo
        for termo in TERMOS_FUTEBOL
    ):
        return True

    if any(
        normalizar_texto(clube) in titulo
        for clube in CLUBES_IMPORTANTES
    ):
        return True

    return False


def filtrar_apenas_futebol(noticias):
    """
    Remove notícias de fontes genéricas de esporte (não
    exclusivas de futebol) cujo título não menciona futebol.
    """

    aprovadas = []
    removidas = 0

    for noticia in noticias:

        fonte = noticia.get("fonte", "")

        if fonte in FONTES_JA_ESCOPADAS_FUTEBOL:
            aprovadas.append(noticia)
            continue

        if eh_sobre_futebol(noticia):
            aprovadas.append(noticia)
            continue

        removidas += 1

    print()
    print(
        f"⚽ Notícias de outros esportes removidas: "
        f"{removidas}"
    )

    print(
        f"📰 Notícias após filtro de futebol: "
        f"{len(aprovadas)}"
    )

    return aprovadas


# ============================================================
# FILTRO COMPLETO
# ============================================================

def preparar_noticias(noticias):
    """
    Executa o pipeline básico:

    1. últimas 12 horas
    2. filtro editorial
    3. somente futebol
    4. remoção de duplicadas
    """

    noticias = filtrar_ultimas_12h(
        noticias
    )

    noticias = filtrar_conteudo_editorial(
        noticias
    )

    noticias = filtrar_apenas_futebol(
        noticias
    )

    noticias = remover_duplicadas(
        noticias
    )

    return noticias


# ============================================================
# TESTE
# ============================================================

if __name__ == "__main__":

    print(
        "🧪 filtrar_noticias.py"
    )

    print(
        f"⏱️ Janela atual: "
        f"{HORAS_JANELA} horas"
    )

    print(
        "✅ Módulo carregado corretamente."
    )
