# consulta-processual-lote

Organiza o texto de processos judiciais que **uma pessoa copiou da tela**, extrai por regra
sete informações com trecho literal de evidência e monta uma planilha de análise para revisão
humana.

> **O programa de análise (`src/`) não acessa sites de tribunal.** A entrada é texto que a própria
> pessoa copia e cola num arquivo `.txt`. O diretório [`coletor/`](coletor/README.md) traz peças
> **opcionais e separadas** para quem quer guardar a tela e as peças já abertas no navegador, logado
> pela própria pessoa. Elas não digitam credencial, não contornam segundo fator e não aceitam avisos
> do sistema. Cada usuário responde pelo cumprimento dos termos de uso do tribunal que consulta
> (muitos proíbem acesso automatizado sem autorização escrita) e pela proteção dos dados pessoais
> que manipula.
>
> **Este repositório é só o programa.** Dados de processos (textos colados, banco, planilhas,
> logs) ficam **só na máquina local**, numa pasta fora do repositório. O programa recusa rodar
> se a pasta de dados estiver dentro dele.

## O que ele faz

1. `limpar`: lê a sua planilha de carteira, separa processos elegíveis dos excluídos (com o
   motivo de cada exclusão), valida o número (dígito verificador) e sorteia um piloto
   estratificado com semente fixa.
2. `importar`: lê os `.txt` colados da tela e preenche os campos abaixo, cada um com estado,
   motivo, evidência literal e localização.
3. `planilha`: gera um `.xlsx`, uma linha por processo, com colunas de revisão. Juízos que
   exigem leitura humana saem em vermelho.
4. `verificar`: confere o banco (nenhum SIM ou NAO sem evidência; toda evidência existe no
   texto colado).

### Campos

| Campo | Observação |
|---|---|
| `parte_alvo_no_polo_passivo` | compara com a lista local de partes-alvo |
| `fase` | por movimentos e marcos; reporta divergência com a fase da sua base, não corrige |
| `pericia`, `pericia_laudo_juizo` | o juízo sobre o laudo nunca sai por regra |
| `acordo`, `desistencia_ou_renuncia` | por texto de movimento ou decisão |
| `decisao`, `decisao_juizo` | existência de sentença ou acórdão; "favorável" é sempre humano |
| `transito_em_julgado` | com data quando o movimento a traz |

### Estados (regra sem exceção)

- `SIM`: texto positivo encontrado, com trecho literal.
- `NAO`: só com texto positivo que afirme o negativo, ou lista completa lida.
- `NAO_VISIVEL_NO_ACESSO_PUBLICO`: todo o resto, com o motivo (`lista_parcial`,
  `documento_restrito`, `juizo_humano`, `sem_mencao_em_movimento`, `nao_consultado`...).
  **Ausência no que foi colado nunca vira "não houve".** Sem trecho literal de evidência, o campo
  fica não visível. O banco recusa SIM ou NAO sem evidência.

## Instalação e uso

```bash
pip install -e .
# 1. escolha uma pasta FORA deste repositório
export CONSULTA_LOTE_DADOS="$HOME/meus-dados-de-processos"      # Windows: setx / $env:
python -m consulta_lote init
# 2. edite, na pasta de dados, partes_alvo.local.yaml e mapa_planilha.local.yaml
python -m consulta_lote limpar caminho/da/sua-planilha.xlsx
# 3. para cada processo: copie o texto da tela e cole num .txt em <pasta de dados>/entrada
python -m consulta_lote importar <pasta de dados>/entrada/*.txt
python -m consulta_lote planilha
python -m consulta_lote verificar
```

Formato do texto colado: veja `examples/processo_sintetico_1.txt` (completo) e
`examples/processo_sintetico_2.txt` (lista parcial). Linhas `#! chave: valor` no começo dizem
o sistema, se a lista de partes e a de movimentos foram lidas por inteiro, e a fase da sua base.
Se um documento abriu sem login, cole o texto entre `=== INTEGRA rótulo ===` e `=== FIM ===`.

## Documentação

- `docs/instalacao-e-uso-windows.md`: instalar e rodar no seu computador.
- `docs/rotas-por-sistema.md`: o que copiar de cada sistema de tribunal e o que cada um entrega.
- `docs/analise-por-blocos.md` e `docs/modelo-planilha-e-painel.md`: análise por blocos, planilha e painel.

## Privacidade (o que o programa garante)

- Pasta de dados fora do repositório; se estiver dentro de outro repositório git, precisa estar
  ignorada por ele. Na dúvida, recusa.
- Nenhum texto de processo sai da máquina e o programa não tem LLM. A rede só é usada pelos subcomandos
  opcionais `datajud` e `levantamento`: eles consultam a API pública do CNJ (`api-publica.datajud.cnj.jus.br`)
  com a chave pública do próprio usuário (arquivo local), enviam só o número do processo no endereço da
  consulta e guardam a resposta numa pasta local. Sem esses subcomandos, nada usa a rede.
  O `coletor/` (opcional) só escuta em `127.0.0.1`.
- Número do processo no banco é local; o identificador interno é HMAC com segredo local.
- `.gitignore` de negação por padrão e ganchos de commit que bloqueiam termos proibidos e
  números de processo (veja abaixo).

## Para quem contribui

```bash
git init && python scripts/instalar_hooks.py
cp scripts/termos_proibidos.example.txt termos_proibidos.local.txt   # edite; o git ignora
python scripts/scan.py historico        # antes de publicar ou mudar a visibilidade
python -m unittest discover -s tests -t .
```

Só exemplos sintéticos entram no repositório (números fictícios, nomes inventados). Os ganchos
falham fechados: sem a lista local de termos, o commit é bloqueado.

## Licença

[PolyForm Noncommercial License 1.0.0](LICENSE): uso livre para fins **não comerciais**, com
código aberto para leitura, estudo e modificação. Uso comercial exige licença à parte do
mantenedor. Não é licença de código aberto no sentido da OSI.
