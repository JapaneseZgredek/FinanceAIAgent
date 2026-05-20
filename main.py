"""Finance AI Agent — entry point dispatcher.

python main.py              → interactive Rich menu
python main.py analyze ...  → CLI (Typer subcommands)
"""

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from app.interfaces.cli import cli_app

        cli_app()
    else:
        from app.interfaces.interactive import run_interactive

        run_interactive()


if __name__ == "__main__":
    main()
