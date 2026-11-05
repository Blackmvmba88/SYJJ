"""Ejecutar con python3 app.py y abrir http://127.0.0.1:8765."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from music import progression, midi, QUALITIES

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == '/':
                body = Path(__file__).with_name('index.html').read_bytes()
                kind = 'text/html; charset=utf-8'
            elif url.path == '/api/progression':
                body = json.dumps(progression(query.get('text', [''])[0])).encode()
                kind = 'application/json'
            elif url.path == '/api/qualities':
                body = json.dumps(list(QUALITIES)).encode()
                kind = 'application/json'
            elif url.path == '/api/midi':
                body = midi(query.get('text',[''])[0], int(query.get('bpm',['86'])[0]))
                kind = 'audio/midi'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            if kind == 'audio/midi':
                self.send_header('Content-Disposition', 'attachment; filename="blackmamba.mid"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except ValueError as error:
            body = json.dumps({'error': str(error)}).encode()
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)

if __name__ == '__main__':
    print('BlackMamba Harmonic Glide: http://127.0.0.1:8765', flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765), Handler).serve_forever()
