import os
import socket
import threading
import time
import webbrowser

from waitress import serve

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

from app import app


def _is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        if probe.connect_ex((host, port)) == 0:
            return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _pick_port() -> int:
    requested = os.environ.get("SCRAPER_PORT", "").strip()
    try:
        preferred = int(requested) if requested else 8000
    except ValueError:
        preferred = 8000

    candidates = [preferred] + [port for port in range(8000, 8011) if port != preferred]
    for port in candidates:
        if _is_port_available(port):
            return port
    raise RuntimeError("No free localhost port found in range 8000-8010")


def _open_browser(port: int) -> None:
    time.sleep(1.2)
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    host = "127.0.0.1"
    port = _pick_port()
    if port != 8000:
        print(f"Port 8000 is busy. Starting Google Maps Scraper on http://{host}:{port} instead.")
    else:
        print(f"Starting Google Maps Scraper on http://{host}:{port}")

    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
    serve(app, host=host, port=port, threads=8)
