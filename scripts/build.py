from collections import Counter, defaultdict
from pathlib import Path
import json, re
from urllib.parse import urlparse
from lxml import html
from prepare import WORK, OUTPUT, file_id, get_document, render_transcript, clean

def load(name):
    return json.loads((WORK/name).read_text())

def cut(text, limit):
    return text if len(text)<=limit else text[:limit-1].rsplit(' ',1)[0].rstrip(' .,;–—')+'…'

def url_for(post,anchor=None):
    return post['url']+('#'+anchor if anchor else '')

def day(value):
    return '.'.join(value.split('-')[::-1])

def heading(x):
    return x.replace('\n',' ').strip('# ')

def md_link(text,url):
    return '['+text.replace('[','').replace(']','')+'](<'+url+'>)'

def q(text):
    return '«'+text.strip().strip('«»').replace('«','„').replace('»','“')+'»'

def choose(point):
    t=point['text']
    strength=0
    if re.search(r'законопроект|закон\b|председател|президент|министерств|внес[её]|проект|указ|правительств|Госдум|ЦИК|ФСБ|регион',t,re.I):
        strength+=2
    if re.search(r'подписал|приговорил|принял|назначил|внес[её]|вступил|утвердил|вв[её]л|опубликовал|возбудил|предложил|рекомендова|запретил',t,re.I):
        strength+=3
    if re.match(r'Ну|Вот|Напомн|А вот|Я |В общем|Поэтому|В частности|Это |Так что|И вот|Если ',t):
        strength-=4
    if re.search(r'как вы понимаете|простите|сами понимаете|давайте|извините|потому что|предполож|если бы',t):
        strength-=2
    return strength - abs(len(t)-180)/210

def note_index(rows):
    ranks=[]
    for i,x in enumerate(rows):
        if not x['points']:
            continue
        point=max(x['points'],key=choose)
        value=(choose(point)+2*bool(x['documents'])+1.4*bool(x['stages'])+0.85*bool(x['people'])
               +0.8*bool(x['agency'])-.28*i)
        ranks.append((value,i,point))
    selected=[]
    seen=set()
    for val,i,point in sorted(ranks, key=lambda r:-r[0]):
        tag=rows[i]['tags'][0]
        if tag in seen and len(ranks)>4 and len(selected)<2:
            continue
        selected.append((i,point))
        seen.add(tag)
        if len(selected)==3:
            break
    return sorted(selected)

MANUAL = {
 'status_s10_e12':[
   ('zHWU','По стенограмме, российскую делегацию на переговорах возглавил Владимир Мединский. Ведущая связала её состав с ролью ФСБ и Генштаба.', 'QfIN'),
   ('HDn4','Группа депутатов во главе с Сергеем Боярским внесла проект о штрафах для аудиовизуальных сервисов. В выпуске отмечено, что в думской базе удалось найти решение о принятии к рассмотрению, а заключение комитета о рекомендации не было опубликовано.', 'QXDj'),
   ('JKWu','Профильный комитет Госдумы, который возглавляет Павел Крашенинников, рекомендовал к первому чтению проект Верховного суда о доплатах судьям и работникам аппаратов судов.', 'JKWu'),
 ],
 'status_s10_e11':[
   ('SqDf','В выпуске разобрали сообщения ФСБ от 31 октября и 1 ноября о проверке сведений, полученных от правоохранительных органов США.', 'SqDf'),
   ('BBwN','Шульман сообщила о сокращении открытых данных Судебного департамента и отдельно разобрала расширение перечня сведений, которые планируется передавать ФСБ из личных кабинетов «Мосэнергосбыта».', 'BBwN'),
   ('FJIz','К моменту эфира Госдума приняла в первом чтении проект федерального бюджета и отдельный проект правительственных поправок в Налоговый кодекс.', 'vitf'),
 ],
 'status_s10__e10':[
   ('4JRi','В выпуске обсуждают кадровые перестановки в России и практику ежегодного президентского послания Федеральному собранию.', '4JRi'),
   ('derL','Обсуждаются уголовные дела и другие меры против провоенных активистов, а также положение ветеранов войны.', 'derL'),
   ('6XSj','Шульман приводит поступившие из регионов сообщения о предполагаемом принуждении к заключению военных контрактов.', '6XSj'),
 ],
}

