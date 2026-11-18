'use strict';

window.StatusMentions = (() => {
  const types = ['person','agency','party','corporation'];
  const labels = {person:'Люди', agency:'Ведомства', party:'Партии', corporation:'Госкорпорации'};
  const width = 1020;
  const lanes = [194,385,615,800];
  const overviewLimit = 30;
  const neighborhoodLimit = 14;
  const nameOrder = new Intl.Collator('ru-RU');

  function collect(rows) {
    const nodes = new Map(), edges = new Map();
    for (const row of rows) {
      const current = new Map();
      for (const [type, names] of Object.entries({
        person:(row.people ?? []).map(name => [name,1]),
        agency:(row.mentionAgencies ?? row.agency ?? []).map(name => [name,1]),
        party:(row.parties ?? []).map(hit => [hit.name, hit.count]),
        corporation:(row.corporations ?? []).map(hit => [hit.name, hit.count]),
      })) {
        for (const [name, count] of names) current.set(type+':'+name, {type,name,count});
      }
      const keys = [...current.keys()].sort();
      for (const [index, key] of keys.entries()) {
        const {type,name,count} = current.get(key);
        if (!nodes.has(key)) nodes.set(key, {key,type,name,count:0,stories:[]});
        const node = nodes.get(key);
        node.count += count;
        node.stories.push(row);
        for (const other of keys.slice(index+1)) {
          const id = JSON.stringify([key,other]);
          if (!edges.has(id)) edges.set(id,{id, keys:[key,other], stories:[]});
          edges.get(id).stories.push(row);
        }
      }
    }
    return {nodes,edges};
  }

  function matches(edge, relation, nodes) {
    const [a,b] = edge.keys.map(key => nodes.get(key).type);
    if (relation==='people') return a==='person' && b==='person';
    if (relation==='agencies') return a==='agency' && b==='agency';
    if (relation==='mixed') return [a,b].includes('person') && [a,b].includes('agency');
    if (relation==='parties') return a==='party' || b==='party';
    if (relation==='corporations') return a==='corporation' || b==='corporation';
    return true;
  }

  function overview(edges, nodes, prioritizeGroups) {
    const groups = new Map(types.map(type => [type, new Set()]));
    const result = new Set();
    const rare = prioritizeGroups ? ['parties','corporations'].flatMap(kind =>
      edges.filter(edge => matches(edge,kind,nodes)).slice(0,3)) : [];
    for (const edge of [...rare,...edges]) {
      const [a,b] = edge.keys.map(key => nodes.get(key));
      if ([a,b].some(n => !groups.get(n.type).has(n.key) &&
          groups.get(n.type).size + ([a,b].filter(x=>x.type===n.type && !groups.get(x.type).has(x.key)).length) > 7)) continue;
      for (const n of [a,b]) groups.get(n.type).add(n.key);
      result.add(edge);
      if (result.size>=overviewLimit) break;
    }
    return [...result];
  }

  function positions(visible, edges, focus, height) {
    const out = new Map();
    const spacedY = (i,size) => (i+.5)*(height-53)/size+35;
    if (focus) {
      const others = edges.map(edge => edge.keys.find(key => key!==focus));
      out.set(focus,{x:155,y:height/2,align:'middle',offset:22});
      others.forEach((key,i) => out.set(key,{x:555,y:spacedY(i,others.length),align:'start',offset:0}));
      return out;
    }
    for (const [index,type] of types.entries()) {
      const group = visible.filter(n => n.type===type).sort((a,b) =>
        b.stories.length-a.stories.length || nameOrder.compare(a.name,b.name));
      group.forEach((n,i) => out.set(n.key,{
        x:lanes[index],y:spacedY(i,group.length),align:['end','middle','middle','start'][index],offset:index===1||index===2?-16:0,
      }));
    }
    return out;
  }

  function edgePath(a,b) {
    const {x,y} = a;
    if (x===b.x) {
      const bow = (x>600?-1:1)*(30+Math.min(53,Math.abs(y-b.y)*.22));
      return ['M',x,y,'C',x+bow,y,x+bow,b.y,b.x,b.y].join(' ');
    }
    const step = (b.x-x)*.45;
    return ['M',x,y,'C',x+step,y,b.x-step,b.y,b.x,b.y].join(' ');
  }

  function create({$,yearOptions,escape,format,storyCount,recordButton,byDate}) {
    const panel = $('mentions');
    const plot = $('mention-plot');
    const focus = $('mention-focus');
    const relation = $('mention-relation');
    const year = $('mention-year');
    const threshold = $('mention-threshold');
    const summaries=[
      {type:'party',table:$('mention-parties'),empty:$('mention-party-empty'),sort:$('mention-party-sort')},
      {type:'corporation',table:$('mention-corporations'),empty:$('mention-corporation-empty'),sort:$('mention-corporation-sort')},
    ];
    const details = $('mention-detail');
    let input = [], net, edges = [], drawn = [], subject = '', selection = '', limit = 7;
    let height = 420, scale = 1, origin = {x:0,y:0}, drag = null;
    year.innerHTML = '<option value="">Все годы</option>'+yearOptions.map(y =>
      '<option value="'+escape(y)+'">'+escape(y)+'</option>').join('');

    function num(value) { return format.format(value); }
    function name(key) { return net.nodes.get(key).name; }
    function pair(edge) { return edge.keys.map(name).join(' ↔ '); }
    function refresh(rows) {
      input=rows;
      const scoped=rows.filter(row => !year.value || row.date.startsWith(year.value));
      net=collect(scoped);
      if (!net.nodes.has(subject)) subject='';
      const options=types.map(type => {
        const items=[...net.nodes.values()].filter(n=>n.type===type).sort((a,b)=>nameOrder.compare(a.name,b.name));
        return items.length ? '<optgroup label="'+labels[type]+'">'+items.map(n=>
          '<option value="'+escape(n.key)+'">'+escape(n.name)+'</option>').join('')+'</optgroup>' : '';
      });
      focus.innerHTML='<option value="">Обзор</option>'+options.join('');
      focus.value=subject;
      edges=[...net.edges.values()].filter(edge => edge.stories.length>=Number(threshold.value) &&
        matches(edge,relation.value,net.nodes) && (!subject || edge.keys.includes(subject)))
        .sort((a,b)=>b.stories.length-a.stories.length || nameOrder.compare(pair(a),pair(b)));
      drawn=subject ? edges.slice(0,neighborhoodLimit) : overview(edges,net.nodes,relation.value==='all');
      if (!edges.some(edge=>edge.id===selection)) selection='';
      if (selection && !drawn.some(edge=>edge.id===selection)) {
        // A connection chosen in the list remains visible in a focused neighborhood.
        if (subject) drawn=[...drawn.slice(0,neighborhoodLimit-1),net.edges.get(selection)];
      }
      drawGraph();
      drawDetails();
      summaries.forEach(drawSummary);
    }

    function drawGraph() {
      const visibleKeys = new Set(drawn.flatMap(edge=>edge.keys));
      if (subject) visibleKeys.add(subject);
      const nodes=[...visibleKeys].map(key=>net.nodes.get(key));
      height=subject ? Math.max(360,drawn.length*31+48) : 398;
      plot.toggleAttribute('hidden',!nodes.length);
      plot.setAttribute('width',width);
      plot.setAttribute('height',height);
      $('mention-empty').hidden=!!nodes.length;
      $('mention-empty').textContent='Связей для этих фильтров нет. Попробуйте выбрать другой период или уменьшить порог.';
      const points=positions(nodes,drawn,subject,height);
      const maxLink=Math.max(1,...drawn.map(edge=>edge.stories.length));
      const maxNode=Math.max(1,...nodes.map(node=>node.stories.length));
      const guides=subject ? '' : types.map((type,i) => {
        if (!nodes.some(n=>n.type===type)) return '';
        const x=lanes[i];
        return '<line class="mention-lane" x1="'+x+'" x2="'+x+'" y1="37" y2="'+(height-14)+'"/>'+
          '<text class="mention-lane-label" text-anchor="middle" x="'+x+'" y="24">'+labels[type]+'</text>';
      }).join('');
      const lines=[...drawn].sort((a,b)=>b.stories.length-a.stories.length).map(edge => {
        const description=pair(edge)+' · '+storyCount(edge.stories.length);
        const d=edgePath(...edge.keys.map(key=>points.get(key)));
        const stroke=(1+4.1*Math.sqrt(edge.stories.length/maxLink)).toFixed(2);
        return '<g class="mention-edge" role="button" tabindex="0" data-mention-edge="'+escape(edge.id)+'" data-party="'+
          matches(edge,'parties',net.nodes)+'" data-corporation="'+matches(edge,'corporations',net.nodes)+'" aria-pressed="'+(selection===edge.id)+'" aria-label="'+escape(description)+'"><title>'+
          escape(description)+'</title><path class="hit" d="'+d+'"/><path class="drawn" d="'+d+'" stroke-width="'+stroke+'"/></g>';
      }).join('');
      const dots=nodes.map(n => {
        const p=points.get(n.key);
        const radius=5+7*Math.sqrt(n.stories.length/maxNode);
        const description=n.name+' · '+storyCount(n.stories.length);
        const maxLabel=subject && n.key!==subject ? 44 : 28;
        const short=n.name.length>maxLabel?n.name.slice(0,maxLabel-1)+'…':n.name;
        const dx=p.align==='end'?-radius-6:p.align==='start'?radius+6:0;
        const dy=p.offset>0?radius+10:p.offset || 0;
        return '<g class="mention-node mention-'+n.type+'" role="button" tabindex="0" aria-label="'+escape(description)+
          '" aria-pressed="'+(subject===n.key)+'" data-mention-node="'+escape(n.key)+'" transform="translate('+p.x+','+p.y+')"><title>'+
          escape(description)+'</title><circle class="halo" r="'+(radius+3)+'"/><circle class="point" r="'+radius+'"/>'+
          '<text x="'+dx+'" y="'+dy+'" dominant-baseline="middle" text-anchor="'+p.align+'">'+escape(short)+'</text></g>';
      }).join('');
      plot.innerHTML=guides+lines+dots;
      viewport();
      $('mention-caption').textContent='Сюжетов в выборке — '+num(input.filter(r=>!year.value||r.date.startsWith(year.value)).length)+
        ' · На графе '+num(drawn.length)+' из '+num(edges.length)+' связей'+(edges.length>drawn.length?' · Выберите узел для детализации.':'.');
    }

    function drawDetails() {
      const selected=selection && net.edges.get(selection);
      if (selected) {
        const stories=byDate(selected.stories);
        details.innerHTML='<h3 tabindex="-1">Общие сюжеты</h3><div class="mention-names">'+selected.keys.map(key=> {
          const n=net.nodes.get(key);
          return '<button type="button" class="chip mention-'+n.type+'" data-mention-node="'+escape(key)+
            '"><span class="mention-dot" aria-hidden="true"></span>'+escape(n.name)+'</button>';
        }).join('')+'</div><p>'+storyCount(stories.length)+' с совместными упоминаниями.</p>'+
          '<button type="button" class="text-button" data-mention-back>К списку связей</button>'+
          stories.slice(0,limit).map(r=>recordButton(r)).join('')+loadMore(stories.length,'сюжеты');
        return;
      }
      const node=subject && net.nodes.get(subject);
      const topics=new Map();
      if (node) for (const r of node.stories) for (const tag of r.tags ?? []) {
        if (tag!=='Другие сюжеты') topics.set(tag,(topics.get(tag)??0)+1);
      }
      const frequent=[...topics].sort((a,b)=>b[1]-a[1]||nameOrder.compare(a[0],b[0])).slice(0,3);
      const summary=node ? '<h3>'+escape(node.name)+'</h3><p>'+storyCount(node.stories.length)+' с упоминанием.</p>'+
        (frequent.length ? '<p>Частые темы — '+frequent.map(([tag,total])=>escape(tag)+' ('+num(total)+')').join(', ')+'</p>' : '')+
        '<button type="button" class="text-button" data-mention-clear>К обзору</button>' :
        '<h3>Частые связи</h3><p>Выберите связь, чтобы открыть сюжеты и стенограммы.</p>';
      const candidates=(node?edges:drawn).slice().sort((a,b)=>b.stories.length-a.stories.length || nameOrder.compare(pair(a),pair(b)));
      details.innerHTML=summary+
        (node?'<details><summary>Сюжеты с упоминанием</summary>'+byDate(node.stories).slice(0,limit).map(r=>recordButton(r)).join('')+
          loadMore(node.stories.length,'сюжеты')+'</details>':'')+
        (candidates.length ? '<div class="mention-edge-list">'+candidates.slice(0,limit).map(edge=>
          '<button type="button" class="mention-edge-item" data-mention-edge="'+escape(edge.id)+'"><span>'+
          escape(node ? name(edge.keys.find(key=>key!==subject)) : pair(edge))+'</span><strong>'+
          num(edge.stories.length)+'</strong></button>').join('')+'</div>'+loadMore(candidates.length,'связи') :
          '<p>Связей по текущим фильтрам нет.</p>');
    }

    function loadMore(total,label) {
      return total>limit ? '<button type="button" class="more" data-mention-more>Ещё '+label+'</button>' : '';
    }

    function drawSummary({type,table,empty,sort}) {
      const data=[...net.nodes.values()].filter(n=>n.type===type).map(n=>({
        key:n.key,name:n.name,count:n.count,stories:n.stories.length,episodes:new Set(n.stories.map(r=>r.slug)).size,
      }));
      data.sort((a,b)=>b[sort.value]-a[sort.value] || nameOrder.compare(a.name,b.name));
      table.hidden=!data.length;
      empty.hidden=!!data.length;
      table.querySelector('tbody').innerHTML=data.map(p=>'<tr'+(subject===p.key?' class="selected"':'')+'>'+
        '<td><button type="button" class="text-button" data-mention-node="'+escape(p.key)+'">'+escape(p.name)+'</button></td>'+
        '<td>'+num(p.count)+'</td><td>'+num(p.stories)+'</td><td>'+num(p.episodes)+'</td></tr>').join('');
    }

    function viewport() {
      const w=width/scale, h=height/scale;
      origin.x=Math.max(0,Math.min(width-w,origin.x));
      origin.y=Math.max(0,Math.min(height-h,origin.y));
      plot.setAttribute('viewBox',[origin.x,origin.y,w,h].join(' '));
      plot.dataset.pannable=scale>1;
      panel.querySelector('[data-mention-zoom="reset"]').textContent=Math.round(scale*100)+'%';
      panel.querySelector('[data-mention-zoom="out"]').disabled=scale<=1 || plot.hasAttribute('hidden');
      panel.querySelector('[data-mention-zoom="in"]').disabled=scale>=4 || plot.hasAttribute('hidden');
    }

    function pickNode(key) {
      const type=net.nodes.get(key)?.type;
      const includeType={party:'parties',corporation:'corporations'}[type];
      if (includeType && !['all',includeType].includes(relation.value)) relation.value=includeType;
      subject=key; selection=''; limit=7; scale=1;
      refresh(input);
    }

    panel.addEventListener('click', event=>{
      const target=event.target.closest('[data-mention-node],[data-mention-edge],[data-mention-back],[data-mention-clear],[data-mention-zoom],[data-mention-more]');
      if (!target) return;
      const d=target.dataset;
      if (d.mentionNode) {
        pickNode(d.mentionNode);
        if (target.closest('table')) $('mentions-title').scrollIntoView({block:'start'});
        focus.focus({preventScroll:true});
      } else if (d.mentionEdge) {
        selection=d.mentionEdge; limit=7; refresh(input);
        details.querySelector('h3').focus({preventScroll:true});
        if (matchMedia('(max-width:900px)').matches) details.scrollIntoView({block:'nearest'});
      } else if ('mentionBack' in d) {
        selection=''; limit=7; refresh(input);
        details.querySelector('button')?.focus({preventScroll:true});
      } else if ('mentionClear' in d) {
        pickNode('');
        focus.focus({preventScroll:true});
      } else if ('mentionMore' in d) {
        const wasOpen=!!details.querySelector('details[open]');
        const before=limit;
        limit+=7; drawDetails();
        const disclosure=details.querySelector('details');
        if (wasOpen && disclosure) disclosure.open=true;
        const added=target.closest('details')?details.querySelectorAll('details [data-record]'):
          details.querySelectorAll(selection?'[data-record]':'[data-mention-edge]');
        added[before]?.focus({preventScroll:true});
      } else if (d.mentionZoom) {
        const previous=scale;
        scale=d.mentionZoom==='reset'?1:Math.max(1,Math.min(4,scale*(d.mentionZoom==='in'?1.5:2/3)));
        origin.x+=width/2*(1/previous-1/scale);
        origin.y+=height/2*(1/previous-1/scale);
        viewport();
      }
    });
    panel.addEventListener('keydown',event=>{
      if (!event.target.matches('g[role="button"]') || !['Enter',' '].includes(event.key)) return;
      event.preventDefault();
      event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));
    });
    focus.addEventListener('change',()=>pickNode(focus.value));
    for (const control of [year,relation,threshold]) control.addEventListener('change',()=>{
      selection=''; limit=7; scale=1; refresh(input);
    });
    for (const summary of summaries) summary.sort.addEventListener('change',()=>drawSummary(summary));

    plot.addEventListener('pointerdown',event=>{
      if (!event.isPrimary || event.button!==0 || scale===1 || event.target.closest('g[role="button"]')) return;
      drag={x:event.clientX,y:event.clientY,origin:{...origin}};
      plot.setPointerCapture(event.pointerId);
      plot.dataset.dragging=true;
    });
    plot.addEventListener('pointermove',event=>{
      if (!drag || !event.isPrimary) return;
      const ratio=Math.max(width/plot.clientWidth,height/plot.clientHeight)/scale;
      origin={x:drag.origin.x-(event.clientX-drag.x)*ratio,y:drag.origin.y-(event.clientY-drag.y)*ratio};
      viewport();
    });
    plot.addEventListener('lostpointercapture',()=>{
      drag=null; plot.dataset.dragging=false;
    });

    return {render:refresh};
  }

  return {create,collect};
})();
