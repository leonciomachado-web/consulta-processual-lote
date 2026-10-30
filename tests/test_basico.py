import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from consulta_lote import campos, cnj, config, db, lista, parser, planilha  # noqa: E402

EX = RAIZ / "examples"
FICT1 = "0000001-80.2025.8.99.0000"


def estado(cs, nome):
    return next(c for c in cs if c.campo == nome)


class TesteCnj(unittest.TestCase):
    def test_ficticio_valido(self):
        c = cnj.tratar(FICT1)
        self.assertTrue(c.dv_confere)
        self.assertEqual(c.digitos, "00000018020258990000")

    def test_espaco_e_sem_pontuacao(self):
        self.assertEqual(cnj.tratar(" 0000001-80.2025.8.99.0000 ").formatado, FICT1)
        self.assertEqual(cnj.tratar("00000018020258990000").formatado, FICT1)

    def test_invalido(self):
        self.assertIsNone(cnj.tratar("123"))
        self.assertFalse(cnj.tratar("0000001-81.2025.8.99.0000").dv_confere)

    def test_hash_depende_do_segredo(self):
        c = cnj.tratar(FICT1)
        self.assertNotEqual(cnj.hash_do_processo(c, b"a"), cnj.hash_do_processo(c, b"b"))


class TesteGuarda(unittest.TestCase):
    def test_recusa_pasta_dentro_do_repositorio(self):
        with self.assertRaises(config.DadosDirInvalido):
            config.dados_dir(RAIZ / "dados-aqui", criar=False)

    def test_recusa_escrita_dentro_do_repositorio(self):
        with self.assertRaises(config.DadosDirInvalido):
            config.proteger_escrita(RAIZ / "x.sqlite")

    def test_aceita_pasta_fora_sem_git(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(config.dados_dir(t), Path(t).resolve())

    def test_recusa_pasta_em_outro_repo_nao_ignorado(self):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["git", "init", "-q", t], check=True)
            with self.assertRaises(config.DadosDirInvalido):
                config.dados_dir(Path(t) / "dados", criar=False)

    def test_aceita_pasta_em_outro_repo_se_ignorada(self):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["git", "init", "-q", t], check=True)
            (Path(t) / ".gitignore").write_text("dados/\n")
            self.assertEqual(config.dados_dir(Path(t) / "dados", criar=False), (Path(t) / "dados").resolve())


class TesteParser(unittest.TestCase):
    def setUp(self):
        self.p1 = parser.ler((EX / "processo_sintetico_1.txt").read_text(encoding="utf-8"))

    def test_capa_e_cnj(self):
        self.assertEqual(self.p1.cnj.formatado, FICT1)
        self.assertEqual(self.p1.capa["comarca"], "Comarca Ficticia")
        self.assertEqual(self.p1.sistema, "legado")

    def test_personagens(self):
        polos = {(x.polo, x.nome) for x in self.p1.personagens}
        self.assertIn(("ativo", "FULANO DE TAL SINTETICO"), polos)
        self.assertIn(("passivo", "EMPRESA ALFA SINTETICA LTDA"), polos)

    def test_movimentos_e_integra(self):
        self.assertEqual(len(self.p1.movimentos), 7)
        self.assertEqual(self.p1.movimentos[0].tipo, "Baixa Definitiva")
        self.assertEqual(len(self.p1.documentos), 1)


