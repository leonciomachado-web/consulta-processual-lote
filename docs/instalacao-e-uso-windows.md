# Instalar e rodar no seu computador (Windows)

O repositório traz **só o programa**. Os dados dos processos não vêm nele e não devem ir para
ele. Você cria a sua própria pasta de dados, fora da pasta do programa.

## 1. Pré-requisitos
- Python 3.10 ou mais novo (marque "Add Python to PATH" ao instalar).
- Git, para baixar o repositório (ou baixe o ZIP no GitHub).
- Opcional, só para PDF escaneado: Tesseract com o idioma português e `pip install pymupdf`.

## 2. Baixar e instalar
```powershell
git clone <endereço do repositório> C:\consulta-processual-lote
cd C:\consulta-processual-lote
python -m pip install -e .
```

## 3. Criar a pasta de dados (fora do repositório)
```powershell
mkdir C:\dados-processos
$env:CONSULTA_LOTE_DADOS = "C:\dados-processos"      # vale para esta janela
python -m consulta_lote init
```
O programa recusa rodar se a pasta de dados ficar dentro do repositório. Para valer sempre:
`setx CONSULTA_LOTE_DADOS C:\dados-processos` e abrir uma janela nova.

## 4. Configurar
Na pasta de dados, edite:
- `partes_alvo.local.yaml`: as partes-alvo (nomes que o programa procura no polo passivo).
- `mapa_planilha.local.yaml`: quais colunas da sua planilha são número do processo, fase etc.
  Há exemplos em `examples/`.

## 5. Rodar
```powershell
python -m consulta_lote limpar C:\caminho\da\sua-planilha.xlsx
# para cada processo: copie o texto da tela e cole num .txt em C:\dados-processos\entrada
python -m consulta_lote importar (Get-ChildItem C:\dados-processos\entrada\*.txt).FullName
python -m consulta_lote saida          # planilha completa e painel (HTML)
python -m consulta_lote verificar      # nenhum SIM ou NAO sem evidência
```
Com centenas de arquivos, `importar` pode estourar o limite de linha de comando; nesse caso
chame `consulta_lote.cli.main([...])` de um script Python com `glob`.

O formato do `.txt` e o que copiar de cada sistema estão em `docs/rotas-por-sistema.md` e nos
exemplos de `examples/`. O painel (`saida/painel.html`) abre direto no navegador.

## 6. Regras de uso
- Os resultados "favorável" e "desfavorável" são **sugestões por regra**. A conferência é humana.
- Dados de processo têm dados pessoais e de saúde. Mantenha a pasta de dados fora de nuvem
  compartilhada e fora do repositório. Nunca envie planilha ou banco para o GitHub.
- O programa não acessa sites de tribunal e não usa rede. Quem copia o texto da tela responde
  pelos termos de uso do tribunal.