def split_names(s):
    return [x.strip() for x in (s or '').split(';') if x.strip()]

def verified_rows(groups, episode_by_slug, anchor_map):
    out=[]
    for g in groups:
        for n,step in enumerate(g['steps'],1):
            when,stage,actors,agencies,description,*extra=step
            source=extra[1] if len(extra)>1 else g['source']
            slug,anchor=source
            assert slug in episode_by_slug and anchor in anchor_map[slug], (slug,anchor)
            actors=split_names(actors)
            agency=split_names(agencies)
            other=split_names(extra[0]) if extra else []
            out.append({
                'id':'action:'+g['key']+':'+str(n),'key':g['key'],'slug':slug,'anchor':anchor,'title':g['name'],
                'date':when,'tags':g['tags'],'stages':[stage],'actors':actors,'agency':agency,
                'actorAgency':agency if g['key']=='foreign-influence' and stage=='Внесение' else agency[:1],
                'people':list(dict.fromkeys(actors+other)),'documents':[g['doc']],
                'bill':g.get('bill'),'official':g['official'],'verified':True,'action':description,
            })
    return out

def make_notes(post, rows, related):
    notes=[]
    for n in MANUAL.get(post['slug'],[]):
        row=next((x for x in rows if x['anchor']==n[0]),None)
        if row:
            notes.append({'id':row['id'],'text':n[1],'anchor':n[2]})
    if not notes and related:
        by_key=defaultdict(list)
        for r in related: by_key[r['key']].append(r)
        for records in by_key.values():
            past=[r for r in records if r['date']<=post['date']]
            if not past:
                continue
            primary=max(past,key=lambda x:x['date'])
            actor=', '.join(primary['actors']) or ', '.join(primary['actorAgency'])
            label=f"{primary['title']}. {day(primary['date'])} · {primary['stages'][0]}"
            if actor:
                label+=f" · {actor}"
            notes.append({'id':primary['id'],'text':label+'. '+primary['action']})
    if len(notes)<3:
        sources={r['id']:r for r in rows}
        known={sources[n['id']]['anchor'] for n in notes if n['id'] in sources}
        for i,p in note_index(rows):
            if rows[i]['anchor'] in known or (rows[i]['title']==p['text'] and len(rows)>3):
                continue
            notes.append({'id':rows[i]['id'],'topic':rows[i]['title'],'text':q(cut(p['text'],290)),'anchor':p['anchor'],'excerpt':True})
            if len(notes)>=3:
                break
    return notes