class TesteCampos(unittest.TestCase):
    def setUp(self):
        self.p1 = parser.ler((EX / "processo_sintetico_1.txt").read_text(encoding="utf-8"))
        self.p2 = parser.ler((EX / "processo_sintetico_2.txt").read_text(encoding="utf-8"))
        self.c1 = campos.extrair(self.p1, ["EMPRESA ALFA"])
        self.c2 = campos.extrair(self.p2, ["EMPRESA ALFA"])

    def test_completo_preenche_com_evidencia(self):
        self.assertEqual(estado(self.c1, "parte_alvo_no_polo_passivo").estado, campos.SIM)
        self.assertEqual(estado(self.c1, "pericia").estado, campos.SIM)
        self.assertEqual(estado(self.c1, "acordo").estado, campos.SIM)
        self.assertEqual(estado(self.c1, "desistencia_ou_renuncia").estado, campos.SIM)
        self.assertEqual(estado(self.c1, "decisao").estado, campos.SIM)
        t = estado(self.c1, "transito_em_julgado")
        self.assertEqual(t.estado, campos.SIM)
        self.assertIn("10/12/2025", t.valor)

    def test_juizo_humano_nunca_sai_por_regra(self):
        j = estado(self.c1, "decisao_juizo")
        self.assertEqual(j.estado, campos.NV)
        self.assertEqual(j.motivo, "juizo_humano")
        self.assertIn("JULGO PROCEDENTE", j.evidencia)
        self.assertEqual(estado(self.c1, "pericia_laudo_juizo").estado, campos.NV)

    def test_toda_evidencia_confere_no_texto_bruto(self):
        for cs in (self.c1, self.c2):
            for c in cs:
                self.assertTrue(c.evidencia_confere, c.campo)
                if c.estado in (campos.SIM, campos.NAO):
                    self.assertTrue(c.evidencia, c.campo)

    def test_ausencia_nao_vira_nao_houve(self):
        # processo 2 tem lista parcial: tudo que não aparece é NAO_VISIVEL
        for nome in ("pericia", "acordo", "desistencia_ou_renuncia", "decisao", "transito_em_julgado"):
            c = estado(self.c2, nome)
            self.assertEqual(c.estado, campos.NV, nome)
            self.assertEqual(c.motivo, "lista_parcial", nome)
        self.assertEqual(estado(self.c2, "parte_alvo_no_polo_passivo").estado, campos.NV)

    def test_lista_completa_sem_parte_alvo_vira_nao(self):
        c = campos.partes(self.p1, ["OUTRA EMPRESA"])
        self.assertEqual(c.estado, campos.NAO)

    def test_evidencia_forjada_e_rebaixada(self):
        c = campos.Campo(campo="x", estado=campos.SIM, evidencia="texto que não existe no bruto")
        campos._confere(self.p1, c)
        self.assertEqual(c.estado, campos.NV)
        self.assertEqual(c.motivo, "evidencia_nao_confere")

    def test_aguardando_transito_nao_e_transito(self):
        txt = "Processo Nº 0000002-65.2025.8.99.0000\nLocalização na Serventia\nAguardando Trânsito Julgado\n"
        p = parser.ler(txt)
        t = campos.transito(p)
        self.assertEqual(t.estado, campos.NAO)
        self.assertEqual(campos.fase(p).valor, "aguardando trânsito em julgado")

    def test_comparacao_com_a_base_reporta_sem_corrigir(self):
        f = estado(self.c1, "fase")
        self.assertEqual(campos.compara_fase("FASE INICIAL", f), "diverge")
        self.assertEqual(campos.compara_fase("PAGAMENTO FINAL", f), "coincide")
        self.assertEqual(campos.compara_fase(None, f), "indeterminado")


