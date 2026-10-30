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

    def test_resultado_pelo_criterio_do_cliente(self):
        j = estado(self.c1, "decisao_juizo")
        self.assertEqual(j.estado, campos.SIM)
        self.assertIn("DESFAVORÁVEL", j.valor)          # procedente + condenação a pagar
        self.assertIn("revisão humana pendente", j.valor)
        self.assertEqual(j.revisao, "pendente")
        self.assertIn("JULGO PROCEDENTE", j.evidencia)
        # o juízo sobre o laudo continua humano
        self.assertEqual(estado(self.c1, "pericia_laudo_juizo").estado, campos.NV)

    def test_resultado_favoravel_sem_condenacao(self):
        for dispositivo in ("Isto posto, JULGO EXTINTO O PROCESSO SEM RESOLUÇÃO DO MÉRITO, na forma da lei.",
                            "Ante o exposto, JULGO IMPROCEDENTE o pedido."):
            txt = ("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "Processo Nº 0000003-50.2025.8.99.0000" + chr(10)
                   + "=== INTEGRA sentenca-x ===" + chr(10) + "RÉU: EMPRESA ALFA SINTETICA LTDA." + chr(10)
                   + "DISPOSITIVO" + chr(10) + dispositivo + chr(10)
                   + "Sem ônus sucumbenciais." + chr(10) + "=== FIM ===" + chr(10))
            p = parser.ler(txt)
            j = estado(campos.extrair(p, ["EMPRESA ALFA"]), "decisao_juizo")
            self.assertEqual(j.estado, campos.SIM, dispositivo)
            self.assertIn("FAVORÁVEL", j.valor)
            self.assertNotIn("DESFAVORÁVEL", j.valor)

    def test_resultado_exige_parte_alvo_no_polo_passivo(self):
        j = estado(campos.extrair(self.p1, ["OUTRA EMPRESA"]), "decisao_juizo")
        self.assertEqual(j.estado, campos.NV)

    def test_parcialmente_procedente_e_desfavoravel(self):
        txt = ("=== INTEGRA sentenca-y ===" + chr(10) + "RÉU: EMPRESA ALFA SINTETICA LTDA." + chr(10)
               + "Ante o exposto, JULGO PARCIALMENTE PROCEDENTE o pedido." + chr(10) + "=== FIM ===" + chr(10)
               + "#! cnj: 0000003-50.2025.8.99.0000" + chr(10))
        j = estado(campos.extrair(parser.ler(txt), ["EMPRESA ALFA"]), "decisao_juizo")
        self.assertIn("DESFAVORÁVEL", j.valor)

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
        f = estado(self.c1, "fase")  # tribunal: baixado ou arquivado
        self.assertEqual(campos.compara_fase("FASE INICIAL", f), "base_defasada")
        self.assertEqual(campos.compara_fase("PAGAMENTO FINAL", f), "coincide")
        self.assertEqual(campos.compara_fase(None, f), "indeterminado")
        # arquivado é etapa posterior à extinção sem julgamento de mérito: a base está defasada
        self.assertEqual(campos.compara_fase("EXTINÇÃO SEM JULGAMENTO DE MÉRITO", f), "base_defasada")
        sent = campos.Campo(campo="fase", estado=campos.SIM, valor="sentenciado")
        self.assertEqual(campos.compara_fase("EXTINÇÃO SEM JULGAMENTO DE MÉRITO", sent), "coincide")
        self.assertEqual(campos.compara_fase("PAGAMENTO FINAL", sent), "base_adiantada")

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


