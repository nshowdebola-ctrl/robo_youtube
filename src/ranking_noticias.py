import re
import unicodedata


# ============================================================
# PALAVRAS DE ALTA IMPORTÂNCIA
# ============================================================

PALAVRAS_FORTES = {
    "contrata": 15,
    "contratacao": 15,
    "contratado": 15,
    "novo reforco": 15,
    "reforco": 10,
    "assinou": 15,
    "acerto": 12,
    "acerta": 12,
    "anuncia": 10,
    "anunciou": 10,

    "demitido": 15,
    "demissao": 15,
    "demite": 15,
    "novo tecnico": 14,
    "novo treinador": 14,

    "lesao": 13,
    "lesionado": 13,
    "desfalque": 9,

    "campeao": 15,
    "titulo": 14,
    "final": 10,

    "libertadores": 10,
    "brasileirao": 10,
    "mundial": 10,
    "selecao brasileira": 12,

    "crise": 9,
    "polemica": 8,
    "urgente": 12,

    "vitoria": 7,
    "derrota": 7,
    "empate": 5,

    "morre": 3,
    "morreu": 3,
    "morte": 3,
}


# ============================================================
# TERMOS QUE DEVEM PERDER PRIORIDADE
# ============================================================

PALAVRAS_FRACAS = {
    "onde assistir": -12,
    "horario": -10,
    "escalacoes": -10,
    "provavel escalacao": -10,
    "transmissao": -10,
    "jogos de hoje": -10,
    "agenda": -10,
    "programacao": -10,
    "atuacoes": -5,
    "de suas notas": -5,
    "veja": -2,
    "confira": -2,
}


# ============================================================
# CLUBES/TERMOS DE INTERESSE
# ============================================================

CLUBES_IMPORTANTES = {
    "flamengo",
    "palmeiras",
    "corinthians",
    "sao paulo",
    "santos",
    "vasco",
    "gremio",
    "internacional",
    "cruzeiro",
    "atletico mineiro",
    "botafogo",
    "fluminense",
    "bahia",
    "bragantino",
}


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto):

    texto = str(texto or "").lower()

    texto = unicodedata.normalize(
        "NFD",
        texto
    )

    texto = "".join(
        c
        for c in texto
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(
        r"[^a-z0-9\s]",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# ============================================================
# PONTUAÇÃO
# ============================================================

def calcular_pontuacao(noticia):

    titulo = normalizar_texto(
        noticia.get("titulo", "")
    )

    resumo = normalizar_texto(
        noticia.get("resumo", "")
    )

    texto = f"{titulo} {resumo}"

    pontos = 0

    # --------------------------------------------------------
    # Palavras fortes
    # --------------------------------------------------------

    for palavra, valor in PALAVRAS_FORTES.items():

        if palavra in texto:
            pontos += valor

    # --------------------------------------------------------
    # Palavras fracas
    # --------------------------------------------------------

    for palavra, valor in PALAVRAS_FRACAS.items():

        if palavra in titulo:
            pontos += valor

    # --------------------------------------------------------
    # Clubes brasileiros importantes
    # --------------------------------------------------------

    clubes_encontrados = 0

    for clube in CLUBES_IMPORTANTES:

        if clube in titulo:
            clubes_encontrados += 1

    if clubes_encontrados:
        pontos += 5

    # --------------------------------------------------------
    # Títulos muito genéricos
    # --------------------------------------------------------

    if len(titulo.split()) < 5:
        pontos -= 3

    # --------------------------------------------------------
    # Penaliza matérias sobre acidentes/mortes
    # sem relação direta com futebol profissional
    # --------------------------------------------------------

    termos_acidente = [
        "acidente de carro",
        "acidente de moto",
        "carro bateu",
        "carro bater",
        "carbonizado",
        "morre apos acidente",
    ]

    if any(
        termo in titulo
        for termo in termos_acidente
    ):

        pontos -= 8

    noticia["pontuacao"] = pontos

    return pontos


# ============================================================
# SIMILARIDADE ENTRE TÍTULOS
# ============================================================

def palavras_titulo(titulo):

    stopwords = {
        "de", "da", "do",
        "das", "dos",
        "a", "o", "as", "os",
        "e", "em", "no", "na",
        "um", "uma",
        "para", "por",
        "com", "que",
        "apos", "sobre",
    }

    palavras = set(
        normalizar_texto(
            titulo
        ).split()
    )

    return palavras - stopwords


def similaridade(titulo_a, titulo_b):

    a = palavras_titulo(
        titulo_a
    )

    b = palavras_titulo(
        titulo_b
    )

    if not a or not b:
        return 0

    intersecao = len(a & b)
    menor = min(
        len(a),
        len(b)
    )

    if menor == 0:
        return 0

    return intersecao / menor


# ============================================================
# REMOVER NOTÍCIAS DO MESMO ASSUNTO
# ============================================================

def remover_assuntos_repetidos(noticias):

    resultado = []

    removidas = 0

    for noticia in noticias:

        titulo = noticia.get(
            "titulo",
            ""
        )

        repetida = False

        for selecionada in resultado:

            outro_titulo = selecionada.get(
                "titulo",
                ""
            )

            grau = similaridade(
                titulo,
                outro_titulo
            )

            if grau >= 0.70:

                repetida = True

                removidas += 1

                break

        if not repetida:

            resultado.append(
                noticia
            )

    print(
        f"🔄 Assuntos repetidos removidos: "
        f"{removidas}"
    )

    return resultado


# ============================================================
# RANKING
# ============================================================

def ranquear_noticias(
    noticias,
    limite=30
):

    print(
        "\n🔥 Calculando ranking..."
    )

    for noticia in noticias:

        calcular_pontuacao(
            noticia
        )

    noticias.sort(
        key=lambda x: x.get(
            "pontuacao",
            0
        ),
        reverse=True
    )

    noticias = remover_assuntos_repetidos(
        noticias
    )

    noticias.sort(
        key=lambda x: x.get(
            "pontuacao",
            0
        ),
        reverse=True
    )

    resultado = noticias[:limite]

    print(
        f"🏆 TOP {len(resultado)} notícias"
    )

    return resultado


# ============================================================
# MOSTRAR RANKING
# ============================================================

def mostrar_ranking(noticias):

    print(
        "\n" + "=" * 75
    )

    print(
        "🔥 RANKING DE NOTÍCIAS"
    )

    print(
        "=" * 75
    )

    for i, noticia in enumerate(
        noticias,
        1
    ):

        print(
            f"\n{i:02d}. "
            f"[{noticia.get('pontuacao', 0)} pontos]"
        )

        print(
            f"    {noticia.get('titulo', '')}"
        )

        print(
            f"    Fonte: "
            f"{noticia.get('fonte', '')}"
        )


# ============================================================
# TESTE
# ============================================================

if __name__ == "__main__":

    from coletar_noticias import (
        coletar_noticias
    )

    from filtrar_noticias import (
        filtrar_ultimas_12h,
        remover_duplicadas,
    )

    print(
        "🔎 Coletando notícias..."
    )

    noticias = coletar_noticias()

    print(
        f"📥 Total: {len(noticias)}"
    )

    noticias = filtrar_ultimas_12h(
        noticias
    )

    noticias = remover_duplicadas(
        noticias
    )

    ranking = ranquear_noticias(
        noticias,
        limite=30
    )

    mostrar_ranking(
        ranking
    )
