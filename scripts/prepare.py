from collections import defaultdict, Counter
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import json, re
from lxml import html

WORK = Path(__file__).resolve().parent / '.cache'
OUTPUT = WORK.parent.parent
SPACE = re.compile(r'\s+')
SPEAKER = re.compile(r'^(?:[А-ЯЁ]\.\s*){0,3}(?:ШУЛЬМАН|КУРНИКОВ|[А-ЯЁ][А-ЯЁ-]{4,}):\s*')
NEWS = re.compile(r'события|новости', re.I)
FILLER = re.compile(r'открытие .*сезона|книга от|реклам|^вступление$|^досочка|^книга недели|^анонс',re.I)

def clean(value):
    return SPACE.sub(' ', value or '').strip()

def decode(value):
    if isinstance(value,str):
        try:
            return value.encode('latin1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            return value
    return value

def day(iso):
    return datetime.fromisoformat(iso.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()

def file_id(post):
    return f"{post['date']}_{post['slug']}"

def get_document(post):
    raw = json.loads((WORK/'raw'/f"{post['id']}.json").read_text())
    return html.fromstring(decode(raw['text']))

def blocks(doc):
    main, extras, current = [], [], None
    zone = ''
    for node in doc:
        value = clean(node.text_content())
        tag = node.tag
        if not value and tag != 'h2':
            continue
        if tag=='h2' and value:
            zone = 'news' if re.search(r'^не новости|^события$',value,re.I) or (zone=='news' and not re.search(r'^(?:рубрика|понятие|от(?:ец|цы)|вопрос|что хотел сказать автор|по понятиям|в завершение|шульман рекомендует|литературн|аудио|видео|содержание выпуска)',value,re.I)) else 'ignore' if re.search(r'^(?:аудио|содержание выпуска|видео|текстовая)',value,re.I) else 'extra'
            if zone == 'news':
                current = {'h': '' if re.search(r'^не новости|^события$',value,re.I) else value, 'a':node.get('anchor'), 'p':[]}
                main.append(current)
            elif zone == 'extra':
                current = {'h':value, 'a':node.get('anchor'), 'p':[]}
                extras.append(current)
            continue
        if tag=='h3' and value and zone=='news' and re.search(r'^(?:от(?:ец|цы)|понятие)\s*[:—–-]|^вопросы (?:от )?слушателей',value,re.I):
            zone='extra'
        if tag=='h3' and value and zone in ('news','extra'):
            current = {'h':value, 'a':node.get('anchor'), 'p':[]}
            (main if zone=='news' else extras).append(current)
            continue
        if current is None or zone not in ('news','extra') or tag not in ('p','blockquote','ul','ol'):
            continue
        if len(value)<28 or 'НАСТОЯЩИЙ МАТЕРИАЛ' in value[:35]:
            continue
        if re.match(r'^(?:М\.\s*)?КУРНИКОВ:',value) and len(value)<105:
            continue
        if re.match(r'^\(?Прим\.',value):
            continue
        for line in re.split(r'(?<!^)(?=(?:[ЕМ]\.\s*)?(?:КУРНИКОВ|ШУЛЬМАН):)',value):
            line = SPEAKER.sub('',line).strip()
            if len(line)>25:
                current['p'].append({'a':node.get('anchor'), 't':line,
                                     'l':[(a.get('href'),clean(a.text_content())) for a in node.xpath('.//a[@href]')]})
    return [x for x in main if x['p'] and not FILLER.search(x['h'])], [x for x in extras if x['h']]

def render_inline(node):
    result = [node.text or '']
    for child in node:
        content = render_inline(child)
        if child.tag in ('strong','b'):
            content = '**' + content + '**' if content.strip() else content
        elif child.tag in ('em','i'):
            content = '*' + content + '*' if content.strip() else content
        elif child.tag == 'a' and urlparse(child.get('href','')).scheme in ('https','http'):
            content = '['+content+'](<'+child.get('href')+'>)'
        elif child.tag == 'br':
            content = '  \n'
        result.extend((content,child.tail or ''))
    return ''.join(result)

def render_transcript(post, doc):
    pieces = [f"# {post['title']}",f"Опубликовано на Teletype {post['date']} · [Оригинал]({post['url']})"]
    for node in doc:
        content = render_inline(node).strip()
        tag=node.tag
        if tag in ('contents', 'hr'):
            continue
        if tag in ('image','soundcloud','youtube','video','iframe'):
            url = node.get('src') or node.get('url') or node.get('href')
            if url and urlparse(url).scheme in ('https','http'):
                label = 'Изображение в оригинале' if tag=='image' else 'Медиа в оригинале'
                pieces.append(f'[{label}](<{url}>)')
            if content:
                pieces.append(content)
            continue
        if not content:
            continue
        if tag in ('ol','ul'):
            pieces.append('\n'.join(f"- {render_inline(x).strip()}" for x in node if clean(x.text_content())))
        elif tag=='blockquote':
            pieces.append('\n'.join('> '+line for line in content.splitlines()))
        else:
            prefix = '## ' if tag in ('h1','h2') else '### ' if tag in ('h3','h4') else ''
            pieces.append(prefix+content)
    return '\n\n'.join(pieces)+'\n'

def collect():
    catalog = json.loads((WORK/'catalog.json').read_text())
    assert len(catalog['posts'])==catalog['reported_count']
    assert not json.loads((WORK/'download_errors.json').read_text())
    results, categories = [], defaultdict(list)
    for page in catalog['posts']:
        doc = get_document(page)
        title, slug = clean(page['title']), page['uri']
        if not re.search(r'\bстатус\b|^status_',title+' '+slug,re.I) and not re.search(r'^status_',slug,re.I):
            continue
        main, extras = blocks(doc)
        if not main:
            raise ValueError(f'No editorial segments identified: {slug}')
        cut = clean(decode(page.get('cut_text')))
        pid = re.search(r'сезон\s*(\d+).*?выпуск\s*(\d+)',title,re.I)
        uid = re.search(r's(\d+)_+e?_?(\d+)',slug,re.I) if slug.startswith('status') else None
        tag_title = tuple(map(int,pid.groups())) if pid else None
        tag_uri = tuple(map(int,uid.groups())) if uid else None
        identifier = tag_title or tag_uri
        post = {'id':page['id'],'published':page['published_at'],'date':day(page['published_at']),
                'title':title,'subtitle':cut,'slug':slug,'url':'https://teletype.in/@eschulmann/'+slug,
                'season':identifier[0] if identifier else None,'episode':identifier[1] if identifier else None,
                'alternateNumber':list(tag_uri) if tag_uri and tag_title and tag_uri!=tag_title else None,
                'sections':main, 'extras':[{'h':e['h'],'a':e['a']} for e in extras],
                'characters':len(clean(doc.text_content())), 'aliases':[],
                'links':list(dict.fromkeys(a.get('href') for a in doc.xpath('.//a[@href]')))}
        if re.fullmatch(r'Пост .*',title) and identifier:
            post['originalTitle']=title
            post['title']=f'Программа «Статус» сезон {identifier[0]}, выпуск {identifier[1]}'
        results.append(post)
        categories[(post['date'],cut)].append((post,clean(doc.text_content())))
    for group in categories.values():
        if len(group)<2:
            continue
        group.sort(key=lambda row:(not row[0]['slug'].startswith('status'), -row[0]['characters']))
        selected,v=group[0]
        for other,w in group[1:]:
            if min(len(v),len(w))/max(len(v),len(w))>.97 and (
                v==w or SequenceMatcher(None,v.split(),w.split(),autojunk=False).ratio()>.98
            ):
                other['duplicateOf']=selected['slug']
                selected['aliases'].append(other['url'])
    return {'posts':results,'catalogCount':catalog['reported_count']}

if __name__=='__main__':
    data=collect()
    (WORK/'episodes.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    print('pages', len(data['posts']), 'duplicates',[(x['slug'],x['duplicateOf']) for x in data['posts'] if 'duplicateOf' in x])
    print('sections',Counter(len(x['sections']) for x in data['posts']))
    print('characters',sum(x['characters'] for x in data['posts']))
    for x in data['posts']:
        if (not x['sections'][0]['h'] and len(x['sections'][0]['p'])>5) or len(x['sections'])<3:
            print(x['slug'],x['date'],x['subtitle'],[(s['h'],len(s['p'])) for s in x['sections'][:3]])