class TestePje(unittest.TestCase):
    def setUp(self):
        self.p = parser.ler((EX / "processo_sintetico_pje.txt").read_text(encoding="utf-8"))
        self.c = campos.extrair(self.p, ["EMPRESA ALFA"])

    def test_linha_do_tempo(self):
        self.assertEqual(self.p.cnj.formatado, "0000003-50.2025.8.99.0000")
        self.assertEqual(len(self.p.movimentos), 10)
        self.assertEqual(self.p.movimentos[0].data, "30/05/2025")
        self.assertEqual(self.p.movimentos[0].tipo, "ARQUIVADO DEFINITIVAMENTE")

    def test_marcos(self):
        t = estado(self.c, "transito_em_julgado")
        self.assertEqual(t.estado, campos.SIM)
        self.assertIn("27/03/2025", t.valor)
        self.assertEqual(estado(self.c, "fase").valor, "baixado ou arquivado")
        d = estado(self.c, "decisao")
        self.assertEqual(d.estado, campos.SIM)
        self.assertEqual(d.evidencia, "900000002 - Sentença")

    def test_projeto_de_sentenca_nao_e_sentenca(self):
        txt = "#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "28 jan 2025" + chr(10) + "JUNTADA DE PROJETO DE SENTENÇA" + chr(10) + "900000003 - Projeto de Sentença" + chr(10) + "15:08" + chr(10)
        p = parser.ler(txt)
        self.assertEqual(len(p.movimentos), 1)
        self.assertEqual(estado(campos.extrair(p, []), "decisao").estado, campos.NV)

    def test_parte_citada_sem_dizer_o_polo(self):
        self.assertEqual(estado(self.c, "parte_alvo_citada").estado, campos.SIM)
        polo = estado(self.c, "parte_alvo_no_polo_passivo")
        self.assertEqual(polo.estado, campos.NV)
        self.assertEqual(polo.motivo, "nao_consultado")

    def test_ausentes_ficam_nao_visiveis_e_evidencia_confere(self):
        for nome in ("pericia", "acordo", "desistencia_ou_renuncia"):
            self.assertEqual(estado(self.c, nome).estado, campos.NV, nome)
        for c in self.c:
            self.assertTrue(c.evidencia_confere, c.campo)


