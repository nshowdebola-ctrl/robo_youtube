import json
import ollama


MODELO = "qwen2.5:3b"


def analisar_noticias(noticias):

    if not noticias:
        print("⚠️ Nenhuma notícia recebida pela IA.")
        return []

    lista = []

    for i, noticia in enumerate(noticias, 1):

        data = noticia.get("data", "")

        if hasattr(data, "isoformat"):
            data = data.isoformat()

        lista.append({
            "id": i,
            "titulo": noticia.get("titulo", ""),
            "fonte": noticia.get("fonte", ""),
            "data": data,
            "pontuacao": noticia.get("pontuacao", 0)
        })

    prompt = f"""
Você é o editor-chefe de um canal brasileiro de notícias de futebol.

Sua tarefa é escolher as 5 melhores notícias para produzir
vídeos no YouTube.

IMPORTANTE:
Escolha acontecimentos diferentes.

NÃO escolha duas notícias que tratem do mesmo acontecimento.

Exemplos:

"Palmeiras vence Vasco"

e

"Abel Ferreira comenta vitória do Palmeiras"

podem ser o MESMO acontecimento.

Escolha somente uma.

Outro exemplo:

"Santos empata com Mirassol"

e

"Cuca comenta empate do Santos"

representam o MESMO acontecimento.

Escolha somente uma.

Outro exemplo:

"Pedro Emanuel fala após derrota do Vasco"

e

"Pedro Emanuel explica derrota do Vasco"

representam o MESMO acontecimento.

Escolha somente uma.

PRIORIDADE:

1. Grandes acontecimentos do futebol brasileiro
2. Grandes clubes
3. Grandes jogadores
4. Mercado da bola
5. Resultados importantes
6. Crises
7. Técnicos
8. Competições importantes
9. Notícias com grande potencial de interesse

EVITE:

- onde assistir
- horários
- programação
- escalações
- transmissão
- gols isolados
- opiniões genéricas
- notícias antigas
- notícias repetidas
- notícias do mesmo jogo
- notícias do mesmo acontecimento

REGRA FUNDAMENTAL:

NÃO INVENTE INFORMAÇÕES.

Use SOMENTE os títulos fornecidos.

Escolha SOMENTE IDs existentes.

Retorne SOMENTE uma lista JSON.

NÃO escreva explicações antes ou depois do JSON.

Formato:

[
  6,
  8,
  3,
  10,
  2
]

Escolha exatamente 5 IDs quando houver pelo menos 5
notícias válidas.

NOTÍCIAS:

{json.dumps(lista, ensure_ascii=False, indent=2)}
"""

    print("🤖 Consultando o Ollama...")

    try:

        resposta = ollama.chat(
            model=MODELO,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            options={
                "temperature": 0.1
            }
        )

    except Exception as erro:

        print(f"❌ Erro no Ollama: {erro}")
        return []

    texto = resposta["message"]["content"].strip()

    print("\n🧠 Resposta bruta da IA:")
    print(texto)

    # ---------------------------------------------------------
    # Limpar Markdown
    # ---------------------------------------------------------

    texto = texto.replace("```json", "")
    texto = texto.replace("```JSON", "")
    texto = texto.replace("```", "")
    texto = texto.strip()

    # ---------------------------------------------------------
    # Encontrar lista JSON
    # ---------------------------------------------------------

    inicio = texto.find("[")
    fim = texto.rfind("]")

    if inicio == -1 or fim == -1:

        print(
            "❌ A IA não retornou uma lista JSON válida."
        )

        return []

    texto_json = texto[inicio:fim + 1]

    try:

        escolhas = json.loads(texto_json)

    except json.JSONDecodeError as erro:

        print(
            f"❌ Erro ao interpretar JSON: {erro}"
        )

        return []

    if not isinstance(escolhas, list):

        print(
            "❌ A resposta da IA não é uma lista."
        )

        return []

    # ---------------------------------------------------------
    # Validar IDs
    # ---------------------------------------------------------

    resultado = []
    ids_usados = set()

    for item in escolhas:

        # O modelo deve retornar números diretamente.
        if isinstance(item, int):

            id_noticia = item

        # Também aceitamos {"id": 3}
        elif isinstance(item, dict):

            id_noticia = item.get("id")

        else:
            continue

        if not isinstance(id_noticia, int):
            continue

        if id_noticia < 1:
            continue

        if id_noticia > len(noticias):
            continue

        if id_noticia in ids_usados:
            continue

        ids_usados.add(id_noticia)

        resultado.append({
            "id": id_noticia,
            "motivo": "Selecionada pela relevância editorial."
        })

        if len(resultado) == 5:
            break

    print(
        f"✅ IA selecionou {len(resultado)} notícias."
    )

    return resultado
