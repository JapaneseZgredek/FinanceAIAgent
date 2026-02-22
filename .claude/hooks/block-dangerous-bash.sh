#!/bin/bash
# =============================================================================
# block-dangerous-bash.sh — blokada niebezpiecznych komend bash
#
# Uruchamiany przez: PreToolUse hook (Bash)
# Wejście:           JSON przez stdin z detalami zdarzenia
# Wyjście:
#   exit 0           → komenda dozwolona, Claude kontynuuje
#   exit 2 + stderr  → komenda ZABLOKOWANA, stderr trafia do Claude
#
# Dlaczego hook zamiast tylko permissions.deny?
#   permissions.deny działa na poziomie wzorców narzędzia — np. "Bash(rm -rf *)"
#   pasuje do "rm -rf /foo" ale może nie pasować do bardziej złożonych przypadków
#   jak "cd /tmp && rm -rf ." albo komend w subprocess wewnątrz skryptu.
#   Hook widzi CAŁĄ komendę bash jako string i szuka podciągów —
#   dlatego jest to drugi poziom ochrony (belt-and-suspenders).
#
# Parsowanie JSON:
#   Używamy Pythona zamiast jq — Python jest zawsze dostępny w tym projekcie.
# =============================================================================

INPUT=$(cat)

# Wyciągnij komendę bash przez Python
COMMAND=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" 2>/dev/null)

# Jeśli nie udało się wyciągnąć komendy — przepuść (fail open, nie fail closed)
# Lepiej nie blokować Claude gdy mamy problem z parsowaniem niż blokować wszystko
if [ -z "$COMMAND" ]; then
    exit 0
fi

# =============================================================================
# WZORCE DO ZABLOKOWANIA
# Format: "wzorzec|powód wyświetlany Claude i użytkownikowi"
#
# Dopasowanie: grep -iF (case-insensitive, fixed string — nie regex)
# Fixed string: bezpieczniejsze niż regex (brak ryzyka ReDoS)
#               i wzorce są bardziej czytelne dla maintainerów
# =============================================================================
BLOCKED_PATTERNS=(
    "rm -rf|Rekursywne usunięcie bez potwierdzenia — operacja nieodwracalna"
    "rm -Rf|Rekursywne usunięcie bez potwierdzenia — operacja nieodwracalna"
    "git push --force|Force push nadpisuje historię zdalną — użyj --force-with-lease jeśli konieczne"
    "git push -f |Force push nadpisuje historię zdalną — spacja po -f wyklucza -fd itp."
    "git reset --hard|Hard reset niszczy WSZYSTKIE niezacommitowane zmiany bez możliwości odwrotu"
    "git clean -fd|Usuwa untracked files i katalogi — operacja nieodwracalna"
    "git clean -fdx|Usuwa untracked i gitignorowane pliki (venv, cache) — operacja nieodwracalna"
    "git clean -fxd|Usuwa untracked i gitignorowane pliki — operacja nieodwracalna"
    "chmod -R 777|World-writable permissions to poważna luka bezpieczeństwa"
    "chmod 777|World-writable permissions to poważna luka bezpieczeństwa"
    "> .env|Nadpisanie pliku .env zniszczyłoby klucze API (GROQ, EXA, ALPHAVANTAGE)"
    "truncate .env|Zerowanie pliku .env zniszczyłoby klucze API"
    "DROP TABLE|Destruktywna operacja bazy danych — wymaga jawnego potwierdzenia"
    "TRUNCATE TABLE|Destruktywna operacja bazy danych — wymaga jawnego potwierdzenia"
)

for ENTRY in "${BLOCKED_PATTERNS[@]}"; do
    # Rozdziel wzorzec i powód po pierwszym "|"
    PATTERN="${ENTRY%%|*}"
    REASON="${ENTRY#*|}"

    # grep -iF: case-insensitive, fixed string (nie regex)
    # -q: quiet — tylko kod wyjścia, bez outputu na stdout
    if echo "$COMMAND" | grep -qiF "$PATTERN"; then
        # Wypisz na stderr — trafia do Claude jako wyjaśnienie blokady
        echo "" >&2
        echo "🚫 ZABLOKOWANO: komenda zawiera zakazany wzorzec" >&2
        echo "   Wzorzec:  '$PATTERN'" >&2
        echo "   Powód:    $REASON" >&2
        echo "   Komenda:  $COMMAND" >&2
        echo "" >&2
        echo "   Jeśli ta operacja jest naprawdę potrzebna, poproś użytkownika" >&2
        echo "   o ręczne wykonanie jej w terminalu po dokładnym przemyśleniu." >&2
        echo "" >&2

        # exit 2 = Claude Code traktuje to jako "blocking error"
        # Narzędzie Bash NIE zostanie wywołane
        # stderr trafi do Claude jako kontekst dlaczego komenda jest niedozwolona
        exit 2
    fi
done

# Żaden wzorzec nie pasował — komenda jest dozwolona
exit 0