class TesteBancoEPlanilha(unittest.TestCase):
    def test_ciclo_completo(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            con = db.abrir(d)
            for nome in ("processo_sintetico_1.txt", "processo_sintetico_2.txt"):
                p = parser.ler((EX / nome).read_text(encoding="utf-8"))
                db.gravar(con, d, p.cnj, p.sistema, "2025-01-15", p.meta.get("fase_base"), nome,
                          campos.extrair(p, ["EMPRESA ALFA"]))
            self.assertEqual(con.execute("select count(*) from processo").fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):  # SIM sem evidência é barrado pelo banco
                con.execute("INSERT INTO campo(hash,campo,estado,evidencia_literal) "
                            "SELECT hash,'teste','SIM','' FROM processo LIMIT 1")
            saida = planilha.gerar(con, d / "p.xlsx")
            from openpyxl import load_workbook
            ws = load_workbook(saida)["Processos"]
            self.assertEqual(ws.max_row, 3)
            self.assertEqual(ws.cell(row=2, column=1).value, FICT1)
            con.close()

    def test_reimportar_mantem_conferencia(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            con = db.abrir(d)
            p = parser.ler((EX / "processo_sintetico_1.txt").read_text(encoding="utf-8"))
            h = db.gravar(con, d, p.cnj, p.sistema, "", None, "a", campos.extrair(p, ["EMPRESA ALFA"]))
            con.execute("UPDATE campo SET revisao_humana='conferido' WHERE hash=? AND campo='acordo'", (h,))
            db.gravar(con, d, p.cnj, p.sistema, "", None, "a", campos.extrair(p, ["EMPRESA ALFA"]))
            r = con.execute("select revisao_humana from campo where hash=? and campo='acordo'", (h,)).fetchone()[0]
            self.assertEqual(r, "conferido")
            con.close()


def _linha(n, bruto, **a):
    return lista.Linha(n=n, cnj_bruto=bruto, cnj=cnj.tratar(bruto), atributos=a)


class TesteLista(unittest.TestCase):
    def test_classifica_com_motivo_e_alerta(self):
        base = dict(tribunal="Ficticio", tipo_pasta="ACAO", tipo_vara="CIVEL", fase_base="FASE INICIAL")
        linhas = [
            _linha(2, FICT1, **base),
            _linha(3, "", **base),
            _linha(4, "123", **base),
            _linha(5, "0000002-65.2025.8.99.0000", **{**base, "tipo_pasta": "ADMINISTRATIVO"}),
            _linha(6, "0000003-50.2025.8.99.0000", **{**base, "tipo_vara": "CRIMINAL"}),
            _linha(7, "0000003-50.2025.8.99.0000", **{**base, "tribunal": "Outro"}),
        ]
        regras = {"jtr_alvo": "8.99", "rotulo_tribunal_esperado": "Ficticio",
                  "excluir_tipo_pasta_contem": ["ADMINISTRATIVO"], "excluir_tipo_vara_contem": ["CRIMINAL"]}
        el, ex, al = lista.classificar(linhas, regras)
        self.assertEqual([l.n for l in el], [2, 7])
        motivos = {l.n: m for l, m in ex}
        self.assertEqual(motivos[3], "sem número de processo")
        self.assertEqual(motivos[4], "número fora do padrão")
        self.assertTrue(motivos[5].startswith("tipo da pasta"))
        self.assertTrue(motivos[6].startswith("tipo de vara"))
        self.assertEqual([l.n for l, _ in al], [7])  # rótulo do tribunal diverge do número

    def test_sorteio_com_semente_e_reprodutivel(self):
        el = [lista.Linha(n=i, cnj_bruto="", cnj=None, atributos={"fase_base": "FASE INICIAL"}) for i in range(20)]
        a = lista.sortear_piloto(el, {"inicial": 5}, 7)
        b = lista.sortear_piloto(el, {"inicial": 5}, 7)
        self.assertEqual([l.n for l in a], [l.n for l in b])
        self.assertEqual(len(a), 5)


class TesteVarredura(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(RAIZ / "scripts"))
        import scan
        self.scan = scan

    def test_pega_termo_e_cnj_real_mas_deixa_o_ficticio(self):
        self.assertTrue(self.scan.varre("cliente Fulano", "x", ["fulano"]))
        self.assertTrue(self.scan.varre("1234567" + "-89.2021.8.26.0100", "x", []))
        self.assertTrue(self.scan.varre("12345678" + "920218260100", "x", []))
        self.assertFalse(self.scan.varre(FICT1, "x", []))

    def test_falha_fechada_sem_lista(self):
        os.environ["CONSULTA_LOTE_TERMOS"] = str(RAIZ / "nao-existe.txt")
        try:
            with self.assertRaises(SystemExit):
                self.scan.termos()
        finally:
            del os.environ["CONSULTA_LOTE_TERMOS"]


class TesteSeguranca(unittest.TestCase):
    def test_neutraliza_formula(self):
        from consulta_lote.seguro import neutraliza
        for perigoso in ("=1+1", "+cmd", "-2", "@SOMA(A1)", chr(9) + "x", chr(13) + "x"):
            self.assertTrue(neutraliza(perigoso).startswith("'"), perigoso)
        self.assertEqual(neutraliza("texto"), "texto")
        self.assertEqual(neutraliza(5), 5)

    def test_planilha_nao_grava_formula(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            con = db.abrir(d)
            p = parser.ler((EX / "processo_sintetico_1.txt").read_text(encoding="utf-8"))
            db.gravar(con, d, p.cnj, p.sistema, "", "=HYPERLINK(\"http://x\")", "a", campos.extrair(p, ["EMPRESA ALFA"]))
            saida = planilha.gerar(con, d / "p.xlsx")
            from openpyxl import load_workbook
            v = load_workbook(saida)["Processos"].cell(row=2, column=3).value
            self.assertTrue(v.startswith("'="))
            con.close()

    def test_csv_nao_grava_formula(self):
        with tempfile.TemporaryDirectory() as t:
            arq = lista.gravar_csv(Path(t) / "x.csv", ["a"], [["=1+1"], ["ok"]])
            linhas = arq.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(linhas[1], "'=1+1")

    def test_guarda_exige_todos_os_artefatos_ignorados(self):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["git", "init", "-q", t], check=True)
            (Path(t) / ".gitignore").write_text("dados/*.sqlite" + chr(10))  # só um dos artefatos
            with self.assertRaises(config.DadosDirInvalido):
                config.dados_dir(Path(t) / "dados", criar=False)

    def test_scan_le_arquivo_com_acento_e_espaco_no_nome(self):
        sys.path.insert(0, str(RAIZ / "scripts"))
        import scan
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["git", "init", "-q", t], check=True)
            nome = "ação com espaço.txt"
            (Path(t) / nome).write_text("cliente Fulano", encoding="utf-8")
            (Path(t) / "dados.csv").write_text("a,b", encoding="utf-8")
            subprocess.run(["git", "-C", t, "add", "-A"], check=True)
            antigo = scan.RAIZ
            scan.RAIZ = Path(t)
            try:
                self.assertIn(nome, scan.arquivos_em_stage())
                achados = scan.pre_commit(["fulano"])
            finally:
                scan.RAIZ = antigo
            self.assertTrue(any("termo proibido" in a for a in achados))
            self.assertTrue(any("tipo de arquivo" in a for a in achados))


if __name__ == "__main__":
    unittest.main()
