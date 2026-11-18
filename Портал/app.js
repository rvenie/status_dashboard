'use strict';
const $ = (id) => document.getElementById(id);
const D = window.STATUS_ARCHIVE;
if (!D) {
  $('time-result').textContent = 'Данные архива не загрузились. Проверьте, что файл data.js находится рядом с порталом.';
  throw new Error('Status archive data missing');
}
const episodes = new Map(D.episodes.map(e => [e.slug,e]));
const records = new Map([...D.rows,...D.actions].map(r => [r.id,r]));
const years = [...new Set(D.episodes.map(e => e.date.slice(0,4)))].sort();
const fmt = new Intl.NumberFormat('ru-RU');
const rules = new Intl.PluralRules('ru-RU');
function quantity(count,action) {
  const forms=action ? {one:'действие',few:'действия',many:'действий'} : {one:'сюжет',few:'сюжета',many:'сюжетов'};
  return fmt.format(count)+' '+(forms[rules.select(count)]??forms.many);
}
const textDate = (x) => x ? x.slice(0,10).split('-').reverse().join('.') : '';
const caps = new Intl.Collator('ru-RU');
const state = {
  tab:'timeline', mode:'publication', year:years.at(-1), period:null,
  id:null, track:null, limit:21, tree:'person', branch:'verified', treeLimit:18, episodeLimit:24
};
const controls = ['topic','person','agency','stage'];
const keyMap = {topic:'tags',person:'people',agency:'agency',stage:'stages'};
const normalize = (s) => String(s ?? '').toLocaleLowerCase('ru-RU').replace(/ё/g,'е').replace(/[№«»"]/g,'').replace(/[‑–—]/g,'-').trim();
const e = (value) => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const u = (url) => /^https?:\/\//i.test(url ?? '') ? e(url) : '#';
const source = (url, label) => '<a href="'+u(url)+'" target="_blank" rel="noopener noreferrer">'+e(label)+' ↗</a>';
const unique = (rows,key) => [...new Set(rows.flatMap(r => r[key] ?? []))];
const sortNames = (a,b) => caps.compare(a.split(' ').at(-1),b.split(' ').at(-1)) || caps.compare(a,b);
const byDate = (arr,desc=true) => [...arr].sort((a,b)=>(desc ? b.date.localeCompare(a.date) : a.date.localeCompare(b.date)) || a.title.localeCompare(b.title,'ru'));
const months = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
const longMonths = ['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь'];
const pubBase='https://teletype.in/@eschulmann/';
const sourceUrl=(r,anchor=r.anchor) => (episodes.get(r.slug)?.url ?? pubBase+r.slug)+(anchor ? '#'+anchor : '');

function pick(value,label,selected=false) {
  return '<option value="'+e(value)+'"'+(selected?' selected':'')+'>'+e(label)+'</option>';
}
for (const k of controls) {
  const values = unique([...D.rows,...D.actions],keyMap[k]).sort(k==='person'?sortNames:caps.compare);
  $(k).innerHTML=pick('',{topic:'Все темы',person:'Все фамилии',agency:'Все ведомства',stage:'Все стадии'}[k])+
    values.map(v=>pick(v,v)).join('');
}
$('episode-year').innerHTML=pick('','Все годы')+years.slice().reverse().map(y=>pick(y,y)).join('');
$('coverage').textContent=textDate(D.start)+' — '+textDate(D.end)+' · Teletype';
$('metrics').innerHTML=[
  ['Уникальных выпусков',D.episodes.length],['Сюжетов',D.rows.length],['Сверенных действий',D.actions.length]
].map(([label,value])=>'<div class="metric"><span>'+label+'</span><strong>'+fmt.format(value)+'</strong></div>').join('');
$('method-coverage').textContent='На Teletype найдено '+D.pages+' страниц программы. '+D.duplicates+
  ' повторные публикации учтены вместе с оригинальными выпусками. Период публикаций — с '+textDate(D.start)+' по '+textDate(D.end)+'.';

function queryTerms() { return normalize($('query').value).split(/\s+/).filter(Boolean); }
function selectedFilters() { return controls.map(k=>[keyMap[k],$(k).value]).filter(([,v])=>v); }
function active(r, terms, filters) {
  return filters.every(([key,value])=>r[key]?.includes(value)) && terms.every(term=>r.search.includes(term));
}
for (const r of records.values()) {
  r.search=normalize([r.title,episodes.get(r.slug)?.subtitle,r.action,(r.points??[]).map(x=>x.text),
    r.tags,r.people,r.agency,r.mentionAgencies,r.stages,r.documents,r.bill,r.parties?.map(p=>[p.name,p.text]),r.corporations?.map(p=>[p.name,p.text])].flat(2).join(' '));
}
for (const e of episodes.values()) {
  e.search=normalize([e.title,e.subtitle,...e.notes.map(x=>x.text??x),e.theses,e.tags].flat(2).join(' '));
}
function filtered(list, agencyField='agency') {
  const terms=queryTerms();
  const filters=selectedFilters().map(([key,value])=>[key==='agency'?agencyField:key,value]);
  return list.filter(r=>active(r,terms,filters));
}
const mentionExplorer=window.StatusMentions.create({
  $,yearOptions:years,escape:e,format:fmt,storyCount:n=>quantity(n,false),recordButton,byDate,
});
function tab(to) {
  state.tab=to;
  document.querySelectorAll('[data-tab]').forEach(b=>b.dataset.tab===to ? b.setAttribute('aria-current','page') : b.removeAttribute('aria-current'));
  for (const current of ['timeline','mentions','tree','archive','method']) $(current).hidden=current!==to;
  $('explorer').hidden=to==='method';
  render();
}
function render() {
  if(state.tab==='timeline') drawTimeline();
  if(state.tab==='mentions') mentionExplorer.render(filtered(D.rows,'mentionAgencies'));
  if(state.tab==='tree') drawTree();
  if(state.tab==='archive') drawArchive();
}
function setToggles(selector, key, value) {
  document.querySelectorAll(selector).forEach(b=>b.setAttribute('aria-pressed',b.dataset[key]===value));
}
function selectFilter(k,value) {
  $(k).value = $(k).value===value ? '' : value;
  state.limit=21; state.treeLimit=18; state.episodeLimit=24;
  render();
}

function drawTimeline() {
  const verified=state.mode==='decision';
  const base=filtered(verified?D.actions:D.rows).filter(r=>state.track===null||D.tracks[state.track].keys.includes(r.key));
  const restricted=base.filter(r=>state.year === 'all' || r.date.startsWith(state.year));
  const visible=restricted.filter(r=>!state.period || r.date.startsWith(state.period));
  $('chart-note').textContent=verified
    ? 'Даты конкретных действий из сверенных карточек'
    : 'Сюжеты по датам публикации стенограмм на Teletype';
  $('records-title').textContent=verified?'Действия':'Сюжеты';
  $('analysis-title').textContent=verified?'Темы сверенных действий':'Что обсуждали чаще';
  $('insight-note').textContent=verified?'Число действий с такой темой в выбранной области':'Число сюжетов с такой темой в выбранной области';
  setToggles('[data-mode]','mode',state.mode);
  $('years').innerHTML=['all',...years].map(y=>'<button type="button" data-year="'+y+'" aria-pressed="'+(y===state.year)+'">'+(y==='all'?'Все годы':y)+'</button>').join('');
  $('clear-period').hidden=!state.period;
  $('clear-period').textContent=state.year==='all'?'Очистить год ×':'Очистить месяц ×';
  const keys=state.year==='all'?years:months.map((m,i)=>state.year+'-'+String(i+1).padStart(2,'0'));
  const counts=Object.fromEntries(keys.map(k=>[k,0]));
  for (const record of restricted) counts[record.date.slice(0,state.year==='all'?4:7)]++;
  const maximum=Math.max(1,...Object.values(counts));
  $('chart').style.gridTemplateColumns='repeat('+keys.length+',minmax(0,1fr))';
  $('chart').innerHTML=keys.map((k,i)=>{
    const label=state.year==='all'?k:months[i];
    const detail=state.year==='all'?k:longMonths[i]+' '+state.year;
    const outOfRange=k.length===7&&(k<D.start.slice(0,7)||k>D.end.slice(0,7));
    const hint=detail+' · '+(outOfRange?'вне периода архива':quantity(counts[k],verified));
    return '<button type="button" class="bar" data-period="'+k+'" data-count="'+counts[k]+'" '+(outOfRange?'disabled ':'')+'aria-pressed="'+(state.period===k)+'" title="'+e(hint)+'" aria-label="'+e(hint)+'" style="--height:'+((counts[k]/maximum)*85)+'%"><span class="bar-track"><span class="bar-fill"></span><span class="bar-number">'+(outOfRange?'—':counts[k])+'</span></span><span class="bar-month">'+label+'</span></button>';
  }).join('');
  const periodText=state.period && (state.period.length===4 ? state.period : longMonths[Number(state.period.slice(-2))-1]+' '+state.year);
  $('time-result').textContent=periodText
    ? periodText.charAt(0).toUpperCase()+periodText.slice(1)+' · '+quantity(visible.length,verified)
    : state.year==='all'?'Нажмите на столбец, чтобы выбрать год.':'Нажмите на столбец, чтобы выбрать месяц.';
  const tags = new Map();
  for (const r of visible) for (const tag of r.tags) {
    if(tag!=='Другие сюжеты') tags.set(tag,(tags.get(tag)??0)+1);
  }
  const top=[...tags].sort((a,b)=>b[1]-a[1]||caps.compare(a[0],b[0])).slice(0,3);
  $('insights').innerHTML=top.length?top.map(([key,count])=>'<button type="button" class="insight" data-filter="topic" data-value="'+e(key)+'"><span>'+e(key)+'</span><strong>'+fmt.format(count)+'</strong></button>').join('')
    :'<p class="help">В этой выборке нет размеченных тем.</p>';
  const sorted=byDate(visible,$('sort').value==='desc');
  if (!sorted.some(r=>r.id===state.id)) state.id=sorted[0]?.id??null;
  const episodeCount=new Set(sorted.map(r=>r.slug)).size;
  $('result-count').textContent=quantity(sorted.length,verified)+' · выпусков: '+fmt.format(episodeCount);
  $('record-list').innerHTML=sorted.length?sorted.slice(0,state.limit).map(r=>recordButton(r,state.id===r.id)).join('')+
    (sorted.length>state.limit?'<button class="more" type="button" data-more="records">Показать ещё '+Math.min(21,sorted.length-state.limit)+'</button>':'')
    :'<div class="empty">По этим фильтрам ничего не найдено. Измените период или очистите фильтры.</div>';
  renderDetail(records.get(state.id));
  $('track-label')?.remove();
  if(state.track!==null) $('chart-note').insertAdjacentHTML('afterend','<p id="track-label">Линия: '+
    e(D.tracks[state.track].name)+' <button data-clear-track class="text-button" type="button">Снять фильтр ×</button></p>');
}
function recordButton(r,active=false) {
  const sub=r.verified ? (r.actors.length ? r.actors.join(', ') : r.agency[0]??'') : r.tags[0];
  return '<button type="button" class="record-button'+(active?' selected':'')+'" data-record="'+e(r.id)+'"'+(active?' aria-current="true"':'')+
    '><time datetime="'+r.date+'">'+textDate(r.date)+'</time><span>'+e(r.title)+(sub?'<small>'+e(sub)+'</small>':'')+
    '</span><span class="arrow" aria-hidden="true">›</span></button>';
}
function chips(values,key,extra='') {
  return values?.length?'<div class="chips">'+values.map(v=>'<button type="button" class="chip '+extra+'" data-filter="'+key+'" data-value="'+e(v)+'">'+e(v)+'</button>').join('')+'</div>':'';
}
function escapeList(items) {return '<ul class="doc-list">'+items.map(x=>'<li>'+e(x)+'</li>').join('')+'</ul>';}
function renderDetail(r) {
  if(!r) {
    $('record-detail').innerHTML='<p class="help">Здесь откроется карточка сюжета или действия.</p>';
    return;
  }
  const ep=episodes.get(r.slug);
  const pubdate=ep?.date??r.date;
  let body='';
  if (r.verified) {
    const actors = r.actors.length ? r.actors.join(', ') : r.actorAgency.join(', ');
    const targets = r.people.filter(p=>!r.actors.includes(p));
    body += (actors ? '<p class="detail-label">Кто действовал</p><p class="detail-fact">'+e(actors)+'</p>' : '')+
      '<p class="detail-action">'+e(r.action)+'</p>'+
      (targets.length?'<p class="detail-label">Другие участники</p>'+chips(targets,'person'):'')+
      '<p class="detail-label">Документ</p>'+escapeList(r.documents);
    const related=D.actions.filter(x=>x.key===r.key && x.id!==r.id);
    if (related.length) body+='<p class="detail-label">Другие стадии этого решения</p><div class="doc-chain">'+
      byDate(related,false).map(x=>'<button class="text-button" type="button" data-record="'+e(x.id)+'">'+textDate(x.date)+' · '+e(x.stages[0])+'</button>').join('')+'</div>';
  } else {
    for(const [hits,label] of [[r.parties,'Упоминания российских партий'],[r.corporations,'Упоминания госкорпораций']]) {
      if(hits?.length) body+='<p class="detail-label">'+label+'</p><ul class="point-list">'+hits.map(p=>
        '<li><strong>'+e(p.name)+' · '+fmt.format(p.count)+'</strong> '+e(p.text)+' '+
        source(sourceUrl(r,p.anchor??r.anchor),'К абзацу')+'</li>').join('')+'</ul>';
    }
    if(r.people.length) body+='<p class="detail-label">Фамилии в контексте</p>'+chips(r.people,'person');
    if(r.points?.length) body+='<p class="detail-label">Что сказано в стенограмме</p><ul class="point-list">'+
      r.points.map(x=>'<li>'+e(x.text)+(x.anchor?' '+source(sourceUrl(r,x.anchor),'К абзацу'):'')+'</li>').join('')+'</ul>';
    if(r.documents.length) body+='<p class="detail-label">Названия и номера из стенограммы</p>'+escapeList(r.documents);
    if(r.dateRefs?.length) body+='<p class="detail-label">Даты, названные в сюжете</p><p class="detail-fact">'+e(r.dateRefs.map(x=>x.text).join(' · '))+'</p>';
  }
  if(r.agency.length) body+='<p class="detail-label">Ведомства в сюжете</p>'+chips(r.agency,'agency');
  const docs=(r.links??[]).map(x=>source(x.url,x.text||'Документ'));
  if(r.official) docs.unshift(source(r.official,'Текст акта или карточка проекта'));
  if(r.bill && !r.official.endsWith('/'+r.bill)) docs.push(source('https://sozd.duma.gov.ru/bill/'+r.bill,'Проект № '+r.bill));
  $('record-detail').innerHTML='<p class="detail-date">'+textDate(r.date)+(r.verified?' · Дата действия':' · Опубликовано')+'</p>'+
    '<h3>'+e(r.title)+'</h3>'+chips(r.tags,'topic')+chips(r.stages,'stage','subdued')+body+
    (r.verified?'<p class="detail-label">Стенограмма опубликована '+textDate(pubdate)+'</p>':'')+
    '<div class="detail-links">'+source(sourceUrl(r),'К стенограмме')+'<button type="button" class="text-button" data-episode="'+e(r.slug)+'">Саммари выпуска</button>'+
    docs.join('')+'</div>';
}
function openRecord(id) {
  const r=records.get(id);
  if(!r)return;
  const nextMode=r.verified?'decision':'publication';
  const fresh=(state.track!==null && !D.tracks[state.track].keys.includes(r.key)) || state.tab!=='timeline' || nextMode!==state.mode || (state.year!=='all' && !r.date.startsWith(state.year)) ||
    (state.period && !r.date.startsWith(state.period)) || !active(r,queryTerms(),selectedFilters());
  if(fresh) {
    if(nextMode!=='decision'||(state.track!==null&&!D.tracks[state.track].keys.includes(r.key))) state.track=null;
    if(!active(r,queryTerms(),selectedFilters())) for(const k of [...controls,'query']) $(k).value='';
    state.mode=nextMode; state.year=r.date.slice(0,4); state.period=r.date.slice(0,7);
  }
  state.id=id;
  tab('timeline');
  if(fresh || matchMedia('(max-width:740px)').matches) {
    $('record-detail').scrollIntoView({block:'start'});
    $('record-detail').focus({preventScroll:true});
  }
}

function drawTree() {
  const verified=state.branch==='verified';
  setToggles('[data-tree]','tree',state.tree);
  setToggles('[data-branch]','branch',state.branch);
  const base=filtered(verified?D.actions:D.rows);
  const field=state.tree==='agency'?(verified?'actorAgency':'agency'):verified?'actors':'people';
  const groups=new Map();
  for(const r of base) for(const name of r[field]) {
    if(!groups.has(name)) groups.set(name,[]);
    groups.get(name).push(r);
  }
  const rows=[...groups].sort((a,b)=>b[1].length-a[1].length||caps.compare(a[0],b[0]));
  if(!rows.length) {
    $('tree-list').innerHTML='<p class="empty">Связей по этим фильтрам не найдено.</p>';
    return;
  }
  $('tree-list').innerHTML=rows.slice(0,state.treeLimit).map(([name,items])=>{
    const ordered=byDate(items);
    return '<details class="tree-row"><summary>'+e(name)+' <span>'+quantity(items.length,verified)+'</span></summary>'+
      ordered.slice(0,12).map(r=>recordButton(r)).join('')+
      (ordered.length>12?'<button class="more" type="button" data-filter="'+state.tree+'" data-value="'+e(name)+'" data-show-all="true">Все записи · '+ordered.length+'</button>':'')+
      '</details>';
  }).join('')+(rows.length>state.treeLimit?'<button class="more" type="button" data-more="tree">Показать ещё</button>':'');
}

function drawArchive() {
  const year=$('episode-year').value;
  const terms=queryTerms();
  const byFilter=new Set(filtered(D.rows).map(r=>r.slug));
  if(selectedFilters().length) for(const r of filtered(D.actions)) byFilter.add(r.slug);
  const selection=byDate(D.episodes.filter(ep=>(!year||ep.date.startsWith(year)) &&
    (byFilter.has(ep.slug)||(!selectedFilters().length && terms.every(t=>ep.search.includes(t))))));
  $('archive-count').textContent='Выпусков: '+fmt.format(selection.length);
  $('episode-list').innerHTML=selection.slice(0,state.episodeLimit).map(ep=>'<article class="episode-card"><p class="detail-date">'+textDate(ep.date)+'</p>'+
    '<h3>'+e(ep.subtitle||ep.title)+'</h3><p>Сезон '+e(ep.season)+' · выпуск '+e(ep.episode)+' · сюжетов: '+ep.rows.length+'</p>'+
    '<button type="button" class="text-button" data-episode="'+e(ep.slug)+'">Открыть саммари</button></article>').join('')+
    (selection.length>state.episodeLimit?'<button class="more" type="button" data-more="archive">Загрузить ещё выпуски</button>':'')+
    (selection.length?'':'<p class="empty">Выпуски по этим фильтрам не найдены.</p>');
}

function showEpisode(slug) {
  const ep=episodes.get(slug);
  if(!ep) return;
  $('episode-detail').innerHTML='<p class="detail-date">'+textDate(ep.date)+' · Опубликовано на Teletype</p>'+
    '<h2 id="episode-title">'+e(ep.subtitle||ep.title)+'</h2><p>'+e(ep.title)+'</p>'+chips(ep.tags,'topic')+
    (ep.notes.length?'<h3>Главное в выпуске</h3><ul>'+ep.notes.map(n=>{
      const r=records.get(n.id);
      return '<li>'+(n.topic?'<strong>'+e(n.topic)+'.</strong> ':'')+e(n.text)+(r?' '+source(sourceUrl(r,n.anchor??r.anchor),'Источник'):'')+'</li>';
    }).join('')+'</ul>':'')+
    (ep.actions.length?'<h3>Сверенные действия</h3><ul>'+ep.actions.map(id=>{
      const r=records.get(id);
      return '<li><button type="button" class="text-button" data-record="'+e(id)+'">'+textDate(r.date)+' · '+e(r.title)+' · '+e(r.stages[0])+'</button></li>';
    }).join('')+'</ul>':'')+
    '<h3>Сюжеты</h3><ul>'+ep.rows.map(id=>{
      const r=records.get(id);
      return '<li><button type="button" class="text-button" data-record="'+e(id)+'">'+e(r.title)+'</button></li>';
    }).join('')+'</ul>'+
    '<p>'+source(ep.url,'Стенограмма целиком')+'</p>';
  if(!$('episode-dialog').open) $('episode-dialog').showModal();
  $('episode-detail').parentNode.scrollTop=0;
}
$('close-dialog').addEventListener('click',()=>$('episode-dialog').close());
$('episode-dialog').addEventListener('click',ev=>{if(ev.target===$('episode-dialog')) $('episode-dialog').close();});
$('filters').addEventListener('submit',ev=>ev.preventDefault());
$('filters').addEventListener('input',()=>{state.limit=21;state.treeLimit=18;state.episodeLimit=24;render();});
$('filters').addEventListener('reset',()=>{state.period=null;state.track=null;state.limit=21;state.treeLimit=18;state.episodeLimit=24;setTimeout(render,0);});
$('sort').addEventListener('change',()=>{state.limit=21;render();});
$('episode-year').addEventListener('change',()=>{state.episodeLimit=24;drawArchive();});
$('home').addEventListener('click',ev=>{ev.preventDefault();tab('timeline');window.scrollTo({top:0});});
$('method-link').addEventListener('click',()=>{tab('method');$('method').scrollIntoView();});
$('clear-period').addEventListener('click',()=>{state.period=null;state.limit=21;drawTimeline();});
document.addEventListener('click',ev=>{
  const b=ev.target.closest('button');
  if(!b)return;
  const d=b.dataset;
  if(d.tab) tab(d.tab);
  if(d.mode) {state.mode=d.mode;state.track=null;state.period=null;state.id=null;state.limit=21;drawTimeline();}
  if(d.year) {state.year=d.year;state.period=null;state.id=null;state.limit=21;drawTimeline();}
  if(d.track!==undefined) {
    for(const key of [...controls,'query']) $(key).value='';
    state.track=Number(d.track);state.year='all';state.period=null;state.mode='decision';state.id=null;state.limit=21;
    drawTimeline(); $('time-title').scrollIntoView({block:'start'});
  }
  if('clearTrack' in d) {state.track=null;drawTimeline();}
  if(d.period) {
    state.period=state.period===d.period?null:d.period;state.limit=21;drawTimeline();
    $('chart').querySelector('[data-period="'+d.period+'"]')?.focus({preventScroll:true});
  }
  if(d.record) {
    if($('episode-dialog').open) $('episode-dialog').close();
    openRecord(d.record);
  }
  if(d.episode) showEpisode(d.episode);
  if(d.filter) {
    if($('episode-dialog').open) $('episode-dialog').close();
    if(d.showAll) {
      $(d.filter).value=d.value;
      state.mode=state.branch==='verified'?'decision':'publication';state.track=null;state.year='all';state.period=null;state.limit=21;
      tab('timeline');$('records-title').scrollIntoView({block:'start'});
    } else selectFilter(d.filter,d.value);
  }
  if(d.tree) {state.tree=d.tree;state.treeLimit=18;drawTree();}
  if(d.branch) {state.branch=d.branch;state.treeLimit=18;drawTree();}
  if(d.more==='records') {state.limit+=21;drawTimeline();}
  if(d.more==='tree') {state.treeLimit+=18;drawTree();}
  if(d.more==='archive') {state.episodeLimit+=24;drawArchive();}
});
$('tracks').innerHTML=D.tracks.map((t,i)=>'<article class="track"><strong>'+e(t.name)+'</strong><p>'+e(t.text)+
  '</p><button type="button" class="text-button" data-track="'+i+'">Показать на графике</button></article>').join('');
window.addEventListener('hashchange',()=>{if(location.hash==='#mentions') tab('mentions');});
tab(location.hash==='#mentions'?'mentions':'timeline');
