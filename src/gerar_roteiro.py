#!/usr/bin/env python3

import json
import re
from pathlib import Path
from urllib.parse import urlparse, quote

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DIR_ROTEIROS = (
    BASE_DIR
    / "dados"
    / "roteiros"
)

CANAL = "Noticias Show de Bola"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": (
        "pt-BR,pt;q=0.9,en;q=0.8"
    ),
}

TIMEOUT = 15

OLLAMA_URL = (
    "http://127.0.0.1:11434/api/generate"
)

OLLAMA_MODEL = "qwen2.5:3b"

# Aproximadamente 60 segundos de narração
# (~14,4 caracteres por segundo na voz pt-BR usada).
MIN_CHARS = 750
MAX_CHARS = 950


# ============================================================
# UTILITÁRIOS
# ============================================================

def limpar(texto):
    """
    Remove espaços duplicados e quebras de linha.
    """
    return re.sub(
        r"\s+",
        " ",
        str(texto or "")
    ).strip()


def limitar_texto(texto, minimo, maximo):
    """
    Ajusta um texto para não ultrapassar o máximo,
    tentando preservar frases completas.
    """

    texto = limpar(texto)

    if len(texto) <= maximo:
        return texto

    corte = texto[:maximo]

    # Tenta terminar na última frase.
    posicao = max(
        corte.rfind(". "),
        corte.rfind("! "),
        corte.rfind("? "),
    )

    if posicao >= minimo:
        return corte[:posicao + 1].strip()

    # Caso não encontre frase completa,
    # corta na última palavra.
    corte = corte.rsplit(" ", 1)[0]

    return corte.rstrip(" ,;:-") + "."


# ============================================================
# RESOLVER LINK REAL DO GOOGLE NOTÍCIAS
# ============================================================

def _resolver_link_google_news(url):
    """
    O link que vem do RSS do Google Notícias é uma página
    intermediária (news.google.com), não a matéria em si.

    Reproduz o mesmo mecanismo que o app/site do Google usa
    pra resolver essa página pra URL real da fonte, então
    dá pra raspar o texto de verdade da matéria.

    Retorna a URL real, ou a URL original se não conseguir
    resolver (comportamento do Google não é documentado e
    pode mudar).
    """

    try:

        partes = urlparse(url)

        caminho = partes.path.split("/")

        eh_google_news = (
            partes.hostname == "news.google.com"
            and len(caminho) > 1
            and caminho[-2] in ("articles", "read")
        )

        if not eh_google_news:
            return url

        base64_str = caminho[-1]

        pagina = requests.get(
            f"https://news.google.com/articles/{base64_str}",
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        pagina.raise_for_status()

        soup = BeautifulSoup(
            pagina.text,
            "html.parser"
        )

        elemento = soup.select_one(
            "c-wiz > div[jscontroller]"
        )

        if elemento is None:
            return url

        assinatura = elemento.get("data-n-a-sg")
        timestamp = elemento.get("data-n-a-ts")

        if not assinatura or not timestamp:
            return url

        payload = [
            "Fbv4je",
            (
                '["garturlreq",[["X","X",["X","X"],null,null,1,1,'
                '"US:en",null,1,null,null,null,null,null,0,1],'
                f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
                f'"{base64_str}",{timestamp},"{assinatura}"]'
            ),
        ]

        resposta = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={
                **HEADERS,
                "Content-Type": (
                    "application/x-www-form-urlencoded;"
                    "charset=UTF-8"
                ),
            },
            data=f"f.req={quote(json.dumps([[payload]]))}",
            timeout=TIMEOUT,
        )

        resposta.raise_for_status()

        dados = json.loads(
            resposta.text.split("\n\n")[1]
        )[:-2]

        url_real = json.loads(dados[0][2])[1]

        return url_real or url

    except Exception:
        return url


# ============================================================
# EXTRAIR TEXTO DA MATÉRIA
# ============================================================

