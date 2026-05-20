#!/bin/bash
# =============================================================================
# format-python.sh — auto-formatowanie plików Python za pomocą ruff
#
# Uruchamiany przez: PostToolUse hook (Write | Edit)
# Wejście:           JSON przez stdin z detalami zdarzenia
# Wyjście:           exit 0 zawsze (PostToolUse nie może blokować — tylko informuje)
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

# Formatuj plik w miejscu
# 2>/dev/null: wycisz stderr
"$RUFF" format "$FILE_PATH" --quiet 2>/dev/null

# Zawsze exit 0 — PostToolUse i tak nie może cofnąć zapisanego pliku
exit 0
