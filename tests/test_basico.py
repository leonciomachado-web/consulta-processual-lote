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

    def test_numero_partido_em_duas_linhas_e_pego(self):
        partido = "1234567-89.2021.8" + chr(10) + ".26.0100"
        self.assertTrue(self.scan.varre(partido, "x", []))
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
            "Nível de Sigilo:" + chr(10) + "0 anexos juntados": False,   # rótulo vazio, próxima linha não é valor
            "Nível de Sigilo: 01": False,
            "Nível de Sigilo: 0 (Público) extra": False,                  # correspondência completa
            "Nível de Sigilo: 0 - Público": True,
            "Nível de Sigilo" + chr(10) + ": 1": False,               # quebra antes dos dois-pontos
            "Nível de Sigilo" + chr(10) + "1 (Segredo)": False,        # rótulo sem dois-pontos nem valor legível
            "Nível  de   Sigilo   :  0": True,
            "Nível de Sigilo" + chr(10) + "1 (Segredo)" + chr(10) + "Sigilo: 0": False,   # um valor não compensa o outro
            "Texto" + chr(10) + "Nível de Sigilo:" + chr(10) + chr(10) + "0": False,   # linha em branco no meio
        }
        for texto, publico in casos.items():
            niveis = cli._niveis_de_sigilo(texto)
            self.assertTrue(niveis, texto)
            self.assertEqual(all(cli._e_publico(v) for v in niveis), publico, repr(texto))


class TesteEproc(unittest.TestCase):
    def setUp(self):
        self.p = parser.ler((EX / "processo_sintetico_eproc.txt").read_text(encoding="utf-8"))
        self.c = campos.extrair(self.p, ["EMPRESA ALFA"])

    def test_eventos_numerados(self):
        self.assertEqual(len(self.p.movimentos), 8)
        self.assertEqual(self.p.movimentos[0].data, "20/06/2025")
        self.assertTrue(self.p.movimentos[0].tipo.startswith("Decorrido prazo"))
        self.assertEqual(self.p.movimentos[-1].tipo, "Juntado(a) - Petição Inicial")

    def test_polo_vem_dos_eventos(self):
        polos = {(x.polo, x.nome) for x in self.p.personagens}
        self.assertIn(("passivo", "EMPRESA ALFA SINTETICA LTDA"), polos)
        self.assertIn(("ativo", "FULANO SINTETICO"), polos)
        c = estado(self.c, "parte_alvo_no_polo_passivo")
        self.assertEqual(c.estado, campos.SIM)
        self.assertEqual(c.evidencia, "(RÉU - EMPRESA ALFA SINTETICA LTDA)")
        self.assertTrue(c.localizacao.startswith("evento"))

    def test_marcos_do_eproc(self):
        self.assertEqual(estado(self.c, "fase").valor, "instrutória")
        self.assertEqual(estado(self.c, "pericia").estado, campos.SIM)   # perito intimado
        self.assertEqual(estado(self.c, "decisao").estado, campos.NV)    # ainda sem sentença
        self.assertEqual(estado(self.c, "transito_em_julgado").estado, campos.NV)
        self.assertEqual(campos.compara_fase("FASE INICIAL", estado(self.c, "fase")), "base_defasada")

    def test_evidencias_conferem(self):
        for c in self.c:
            self.assertTrue(c.evidencia_confere, c.campo)

    def test_cabecalho_de_colunas_nao_vira_parte(self):
        p = parser.ler("AUTOR" + chr(9) + "RÉU" + chr(10) + "AUTOR   RÉU" + chr(10))
        self.assertEqual(p.personagens, [])


