#!/bin/bash
# =============================================================================
# format-python.sh — ruff check --fix + ruff format po każdej edycji pliku .py
#
# Uruchamiany przez: PostToolUse hook (Write | Edit)
# Wejście:           JSON przez stdin z detalami zdarzenia
# Wyjście:           exit 0 = czysto; exit 2 = pozostałe błędy ruff (stderr → Claude)
#
# Parsowanie JSON:
#   Używamy Pythona zamiast jq — Python jest zawsze dostępny w tym projekcie
#   i nie wymaga dodatkowych zależności systemowych.
# =============================================================================

# Odczytaj cały event JSON ze stdin i zapisz do zmiennej
INPUT=$(cat)

# Wyciągnij ścieżkę pliku przez Python — bezpieczniejsze niż grep/sed
# python3 -c: one-liner; czyta INPUT z env przez sys.stdin nie jest potrzebny
# bo używamy zmiennej powłoki przekazanej przez heredoc do stdin Pythona
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    # file_path istnieje zarówno dla Write jak i Edit
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null)

# Pomiń jeśli nie udało się wyciągnąć ścieżki
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Pomiń pliki które nie są Pythonem
if [[ "$FILE_PATH" != *.py ]]; then
    exit 0
fi

# Pomiń jeśli plik nie istnieje na dysku
if [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

# Zlokalizuj ruff — priorytet: venv projektu > system
if [ -x ".venv/bin/ruff" ]; then
    RUFF=".venv/bin/ruff"
elif command -v ruff &>/dev/null; then
    RUFF="ruff"
else
    # ruff nie jest zainstalowany — pomiń cicho
    exit 0
fi

# 1) Auto-fix lintu (np. kolejność importów, UP*). F401 (nieużywany import) NIE jest
#    naprawiany automatycznie — Claude często dodaje import w jednej edycji, a używa
#    go w następnej; auto-fix usunąłby go w międzyczasie.
"$RUFF" check --fix --unfixable F401 --quiet "$FILE_PATH" >/dev/null 2>&1

# 2) Formatowanie w miejscu
"$RUFF" format --quiet "$FILE_PATH" 2>/dev/null

# 3) Raport tego, czego nie dało się naprawić automatycznie.
#    exit 2 w PostToolUse = stderr trafia do Claude jako feedback (plik i tak zapisany).
REMAINING=$("$RUFF" check --output-format concise --quiet "$FILE_PATH" 2>&1)
if [ -n "$REMAINING" ]; then
    echo "ruff: pozostałe błędy w $FILE_PATH — popraw je:" >&2
    echo "$REMAINING" >&2
    exit 2
fi

exit 0
