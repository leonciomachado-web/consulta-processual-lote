# Coletor opcional (navegador do próprio usuário)

Este diretório é **separado do programa de análise**. O programa em `src/` continua sem acessar
site nenhum: ele só lê texto. O coletor é um conjunto de peças auxiliares para quem já tem
direito de consultar os processos e quer guardar o que vê na tela e as peças em pastas por
processo, em vez de copiar e colar à mão.

## Regras de uso

- **A pessoa entra no sistema sozinha** (senha, certificado, segundo fator). Nenhum trecho aqui
  digita credencial nem contorna segundo fator.
- **Caixas de aviso e confirmações do sistema são da pessoa.** O coletor não as aceita por ela.
- Rode sobre processos que a pessoa pode consultar, em ritmo humano e **só se os termos de uso
  do tribunal permitirem**. Muitos tribunais proíbem acesso automatizado sem autorização
  escrita. Cada usuário responde por isso e pela proteção dos dados pessoais que manipula.
- Dados reais ficam **só na máquina local**, em pasta fora do repositório. Os dois scripts
  recusam rodar com a pasta de dados dentro dele.

## Peças

| Arquivo | Função |
|---|---|
| `receptor.py` | Servidor local (127.0.0.1) que recebe texto, JSON de peças ou PDF enviados pela página aberta no navegador e grava na pasta de dados. Valida o nome (número CNJ) e o início `%PDF`. |
| `converter.py` | Transforma o que o coletor gravou (texto da tela, JSON de peças, despejos da consulta pública) em `entrada/<CNJ>.txt` e `documentos/<CNJ>/*.txt` no formato do parser. Modos: `eproc`, `pje`, `legado`, `pje-publico`, `eproc-despejo`, `pecas-eproc` (veja o cabeçalho do arquivo). Não importa nada; imprime a lista para o `importar`. Separa processos em segredo de justiça. |
| `organizar_processos.py` | Monta `processos/<CNJ>/` com `fontes/` (PDF), `convertido/` (texto), `analises/campos.json` (os 7 itens com evidência) e `_MAPA-CASO.md` (o que existe e o que falta). Copia, nunca apaga. |
| `laco-no-navegador.md` | Esqueleto do laço em JavaScript, sem endereço nem número reais. |

## Fluxo

```bash
python -I coletor/receptor.py --dados <pasta-fora-do-repo> --origem https://<sistema>   # terminal 1; imprime o token
# no navegador, já logado: rodar o laço de laco-no-navegador.md
python -I coletor/converter.py --dados <pasta> eproc          # ou pje, legado, pje-publico <json>...
# importar o que o conversor listou (um arquivo por linha em entrada/lista-convertidos.txt)
python -I coletor/organizar_processos.py --dados <pasta> --gravar
```

## O que o conversor não faz

Ajustes depois da conversão dependem do caso e ficam por conta de quem coleta: anexar o histórico do
sistema anterior a um processo migrado (marca `=== HISTÓRICO DO SISTEMA ANTERIOR (PJe) ===`), trocar uma
linha do tempo truncada pela completa (e marcar `#! linha_do_tempo`), e incluir a lista de personagens do
modal (`#! partes_lista_completa: sim`). Veja `docs/rotas-por-sistema.md`.
