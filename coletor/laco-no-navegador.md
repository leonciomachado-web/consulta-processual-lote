# Laço no navegador (esqueleto)

Rode no console da aba **já logada** pela própria pessoa. Endereços de sistema e números de
processo ficam por sua conta: aqui só há marcadores `<...>`. Cada sistema muda o HTML; confira os
seletores no seu caso.

## Regras que valeram em teste real

- **Uma chamada de JavaScript não deve passar de ~45 s** em ferramentas que impõem limite.
  Dispare o laço sem `await` (`window.__bg = window.__rodar()`) e acompanhe `window.__i`.
- **Aba em segundo plano reduz o ritmo.** Mantenha a aba em primeiro plano.
- **Confira o número antes de enviar**: o título da página tem de começar pelo CNJ esperado, senão
  você grava a página do processo anterior.
- **Nunca poste teste no nome de um arquivo bom**: o receptor sobrescreve.
- **A sessão expira** após minutos parada: se o laço cair na tela de login, a pessoa entra de novo.
- **O `JSON.stringify` pode ser sobrescrito pela página** (Prototype.js): o corpo pode chegar como
  JSON dentro de string. No Python: `d = json.load(f); d = json.loads(d) if isinstance(d, str) else d`.
- **O envio ao receptor pode ficar pendurado** em alguns navegadores (permissão de rede local: página pública
  chamando `127.0.0.1`). O receptor já responde ao pedido de verificação prévia com
  `Access-Control-Allow-Private-Network: true`. Se ainda travar, grave o resultado pela ferramenta do
  navegador (salvar em arquivo) e converta depois, em vez de enviar pela rede.
- Documento em PDF abre num visualizador que não dá texto limpo: baixe o PDF (próxima seção).

O receptor só aceita POST da origem informada em `--origem` e com o token da sessão (muda a cada
execução). `TOKEN` é definido na primeira linha do bloco abaixo; `enviarPdf` usa a mesma constante.

## Texto da tela para o receptor

```js
const PORTA = 18765, TOKEN = '<token impresso pelo receptor>', w = ms => new Promise(r => setTimeout(r, ms));
window.__fila = [/* números CNJ */]; window.__i = 0; window.__res = [];
window.__rodar = async (maxMs = 36000) => {
  const campo = [...document.querySelectorAll('input[type=search]')].find(x => x.offsetParent !== null);
  const t0 = Date.now();
  while (window.__i < window.__fila.length && Date.now() - t0 < maxMs) {
    const num = window.__fila[window.__i];
    // 1) preencher <campo> com num e enviar o formulário de busca do sistema
    // 2) esperar até o título começar por num e o texto passar de ~800 caracteres
    if (!document.title.startsWith(num + ' ')) { window.__res.push([num, 'titulo_errado']); window.__i++; continue; }
    const tx = document.body.innerText;
    await fetch(`http://127.0.0.1:${PORTA}/salvar?nome=${num}&t=${TOKEN}`, { method: 'POST', mode: 'no-cors', body: tx });
    window.__res.push([num, 'ok', tx.length]); window.__i++; await w(2500);
  }
  return [window.__i, window.__fila.length, window.__res.slice(-10)];
};
```

## PDF de uma peça para o receptor

Use o link que o próprio sistema oferece para a peça (a pessoa tem direito de abri-la). Só
as peças que importam aos 7 itens: sentença, acórdão, laudo, acordo, certidão de trânsito.

```js
async function enviarPdf(cnj, idPeca, tipo, urlDaPeca) {
  const r = await fetch(urlDaPeca, { credentials: 'include' });
  const buf = await r.arrayBuffer();
  const ini = new TextDecoder().decode(buf.slice(0, 4));
  if (ini !== '%PDF') return [cnj, idPeca, 'nao_e_pdf'];   // o receptor também recusa
  await fetch(`http://127.0.0.1:${PORTA}/salvar-pdf?nome=${cnj}&arq=${idPeca}-${tipo}&t=${TOKEN}`,
              { method: 'POST', mode: 'no-cors', body: buf });
  return [cnj, idPeca, 'ok', buf.byteLength];
}
```

`tipo` em minúsculas e sem acento (`sentenca`, `acordao`, `laudo`, `acordo`, `transito`).