class TesteEprocSentenca(unittest.TestCase):
    def _txt(self, titulo):
        nl = chr(10)
        return ("#! sistema: eproc" + nl + "#! cnj: 0000002-65.2025.8.99.0000" + nl + "#! movimentos_lista_completa: sim" + nl
                + "AUTOR" + chr(9) + "RÉU" + nl + nl + "FULANO SINTETICO (000.000.000-00)" + chr(160) + " - Pessoa Física" + nl
                + "EMPRESA ALFA SINTETICA LTDA (00.000.000/0001-00)" + chr(160) + " - Pessoa Jurídica" + nl + "e outros" + nl
                + "Informações Adicionais" + nl + "Eventos" + nl + nl
                + "3" + chr(160) + nl + chr(9) + "10/06/2026 10:00:00" + chr(9) + titulo + chr(9) + nl + "SENT1" + nl + nl
                + "1" + chr(160) + nl + chr(9) + "10/01/2026 09:00:00" + chr(9) + "Juntado(a) - Petição Inicial" + chr(9) + nl + "SISTEMA" + nl)

    def test_julgado_improcedente_e_favoravel_a_reu(self):
        p = parser.ler(self._txt("Julgado improcedente o pedido"))
        cs = campos.extrair(p, ["EMPRESA ALFA"])
        self.assertEqual(estado(cs, "decisao").estado, campos.SIM)
        self.assertIn("FAVORÁVEL", estado(cs, "decisao_juizo").valor)
        self.assertNotIn("DESFAVORÁVEL", estado(cs, "decisao_juizo").valor)
        self.assertEqual(estado(cs, "fase").valor, "sentenciado")

    def test_julgado_procedente_e_desfavoravel(self):
        cs = campos.extrair(parser.ler(self._txt("Julgado procedente em parte o pedido")), ["EMPRESA ALFA"])
        self.assertIn("DESFAVORÁVEL", estado(cs, "decisao_juizo").valor)

    def test_partes_pelas_colunas_autor_e_reu(self):
        p = parser.ler(self._txt("Julgado improcedente o pedido"))
        polos = {(x.polo, x.nome) for x in p.personagens}
        self.assertIn(("ativo", "FULANO SINTETICO"), polos)
        self.assertIn(("passivo", "EMPRESA ALFA SINTETICA LTDA"), polos)
        c = campos.partes(p, ["OUTRA EMPRESA"])
        self.assertEqual(c.estado, campos.NV)   # coluna mostra só uma parte: nunca vira NAO


class TesteCpf(unittest.TestCase):
    def test_cpf_nao_vai_para_evidencia_nem_para_valor(self):
        txt = ("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "=== INTEGRA decisao-1 ===" + chr(10)
               + "Homologo o acordo de FULANO SINTETICO (123.456.789-09) com a parte." + chr(10) + "=== FIM ===" + chr(10))
        cs = campos.extrair(parser.ler(txt), ["X"])
        for c in cs:
            self.assertNotRegex(c.evidencia or "", "[0-9]{3}[.][0-9]{3}[.][0-9]{3}-[0-9]{2}", c.campo)
            self.assertNotRegex(c.valor or "", "[0-9]{3}[.][0-9]{3}[.][0-9]{3}-[0-9]{2}", c.campo)
        acordo = next(c for c in cs if c.campo == "acordo")
        self.assertIn("***.***.***-**", acordo.evidencia)
        self.assertTrue(acordo.evidencia_confere)  # a conferência literal aconteceu antes da máscara

    def test_parte_das_colunas_guarda_so_o_nome(self):
        nl = chr(10)
        txt = ("#! cnj: 0000002-65.2025.8.99.0000" + nl + "AUTOR" + chr(9) + "RÉU" + nl
               + "FULANO SINTETICO (123.456.789-09)" + chr(160) + " - Pessoa Física" + nl
               + "EMPRESA ALFA SINTETICA LTDA (00.000.000/0001-00)" + chr(160) + " - Pessoa Jurídica" + nl
               + "Informações Adicionais" + nl)
        p = parser.ler(txt)
        for per in p.personagens:
            self.assertNotIn("(", per.linha)
        c = campos.partes(p, ["EMPRESA ALFA"])
        self.assertEqual(c.evidencia, "EMPRESA ALFA SINTETICA LTDA")
        self.assertTrue(campos.extrair(p, ["EMPRESA ALFA"])[0].evidencia_confere)


class TesteCpfVariantes(unittest.TestCase):
    def test_variantes_de_cpf_sao_mascaradas_e_numero_de_processo_nao(self):
        for v in ("123.456.789-09", "12345678909", "123 456 789 09", "123.456.789/09", "123456789-09"):
            self.assertNotIn("789", campos.mascara_cpf("parte FULANO " + v + " fim"), v)
        proc = FICT1
        self.assertEqual(campos.mascara_cpf("processo " + proc), "processo " + proc)
        self.assertEqual(campos.mascara_cpf("CNPJ 00.000.000/0001-00"), "CNPJ 00.000.000/0001-00")

    def test_todos_os_campos_de_texto_sao_mascarados(self):
        txt = ("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "=== INTEGRA decisao-123.456.789-09 ===" + chr(10)
               + "Homologo o acordo de FULANO SINTETICO." + chr(10) + "=== FIM ===" + chr(10))
        for c in campos.extrair(parser.ler(txt), ["X"]):
            for atributo in ("evidencia", "valor", "fonte", "localizacao", "documento_origem"):
                self.assertNotIn("123.456.789", getattr(c, atributo) or "", (c.campo, atributo))

    def test_truncamento_nao_deixa_cpf_partido(self):
        longa = "Homologo o acordo " + "palavra " * 20 + "de FULANO 123.456.789-09 fim"
        txt = "#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "=== INTEGRA d ===" + chr(10) + longa + chr(10) + "=== FIM ==="
        ev = campos._trecho(longa, campos.R_ACORDO, janela=45)
        self.assertNotRegex(ev or "", "[0-9]{3}[.][0-9]{1,3}")


