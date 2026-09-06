def _run() -> None:
    try:
        from .main import main
    except ImportError:
        from main import main
    main()


if __name__ == "__main__":
    _run()
