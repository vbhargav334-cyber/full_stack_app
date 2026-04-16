import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from waitress import serve

# Load .env before importing app so all env vars are available
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

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


def _pick_port(preferred: int) -> int:
    if _is_port_available(preferred):
        return preferred

    candidates = [port for port in range(8000, 8011) if port != preferred]
    for port in candidates:
        if _is_port_available(port):
            return port
    raise RuntimeError("No free localhost port found in range 8000-8010")


def _open_browser(host: str, port: int) -> None:
    time.sleep(1.2)
    webbrowser.open(f"http://{host}:{port}")


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    preferred_port = int(os.environ.get("FLASK_PORT", "8000"))
    port = _pick_port(preferred_port)
    if port != preferred_port:
        print(f"Port {preferred_port} is busy. Starting Google Maps Scraper on http://{host}:{port} instead.")
    else:
        print(f"Starting Google Maps Scraper on http://{host}:{port}")

    threading.Thread(target=_open_browser, args=(host, port), daemon=True).start()
    serve(app, host=host, port=port, threads=8)