class TesteLevantamento(unittest.TestCase):
    def _resp(self, codigos, sistema="Projudi"):
        movs = [{"codigo": c, "nome": "x", "dataHora": "2026-0%d-10T10:00:00.000Z" % (i + 1)} for i, c in enumerate(codigos)]
        return {"hits": {"hits": [{"_source": {"sistema": {"nome": sistema}, "grau": "G1", "movimentos": movs,
                                                "orgaoJulgador": {"nome": "VARA"}, "classe": {"nome": "Comum"},
                                                "dataAjuizamento": "20250110090000",
                                                "dataHoraUltimaAtualizacao": "2026-09-01T10:00:00Z"}}]}}

    def test_triagem_por_marcos_e_sistema(self):
        from consulta_lote import levantamento as lv
        c = cnj.tratar(FICT1)
        self.assertEqual(lv.linha(c, None)["encontrado"], "nao")
        migrado = lv.linha(c, self._resp([15417]))
        self.assertEqual(migrado["sistema_provavel"], "eproc")
        self.assertEqual(migrado["migrado_em"], "10/01/2026")
        sent = lv.linha(c, self._resp([219]))
        self.assertTrue(sent["sentenca_em"])
        self.assertIn("ler a sentença", sent["proximo_passo"])
        enc = lv.linha(c, self._resp([219, 848, 22], sistema="PJe"))
        self.assertEqual(enc["sistema_provavel"], "pje")
        self.assertIn("encerrado", enc["proximo_passo"])
        self.assertEqual(lv.linha(c, self._resp([85]))["sistema_provavel"], "legado")


class TesteCpfCentral(unittest.TestCase):
    def test_variantes_extras(self):
        for v in ("123.456.789-09/2025", "123" + chr(0x2013) + "456" + chr(0x2013) + "789" + chr(0x2013) + "09",
                  "123" + chr(160) + "456" + chr(160) + "789" + chr(160) + "09", "x/12345678909/y"):
            self.assertNotIn("789", campos.mascara_cpf("parte " + v), v)
        self.assertEqual(campos.mascara_cpf("CNPJ 00.000.000/0001-00 ok"), "CNPJ 00.000.000/0001-00 ok")
        self.assertEqual(campos.mascara_cpf("proc " + FICT1 + " ok"), "proc " + FICT1 + " ok")

    def test_blocos_e_planilha_mascaram_na_saida(self):
        from consulta_lote import blocos
        txt = ("#! cnj: 0000003-50.2025.8.99.0000" + chr(10) + "#! movimentos_lista_completa: sim" + chr(10)
               + "28 jan 2025" + chr(10) + "PARTE FULANO 123.456.789-09 INTIMADA" + chr(10) + "15:08" + chr(10))
        p = parser.ler(txt)
        cs = campos.extrair(p, ["X"])
        with tempfile.TemporaryDirectory() as t:
            for arq in blocos.gerar(p, cs, Path(t) / "b"):
                self.assertNotIn("123.456.789", arq.read_text(encoding="utf-8"), arq.name)
            d = Path(t)
            con = db.abrir(d)
            db.gravar(con, d, p.cnj, "123.456.789-09", "", None, "a", cs)  # até o sistema, se tiver CPF
            from openpyxl import load_workbook
            ws = load_workbook(planilha.gerar(con, d / "p.xlsx"))["Processos"]
            for linha in ws.iter_rows(values_only=True):
                for cel in linha:
                    self.assertNotIn("123.456.789", str(cel))
            con.close()


