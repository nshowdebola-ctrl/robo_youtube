from coletar_noticias import coletar_noticias
from filtrar_noticias import filtrar_ultimas_12h, remover_duplicadas
from ia_editor import analisar_noticias


print("🔎 Coletando notícias...")

todas = coletar_noticias()

print(f"📥 Total coletado: {len(todas)}")

recentes = filtrar_ultimas_12h(todas)

recentes = remover_duplicadas(recentes)

print(f"📅 Últimas 12h: {len(recentes)}")

# Para não mandar centenas de notícias para o modelo,
# usamos somente as 30 mais recentes.
recentes = recentes[:30]

print(f"🤖 Enviando {len(recentes)} notícias para a IA...")

resultado = analisar_noticias(recentes)

print("\n" + "=" * 70)
print("🏆 ESCOLHAS DA IA")
print("=" * 70)
print(resultado)
