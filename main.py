"""Launch the native Moth desktop application."""


def main() -> None:
    from moth.desktop import run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
