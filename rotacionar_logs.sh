#!/bin/bash
# Rotaciona os logs do cron em dados/cron_*.log.
#
# Quando um log passa do limite de tamanho, guarda uma cópia
# compactada (.1.gz = a mais recente, até .3.gz) e esvazia o log
# original NO LUGAR (sem trocar o arquivo), então um job do cron
# que esteja com ele aberto continua escrevendo normalmente.
# Cópias além de .3.gz são descartadas.
#
# Uso: ./rotacionar_logs.sh [pasta_dos_logs] [limite_em_KB]
#   padrão: dados/ do projeto, 1024 KB (1 MB)

set -euo pipefail

cd "$(dirname "$0")"

PASTA="${1:-dados}"
LIMITE_KB="${2:-1024}"
COPIAS=3

for log in "$PASTA"/cron_*.log; do

    [ -f "$log" ] || continue

    tamanho_kb=$(( $(stat -c %s "$log") / 1024 ))

    [ "$tamanho_kb" -gt "$LIMITE_KB" ] || continue

    # Desloca .2.gz -> .3.gz, .1.gz -> .2.gz (a .3.gz antiga sai).
    for n in $(seq $((COPIAS - 1)) -1 1); do
        [ -f "$log.$n.gz" ] && mv -f "$log.$n.gz" "$log.$((n + 1)).gz"
    done

    gzip -c "$log" > "$log.1.gz"
    : > "$log"

    echo "$(date -Is) rotacionado $log (${tamanho_kb} KB)"
done