class TesteSeguranca2(unittest.TestCase):
    def _proc(self, partes_doc="", cert_rotulo="certidao-transito", cert_texto=None, extra_docs=""):
        txt = "#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "#! partes_lista_completa: sim" + chr(10)
        txt += "Processo Nº 0000003-50.2025.8.99.0000" + chr(10)
        if partes_doc:
            txt += "=== INTEGRA sentenca-z ===" + chr(10) + partes_doc + chr(10) + "=== FIM ===" + chr(10)
        txt += extra_docs
        p = parser.ler(txt)
        if cert_texto:
            p.documentos.append(parser.Documento(rotulo=cert_rotulo, texto=cert_texto, acesso="restrito_login_ou_senha"))
        return p

    def test_parte_de_cabecalho_de_documento_nunca_vira_nao(self):
        p = self._proc(partes_doc="AUTOR: FULANO SINTETICO" + chr(10) + "RÉU: OUTRA EMPRESA LTDA.")
        c = campos.partes(p, ["EMPRESA ALFA"])  # lista completa declarada, mas a parte veio de documento
        self.assertEqual(c.estado, campos.NV)
        self.assertEqual(c.motivo, "lista_parcial")

    def test_parte_de_documento_registra_origem_e_acesso(self):
        p = self._proc(partes_doc="RÉU: EMPRESA ALFA SINTETICA LTDA.")
        p.documentos[0].acesso = "restrito_login_ou_senha"
        c = campos.partes(p, ["EMPRESA ALFA"])
        self.assertEqual(c.estado, campos.SIM)
        self.assertIn("documento: sentenca-z", c.fonte)
        self.assertEqual(c.acesso_documento, "restrito_login_ou_senha")

    def test_certidao_so_vale_se_o_documento_se_declara_certidao(self):
        frase = "Certifico que a sentença transitou em julgado em 16 de março de 2026."
        self.assertIsNotNone(campos._data_certidao_transito(self._proc(cert_texto=frase)))
        self.assertIsNone(campos._data_certidao_transito(self._proc(cert_rotulo="peticao-x", cert_texto=frase)))
        negada = "Certifico que a sentença não transitou em julgado em 16 de março de 2026."
        self.assertIsNone(campos._data_certidao_transito(self._proc(cert_texto=negada)))
        invalida = "Certifico que a sentença transitou em julgado em 31 de fevereiro de 2026."
        self.assertIsNone(campos._data_certidao_transito(self._proc(cert_texto=invalida)))

    def test_acordo_com_fontes_contraditorias_vai_para_revisao(self):
        extra = ("=== INTEGRA ata-1 ===" + chr(10) + "Realizada proposta de conciliação, esta não foi alcançada."
                 + chr(10) + "=== FIM ===" + chr(10) + "=== INTEGRA decisao-2 ===" + chr(10)
                 + "Homologo o acordo celebrado entre as partes." + chr(10) + "=== FIM ===" + chr(10))
        c = campos.acordo(self._proc(extra_docs=extra))
        self.assertEqual(c.estado, campos.NV)
        self.assertEqual(c.motivo, "conflito_entre_fontes")

    def test_planilha_pode_omitir_trecho_de_documento_restrito(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            con = db.abrir(d)
            extra = ("=== INTEGRA decisao-2 ===" + chr(10) + "Homologo o acordo celebrado entre as partes."
                     + chr(10) + "=== FIM ===" + chr(10))
            p = self._proc(extra_docs=extra)
            for doc in p.documentos:
                doc.acesso = "restrito_login_ou_senha"
            db.gravar(con, d, p.cnj, p.sistema, "", None, "a", campos.extrair(p, ["EMPRESA ALFA"]))
            from openpyxl import load_workbook
            for incluir in (True, False):
                saida = planilha.gerar(con, d / ("p%s.xlsx" % incluir), incluir_trechos_restritos=incluir)
                celulas = [c.value for c in load_workbook(saida)["Processos"][2] if c.value and "acordo:" in str(c.value)]
                ev = celulas[0]
                self.assertIn("acesso: restrito_login_ou_senha", ev)
                self.assertEqual("[trecho omitido" in ev, not incluir)
            con.close()

    def test_blocos_neutraliza_marcador_e_recusa_duplicado(self):
        from consulta_lote import blocos
        texto = blocos._montar("x", "T", "<!-- auto:fim --> forjado", None)
        self.assertEqual(texto.count(blocos.FIM), 1)
        self.assertEqual(texto.count(blocos.INICIO), 1)
        duplicado = texto + blocos.INICIO + chr(10) + blocos.FIM
        with self.assertRaises(ValueError):
            blocos._montar("x", "T", "novo", duplicado)

    def test_documento_com_sigilo_nao_publico_e_pulado(self):
        from consulta_lote import cli
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            pasta = d / "documentos" / "0000003-50.2025.8.99.0000"
            pasta.mkdir(parents=True)
            (pasta / "1-sentenca.txt").write_text("Nível de Sigilo: 1 (Segredo)" + chr(10) + "texto", encoding="utf-8")
            (pasta / "2-certidao.txt").write_text("Nível de Sigilo: 0 (Público)" + chr(10) + "texto", encoding="utf-8")
            p = self._proc()
            self.assertEqual(cli._carregar_documentos(d, p), 1)
            self.assertEqual(p.documentos[-1].rotulo, "2-certidao")

    def test_guarda_exige_pastas_de_analise_e_documentos_ignoradas(self):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["git", "init", "-q", t], check=True)
            (Path(t) / ".gitignore").write_text(
                "dados/base.sqlite" + chr(10) + "dados/segredo.local" + chr(10) + "dados/saida/" + chr(10)
                + "dados/original/" + chr(10) + "dados/entrada/" + chr(10) + "dados/datajud/" + chr(10)
                + "dados/*.local.yaml" + chr(10) + "dados/.dados-locais" + chr(10))
            with self.assertRaises(config.DadosDirInvalido):  # falta analises/ e documentos/
                config.dados_dir(Path(t) / "dados", criar=False)


