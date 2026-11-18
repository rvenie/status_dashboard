from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from collections import Counter
import json, re, threading, time
import requests

ROOT = Path(__file__).resolve().parent / '.cache'
BASE = 'https://teletype.in'
PROFILE = BASE + '/@eschulmann'
HEADERS = {'Accept':'application/json','Content-Type':'application/json',
           'X-Client-Version':'Teletype.Web/4.41.27','Referer':PROFILE}
LOCAL = threading.local()

def fetch(url, **kwargs):
    if not hasattr(LOCAL, 'session'):
        LOCAL.session = requests.Session()
        LOCAL.session.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    for attempt in range(4):
        try:
            response = LOCAL.session.get(url, timeout=28, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(1 + 2 * attempt)

def state(html):
    return json.JSONDecoder().raw_decode(html.split('window.__INITIAL_STATE__=',1)[1])[0]

def save(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def get_catalog():
    profile = fetch(PROFILE).content.decode('utf-8')
    initial = state(profile)['blog_articles']['items']['1033441']
    entries = {}
    if initial.get('pinned_article'):
        entries[initial['pinned_article']['id']] = initial['pinned_article']
    cursor = 0
    while True:
        page = fetch(BASE + '/api/blogs/id/1033441/articles',
                     params={'limit':100, 'last_article':cursor}, headers=HEADERS).json()
        posts = page['articles'] or []
        if not posts:
            break
        size = len(entries)
        entries.update((post['id'], post) for post in posts)
        print('catalog', len(entries), posts[-1]['published_at'], flush=True)
        if cursor == posts[-1]['id'] or size == len(entries):
            raise RuntimeError('The public catalogue repeated a page')
        cursor = posts[-1]['id']
        time.sleep(.28)
    expected = initial['sections']['published']
    if len(entries) != expected:
        print('CATALOG COUNT MISMATCH', len(entries), expected, flush=True)
    save(ROOT / 'catalog.json', {'reported_count':expected, 'posts':list(entries.values())})
    return list(entries.values())

def download(post):
    dest = ROOT / 'raw' / (str(post['id']) + '.json')
    if dest.exists():
        return
    url = PROFILE + '/' + quote(post['uri'], safe='')
    document = state(fetch(url).content.decode('utf-8'))['articles']['items'][str(post['id'])]
    if document['id'] != post['id'] or len(document.get('text','')) < 100:
        raise ValueError(f'Mismatched or empty page {url}')
    document['url'] = url
    save(dest, document)

if __name__ == '__main__':
    ROOT.mkdir(exist_ok=True)
    posts = get_catalog()
    folder = ROOT/'raw'
    folder.mkdir(exist_ok=True)
    failures = []
    candidates = [p for p in posts if re.search(r'статус|status',p['title']+' '+p['uri'],re.I)]
    other = [p for p in posts if p not in candidates]
    print('transcript candidates',len(candidates),'remaining',len(other),flush=True)
    for p in other:
        print(p['published_at'][:10],p['title'],p['uri'],flush=True)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(download, post): post for post in candidates + other}
        for i, task in enumerate(as_completed(futures), 1):
            try:
                task.result()
            except Exception as error:
                post = futures[task]
                failures.append({'id':post['id'], 'uri':post['uri'], 'error':str(error)})
                print('FAILED', failures[-1],flush=True)
            if i % 20 == 0 or i == len(futures):
                print('downloaded',i-len(failures),'/',len(futures),flush=True)
    save(ROOT/'download_errors.json', failures)
