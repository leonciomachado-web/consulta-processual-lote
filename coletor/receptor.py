"""Receptor local do coletor: grava o que a página (já aberta e logada pela própria pessoa) envia.

Só escuta 127.0.0.1, só aceita nomes no formato de número CNJ e encerra sozinho.
A pasta de dados tem de ficar FORA do repositório (o programa recusa a mesma situação).

Rotas (POST):
  /salvar?nome=<CNJ>[__sufixo]       texto da tela   -> <dados>/entrada/_recebido/<nome>.txt
  /salvar-docs?nome=<CNJ>[__sufixo]  JSON das peças  -> <dados>/entrada/_recebido_docs/<nome>.json
  /salvar-pdf?nome=<CNJ>&arq=<id>-<tipo>  PDF        -> <dados>/processos/<CNJ>/fontes/<arq>.pdf

Uso: python -I coletor/receptor.py --dados <pasta-fora-do-repo> [--porta 18765] [--minutos 150]
"""
import argparse
import http.server
import pathlib
import re
import threading
import time
import urllib.parse

REGEX_CNJ = r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}"
REGEX_NOME = REGEX_CNJ + r"(__[a-z0-9]{1,16})?"
REGEX_ARQ = r"[0-9]{4,12}-[a-z]{2,24}"
LIMITE_PDF = 60 * 1024 * 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True, type=pathlib.Path)
    ap.add_argument("--porta", type=int, default=18765)
    ap.add_argument("--minutos", type=int, default=150)
    a = ap.parse_args()

    dados = a.dados.resolve()
    repo = pathlib.Path(__file__).resolve().parent.parent
    if dados == repo or repo in dados.parents:
        raise SystemExit("A pasta de dados não pode ficar dentro do repositório.")
    pasta_txt = dados / "entrada" / "_recebido"
    pasta_docs = dados / "entrada" / "_recebido_docs"
    pasta_proc = dados / "processos"
    for p in (pasta_txt, pasta_docs, pasta_proc):
        p.mkdir(parents=True, exist_ok=True)

    class H(http.server.BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")

        def _fim(self, codigo, corpo=b""):
            self.send_response(codigo)
            self._cors()
            self.end_headers()
            if corpo:
                self.wfile.write(corpo)

        def do_OPTIONS(self):
            self._fim(204)

        def do_POST(self):
            q = urllib.parse.urlparse(self.path)
            par = urllib.parse.parse_qs(q.query)
            nome = par.get("nome", [""])[0]
            n = int(self.headers.get("Content-Length", 0))
            if q.path == "/salvar-pdf":
                arq = par.get("arq", [""])[0]
                if not (re.fullmatch(REGEX_CNJ, nome) and re.fullmatch(REGEX_ARQ, arq)) or n <= 0 or n > LIMITE_PDF:
                    return self._fim(400)
                corpo = self.rfile.read(n)
                if not corpo.startswith(b"%PDF"):
                    return self._fim(415)
                destino = pasta_proc / nome / "fontes"
                destino.mkdir(parents=True, exist_ok=True)
                (destino / f"{arq}.pdf").write_bytes(corpo)
                return self._fim(200, b"ok")
            if q.path not in ("/salvar", "/salvar-docs") or not re.fullmatch(REGEX_NOME, nome):
                return self._fim(400)
            corpo = self.rfile.read(n)
            alvo = pasta_docs / f"{nome}.json" if q.path == "/salvar-docs" else pasta_txt / f"{nome}.txt"
            alvo.write_bytes(corpo)
            self._fim(200, b"ok")

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.porta), H)
    fim = time.time() + a.minutos * 60
    threading.Thread(target=lambda: (time.sleep(max(0, fim - time.time())), srv.shutdown()), daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