class TesteCpfExtra(unittest.TestCase):
    def test_separadores_multiplos_largura_zero_e_algarismos_largos(self):
        casos = ["123 - 456 - 789 - 09", "123" + chr(0x200B) + "456" + chr(0x200B) + "789" + chr(0x200B) + "09",
                 "".join(chr(0xFF10 + int(c)) for c in "12345678909"), "123" + chr(10) + "456" + chr(10) + "789" + chr(10) + "09"]
        for v in casos:
            self.assertNotRegex(campos.mascara_cpf("parte " + v + " fim"), "789|" + chr(0xFF17) + chr(0xFF18) + chr(0xFF19), repr(v))
        self.assertEqual(campos.mascara_cpf("CNPJ 00.000.000/0001-00 e " + FICT1), "CNPJ 00.000.000/0001-00 e " + FICT1)


class TesteSaidaEPainel(unittest.TestCase):
    def test_modelo_gera_planilha_e_painel(self):
        from consulta_lote import modelos
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as t:
            xlsx, html = modelos.gravar(Path(t))
            wb = load_workbook(xlsx)
            self.assertEqual(wb.sheetnames, ["Resumo", "Processos", "Evidências", "Pendências de revisão", "Perguntas e legenda"])
            self.assertEqual(wb["Processos"].max_row, 9)  # 8 processos + cabeçalho
            resumo = wb["Resumo"]
            self.assertTrue(str(resumo["B3"].value).startswith("=COUNTA("))
            texto = html.read_text(encoding="utf-8")
            self.assertIn("MODELO COM DADOS INVENTADOS", texto)
            self.assertNotIn("/*__DADOS__*/", texto)
            self.assertIn("0000001-", texto)

    def test_html_nao_deixa_texto_do_processo_fechar_o_script(self):
        from consulta_lote import painel
        d = {"gerado_em": "x", "processos": [{"numero": "n", "obs": "</script><script>alert(1)</script>"}],
             "filtros": [], "graficos": [], "perguntas": []}
        html = painel.renderizar_html(d)
        dentro = html.split('id="dados" type="application/json">')[1].split("</script>")[0]
        self.assertNotIn("<script>", dentro)
        self.assertEqual(html.count("</script>"), 2)  # o dos dados e o do programa

    def test_cpf_mascarado_na_planilha_e_no_painel(self):
        from consulta_lote import modelos, painel, saida
        from openpyxl import load_workbook
        d = modelos.dados_modelo()
        d["processos"][0]["campos"]["acordo"]["evidencia"] = "FULANO SINTETICO (123.456.789-09) acordou"
        d["processos"][0]["proximo_passo"] = "ligar para 123 456 789 09"
        with tempfile.TemporaryDirectory() as t:
            self.assertNotIn("123.456.789", painel.renderizar_html(d))
            ws = load_workbook(saida.gerar(d, Path(t) / "s.xlsx"))
            for folha in ws.worksheets:
                for linha in folha.iter_rows(values_only=True):
                    for cel in linha:
                        self.assertNotIn("789-09", str(cel))
                        self.assertNotIn("789 09", str(cel))

    def test_montar_dados_une_base_datajud_e_analise(self):
        from consulta_lote import painel
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "saida").mkdir()
            (d / "saida" / "elegiveis.csv").write_text(
                "linha;numero;comarca;fase_base;valor_causa;tipo_pasta" + chr(10)
                + "2;" + FICT1 + ";COMARCA ALFA;FASE INICIAL;45000;AÇÃO JUDICIAL" + chr(10), encoding="utf-8-sig")
            dados = painel.montar_dados(d)
            r = dados["processos"][0]
            self.assertEqual(r["analise"], "não consultado")
            self.assertEqual(r["faixa_valor"], "20 a 50 mil")
            self.assertEqual(r["fase_base_cat"], "inicial")
            self.assertEqual(r["ano"], "2025")
            self.assertTrue(len(dados["filtros"]) >= 20)


class TesteTruncamentoCpf(unittest.TestCase):
    def test_cpf_com_travessao_e_sublinhado_cortado_no_meio(self):
        en = chr(0x2013)
        for corpo in ("123" + en + "456" + en + "789" + en + "09", "123_456_789_09", "123 / 456 / 789 / 09"):
            longa = "Homologo o acordo " + "palavra " * 5 + "de FULANO " + corpo + " fim"
            ate = longa.index(corpo)
            for corte in range(ate + 3, ate + len(corpo)):
                ev = campos._trecho(longa, campos.R_ACORDO, janela=corte // 2 + 1)
                self.assertNotRegex(ev or "", "[0-9]{3}[^0-9A-Za-z]{0,6}[0-9]", (corpo, corte))


if __name__ == "__main__":
    unittest.main()