def extrair_texto_materia(url):

    if not isinstance(url, str):
        return ""

    url = url.strip()

    if not url.startswith("http"):
        return ""

    url = _resolver_link_google_news(url)

    try:

        resposta = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        resposta.raise_for_status()

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # Remove elementos que não são conteúdo
        # ----------------------------------------------------

        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "svg",
                "nav",
                "footer",
                "header",
                "form",
            ]
        ):

            tag.decompose()

        # ----------------------------------------------------
        # Tenta localizar conteúdo principal
        # ----------------------------------------------------

        candidatos = []

        for seletor in [
            "article",
            "main",
            "[role='main']",
            ".article",
            ".article-body",
            ".post-content",
            ".entry-content",
            ".content",
        ]:

            try:

                encontrados = soup.select(
                    seletor
                )

                candidatos.extend(
                    encontrados
                )

            except Exception:
                pass

        # ----------------------------------------------------
        # Primeiro tenta os blocos principais
        # ----------------------------------------------------

        paragrafos = []

        for bloco in candidatos:

            for p in bloco.find_all("p"):

                texto = limpar(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(texto) >= 40:

                    paragrafos.append(
                        texto
                    )

        # ----------------------------------------------------
        # Se não encontrou, usa todos os <p>
        # ----------------------------------------------------

        if not paragrafos:

            for p in soup.find_all("p"):

                texto = limpar(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(texto) >= 40:

                    paragrafos.append(
                        texto
                    )

        # ----------------------------------------------------
        # Remove duplicados
        # ----------------------------------------------------

        unicos = []

        vistos = set()

        for paragrafo in paragrafos:

            chave = paragrafo.lower()

            if chave in vistos:
                continue

            vistos.add(chave)

            unicos.append(
                paragrafo
            )

        texto = " ".join(
            unicos
        )

        return texto[:12000]

    except Exception as erro:

        print(
            f"   ⚠️ Não foi possível "
            f"extrair a matéria: {erro}"
        )

        return ""


# ============================================================
# DETECTAR TIPO DA NOTÍCIA
# ============================================================

def detectar_tipo(titulo):

    t = titulo.lower()

    regras = [

        (
            "transferencia",
            [
                "venda",
                "vendido",
                "vendeu",
                "transferência",
                "transferencia",
                "negociação",
                "negociacao",
            ],
        ),

        (
            "contratacao",
            [
                "contrata",
                "contratação",
                "contratacao",
                "acerta contratação",
                "reforço",
                "reforco",
                "anuncia",
                "novo reforço",
                "novo reforco",
            ],
        ),

        (
            "demissao",
            [
                "demite",
                "demitido",
                "demissão",
                "demissao",
                "deixa o clube",
                "deixa clube",
            ],
        ),

        (
            "vitoria",
            [
                "vence",
                "venceu",
                "vitória",
                "vitoria",
                "atropela",
                "ganha",
                "ganhou",
            ],
        ),

        (
            "derrota",
            [
                "perde",
                "perdeu",
                "derrota",
                "cai",
                "eliminado",
                "eliminada",
            ],
        ),

        (
            "empate",
            [
                "empata",
                "empatou",
                "empate",
            ],
        ),

        (
            "lesao",
            [
                "lesão",
                "lesao",
                "machucado",
                "desfalque",
                "fora por",
            ],
        ),

        (
            "patrocinio",
            [
                "patrocinadora",
                "patrocínio",
                "patrocinio",
                "patrocina",
                "patrocinador",
            ],
        ),
    ]

    for tipo, termos in regras:

        if any(
            termo in t
            for termo in termos
        ):

            return tipo

    return "futebol"


# ============================================================
# FALLBACK — SEM IA
# ============================================================

def fallback_roteiro(
    titulo,
    tipo,
):
    """
    Roteiro seguro, usado quando o Ollama não consegue
    reescrever a notícia.

    IMPORTANTE: nunca reproduz o texto_materia (matéria
    raspada de terceiros) literalmente na narração — isso
    seria republicar o texto de outro veículo palavra por
    palavra, o que é violação de direitos autorais, mesmo
    que apenas narrado. O texto_materia só serve de fonte
    de fatos pro Ollama reescrever; aqui usamos somente o
    título (fato/manchete, não protegido por copyright) e
    um comentário genérico por tipo de notícia.
    """

    # --------------------------------------------------------
    # Sem citar a matéria de terceiros, NÃO inventar fatos.
    # --------------------------------------------------------

    aberturas = {

        "transferencia":
            "Mercado da bola em movimento.",

        "contratacao":
            "Mercado da bola agitado.",

        "demissao":
            "Mudança importante no futebol.",

        "vitoria":
            "Resultado de destaque no futebol.",

        "derrota":
            "Derrota que repercute no futebol.",

        "empate":
            "Empate que chama atenção.",

        "lesao":
            "Notícia importante sobre o elenco.",

        "patrocinio":
            "Novidade importante fora das quatro linhas.",

        "futebol":
            "Notícia em destaque no futebol.",
    }

    abertura = aberturas.get(
        tipo,
        "Notícia em destaque no futebol."
    )

    desenvolvimentos = {

        "transferencia":
            "A negociação chama atenção no mercado da bola "
            "e pode mexer com os planos do clube pra "
            "sequência da temporada.",

        "contratacao":
            "A chegada pode reforçar o elenco e muda o "
            "cenário do time pros próximos jogos.",

        "demissao":
            "A saída marca uma mudança importante nos "
            "bastidores e deve repercutir nos próximos dias.",

        "vitoria":
            "O resultado pode pesar na briga pelos "
            "objetivos da equipe e aumenta a confiança "
            "do grupo.",

        "derrota":
            "Agora a equipe precisa reagir rápido e "
            "corrigir os erros que apareceram na partida.",

        "empate":
            "O resultado deixa sensação de oportunidade "
            "perdida, pensando na sequência da competição.",

        "lesao":
            "A situação preocupa a comissão técnica e pode "
            "mudar os planos da equipe pros próximos jogos.",

        "patrocinio":
            "A parceria reforça a estrutura do clube fora "
            "de campo e mostra o interesse do mercado.",

        "futebol":
            "O assunto repercute entre os torcedores e deve "
            "ganhar mais desdobramentos nos próximos dias.",
    }

    desenvolvimento = desenvolvimentos.get(
        tipo,
        desenvolvimentos["futebol"]
    )

    contextos = {

        "transferencia":
            "Esse tipo de movimentação costuma gerar bastante "
            "repercussão entre os torcedores nas redes sociais.",

        "contratacao":
            "Reforços assim tendem a aumentar a expectativa "
            "da torcida pra sequência da temporada.",

        "demissao":
            "Trocas de comando costumam gerar debate entre "
            "torcedores e especialistas sobre os próximos "
            "passos do clube.",

        "vitoria":
            "Resultados assim ajudam a fortalecer o ambiente "
            "dentro do elenco.",

        "derrota":
            "Esse tipo de resultado costuma acender o alerta "
            "entre torcida e diretoria.",

        "empate":
            "Resultados assim geram debate sobre o que pode "
            "melhorar nos próximos jogos.",

        "lesao":
            "Departamento médico e comissão técnica costumam "
            "acompanhar de perto a evolução desses casos.",

        "patrocinio":
            "Esse tipo de acordo costuma trazer mais "
            "visibilidade e recursos pro clube.",

        "futebol":
            "Fique de olho, porque assuntos assim costumam "
            "evoluir rápido no mundo do futebol.",
    }

    contexto = contextos.get(
        tipo,
        contextos["futebol"]
    )

    texto = (
        f"{abertura} "
        f"{titulo}. "
        f"{desenvolvimento} "
        f"{contexto} "
        f"Fique ligado no canal pra acompanhar as "
        f"próximas atualizações sobre o assunto."
    )

    return limitar_texto(
        texto,
        200,
        MAX_CHARS
    )


# ============================================================
# OLLAMA — ROTEIRO
# ============================================================

def gerar_com_ollama(
    titulo,
    fonte,
    texto_materia
):

    prompt = f"""
Você é o roteirista principal do canal brasileiro
de notícias esportivas "Noticias Show de Bola".

Sua tarefa é transformar a notícia fornecida em uma
narração jornalística para vídeo no YouTube.

DURAÇÃO:
A narração deve durar aproximadamente 60 segundos.

TAMANHO:
Escreva entre {MIN_CHARS} e {MAX_CHARS} caracteres.

REGRAS OBRIGATÓRIAS:

- Use SOMENTE informações presentes no título
  ou no texto disponível da matéria.
- ESCREVA COM SUAS PRÓPRIAS PALAVRAS. NÃO copie frases
  ou trechos literais do texto da matéria — reescreva os
  fatos numa narração original. Copiar o texto de outro
  veículo é violação de direitos autorais.
- Não copie citações longas entre aspas do texto da
  matéria; se precisar citar alguém, resuma o que a
  pessoa disse em vez de reproduzir a frase inteira.
- NÃO invente informações.
- NÃO invente valores.
- NÃO invente placares.
- NÃO invente datas.
- NÃO invente declarações.
- NÃO invente jogadores.
- NÃO invente clubes.
- NÃO invente lesões.
- NÃO invente negociações.
- Não transforme especulação em fato.
- Não diga que algo foi confirmado se o material
  não confirmar.
- Preserve corretamente nomes próprios.
- Não repita o título inteiro várias vezes.
- Escreva como uma notícia esportiva brasileira.
- Linguagem natural para narração.
- Frases curtas e claras.
- O texto deve ter ritmo.
- Comece com um gancho interessante.
- Apresente o fato principal.
- Explique os detalhes disponíveis.
- Apresente o contexto que estiver no material.
- Termine de forma natural.
- NÃO use a frase "agora fica a expectativa
  pelos próximos capítulos".
- NÃO coloque título.
- NÃO coloque tópicos.
- NÃO coloque aspas.
- NÃO explique o que você está fazendo.
- Retorne SOMENTE a narração.

CANAL:
{CANAL}

TÍTULO ORIGINAL:
{titulo}

FONTE:
{fonte}

TEXTO DA MATÉRIA:
{texto_materia[:10000]}
""".strip()

    try:

        resposta = requests.post(

            OLLAMA_URL,

            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.25,
                },
            },

            timeout=300,
        )

        resposta.raise_for_status()

        texto = (
            resposta
            .json()
            .get("response", "")
        )

        texto = limpar(texto)

        # Remove possíveis aspas.
        texto = texto.strip(
            "\"' "
        )

        # Remove marcadores caso a IA tenha colocado.
        texto = re.sub(
            r"^(narração|narra[cç][aã]o)\s*:\s*",
            "",
            texto,
            flags=re.IGNORECASE,
        )

        texto = limpar(texto)

        # Só rejeita se a IA escreveu pouco demais (não dá
        # pra completar sem inventar). Se escreveu além do
        # limite, corta no tamanho certo em vez de descartar
        # a resposta inteira.
        if len(texto) >= MIN_CHARS:

            return limitar_texto(
                texto,
                MIN_CHARS,
                MAX_CHARS
            )

    except Exception as erro:

        print(
            f"   ⚠️ Ollama indisponível: "
            f"{erro}"
        )

    return None


