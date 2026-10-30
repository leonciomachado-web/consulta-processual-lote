<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel de análise de processos</title>
<style>
:root{--bg:#f6f7f9;--painel:#fff;--tinta:#1c2330;--suave:#5b6577;--linha:#dfe3ea;--marca:#1f5fbf;--marca-t:#fff;
--bom:#116b3a;--bom-f:#dff3e7;--mau:#a01c2b;--mau-f:#fbe3e6;--aviso:#7a5200;--aviso-f:#fff1cf;--neutro-f:#e9ecf2;--sombra:0 1px 2px rgba(0,0,0,.08)}
@media (prefers-color-scheme:dark){:root:not([data-tema=claro]){--bg:#10141b;--painel:#181e29;--tinta:#e8ecf3;--suave:#9aa6bb;--linha:#2a3345;--marca:#6aa3ff;--marca-t:#08101f;
--bom:#7be0a6;--bom-f:#12351f;--mau:#ff9aa6;--mau-f:#3a1219;--aviso:#ffd37a;--aviso-f:#3a2d0c;--neutro-f:#232b3b;--sombra:none}}
:root[data-tema=escuro]{--bg:#10141b;--painel:#181e29;--tinta:#e8ecf3;--suave:#9aa6bb;--linha:#2a3345;--marca:#6aa3ff;--marca-t:#08101f;--bom:#7be0a6;--bom-f:#12351f;--mau:#ff9aa6;--mau-f:#3a1219;--aviso:#ffd37a;--aviso-f:#3a2d0c;--neutro-f:#232b3b;--sombra:none}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tinta);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;padding:14px 20px;background:var(--painel);border-bottom:1px solid var(--linha)}
h1{font-size:18px;margin:0}
.sub{color:var(--suave);font-size:12px}
.aviso{background:var(--aviso-f);color:var(--aviso);padding:6px 20px;font-size:12px}
button,select,input[type=search]{font:inherit;color:inherit}
button{background:var(--painel);border:1px solid var(--linha);border-radius:6px;padding:6px 10px;cursor:pointer}
button.p{background:var(--marca);border-color:var(--marca);color:var(--marca-t)}
button:focus-visible,summary:focus-visible,input:focus-visible,th button:focus-visible{outline:2px solid var(--marca);outline-offset:2px}
.layout{display:grid;grid-template-columns:300px 1fr;gap:16px;padding:16px 20px;align-items:start}
@media (max-width:900px){.layout{grid-template-columns:1fr}}
aside{background:var(--painel);border:1px solid var(--linha);border-radius:8px;padding:10px;position:sticky;top:8px;max-height:calc(100vh - 16px);overflow:auto}
aside input[type=search]{width:100%;padding:7px 9px;border:1px solid var(--linha);border-radius:6px;background:var(--bg);margin-bottom:8px}
details{border-top:1px solid var(--linha);padding:4px 0}
summary{cursor:pointer;padding:6px 2px;font-weight:600}
summary .n{font-weight:400;color:var(--suave)}
.op{display:flex;gap:6px;align-items:center;padding:2px 6px;font-size:13px}
.op span.c{margin-left:auto;color:var(--suave);font-variant-numeric:tabular-nums}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:12px}
.card{background:var(--painel);border:1px solid var(--linha);border-radius:8px;padding:10px 12px;box-shadow:var(--sombra)}
.card b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.card span{color:var(--suave);font-size:12px}
.graficos{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-bottom:12px}
.gr{background:var(--painel);border:1px solid var(--linha);border-radius:8px;padding:10px 12px}
.gr h3{margin:0 0 8px;font-size:13px}
.barra{display:grid;grid-template-columns:minmax(80px,45%) 1fr 34px;gap:6px;align-items:center;font-size:12px;margin:3px 0}
.barra div.t{background:var(--neutro-f);border-radius:3px;height:12px}
.barra div.t i{display:block;height:12px;background:var(--marca);border-radius:3px;min-width:2px}
.barra .l{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.barra .v{text-align:right;font-variant-numeric:tabular-nums}
.tabela{background:var(--painel);border:1px solid var(--linha);border-radius:8px;overflow:auto}
table{border-collapse:collapse;width:100%;min-width:980px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--linha);vertical-align:top;font-size:13px}
th{position:sticky;top:0;background:var(--painel);white-space:nowrap}
th button{border:0;background:none;padding:0;font-weight:700}
tr.l:hover{background:var(--neutro-f);cursor:pointer}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;background:var(--neutro-f);white-space:nowrap}
.chip.bom{background:var(--bom-f);color:var(--bom)}
.chip.mau{background:var(--mau-f);color:var(--mau)}
.chip.av{background:var(--aviso-f);color:var(--aviso)}
.pag{display:flex;gap:8px;align-items:center;justify-content:space-between;padding:8px 4px;color:var(--suave)}
#gaveta{position:fixed;top:0;right:0;bottom:0;width:min(560px,100%);background:var(--painel);border-left:1px solid var(--linha);box-shadow:-4px 0 18px rgba(0,0,0,.25);transform:translateX(105%);transition:transform .2s;overflow:auto;padding:14px 16px;z-index:10}
#gaveta.a{transform:none}
#gaveta h2{font-size:16px;margin:0 0 4px}
.it{border:1px solid var(--linha);border-radius:8px;padding:8px 10px;margin:8px 0}
.it h4{margin:0 0 4px;font-size:13px}
.it q{display:block;color:var(--suave);margin-top:4px;font-size:12px;quotes:"“" "”"}
.kv{display:grid;grid-template-columns:140px 1fr;gap:2px 10px;font-size:13px}
.kv dt{color:var(--suave)}.kv dd{margin:0}
.vazio{padding:24px;text-align:center;color:var(--suave)}
@media print{aside,#gaveta,header button{display:none}.layout{display:block}}
</style>
</head>
<body>
<header>
  <div><h1>Painel de análise de processos</h1><div class="sub" id="meta"></div></div>
  <div><button id="limpar">Limpar filtros</button> <button id="csv" class="p">Exportar CSV filtrado</button> <button id="tema" aria-label="Alternar tema claro e escuro">Tema</button></div>
</header>
<div class="aviso">Dados privados do escritório. Resultado "favorável" ou "desfavorável" é sugestão por regra e depende de revisão humana. Esta minuta requer revisão por profissional habilitado antes de qualquer uso externo.</div>
<div class="layout">
  <aside aria-label="Filtros"><input type="search" id="busca" placeholder="Buscar número, comarca, órgão" aria-label="Buscar"><div id="filtros"></div></aside>
  <main>
    <div class="cards" id="cards"></div>
    <div class="graficos" id="graficos"></div>
    <div class="tabela"><table><thead id="cab"></thead><tbody id="corpo"></tbody></table><div class="vazio" id="vazio" hidden>Nenhum processo com esses filtros.</div></div>
    <div class="pag"><span id="contagem"></span><span><button id="ant">Anterior</button> <button id="prox">Próxima</button></span></div>
  </main>
</div>
<div id="gaveta" role="dialog" aria-modal="false" aria-label="Detalhe do processo"><button id="fechar" style="float:right">Fechar</button><div id="detalhe"></div></div>
<script id="dados" type="application/json">/*__DADOS__*/</script>
<script>
(function(){
"use strict";
var D=JSON.parse(document.getElementById("dados").textContent), R=D.processos, POR=50, pag=0, ordem={k:"numero",d:1}, sel={}, termo="";
var COLS=[["numero","Processo"],["analise","Análise"],["sistema","Sistema"],["fase_base","Fase na base"],["fase_tribunal","Fase no tribunal"],["base_x_tribunal","Base x tribunal"],["sentenca","Sentença"],["resultado","Resultado"],["transito","Trânsito"],["pericia","Perícia"],["acordo","Acordo"],["proximo_cat","Próximo passo"],["revisao","Revisão"]];
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function val(r,k){var v=r[k];return Array.isArray(v)?v:[v==null||v===""?"(vazio)":String(v)]}
function passa(r,ign){
  for(var k in sel){ if(k===ign||!sel[k].size) continue; var vs=val(r,k),ok=false; for(var i=0;i<vs.length;i++) if(sel[k].has(vs[i])) ok=true; if(!ok) return false; }
  if(termo){var t=(r.numero+" "+r.comarca+" "+r.orgao+" "+r.foro).toLowerCase(); if(t.indexOf(termo)<0) return false;}
  return true;
}
function contar(chave,ign){var m={};R.forEach(function(r){if(!passa(r,ign))return;val(r,chave).forEach(function(v){m[v]=(m[v]||0)+1})});return m}
function filtros(){
  var h="";
  D.filtros.forEach(function(f){
    var m=contar(f.chave,f.chave),ks=Object.keys(m).sort(function(a,b){return m[b]-m[a]}),n=sel[f.chave]?sel[f.chave].size:0;
    h+='<details'+(n?" open":"")+'><summary>'+esc(f.rotulo)+(n?' <span class="n">('+n+')</span>':"")+'</summary>';
    ks.forEach(function(k){var id="f_"+f.chave+"_"+k.replace(/\W/g,"_");
      h+='<label class="op"><input type="checkbox" data-k="'+f.chave+'" data-v="'+esc(k)+'"'+(n&&sel[f.chave].has(k)?" checked":"")+'><span>'+esc(k)+'</span><span class="c">'+m[k]+'</span></label>'});
    if(!ks.length) h+='<div class="op">sem valores</div>';
    h+="</details>";
  });
  document.getElementById("filtros").innerHTML=h;
}
function lista(){var l=R.filter(function(r){return passa(r)}),k=ordem.k;l.sort(function(a,b){var x=String(a[k]),y=String(b[k]);return (x<y?-1:x>y?1:0)*ordem.d});return l}
function chip(k,v){var c="";if(k==="resultado"){c=/^favor/.test(v)?"bom":/^desfavor/.test(v)?"mau":/classificar/.test(v)?"av":""}
 else if(k==="base_x_tribunal"){c=v==="coincide"?"bom":v==="indeterminado"?"":"av"} else if(k==="revisao"){c=v==="conferido"?"bom":v==="pendente"?"av":""}
 else if(k==="sentenca"||k==="transito"||k==="pericia"||k==="acordo"){c=/^sim/.test(v)?"bom":""}
 return '<span class="chip '+c+'">'+esc(v)+"</span>"}
function tabela(l){
  var h="<tr>"+COLS.map(function(c){return '<th scope="col"><button data-o="'+c[0]+'" aria-label="Ordenar por '+esc(c[1])+'">'+esc(c[1])+(ordem.k===c[0]?(ordem.d>0?" ▲":" ▼"):"")+"</button></th>"}).join("")+"</tr>";
  document.getElementById("cab").innerHTML=h;
  var ini=pag*POR,b="";
  l.slice(ini,ini+POR).forEach(function(r){
    b+='<tr class="l" tabindex="0" data-n="'+esc(r.numero)+'">'+COLS.map(function(c){var v=r[c[0]];v=Array.isArray(v)?v.join(", "):v;
      return "<td>"+(c[0]==="numero"?esc(v):chip(c[0],v==null||v===""?"-":v))+"</td>"}).join("")+"</tr>"});
  document.getElementById("corpo").innerHTML=b;
  document.getElementById("vazio").hidden=l.length>0;
  document.getElementById("contagem").textContent=l.length?("Mostrando "+(ini+1)+" a "+Math.min(ini+POR,l.length)+" de "+l.length):"0 processos";
}
function cartoes(l){
  function n(f){return l.filter(f).length}
  var c=[["Processos no filtro",l.length],["Com análise completa",n(function(r){return r.analise==="análise completa"})],["Só DataJud",n(function(r){return r.analise==="só DataJud"})],
   ["Sentença registrada",n(function(r){return /^sim/.test(r.sentenca)})],["Desfavorável (sugestão)",n(function(r){return /^desfavor/.test(r.resultado)})],
   ["Favorável (sugestão)",n(function(r){return /^favor/.test(r.resultado)})],["Base defasada",n(function(r){return r.base_x_tribunal==="base_defasada"})],["Revisão pendente",n(function(r){return r.revisao==="pendente"})]];
  document.getElementById("cartoes");
  document.getElementById("cards").innerHTML=c.map(function(x){return '<div class="card"><b>'+x[1]+"</b><span>"+esc(x[0])+"</span></div>"}).join("");
}
function graficos(l){
  document.getElementById("graficos").innerHTML=D.graficos.map(function(g){
    var m={};l.forEach(function(r){val(r,g.chave).forEach(function(v){m[v]=(m[v]||0)+1})});
    var ks=Object.keys(m).sort(function(a,b){return m[b]-m[a]}).slice(0,8),mx=Math.max.apply(null,ks.map(function(k){return m[k]}).concat([1]));
    return '<div class="gr"><h3>'+esc(g.rotulo)+"</h3>"+ks.map(function(k){return '<div class="barra"><span class="l" title="'+esc(k)+'">'+esc(k)+'</span><div class="t"><i style="width:'+Math.round(m[k]*100/mx)+'%"></i></div><span class="v">'+m[k]+"</span></div>"}).join("")+"</div>"}).join("");
}
function render(){var l=lista();if(pag*POR>=l.length)pag=0;cartoes(l);graficos(l);tabela(l);filtros()}
function gaveta(num){
  var r=R.filter(function(x){return x.numero===num})[0];if(!r)return;
  var p=D.perguntas.map(function(q){var c=r.campos[q.campo];
    if(!c) return '<div class="it"><h4>'+esc(q.texto)+'</h4><span class="chip">não analisado</span></div>';
    var ev=c.evidencia?'<q>'+esc(c.evidencia)+"</q><small>"+esc(c.localizacao)+" · acesso: "+esc(c.acesso)+(c.data?" · "+esc(c.data):"")+"</small>":"";
    var extra="";if(q.campo==="decisao"&&r.campos.decisao_juizo){var j=r.campos.decisao_juizo;extra='<div style="margin-top:4px">'+chip("resultado",j.valor||"revisão humana")+(j.evidencia?"<q>"+esc(j.evidencia)+"</q>":"")+"</div>"}
    if(q.campo==="pericia"&&r.campos.pericia_laudo_juizo)extra='<div style="margin-top:4px"><span class="chip">laudo: juízo humano</span></div>';
    return '<div class="it"><h4>'+esc(q.texto)+'</h4>'+chip("revisao",c.estado==="SIM"?"SIM":c.estado==="NAO"?"NÃO":"NÃO VISÍVEL"+(c.motivo?" ("+c.motivo+")":""))+" "+esc(c.valor)+ev+extra+"</div>"}).join("");
  var dj=r.datajud,kv=[["Sistema",r.sistema],["Comarca / foro",r.comarca+" / "+r.foro],["Órgão (DataJud)",r.orgao],["Distribuição",r.distribuicao],["Valor da causa",r.valor_causa==null?"-":"R$ "+Number(r.valor_causa).toLocaleString("pt-BR")],["Fase na base",r.fase_base],["Fase no tribunal",r.fase_tribunal],["Base x tribunal",r.base_x_tribunal],["Atividade (base)",r.atividade],["Motivo (base)",r.motivo_acao],
   ["DataJud: migrado em",dj.migrado_em],["DataJud: sentença",dj.sentenca_em],["DataJud: trânsito",dj.transito_em],["DataJud: baixa",dj.baixa_em],["DataJud: último mov.",dj.ultimo_movimento],["Próximo passo",r.proximo_passo]]
   .filter(function(x){return x[1]&&x[1]!==" / "}).map(function(x){return "<dt>"+esc(x[0])+"</dt><dd>"+esc(x[1])+"</dd>"}).join("");
  document.getElementById("detalhe").innerHTML="<h2>"+esc(r.numero)+'</h2><div class="sub">'+esc(r.analise)+'</div><button id="cp">Copiar número</button><dl class="kv">'+kv+"</dl>"+p;
  document.getElementById("cp").onclick=function(){navigator.clipboard&&navigator.clipboard.writeText(r.numero)};
  document.getElementById("gaveta").classList.add("a");document.getElementById("fechar").focus();
}
function csv(){
  var l=lista(),cab=COLS.map(function(c){return c[1]}).concat(["Comarca","Valor da causa","Próximo passo (texto)"]),q=function(s){s=String(s==null?"":s);if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'};
  var linhas=[cab.map(q).join(";")].concat(l.map(function(r){return COLS.map(function(c){var v=r[c[0]];return q(Array.isArray(v)?v.join(", "):v)}).concat([q(r.comarca),q(r.valor_causa),q(r.proximo_passo)]).join(";")}));
  var b=new Blob(["﻿"+linhas.join("\r\n")],{type:"text/csv;charset=utf-8"}),a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="processos-filtrados.csv";a.click();
}
document.getElementById("meta").textContent="Gerado em "+D.gerado_em+" · "+R.length+" processos";
document.getElementById("filtros").addEventListener("change",function(e){var t=e.target;if(!t.dataset.k)return;var s=sel[t.dataset.k]||(sel[t.dataset.k]=new Set());t.checked?s.add(t.dataset.v):s.delete(t.dataset.v);pag=0;render()});
document.getElementById("busca").addEventListener("input",function(e){termo=e.target.value.trim().toLowerCase();pag=0;render()});
document.getElementById("limpar").onclick=function(){sel={};termo="";document.getElementById("busca").value="";pag=0;render()};
document.getElementById("cab").addEventListener("click",function(e){var b=e.target.closest("button");if(!b)return;var k=b.dataset.o;ordem=ordem.k===k?{k:k,d:-ordem.d}:{k:k,d:1};render()});
document.getElementById("corpo").addEventListener("click",function(e){var tr=e.target.closest("tr.l");if(tr)gaveta(tr.dataset.n)});
document.getElementById("corpo").addEventListener("keydown",function(e){if(e.key==="Enter"){var tr=e.target.closest("tr.l");if(tr)gaveta(tr.dataset.n)}});
document.getElementById("fechar").onclick=function(){document.getElementById("gaveta").classList.remove("a")};
document.addEventListener("keydown",function(e){if(e.key==="Escape")document.getElementById("gaveta").classList.remove("a")});
document.getElementById("ant").onclick=function(){if(pag>0){pag--;render()}};
document.getElementById("prox").onclick=function(){if((pag+1)*POR<lista().length){pag++;render()}};
document.getElementById("csv").onclick=csv;
document.getElementById("tema").onclick=function(){var r=document.documentElement;r.dataset.tema=r.dataset.tema==="escuro"?"claro":"escuro"};
render();
})();
</script>
</body>
</html>
