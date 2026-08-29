#!/usr/bin/env python3

"""
Refaz a autenticação OAuth do YouTube do zero e confirma, via
API, a qual canal o token gerado pertence.

Use isso sempre que:
- o token expirar/for revogado e o pipeline parar de publicar;
- você desconfiar que o token está preso à conta/canal errado;
- o client OAuth do Google Cloud Console for recriado (o
  client_secret.json muda de client_id).

Não publica nenhum vídeo — só autentica e confirma o canal.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from youtube_upload import CREDENCIAIS_DIR, TOKEN_FILE, autenticar


def main():

    print()
    print("=" * 70)
    print("🔑 REAUTENTICAÇÃO DO YOUTUBE")
    print("=" * 70)

    if TOKEN_FILE.exists():

        resposta = input(
            f"Já existe um token em {TOKEN_FILE}. "
            f"Apagar e gerar um novo? [s/N] "
        ).strip().lower()

        if resposta != "s":
            print("Cancelado. Token atual mantido.")
            return 0

        TOKEN_FILE.unlink()
        print("🗑️  Token antigo apagado.")

    print()
    print(
        "Um link vai aparecer abaixo. Abra ele no navegador, "
        "logado na conta certa (nshowdebola@gmail.com), e "
        "autorize o acesso."
    )
    print(
        "⚠️  Se aparecer uma tela pra escolher canal/Brand "
        "Account, selecione 'Noticias Show de Bola', não o "
        "canal pessoal."
    )
    print()

    try:
        youtube = autenticar()

    except Exception as erro:

        print()
        print(f"❌ Falha na autenticação: {erro}")
        print()
        print(
            "Se o erro for 'deleted_client': o client OAuth no "
            "Google Cloud Console foi apagado. Vá em "
            "console.cloud.google.com/auth/clients, confira o "
            "client ativo e gere um novo secret nele "
            "('+ Add secret'), ou crie um client novo — depois "
            "substitua credenciais/client_secret.json e rode "
            "este script de novo."
        )
        return 1

    print("✅ Token gerado.")
    print()
    print("Confirmando o canal vinculado a esse token...")

    resposta = youtube.channels().list(
        part="snippet",
        mine=True,
    ).execute()

    itens = resposta.get("items", [])

    if not itens:

        print(
            "⚠️  Não achei nenhum canal associado a essa conta. "
            "O token pode estar preso à conta errada — apague "
            f"{TOKEN_FILE} e rode de novo, atento à conta usada "
            "no login."
        )
        return 1

    canal = itens[0]["snippet"]

    print()
    print("=" * 70)
    print(f"📺 Canal: {canal['title']}")
    print(f"🔗 Handle: {canal.get('customUrl', '(sem handle definido)')}")
    print(f"🆔 Channel ID: {itens[0]['id']}")
    print("=" * 70)

    if canal.get("customUrl") != "@noticiasshowdebola":

        print(
            "⚠️  ATENÇÃO: esse não é o canal esperado "
            "(@noticiasshowdebola). Confira se você logou com a "
            "conta certa antes de usar esse token pra publicar."
        )
        return 1

    print("Canal confere. Token pronto pra uso no pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
