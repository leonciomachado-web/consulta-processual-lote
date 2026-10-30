# Análise por blocos

`python -m consulta_lote blocos <texto-do-processo.txt>` cria, na pasta de dados local (nunca neste
repositório), uma pasta `analises/<numero>/blocos/` com um arquivo por bloco:

| Bloco | Conteúdo automático (regras, evidência literal) |
|---|---|
| 00-identificacao | número, sistema, data da consulta, documentos lidos e o acesso de cada um, sigilo |
| 01-fluxo-temporal | cronologia literal dos movimentos |
| 02-partes | parte-alvo no polo passivo e parte-alvo citada |
| 03-pericia | existência de perícia; o juízo sobre o laudo é humano |
| 04-acordo-e-desistencia | acordo; desistência e renúncia |
| 05-decisoes | sentença ou acórdão; o juízo "favorável" é humano |
| 06-transito-e-fase | trânsito (a certidão vence o movimento do histórico) e fase atual |
| 07-armadilhas | armadilhas de leitura detectadas, com como detectar |
| 08-chance-de-perda | só se pedido; rótulo "chance de perda" |
| resumo | tabela dos sete itens, comparação com a fase da base do cliente e pendências |

Regras do método:
- Três camadas em todo bloco: (a) literal, (b) paráfrase, (c) análise. A regra gera só (a).
  (b) e (c) são escritas por uma pessoa, fora dos marcadores `auto:inicio` e `auto:fim`.
- Regenerar um bloco reescreve só a parte entre os marcadores e guarda a versão anterior em
  `versoes/`. O texto escrito pela pessoa não é tocado.
- O que a busca não confirma vira `[CONFERIR NA FONTE: ...]`. Nunca há suposição.
- Só a pessoa que revisa marca um bloco como concluído (`_HANDOFF.md` da pasta).
- Documentos: coloque o texto de cada documento do processo em
  `<pasta de dados>/documentos/<numero>/<id>-<tipo>.txt`. O arquivo `processo-completo.txt` é
  ignorado; a análise usa os documentos separados.
- Comparação com a fase da base do cliente: `coincide`, `base_defasada` (o tribunal está em etapa
  posterior, por exemplo arquivado depois de extinção) ou `base_adiantada`. É reportada, não corrigida.
