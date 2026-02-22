#!/bin/bash
# =============================================================================
# check-print-statements.sh — detekcja print() zamiast loggera
#
# Uruchamiany przez: PostToolUse hook (Write | Edit)
# Wejście:           JSON przez stdin z detalami zdarzenia
# Wyjście:
#   exit 0 + brak output → wszystko OK
#   exit 0 + stderr      → znaleziono print(), Claude dostaje ostrzeżenie
#   (nigdy exit 2 — to tylko ostrzeżenie, nie blokujemy workflow)
#
# Kontekst projektu:
#   Finance AI Agent używa standardowego modułu `logging` z Pythona.
#   Każdy moduł definiuje: logger = logging.getLogger(__name__)
#   Print() zamiast loggera jest problemem bo:
#     - nie ma timestampów ani poziomu severity
#     - nie można wyłączyć przez zmianę log level
#     - nie trafia do pliku logów jeśli skonfigurowany
# =============================================================================

INPUT=$(cat)

# Wyciągnij ścieżkę pliku przez Python (jq może nie być zainstalowane)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Tylko pliki Python
if [[ "$FILE_PATH" != *.py ]]; then
    exit 0
fi

# Pomiń jeśli plik nie istnieje
if [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

# Wyjątki — pliki gdzie print() jest dopuszczalny:
#   main.py   → entry point z CLI (print do użytkownika jest OK)
#   test_*    → testy mogą używać print do debugowania
#   *_test.py → j.w.
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" == "main.py" || "$BASENAME" == test_* || "$BASENAME" == *_test.py ]]; then
    exit 0
fi

# Szukaj wywołań print() które są na początku linii (opcjonalne wcięcie)
# Wzorzec: ^\s*print\(
#   ^\s*   — opcjonalne białe znaki na początku linii (wcięcie w bloku/funkcji)
#   print\(— literalne "print(" — samo "print" bez nawiasu to zmienna, nie wywołanie
#
# Ograniczenie: grep -P nie parsuje składni Pythona — może dać false positives
# dla print() w stringu. Dla naszych celów (hint dla Claude) to wystarczające.
MATCHES=$(grep -nP '^\s*print\(' "$FILE_PATH" 2>/dev/null || true)

if [ -n "$MATCHES" ]; then
    echo "" >&2
    echo "⚠  print() w $FILE_PATH — ten projekt używa modułu logging:" >&2
    echo "$MATCHES" >&2
    echo "" >&2
    echo "   Zamień na odpowiedni poziom loggera:" >&2
    echo "   logger.debug()    → szczegóły techniczne (domyślnie niewidoczne)" >&2
    echo "   logger.info()     → informacje o przebiegu" >&2
    echo "   logger.warning()  → ostrzeżenia, coś nieoczekiwanego" >&2
    echo "   logger.error()    → błędy które nie przerywają działania" >&2
    echo "" >&2
fi

# Zawsze exit 0 — to ostrzeżenie, nie blokada
exit 0