# ============================================================
# GERAR TÍTULO PARA YOUTUBE
# ============================================================

# O pipeline principal agora grava vertical (ver W/H em
# gerar_video.py) — precisa do "#Shorts" no título pra
# competir na aba Shorts igual o pipeline de resultado, que
# performa muito melhor (vídeo horizontal curto de antes não
# era nem Short nem vídeo longo de verdade).
SUFIXO_SHORTS = " #Shorts"

LIMITE_TITULO_YOUTUBE = 100


def gerar_titulo_youtube(
    titulo_original,
    texto,
    publicador=""
):
    """
    Título determinístico: usa o próprio título original
    da notícia (sem chamar IA), removendo o sufixo
    " - Veículo" que o Google Notícias acrescenta (senão o
    vídeo parece ser do veículo original, não do canal), e
    acrescenta "#Shorts" no final.
    """

    titulo = limpar(
        titulo_original
    )

    publicador = limpar(
        publicador
    )

    sufixo = f" - {publicador}"

    if (
        publicador
        and titulo.lower().endswith(sufixo.lower())
    ):

        titulo = titulo[
            : -len(sufixo)
        ].strip()

    limite = LIMITE_TITULO_YOUTUBE - len(SUFIXO_SHORTS)

    if len(titulo) > limite:

        corte = titulo[:limite].rsplit(" ", 1)[0].rstrip(" ,;:-")
        titulo = corte + "…"

    return titulo + SUFIXO_SHORTS


