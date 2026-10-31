# Rotas possíveis por sistema de tribunal

Consolidação dos aprendizados de uma leitura real de 674 processos. O programa **não acessa
sites**: ele só organiza o texto que uma pessoa copia da tela. Este documento diz **o que copiar,
de onde, e o que cada sistema entrega** para os 7 itens (parte-alvo, fase, perícia, acordo,
desistência, sentença ou acórdão, trânsito).

Sem número de processo, nome de parte ou nome de tribunal: vale para qualquer tribunal estadual
que use estes sistemas. Cada usuário responde pelos termos de uso do tribunal que consulta.

## Quadro geral

| Sistema | Sem login | Com login de advogado | Entrega bem | Não entrega |
|---|---|---|---|---|
| Portal público do sistema antigo (processo físico ou digital antigo) | capa, partes, todos os movimentos, texto de decisões e sentenças | igual | fase, sentença, acórdão de 2º grau, trânsito | petição, laudo, acordo em documento |
| PJe | só o aviso de roteamento no portal público | busca por número, linha do tempo completa, peças por clique, PDF único dos autos | fase, marcos, partes, sentença, decisões | laudo (vem como anexo em PDF) |
| eproc | só o aviso de roteamento no portal público | detalhes do processo com todos os eventos numa página; peças por evento | fase, marcos, partes com polo, sentença, certidão, acórdão | laudo e petições (exigem a íntegra com segundo fator) |
| DataJud (API pública do CNJ) | metadados e movimentos por código | não se aplica | triagem: classe, órgão, assuntos, marcos por código | partes, texto, perícia, acordo, quem ganhou |

## 1. Portal público do sistema antigo

- **Copiar:** capa, "Listar todos os personagens" (polo e advogados), todos os movimentos. O
  paginador aceita 500 linhas por página: uma tela cobre o processo.
- **Sentença e acórdão:** o texto fica no movimento de recebimento, atrás de "Ver íntegra do(a)
  Sentença" ou "Acórdão". Cole entre `=== INTEGRA rótulo ===` e `=== FIM ===`. "Ver íntegra da
  Decisão" e "projeto de sentença" não contam como sentença.
- **Dispositivo cortado:** o resumo termina em "..." e esconde o julgamento. O programa só sugere
  resultado quando a parte visível tem "julgo procedente", "condeno" ou equivalente.
- **Processo migrado:** a tela lista uma linha por sistema. Só migrados **do sistema antigo** têm
  histórico aqui. Migrados **do PJe para o eproc** têm o histórico anterior no PJe.
- **Segundo grau:** o mesmo número pode listar linha de 1º e de 2º grau, em outro endereço do
  portal. Leia o acórdão ali.
- **Documentos do processo** (petição, laudo, acordo): pedem senha provisória ou login. O que
  não está em movimento fica `NAO_VISIVEL`.

## 2. PJe

- **Busca por número:** devolve órgão, autuação, classe, polos, localização e última
  movimentação, sem abrir autos.
- **Abrir autos de processo em que o advogado não consta:** o navegador mostra aviso de
  registro de acesso (norma do CNJ sobre registro de consultas). A pessoa lê e decide. O
  programa não aceita esse aviso por ninguém.
- **Limite por usuário:** o PJe bloqueia depois de certo número de processos abertos sem
  habilitação ("limite atual: 200 processos" na leitura que originou este documento). Conte as
  aberturas; planeje o lote para caber. Não contorne com novo login.
- **Linha do tempo:** carrega aos poucos. Rolar até o texto parar de crescer; copiar antes disso
  dá lista truncada (na leitura real, 170 de 174 cópias vieram assim e 83 nem chegavam à
  distribuição). Marque `#! movimentos_lista_completa: sim` **só** depois de rolar tudo.
  Leitura de comprimento 0 significa "ainda renderizando".
- **Peças:** abrem por clique na linha do tempo. O corpo da peça pode estar num quadro interno
  que não sai no texto da página. Peça em PDF sem texto exige OCR (item 5).
- **Download dos autos:** gera um PDF único com todos os documentos, texto pesquisável e rodapé
  "Num. <id> - Pág. n". `pdftotext -layout` converte; separe por rodapé.
- **Laudos:** costumam ser anexos das partes (PDF), não laudo do perito na tela.
- **Processo migrado para o eproc:** a última movimentação diz "Migrada a tramitação...".
  Anexe o histórico do PJe ao arquivo do eproc sob a marca
  `=== HISTÓRICO DO SISTEMA ANTERIOR (PJe) ===`. O parser **soma** os dois históricos.
- **Fase de processo migrado:** reflete o histórico só até a migração. A fase "inicial" sai como
  sugestão para revisão humana.

## 3. eproc

