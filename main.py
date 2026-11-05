"""Launch Moth's local web interface."""
import argparse
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Moth website security assessment")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    import uvicorn
    from moth.app import app

    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
