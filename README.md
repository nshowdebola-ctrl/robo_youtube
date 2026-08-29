# Noticias Show de Bola — News YouTube

Sistema automatizado que gera e publica vídeos de notícias de futebol no
YouTube: um pipeline principal (notícias em geral, ~50-70s) e uma pipeline
separada de Shorts (resultados de jogos do dia, formato vertical).

## Como funciona

**Pipeline principal** (`src/pipeline.py`):
1. `buscar_noticia.py` — coleta RSS (Google Notícias + UOL Esporte),
   filtra últimas 12h, remove conteúdo indesejado/outros esportes,
   rankeia por relevância, descarta notícias já usadas (histórico de
   30 dias) e gera o roteiro da mais relevante ainda não usada.
2. `gerar_video.py` — gera a narração (TTS via edge-tts), busca uma
   imagem relevante e com licença de reuso comercial (Bing, filtrado),
   monta o vídeo final (zoom lento, selo de inscrição) e atualiza a fila.

**Pipeline de Shorts** (`src/pipeline_shorts.py`) — totalmente separada,
não compartilha arquivos/fila/histórico com a principal:
1. `buscar_resultado.py` — mesma coleta/filtros, mas foca em notícias de
   resultado (vitória/derrota/empate) de times grandes (com fallback pra
   Série B), extrai time A, time B e placar do corpo da matéria via regex
   (o título raramente tem o placar).
2. `gerar_short.py` — monta um vídeo vertical (1080x1920) tipo card de
   placar, com a mesma foto licenciada + zoom + selo de inscrição.

Ambas pipelines processam **uma notícia/resultado por execução** — a
ideia é rodar via cron de hora em hora.

## Publicação automática no YouTube

`src/youtube_upload.py` + `src/enviar_youtube_video.py` +
`src/enviar_youtube_short.py` publicam o próximo vídeo/short concluído
que ainda não foi enviado, usando a YouTube Data API v3 (OAuth2).

## Requisitos

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) e `ffprobe` no PATH
- Fontes DejaVu Sans (`fonts-dejavu` no Debian/Ubuntu) — usadas no texto
  sobreposto aos vídeos
- [Ollama](https://ollama.com/) rodando localmente (usado só para
  reescrever a narração da pipeline principal; sem ele, cai num texto
  seguro determinístico)
- Um projeto no Google Cloud com a YouTube Data API v3 ativada e
  credenciais OAuth (tipo "App para computador") — necessário só para
  publicação automática, não para gerar os vídeos

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuração da publicação no YouTube

1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com/)
2. Ative a **YouTube Data API v3**
3. Configure a tela de consentimento OAuth (Externo, com seu e-mail como
   usuário de teste, escopo `.../auth/youtube.upload`)
4. Crie uma credencial OAuth do tipo **App para computador** e baixe o
   JSON como `credenciais/client_secret.json`
5. Na primeira execução de `enviar_youtube_video.py` (ou
   `enviar_youtube_short.py`), um link de autorização é impresso no
   terminal — abra no navegador e autorize. O token fica salvo em
   `credenciais/token.json` para as próximas execuções.

`credenciais/` nunca é versionado (está no `.gitignore`).

## Uso

```bash
# Pipeline principal (notícia + vídeo)
python3 src/pipeline.py

# Pipeline de Shorts (resultado do dia)
python3 src/pipeline_shorts.py

# Publicar no YouTube o próximo vídeo/short pronto
python3 src/enviar_youtube_video.py
python3 src/enviar_youtube_short.py
```

### Rodando de hora em hora (cron)

```cron
0 * * * * cd /caminho/do/projeto && .venv/bin/python3 src/pipeline.py >> dados/status/pipeline.log 2>&1
5 * * * * cd /caminho/do/projeto && .venv/bin/python3 src/pipeline_shorts.py >> dados/shorts/status/pipeline.log 2>&1
```

## Estrutura de dados

```
dados/
├── roteiros/        # roteiro + metadados de cada notícia (pipeline principal)
├── audios/          # narração gerada (TTS)
├── imagens/          # foto + frame final de cada vídeo
├── videos/           # vídeos finais
├── status/           # fila.json (status de geração) e youtube.json (status de publicação)
├── historico_noticias.json   # notícias já usadas (30 dias)
└── shorts/            # mesma estrutura acima, isolada, para a pipeline de Shorts
```