def summary(post, rows, actions, notes, visible_tags, transcript_name, canonical):
    out=[f"# Саммари · {post['subtitle'] or post['title']}",'',post['title'],'',
         f"- Опубликовано {day(post['date'])} по московскому времени.",
         f"- {md_link('Стенограмма рядом',transcript_name)} · {md_link('Оригинал на Teletype',post['url'])}.",
         f"- Темы выпуска — {', '.join(visible_tags)}."]
    if post.get('alternateNumber'):
        n,m=post['alternateNumber']
        out.append(f'- В адресе Teletype указан сезон {n}, выпуск {m}. Здесь сохранена нумерация из заголовка публикации.')
    if post.get('aliases'):
        out.append('- Повторные публикации — '+', '.join(md_link('Teletype',u) for u in post['aliases'])+'.')
    if post.get('duplicateOf'):
        out.append('- Повторная публикация. В статистике портал учитывает '+md_link('основную страницу',canonical['url'])+'.')
    out+=['','## Главное в выпуске','']
    top=Counter(x['tags'][0] for x in rows if x['tags'][0]!='Другие сюжеты').most_common(2)
    if top:
        out+=['В центре новостной части — '+', '.join(k.lower() for k,v in top)+'.','']
    for item in notes:
        r=next((x for x in rows+actions if x['id']==item['id']),None)
        if not r:
            continue
        label=f"**{heading(item['topic']).rstrip('.')}.** " if item.get('topic') and len(item['topic'])<115 else ''
        out.append('- '+label+item['text']+' '+md_link('Источник',url_for(post,item.get('anchor') or (r['anchor'] if r['slug']==post['slug'] else None)))+'.')
    if actions:
        out+=['','## Действия, сверенные по документам','']
        for r in sorted(actions,key=lambda x:x['date']):
            actor=', '.join(r['actors']) or (r['actorAgency'][0] if r['actorAgency'] else '')
            label=f' — {actor}' if actor else ''
            out+=['- **'+day(r['date'])+' · '+r['stages'][0]+label+'.** '+r['action'],
                  '  '+r['documents'][0]+'. '+md_link('Документ',r['official'])+'.']
    out+=['','## Сюжеты и детали','']
    for r in rows:
        out+=['### '+heading(r['title']),'',
              '- Темы — '+', '.join(r['tags'])+'.']
        if r['people']:
            out.append('- Люди в сюжете — '+', '.join(r['people'])+'.')
        for field,label in (('parties','Упоминания партий'),('corporations','Упоминания госкорпораций')):
            if r.get(field):
                labels=[md_link(f"{hit['name']} · {hit['count']}",url_for(post,hit['anchor'] or r.get('anchor'))) for hit in r[field]]
                out.append(f'- {label} — '+', '.join(labels)+'.')
        if r['agency']:
            out.append('- Ведомства в сюжете — '+', '.join(r['agency'])+'.')
        if r['stages']:
            out.append('- Стадии и действия, упомянутые в тексте — '+', '.join(r['stages'])+'.')
        if r['documents']:
            out.append('- Названия, номера и статьи из текста — '+'; '.join(r['documents'])+'.')
        if r['dateRefs']:
            out.append('- Даты из текста — '+', '.join(x['text'] for x in r['dateRefs'])+'.')
        for l in r['links']:
            if urlparse(l['url']).scheme in ('http','https'):
                out.append('- '+md_link(l['text'] or 'Документ из стенограммы',l['url'])+'.')
        for p in r['points']:
            out.append('- По стенограмме — '+q(p['text'])+' '+md_link('К абзацу',url_for(post,p.get('anchor') or r.get('anchor')))+'.')
        out+=['',md_link('К сюжету',url_for(post,r['anchor'])), '']
    rubrics=[x['h'] for x in post['extras'] if not re.search(r'^(?:вопрос|аудио|видео|содержание)',x['h'],re.I)]
    if rubrics:
        out+=['## Другие рубрики','']+['- '+x for x in list(dict.fromkeys(rubrics))[:10]]+['']
    out+=['*Краткая выжимка и автоматическая разметка по тексту программы. Фамилии в контексте могут относиться к участникам, фигурантам или людям, которых ведущие привели в пример.*','']
    return '\n'.join(out)

