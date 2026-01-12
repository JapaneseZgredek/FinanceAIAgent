from app.crew_runner import run


def main():
    symbol = input("Which cryptocurrency symbol do you want to analyze (e.g. BTC)? ").strip().upper()
    if not symbol:
        raise SystemExit("Empty symbol.")
    result = run(symbol)
    print("\n\n========== FINAL RESULT ==========\n")
    print(result)


if __name__ == "__main__":
    main()
