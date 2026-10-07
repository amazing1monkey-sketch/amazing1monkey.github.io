"""Refresh the generated site when local workbooks or images change."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from build import ROOT, IMAGE_EXTENSIONS, build
import argparse
import threading

last_state = None
lock = threading.Lock()


def refresh():
    global last_state
    paths = [ROOT / 'site.config.json', *ROOT.glob('content/*.xlsx')]
    paths += [p for p in ROOT.rglob('*') if p.suffix.lower() in IMAGE_EXTENSIONS
              and not any(part.startswith('.') or part in {'dist', 'node_modules'} for part in p.relative_to(ROOT).parts)]
    current = tuple(sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.is_file()))
    with lock:
        if last_state != current:
            build()
            last_state = current


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        try:
            refresh()
        except Exception as error:
            self.send_error(500, 'Workbook could not be built', str(error))
            return
        super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    refresh()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'本地预览：http://127.0.0.1:{args.port}；修改表格后刷新页面。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