def main():
    archive=load('episodes.json')
    all_posts=archive['posts']
    all_rows=load('evidence.json')
    groups=json.loads((Path(__file__).resolve().parent/'verified.json').read_text())
    post_by_slug={p['slug']:p for p in all_posts}
    rows_by_slug=defaultdict(list)
    for r in all_rows: rows_by_slug[r['slug']].append(r)
    docs={p['slug']:get_document(p) for p in all_posts}
    anchors={k:set(doc.xpath('.//@anchor')) for k,doc in docs.items()}
    actions=verified_rows(groups,post_by_slug,anchors)
    actions_by_slug=defaultdict(list)
    for a in actions: actions_by_slug[a['slug']].append(a)
    for r in all_rows:
        assert not r.get('anchor') or r['anchor'] in anchors[r['slug']],r
        assert all(not x['anchor'] or x['anchor'] in anchors[r['slug']] for x in r['points']+r.get('parties',[])+r.get('corporations',[])),r
    local=OUTPUT
    transcript_dir=local/'Стенограммы'
    portal=local/'Портал'
    portal.mkdir(parents=True,exist_ok=True)
    canonical_posts=[]
    canonical_rows=[]
    for p in all_posts:
        slug=p['slug']
        original=post_by_slug[p.get('duplicateOf',slug)]
        rows=rows_by_slug[slug]
        related=actions_by_slug[original['slug']]
        tags=[x for x,count in Counter(tag for row in rows for tag in row['tags'] if tag!='Другие сюжеты').most_common(5)]
        notes=make_notes(p,rows,related if slug==original['slug'] else [])
        folder=transcript_dir/p['date'][:4]
        folder.mkdir(parents=True,exist_ok=True)
        base=file_id(p)
        name=base+'.стенограмма.md'
        (folder/name).write_text(render_transcript(p,docs[slug]),encoding='utf-8')
        sam=summary(p,rows,related if slug==original['slug'] else [],notes,tags,name,original)
        assert '## Главное в выпуске' in sam and notes,(slug,len(rows))
        (folder/(base+'.саммари.md')).write_text(sam,encoding='utf-8')
        if p.get('duplicateOf'):
            continue
        named={k:p[k] for k in ('id','date','url','slug','subtitle','title','season','episode','aliases')}
        named['notes']=notes
        named['tags']=tags
        named['rows']=[r['id'] for r in rows]
        named['actions']=[r['id'] for r in related]
        canonical_posts.append(named)
        for r in rows:
            item={k:v for k,v in r.items() if k not in ('words','actors')}
            item['points']=[{**point,'text':cut(point['text'],420)} for point in r['points']]
            canonical_rows.append(item)
    years=sorted({p['date'][:4] for p in canonical_posts})
    counts=Counter(r['date'][:4] for r in canonical_rows)
    counts_ep=Counter(p['date'][:4] for p in canonical_posts)
    counts_action=Counter(a['date'][:4] for a in actions)
    first,last=min(p['date'] for p in canonical_posts),max(p['date'] for p in canonical_posts)
    topics=Counter(t for r in canonical_rows for t in r['tags'] if t!='Другие сюжеты')
    data={
        'pages':len(all_posts),'catalog':archive['catalogCount'],'duplicates':len(all_posts)-len(canonical_posts),
        'start':first,'end':last,'episodes':canonical_posts,'rows':canonical_rows,'actions':actions,
        'tracks':[
            {'name':'Воинский учёт и призыв','text':'Частичная мобилизация в 2022 году, электронные повестки в 2023-м и круглогодичные призывные мероприятия с 2026-го. Указ, законы и парламентские стадии видны на одной шкале.','keys':['mobilization','e-summons','draft-year']},
            {'name':'Ограничения для иноагентов','text':'В 2022 году нормы объединили в единый закон. В 2024-м отдельным законом ограничили рекламу на ресурсах иноагентов и рекламу самих ресурсов.','keys':['foreign-influence','foreign-advertising']},
            {'name':'Налоги и бюджет','text':'Налоговые поправки ввели пятиступенчатую шкалу НДФЛ и повысили НДС, а поправки 2026 года расширили возможности правительства увеличивать бюджетные расходы.','keys':['tax-2024','budget-2026','vat-2026','budget-flex']},
        ],
    }
    content=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    (portal/'data.js').write_text('window.STATUS_ARCHIVE = '+content+';\n',encoding='utf8')
    headline=', '.join(f'{tag.lower()} ({count})' for tag,count in topics.most_common(3))
    rows='\n'.join(f'| {y} | {counts_ep[y]} | {counts[y]} | {counts_action[y]} |' for y in years)
    readme=f"""# Статус · Политическая хронология

Откройте [Портал/index.html](Портал/index.html) в браузере. Для просмотра хронологии, графа упоминаний, дерева и саммари интернет не нужен. Ссылки на оригиналы и официальные документы открываются в сети.

В папке **Стенограммы** файлы разложены по годам. У стенограммы и её саммари одинаковый префикс имени. В оригинале сохранён текст, а изображения и аудио доступны по ссылкам из публикации.

## Охват

Из {archive['catalogCount']} открытых публикаций [профиля Екатерины Шульман](https://teletype.in/@eschulmann) к «Статусу» относятся **{len(all_posts)} страниц** за период с {day(first)} по {day(last)}. Три повторные публикации сохранены в архиве. В портале **{len(canonical_posts)} уникальных выпусков**, **{len(canonical_rows)} сюжетов** и **{len(actions)} действий** по {len(groups)} решениям, отобранным для сверки. Каталог проверен 18 ноября 2026 года. Даты публикаций приведены по московскому времени.

| Год | Выпуски по дате публикации | Сюжеты по дате публикации | Сверенные действия по дате события |
| --- | ---: | ---: | ---: |
{rows}

## Что видно в архиве

- По количеству сюжетов в автоматической разметке чаще всего встречаются темы {headline}. У одного сюжета может быть несколько тем. Сюжет может посвящаться нескольким решениям или возвращаться к тому же решению в разных выпусках.
- В воинском учёте можно проследить три разных изменения. Указ о частичной мобилизации вышел в сентябре 2022 года. В апреле 2023 года появились электронные повестки и единый реестр. Закон 2025 года сделал призывные мероприятия круглогодичными с 1 января 2026 года. [Указ № 647](https://publication.pravo.gov.ru/Document/View/0001202209210001), [№ 127-ФЗ](https://publication.pravo.gov.ru/Document/View/0001202304140051), [проект № 973851-8](https://sozd.duma.gov.ru/bill/973851-8).
- В регулировании иноагентов видны отдельные шаги. В 2022 году появился единый закон о контроле за деятельностью лиц под иностранным влиянием. В 2024 году отдельный акт ввёл запрет рекламы на ресурсах иноагентов и рекламы самих ресурсов. [№ 255-ФЗ](https://publication.pravo.gov.ru/document/0001202207140018), [№ 42-ФЗ](https://publication.pravo.gov.ru/document/0001202403110004).
- В налогах и бюджете карточки разделяют полномочия. Правительство внесло налоговый проект 2024 года, Госдума провела чтения, президент подписал закон. В 2026 году тот же маршрут прошли поправки, расширившие основания для увеличения расходов правительством без поправок в закон о бюджете. [№ 176-ФЗ](https://publication.pravo.gov.ru/document/0001202407120009), [№ 195-ФЗ](https://publication.pravo.gov.ru/document/0001202606260034).

## Как читать карточки

Во вкладке «Граф упоминаний» линии показывают, где два имени встретились в одном сюжете. В таблицах партий и госкорпораций считаются повторения названий, число сюжетов и число выпусков. Нажатие на имя открывает темы и связанные сюжеты.

В режиме «Публикации» датой служит размещение стенограммы. Иные даты, найденные в тексте, приведены в карточке с контекстом. В режиме «Даты решений» показываются подтверждённые даты отобранных действий. На ветках «Упоминания» фамилия обозначает присутствие в тексте. На ветках «Сверенные действия» можно увидеть, кто внёс, принял, подписал документ или произвёл назначение. Фигуранты и другие участники указаны отдельно.

Саммари используют заголовки и фрагменты стенограмм. Машинная разметка фамилий, тем и стадий проверялась выборочно. Число сюжетов в архиве описывает повестку программы. Три повторных публикации не влияют на счётчики. По всему массиву полнота дат и ролей зависит от содержания стенограмм.
"""
    (local/'Как открыть.md').write_text(readme,encoding='utf-8')
    trans=list(transcript_dir.glob('*/*.стенограмма.md'))
    sam=list(transcript_dir.glob('*/*.саммари.md'))
    prefix=lambda s: {str(x).rsplit('.',2)[0] for x in s}
    assert len(trans)==len(sam)==len(all_posts) and prefix(trans)==prefix(sam)
    assert len({r['id'] for r in canonical_rows+actions})==len(canonical_rows)+len(actions)
    assert len(data['episodes'])+data['duplicates']==data['pages']
    print(dict(pages=len(all_posts),episodes=len(canonical_posts),stories=len(canonical_rows),verified_actions=len(actions),decisions=len(groups),range=[first,last],themes=topics.most_common(5)))
    print('per year:',dict(counts_ep),dict(counts),dict(counts_action))
    print('bytes',len(content.encode()),'summaries',len(sam),'transcripts',len(trans))
if __name__=='__main__':
    main()