- **Busca por número no cabeçalho** abre "Detalhes do Processo" sem aviso: classe, órgão,
  partes e representantes (com CPF/CNPJ e OAB), e **todos os eventos numa página** (evento
  numerado; data e hora na linha seguinte). É o melhor ponto de copiar.
- **Partes:** a tela mostra só a primeira de cada polo. "e outros" expande (espere alguns
  segundos) e a tabela dá autor e réu por coluna.
- **Peça por evento** (sentença, decisão, certidão, acórdão): abre sem segundo fator para
  processo em que o advogado não consta. Petição inicial e laudo não aparecem como peça.
- **Íntegra dos autos:** caixa de interesse com registro **e** código de 6 dígitos do aplicativo
  de autenticação. Só a pessoa titular digita, a cada processo. Não há como automatizar.
  Liberada, oferece "Download Completo" (ZIP enviado por e-mail).
- **Segundo grau:** relatório/voto e acórdão abrem em outro endereço do eproc, nova aba, sem
  novo login.
- **Raiz do eproc:** voltar ou navegar para a raiz mostra "Usuário logado como..." e trava a
  aba até a pessoa clicar OK.
- **Trânsito:** baixa após acordo homologado costuma vir **sem** evento de trânsito. Isso é
  esperado, não é falha de leitura.

## 4. DataJud (API pública do CNJ)

- **Rápido:** `GET .../_doc/<TRIBUNAL>_<GRAU>_<20 dígitos>` leva ~0,5 s e dá 404 se não existe.
  Graus: `G1`, `JE` (juizado) e `G2` (2º grau é documento separado: sinal de recurso). Tente os
  três. A consulta `_search` leva 20 a 36 s e deu falso "não achado". O programa usa a leitura
  direta (`datajud`, `levantamento`).
- **Conteúdo:** metadados e movimentos **só por código** da tabela unificada do CNJ, sem partes
  e sem texto. Códigos usados: 848 trânsito; 22 baixa; 193, 219 e 220 julgamento, procedência e
  improcedência; 466, 15238 e 14099 acordo; 463, 12467 e 944 desistência; 14901 e 14902
  perícia; 15417 migração de sistema.
- **Cuidados:** atrasa em relação ao tribunal; processos muito novos faltam; o rótulo de
  sistema erra (dezenas de processos "legado" estavam no eproc). Serve para triagem e para
  roteamento provável, nunca para afirmar conteúdo. A chave pública muda: guarde em arquivo
  local. Limite dos termos: 120 requisições por minuto.

## 5. PDF sem camada de texto (OCR)

- Tente `pdftotext` primeiro. Se vier vazio, o PDF é imagem.
- `scripts/ocr_pdf.py <pdf> <saida.txt>` renderiza cada página (PyMuPDF) e lê com Tesseract em
  português. O arquivo sai com cabeçalho "fonte: OCR; conferir contra o original". OCR erra:
  nunca cite dele sem conferir contra o PDF.
- Salve o texto em `<pasta de dados>/documentos/<numero>/<id>-<tipo>.txt`; o `importar` carrega
  sozinho.

## 6. Roteamento

- O portal público é um **roteador**: para processo do PJe ou do eproc só diz em que sistema ele
  está. Use isso, ou o DataJud, para descobrir o sistema antes de copiar.
- O rótulo do DataJud não decide o sistema. Se a tela disser outro, vale a tela.

## 7. Canais oficiais e termos de uso

- Termos de uso de portais de tribunal costumam proibir robôs, varredura e extração automática
  sem permissão escrita. Leia o do seu tribunal.
- Canais oficiais para acesso automatizado: MNI (serviço de intercâmbio entre sistemas) e
  APIs abertas do tribunal. Peça acesso pelo canal do tribunal.
- Sem permissão, o modo seguro é este: a pessoa consulta à mão, em ritmo humano, cola o texto
  e o programa organiza.

## 8. Armadilhas que já custaram tempo

- A cópia da tela do PJe truncada vira "lista completa" por engano: sempre conferir o tamanho e
  a data mais antiga da linha do tempo.
- Aba do navegador em segundo plano reduz o ritmo de qualquer rotina de JavaScript (de segundos
  a minutos por processo).
- Número de processo parecido no corpo do texto pode enganar: o CNJ do cabeçalho vale mais.
- Ausência no que foi copiado nunca vira "não houve". É `NAO_VISIVEL`.
- Acórdão de 2º grau sobrepõe a sentença; condenação mantida, mesmo reduzida, continua condenação.
- Acordo homologado é categoria própria: a regra não diz quem pagou.
- `importar` com centenas de arquivos pode estourar o limite de linha de comando do shell:
  chame `consulta_lote.cli.main([...])` de um script Python com `glob`.
