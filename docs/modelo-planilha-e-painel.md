# Modelo da planilha de saída e do painel de análise

Dois produtos saem dos mesmos dados (`painel.montar_dados`): a planilha `saida-completa.xlsx` e o painel
`painel.html`. Os dados reunidos são a base do cliente (planilha de entrada), o levantamento do DataJud
(cache local) e as análises (banco local).

```
python -m consulta_lote saida     # planilha e painel com os dados da carteira (em <pasta de dados>/saida)
python -m consulta_lote modelo    # os mesmos arquivos com processos inventados (em <pasta de dados>/modelos)
```

## Planilha de saída (`saida-completa.xlsx`)

| Aba | Conteúdo |
|---|---|
| Resumo | contagens por fórmula (`COUNTIF`) sobre a aba Processos: análise, sistema, sentença, resultado, base defasada, revisão pendente |
| Processos | uma linha por processo da carteira: identificação, base do cliente, fase no tribunal, comparação base x tribunal, as sete respostas, resultado sugerido, próximo passo e três colunas de revisão (conferido por, correção, observação). Filtro automático, cabeçalho congelado, cores por resultado e por defasagem, lista de valores na coluna Revisão |
| Evidências | uma linha por processo e campo: estado, valor, motivo, trecho literal, onde, acesso do documento, data, confiança, revisão |
| Pendências de revisão | o que a revisora precisa decidir: confirmar resultado sugerido, fontes contraditórias, base a atualizar, data do trânsito que difere do histórico, documento com acesso não testado |
| Perguntas e legenda | as sete perguntas, como cada uma é respondida e o significado dos estados |

As sete perguntas: parte-alvo no polo passivo; fase; perícia (e laudo); acordo; desistência ou renúncia;
sentença ou acórdão (e resultado); trânsito em julgado com data.

## Painel (`painel.html`)

Arquivo único, sem biblioteca externa nem rede, para abrir offline. Tem cartões de totais, gráficos de barras
que acompanham o filtro, tabela ordenável e paginada, gaveta de detalhe com evidência literal por pergunta,
exportação do filtro para CSV, busca por número, comarca ou órgão, e tema claro e escuro.

Filtros: situação da análise; sistema; fase no tribunal; base x tribunal; fase na base; resultado da decisão;
sentença; trânsito; perícia; acordo; desistência; parte-alvo no polo passivo; próximo passo; revisão humana;
acesso dos documentos; tipo da pasta; rito; tipo de ação; comarca; ano; faixa de valor da causa; atividade
atual e motivo da ação (da base do cliente).

## Regras de segurança dos dois produtos

- CPF de pessoa física nunca sai: todo texto passa por máscara antes de entrar na planilha e no painel.
- Texto do processo nunca fecha o bloco de dados do painel (`<` vira `<`) e células de planilha ou CSV
  que começam com `=`, `+`, `-` ou `@` são neutralizadas.
- O resultado "favorável" ou "desfavorável" é sugestão por regra, com revisão humana pendente.
- Os dois arquivos contêm dados de processos: ficam só na pasta de dados local, fora deste repositório.
