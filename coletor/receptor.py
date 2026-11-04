"""Receptor local do coletor: grava o que a página (já aberta e logada pela própria pessoa) envia.

Só escuta 127.0.0.1, só aceita nomes no formato de número CNJ e encerra sozinho.
A pasta de dados tem de ficar FORA do repositório (o programa recusa a mesma situação).

Rotas (POST):
  /salvar?nome=<CNJ>[__sufixo]       texto da tela   -> <dados>/entrada/_recebido/<nome>.txt
  /salvar-docs?nome=<CNJ>[__sufixo]  JSON das peças  -> <dados>/entrada/_recebido_docs/<nome>.json
  /salvar-pdf?nome=<CNJ>&arq=<id>-<tipo>  PDF        -> <dados>/processos/<CNJ>/fontes/<arq>.pdf

Proteção contra outras páginas do navegador: cada POST precisa vir de uma origem listada em
--origem (a do sistema que a pessoa abriu) e trazer o token da sessão (parâmetro t=), impresso ao
iniciar. O token muda a cada execução. Sem isso, qualquer site aberto poderia gravar aqui.

Uso: python -I coletor/receptor.py --dados <pasta-fora-do-repo> --origem https://<sistema> [--origem ...]
     [--porta 18765] [--minutos 150]
"""
import argparse
import hmac
import http.server
import pathlib
import re
import secrets
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
    ap.add_argument("--origem", action="append", required=True,
                    help="origem permitida, ex.: https://sistema.exemplo (repita para mais de uma)")
    a = ap.parse_args()
    permitidas = {o.rstrip("/") for o in a.origem}
    token = secrets.token_urlsafe(24)

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
        def _origem_ok(self):
            host_ok = self.headers.get("Host", "") in (f"127.0.0.1:{a.porta}", f"localhost:{a.porta}")
            return host_ok and self.headers.get("Origin", "").rstrip("/") in permitidas

        @staticmethod
        def _gravar(alvo, corpo):
            """Não sobrescreve em silêncio: o arquivo anterior vira <nome>.anterior."""
            if alvo.exists():
                alvo.replace(alvo.with_name(alvo.name + ".anterior"))
            alvo.write_bytes(corpo)

        def _cors(self):
            if self._origem_ok():
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"].rstrip("/"))
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _fim(self, codigo, corpo=b""):
            self.send_response(codigo)
            self._cors()
            self.end_headers()
            if corpo:
                self.wfile.write(corpo)

        def do_OPTIONS(self):
            self._fim(204 if self._origem_ok() else 403)

        def do_POST(self):
            q = urllib.parse.urlparse(self.path)
            par = urllib.parse.parse_qs(q.query)
            nome = par.get("nome", [""])[0]
            if not self._origem_ok() or not hmac.compare_digest(par.get("t", [""])[0], token):
                return self._fim(403)
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
                self._gravar(destino / f"{arq}.pdf", corpo)
                return self._fim(200, b"ok")
            if q.path not in ("/salvar", "/salvar-docs") or not re.fullmatch(REGEX_NOME, nome):
                return self._fim(400)
            corpo = self.rfile.read(n)
            alvo = pasta_docs / f"{nome}.json" if q.path == "/salvar-docs" else pasta_txt / f"{nome}.txt"
            self._gravar(alvo, corpo)
            self._fim(200, b"ok")

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.porta), H)
    print(f"Receptor em 127.0.0.1:{a.porta}. Token da sessão (use como t=<token> nas URLs): {token}", flush=True)
    fim = time.time() + a.minutos * 60
    threading.Thread(target=lambda: (time.sleep(max(0, fim - time.time())), srv.shutdown()), daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