# ============================================================
# GERAR DESCRIÇÃO
# ============================================================

def gerar_descricao(
    titulo,
    texto,
    fonte
):
    """
    Descrição determinística (template), sem chamar IA.
    """

    return (
        f"{titulo}. "
        f"Confira os principais detalhes desta "
        f"notícia no Noticias Show de Bola. "
        f"Inscreva-se no canal para acompanhar "
        f"as principais notícias do futebol.\n\n"
        f"#Shorts #futebol #noticias"
    )


# ============================================================
# GERAR TAGS
# ============================================================

# Orçamento de tags do YouTube (495 caracteres, ver
# youtube_upload.py) dividido em duas partes: ~290 caracteres
# de base fixa relacionada a futebol/canal, e até ~200
# caracteres reservados pras palavras específicas extraídas do
# título de cada notícia — antes a base era só ~205 caracteres
# e sobrava orçamento sem uso (ex.: um vídeo saindo com só 116
# de 500 caracteres de tags).
ORCAMENTO_TAGS_TITULO = 200


def gerar_tags(
    titulo,
    texto
):
    """
    Tags determinísticas: base fixa do canal + palavras
    relevantes extraídas do título (sem chamar IA).
    """

    palavras = re.findall(
        r"[A-Za-zÀ-ÿ0-9]+",
        titulo
    )

    # Base fixa (~290 caracteres com separadores).
    tags = [
        "futebol",
        "notícias de futebol",
        "futebol hoje",
        "notícias futebol",
        "mercado da bola",
        "transferências",
        "futebol brasileiro",
        "Brasileirão",
        "notícias esportivas",
        "futebol ao vivo",
        "últimas notícias",
        "notícias de hoje",
        "futebol mundial",
        "shorts",
        "Noticias Show de Bola",
        "campeonato brasileiro",
        "seleção brasileira",
        "resumo de jogo",
    ]

    orcamento_usado = 0

    for palavra in palavras:

        if len(palavra) < 4:
            continue

        if palavra.lower() in [
            x.lower()
            for x in tags
        ]:
            continue

        acrescimo = len(palavra) + 1

        if orcamento_usado + acrescimo > ORCAMENTO_TAGS_TITULO:
            continue

        tags.append(
            palavra
        )

        orcamento_usado += acrescimo

    return tags


