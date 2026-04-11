"""
price_validation/main.py — entry point
"""
from __future__ import annotations


def main() -> None:
    from price_validation.ui.app import App
    app = App()
    app.run()


if __name__ == "__main__":
    main()
