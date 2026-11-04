"""Testes do conversor do coletor, só com dados sintéticos."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from consulta_lote import campos, parser  # noqa: E402

CONV = RAIZ / "coletor" / "converter.py"
N = "0000001-80.2025.8.99.0000"
NL = chr(10)


class TesteConversor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "saida").mkdir()
        (self.d / "saida" / "elegiveis.csv").write_text("numero;fase_base" + NL + N + ";FASE INICIAL" + NL, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def roda(self, *args):
        r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CONV), "--dados", str(self.d), "--data", "2026-01-02", *args],
                           capture_output=True, text=True, encoding="utf-8")
        return r

    def despejo(self, nome, obj):
        p = self.d / nome
        p.write_text("prefixo-lixo " + json.dumps(obj), encoding="utf-8")
        return str(p)

    def test_pje_publico_gera_entrada_que_o_parser_le(self):
        capa = ("FULANO DE TAL SINTETICO - CPF: 000.000.000-00 (AUTOR)" + NL +
                "EMPRESA ALFA SINTETICA LTDA - CNPJ: 00.000.000/0001-00 (RÉU)" + NL +
                "ADVOGADO SINTETICO - OAB 0000 (ADVOGADO)")
        dump = {N: {"capa": capa, "movs": ["10/03/2025 14:30:00 - JULGADO PROCEDENTE O PEDIDO",
                                           "05/02/2025 09:00:00 - CONCLUSOS PARA SENTENÇA"],
                    "docs": [{"rot": "99 - Sentença", "texto": "SENTENÇA" + NL + "Julgo procedente o pedido."}]}}
        r = self.roda("pje-publico", self.despejo("p.json", dump))
        self.assertEqual(r.returncode, 0, r.stderr)
        txt = (self.d / "entrada" / (N + ".txt")).read_text(encoding="utf-8")
        self.assertIn("#! sistema: pje", txt)
        self.assertIn("#! data_consulta: 2026-01-02", txt)
        self.assertIn("#! fase_base: FASE INICIAL", txt)
        p = parser.ler(txt)
        self.assertIn(("passivo", "EMPRESA ALFA SINTETICA LTDA"), {(x.polo, x.nome) for x in p.personagens})
        self.assertTrue(p.movimentos)
        self.assertEqual(estado(campos.extrair(p, ["EMPRESA ALFA"]), "parte_alvo_no_polo_passivo").estado, campos.SIM)
        self.assertTrue((self.d / "documentos" / N / "doc1-sentenca.txt").exists())
        self.assertIn(N, (self.d / "entrada" / "lista-convertidos.txt").read_text(encoding="utf-8"))

    def test_eproc_despejo_separa_segredo_de_justica(self):
        dump = {N: "Segredo de Justiça" + NL + "capa sem eventos " + N}
        r = self.roda("eproc-despejo", self.despejo("e.json", dump))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.d / "entrada" / (N + ".txt")).exists())
        self.assertEqual((self.d / "saida" / "sigilosos.txt").read_text(encoding="utf-8").strip(), N)

    def test_pecas_eproc_nomeia_rotulo_com_numero_sem_duplicar(self):
        dump = {N: [{"ev": 5, "label": "ACOR2", "text": "ACÓRDÃO: nego provimento."},
                    {"ev": 6, "label": "SENT1", "text": "SENTENÇA"}, {"ev": 7, "label": "DEC1", "erro": True, "text": "x"}]}
        r = self.roda("pecas-eproc", self.despejo("c.json", dump))
        self.assertEqual(r.returncode, 0, r.stderr)
        nomes = sorted(x.name for x in (self.d / "documentos" / N).iterdir())
        self.assertEqual(nomes, ["ev5-acordao2.txt", "ev6-sentenca1.txt"])   # nunca "ACOR22"
        self.assertIn("sem texto 1", r.stdout)

    def test_pje_da_tela_com_json_duplo_do_receptor(self):
        rec = self.d / "entrada" / "_recebido"
        recd = self.d / "entrada" / "_recebido_docs"
        rec.mkdir(parents=True)
        recd.mkdir()
        (rec / (N + ".txt")).write_text(
            "Processo " + N + NL + "FULANO SINTETICO X EMPRESA ALFA SINTETICA LTDA" + NL + NL +
            "10 mar 2025" + NL + "SENTENÇA" + NL + "14:30" + NL, encoding="utf-8")
        docs = [{"lab": "123456 - Sentença", "text": "Julgo procedente."}, {"lab": "123457 - Petição", "pdf": True, "text": "x"}]
        (recd / (N + ".json")).write_text(json.dumps(json.dumps(docs)), encoding="utf-8")   # JSON dentro de string
        r = self.roda("pje")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.d / "entrada" / (N + ".txt")).exists())
        self.assertEqual(sorted(x.name for x in (self.d / "documentos" / N).iterdir()), ["123456-sentenca.txt"])

    def test_numero_fora_da_lista_e_pulado(self):
        outro = "0000002-65.2025.8.99.0000"
        r = self.roda("pje-publico", self.despejo("p.json", {outro: {"capa": "", "movs": ["01/01/2025 10:00:00 - X"]}}))
        self.assertIn("pulados 1", r.stdout)
        self.assertFalse((self.d / "entrada" / (outro + ".txt")).exists())

    def test_recusa_pasta_de_dados_dentro_do_repositorio(self):
        r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CONV), "--dados", str(RAIZ / "tests"), "pecas-eproc"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dentro do repositório", r.stderr)


def estado(cs, nome):
    return next(c for c in cs if c.campo == nome)


if __name__ == "__main__":
    unittest.main()