# ============================================================
# SALVAR ROTEIRO
# ============================================================

def _noticia_serializavel(noticia):
    """
    Copia a notícia trocando campos não serializáveis
    (ex.: datetime vindo do RSS) por texto.
    """

    copia = dict(noticia)

    data = copia.get("data")

    if hasattr(data, "isoformat"):
        copia["data"] = data.isoformat()

    return copia


def salvar_roteiro(
    indice,
    noticia,
    titulo_youtube,
    gancho,
    texto,
    tipo,
    descricao,
    tags
):

    destino = (
        DIR_ROTEIROS
        / f"noticia_{indice}.json"
    )

    dados = {

        "noticia": _noticia_serializavel(noticia),

        "roteiro": {

            # Mantém o campo usado pelo
            # gerar_video.py atual.
            "titulo": titulo_youtube,

            "titulo_original":
                limpar(
                    noticia.get(
                        "titulo"
                    )
                ),

            "gancho": gancho,

            "roteiro": texto,

            "tipo": tipo,

            "fonte":
                limpar(
                    noticia.get(
                        "fonte"
                    )
                ),

            "descricao":
                descricao,

            "tags":
                tags,

            "canal": CANAL,
        },
    }

    with open(
        destino,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            dados,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    return destino


# ============================================================
# PRÓXIMO ÍNDICE
# ============================================================

def proximo_indice_roteiro():
    """
    Devolve o próximo número de roteiro a ser usado,
    com base no maior noticia_N.json já existente.

    Isso mantém os IDs estáveis entre execuções, em vez
    de reindexar por posição a cada rodada.
    """

    maior = 0

    for arquivo in DIR_ROTEIROS.glob("noticia_*.json"):

        try:
            numero = int(arquivo.stem.split("_")[-1])

        except ValueError:
            continue

        maior = max(maior, numero)

    return maior + 1


# ============================================================
# PROCESSAR UMA NOTÍCIA
# ============================================================

def gerar_roteiro_para_noticia(noticia, indice):
    """
    Gera e salva o roteiro de UMA notícia já escolhida
    (chamado por buscar_noticia.py).
    """

    titulo_original = limpar(
        noticia.get("titulo")
    )

    fonte = limpar(
        noticia.get("fonte")
    ) or "Google Notícias"

    publicador = limpar(
        noticia.get("publicador")
    )

    url = (
        noticia.get("url")
        or noticia.get("link")
        or ""
    )

    print()
    print("=" * 75)

    print(
        f"📰 Processando: "
        f"noticia_{indice}.json"
    )

    print(
        f"📰 Título: "
        f"{titulo_original}"
    )

    print(
        f"🗞️ Fonte: {fonte}"
    )

    tipo = detectar_tipo(
        titulo_original
    )

    print(
        f"🎯 Tipo detectado: "
        f"{tipo}"
    )

    # ----------------------------------------------------
    # MATÉRIA
    # ----------------------------------------------------

    print()
    print(
        "🌐 Tentando obter texto "
        "da matéria..."
    )

    texto_materia = (
        extrair_texto_materia(
            url
        )
    )

    if texto_materia:

        print(
            f"✅ Texto encontrado: "
            f"{len(texto_materia)} "
            f"caracteres"
        )

    else:

        print(
            "⚠️ Texto da matéria "
            "não disponível."
        )

    # ----------------------------------------------------
    # ROTEIRO
    # ----------------------------------------------------

    print()
    print(
        "🤖 Gerando roteiro com Ollama..."
    )

    texto = gerar_com_ollama(
        titulo_original,
        fonte,
        texto_materia
    )

    if texto:

        print(
            "✅ Roteiro gerado pelo Ollama."
        )

    else:

        print(
            "⚠️ Ollama indisponível "
            "ou não gerou um roteiro válido."
        )

        print(
            "🛡️ Usando roteiro seguro."
        )

        texto = fallback_roteiro(
            titulo_original,
            tipo,
        )

    texto = limitar_texto(
        texto,
        500,
        MAX_CHARS
    )

    # ----------------------------------------------------
    # GANCHO
    # ----------------------------------------------------

    frases = re.split(
        r"(?<=[.!?])\s+",
        texto
    )

    gancho = (
        frases[0].strip()
        if frases
        else ""
    )

    # ----------------------------------------------------
    # TÍTULO YOUTUBE
    # ----------------------------------------------------

    print()
    print(
        "🎯 Gerando título para YouTube..."
    )

    titulo_youtube = (
        gerar_titulo_youtube(
            titulo_original,
            texto,
            publicador
        )
    )

    # ----------------------------------------------------
    # DESCRIÇÃO
    # ----------------------------------------------------

    print(
        "📝 Gerando descrição..."
    )

    descricao = gerar_descricao(
        titulo_youtube,
        texto,
        fonte
    )

    # ----------------------------------------------------
    # TAGS
    # ----------------------------------------------------

    print(
        "🏷️ Gerando tags..."
    )

    tags = gerar_tags(
        titulo_youtube,
        texto
    )

    # ----------------------------------------------------
    # EXIBIÇÃO
    # ----------------------------------------------------

    print()
    print(
        "📝 ROTEIRO PARA NARRAÇÃO"
    )

    print("-" * 75)

    print(
        texto
    )

    print("-" * 75)

    print(
        f"📏 Caracteres: "
        f"{len(texto)}"
    )

    print()
    print(
        "🎬 TÍTULO YOUTUBE:"
    )

    print(
        titulo_youtube
    )

    print()
    print(
        "📄 DESCRIÇÃO:"
    )

    print(
        descricao
    )

    print()
    print(
        "🏷️ TAGS:"
    )

    print(
        ", ".join(tags)
    )

    # ----------------------------------------------------
    # SALVAR
    # ----------------------------------------------------

    destino = salvar_roteiro(

        indice,

        noticia,

        titulo_youtube,

        gancho,

        texto,

        tipo,

        descricao,

        tags,
    )

    print()
    print(
        f"✅ Roteiro salvo: "
        f"{destino}"
    )

    return destino


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "ℹ️ Este módulo é chamado por buscar_noticia.py "
        "e não deve ser executado sozinho."
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()
