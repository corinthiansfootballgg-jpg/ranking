"""Servidor local para visualizar o dashboard."""
import http.server
import socketserver
import webbrowser
from pathlib import Path

PORT = 8080
ROOT = Path(__file__).resolve().parent

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}/dashboard/"
        print(f"Dashboard em {url}")
        webbrowser.open(url)
        httpd.serve_forever()