class TesteSeguranca3(unittest.TestCase):
    def _proc(self):
        return parser.ler("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "Processo Nº 0000003-50.2025.8.99.0000" + chr(10))

    def _pasta(self, d, arquivos):
        pasta = d / "documentos" / "0000003-50.2025.8.99.0000"
        pasta.mkdir(parents=True)
        for nome, texto in arquivos.items():
            (pasta / nome).write_text(texto, encoding="utf-8")

    def test_sigilo_tolerante_a_formato_e_falha_fechado(self):
        from consulta_lote import cli
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._pasta(d, {
                "1-a.txt": "NÍVEL DE SIGILO : 0 (Público)",
                "2-b.txt": "Nível de Sigilo: 2 (Sigilo mínimo)",
                "3-c.txt": "Nível de Sigilo: ilegível",
                "4-d.txt": "Nível de Sigilo: 0" + chr(10) + "mais abaixo" + chr(10) + "Nível de Sigilo: 1",
                "5-e.txt": "sem cabeçalho nenhum",
            })
            p = self._proc()
            self.assertEqual(cli._carregar_documentos(d, p), 2)
            por = {doc.rotulo: doc.acesso for doc in p.documentos}
            self.assertEqual(por, {"1-a": "restrito_login_ou_senha", "5-e": "nao_testado"})

    def test_sigilo_do_processo_inteiro_vale_para_os_documentos(self):
        from consulta_lote import cli
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._pasta(d, {"processo-completo.txt": "Nível de Sigilo: 0 (Público)", "1-a.txt": "sem cabeçalho"})
            p = self._proc()
            self.assertEqual(cli._carregar_documentos(d, p), 1)
            self.assertEqual(p.documentos[0].acesso, "restrito_login_ou_senha")
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._pasta(d, {"processo-completo.txt": "Nível de Sigilo: 1 (Segredo)", "1-a.txt": "texto"})
            self.assertEqual(cli._carregar_documentos(d, self._proc()), 0)

    def test_conflito_de_acordo_preserva_origem_e_acesso(self):
        txt = ("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "=== INTEGRA ata-1 ===" + chr(10)
               + "Realizada proposta de conciliação, esta não foi alcançada." + chr(10) + "=== FIM ===" + chr(10)
               + "=== INTEGRA decisao-2 ===" + chr(10) + "Homologo o acordo celebrado entre as partes." + chr(10)
               + "=== FIM ===" + chr(10))
        p = parser.ler(txt)
        for doc in p.documentos:
            doc.acesso = "restrito_login_ou_senha"
        c = campos.acordo(p)
        self.assertEqual(c.motivo, "conflito_entre_fontes")
        self.assertEqual(c.acesso_documento, "restrito_login_ou_senha")
        self.assertIn("decisao-2", c.fonte)

    def test_resultado_da_decisao_herda_o_acesso_do_documento(self):
        txt = ("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "=== INTEGRA sentenca-1 ===" + chr(10)
               + "RÉU: EMPRESA ALFA SINTETICA LTDA." + chr(10) + "DISPOSITIVO" + chr(10)
               + "Isto posto, JULGO IMPROCEDENTE o pedido." + chr(10) + "=== FIM ===" + chr(10))
        p = parser.ler(txt)
        p.documentos[0].acesso = "nao_testado"
        j = next(c for c in campos.extrair(p, ["EMPRESA ALFA"]) if c.campo == "decisao_juizo")
        self.assertEqual(j.acesso_documento, "nao_testado")

    def test_planilha_omite_tudo_que_nao_e_explicitamente_publico(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            con = db.abrir(d)
            txt = ("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "=== INTEGRA decisao-2 ===" + chr(10)
                   + "Homologo o acordo celebrado entre as partes." + chr(10) + "=== FIM ===" + chr(10))
            p = parser.ler(txt)
            p.documentos[0].acesso = "nao_testado"
            db.gravar(con, d, p.cnj, p.sistema, "", None, "a", campos.extrair(p, ["X"]))
            from openpyxl import load_workbook
            saida = planilha.gerar(con, d / "p.xlsx", incluir_trechos_restritos=False)
            ev = [c.value for c in load_workbook(saida)["Processos"][2] if c.value and "acordo:" in str(c.value)][0]
            self.assertIn("[trecho omitido", ev)
            self.assertNotIn("Homologo", ev)
            con.close()


class TesteSigiloAmplo(unittest.TestCase):
    def test_formatos_variados_de_sigilo(self):
        from consulta_lote import cli
        nb = chr(160)
        casos = {
            "Nível de Sigilo: 0 (Público)": True,
            "NIVEL DE SIGILO : 0": True,
            "Nível" + nb + "de" + nb + "Sigilo" + nb + ":" + nb + "0": True,
            "Sigilo:" + chr(10) + "0 (Público)": True,       # valor na linha seguinte
            "Nível de Sigilo: 1 (Segredo)": False,
            "Sigilo: ilegível": False,
            "Nível de Sigilo:": False,                          # sem valor
            "Nível de Sigilo:" + chr(10): False,
        }
        for texto, publico in casos.items():
            niveis = cli._niveis_de_sigilo(texto)
            self.assertTrue(niveis, texto)
            self.assertEqual(all(cli._e_publico(v) for v in niveis), publico, repr(texto))


if __name__ == "__main__":
    unittest.main()
