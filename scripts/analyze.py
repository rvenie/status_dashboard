from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path
import re, json
from natasha import Doc, Segmenter, NewsEmbedding, NewsNERTagger
from pymorphy3 import MorphAnalyzer
from razdel import sentenize
from prepare import WORK, clean

TOPICS = {
 'Законы и регулирование':r'законопроект|федеральн\w+ закон|(?:перв|втор|треть)\w+ чтени|поправк|законодательств|кодекс|указ|постановлени|реестр|регулировани',
 'Суды и преследование':r'приговор|уголовн\w+ дел|преследовани|репресси|арест|суд(?:ебн|ь[ияе]|ом|у|\b)|прокуратур|срок\w* лишени|штраф|обыск|колони|сизо|экстремис|иноагент|иностранн\w+ агент',
 'Выборы и партии':r'выбор\w*|выборн|кандидат|голосовани|избирательн|электоральн|мандат|референдум|предвыбор|(?:^|\W)цик\b|праймериз',
 'Кадры и институты':r'отставк|перестанов|назначени|назначил|переназнач|губернатор|сенатор|структур\w* правительств|перестро\w+ дум|формировани\w* правительств|состав правительств|комитет\w* госдум|вице-премьер',
 'Экономика и бюджет':r'бюджет|налог|инфляци|тариф|дефицит|ставк|рубл|экономик|экономическ|цен(?:ы|а|ам|ах)\b|санкци|национализаци|пошлин|конфискаци|собственност|госзаказ|госдолг',
 'Война и мобилизация':r'мобилизац|воинск\w+ учет|повестк|военком|призыв|контрактни|(?:^|\W)сво\b|боев\w+ действи|войн\w*|военн\w+ операци|дрон|беспилот|обстрел|военн\w+ служб',
 'Права и общество':r'правозащит|гражданств|дискриминаци|образовани|медицин|мигрант|миграци|гражданск\w+ прав|права человек|пенси|пособи|социальн|лгбт|здравоохранени|религи',
 'Интернет и медиа':r'блокировк|цензур|роскомнадзор|интернет|(?:^|\W)сми\b|мессенджер|телеграм|(?:^|\W)telegram|(?:^|\W)vpn|доступ\w* к сайт|запрет\w* на публикаци|шпионаж|цифров',
 'Международная политика':r'дипломати|переговор|международн|инаугурац|форум|внешн\w+ политик|делегаци|соглашени\w* с |ес\b|нато|трамп|сша|украин|германи|франци|польш|казахстан|беларус|иран|венгри|венесуэл|серби|грузи|европейс',
 'Опросы и статистика':r'опрос|рейтинг|статистик|общественн\w+ мнени|социолог|демограф|левад\w+|вциом|исследовани',
}
TOPICS = {k:re.compile(v,re.I) for k,v in TOPICS.items()}
AGENCIES = {
 'Госдума':r'(?:Государственн[а-яё]+ Дум[а-яё]+|Госдум[а-яё]+|ГД)',
 'Совет Федерации':r'Совет(?:а|у|ом|е)? Федераци[ия]|Совфед(?:а|ом|у|е)?',
 'Правительство РФ':r'правительств[а-яё]+(?: РФ| Росси[ия])?|Белый дом РФ',
 'Президент РФ':r'(?:президент(?:а|у|ом|е)? (?:РФ|Росси[ия])|Владимир[а-яё]* Путин[а-яё]*|Путин(?:а|у|ым|е)?)',
 'Администрация президента':r'администраци[а-яё]+ президент[а-яё]*',
 'Минфин':r'Минфин(?:а|у|ом|е)?|министерств[а-яё]+ финансов',
 'Минобороны':r'Миноборон[а-яё]+|министерств[а-яё]+ обороны',
 'Минюст':r'Минюст(?:а|у|ом|е)?|министерств[а-яё]+ юстиции',
 'МВД':r'МВД|министерств[а-яё]+ внутренних дел',
 'ФСБ':r'ФСБ|федеральн[а-яё]+ служб[а-яё]+ безопасности',
 'Роскомнадзор':r'Роскомнадзор(?:а|у|ом|е)?',
 'Росгвардия':r'Росгварди[а-яё]+',
 'ЦИК':r'ЦИК(?:а|у|ом|е)?|Центральн[а-яё]+ избирательн[а-яё]+ комисси[а-яё]+',
 'Верховный суд РФ':r'Верховн[а-яё]+ суд(?:а|у|ом|е)?(?: РФ| Росси[ия])?',
 'Конституционный суд РФ':r'Конституционн[а-яё]+ суд(?:а|у|ом|е)?(?: РФ| Росси[ия])?',
 'Генпрокуратура':r'Генпрокуратур[а-яё]+|Генеральн[а-яё]+ прокуратур[а-яё]+',
 'Следственный комитет':r'Следственн[а-яё]+ комитет(?:а|у|ом|е)?|СК РФ',
 'ФСИН':r'ФСИН',
 'Банк России':r'(?:Центробанк|Банк Росси[ия]|Центральный банк РФ|ЦБ)(?:а|у|ом|е)?',
 'Минцифры':r'Минцифр[а-яё]+',
 'Московская мэрия':r'Московск[а-яё]+ мэри[а-яё]+|мэри[а-яё]+ Москвы',
 'Генштаб':r'Генштаб(?:а|у|ом|е)?|Генеральн[а-яё]+ штаб(?:а|у|ом|е)?',
}
AGENCIES = {k:re.compile(r'(?<![\w-])(?:'+v+r')(?![\w-])',re.I) for k,v in AGENCIES.items()}
GRAPH_PUBLIC_BODIES = {
    **AGENCIES,
    'Президент РФ':re.compile(r'\bпрезидент(?:а|у|ом|е)?\s+(?:российской\s+федерации|росси[ия]|рф)\b',re.I),
    'Правительство РФ':re.compile(r'\bправительств[а-яё]+\s+(?:российской\s+федерации|росси[ия]|рф|мишустина)\b',re.I),
}
PRESIDENTIAL_OFFICE = re.compile(r'\bадминистраци[а-яё]+\s+президент(?:а|у|ом|е)?\s+(?:российской\s+федерации|росси[ия]|рф)\b',re.I)

KNOWN = {
 'Владимир Путин':r'Путин(?:а|у|ом|ым|е)?',
 'Михаил Мишустин':r'Мишустин(?:а|у|ым|е)?',
 'Вячеслав Володин':r'Володин(?:а|у|ым|е)?',
 'Валентина Матвиенко':r'Матвиенко',
 'Дмитрий Медведев':r'Медведев(?:а|у|ым|е)?',
 'Сергей Собянин':r'Собянин(?:а|у|ым|е)?',
 'Сергей Шойгу':r'Шойгу',
 'Андрей Белоусов':r'Белоусов(?:а|у|ым|е)?',
 'Дмитрий Песков':r'Песков(?:а|у|ым|е)?',
 'Павел Крашенинников':r'Крашенинников(?:а|у|ым|е)?',
 'Андрей Клишас':r'Клишас(?:а|у|ом|е)?',
 'Андрей Картаполов':r'Картаполов(?:а|у|ым|е)?',
 'Александр Хинштейн':r'Хинштейн(?:а|у|ом|е)?',
 'Василий Пискарёв':r'Пискар[её]в(?:а|у|ым|е)?',
 'Александр Бастрыкин':r'Бастрыкин(?:а|у|ым|е)?',
 'Игорь Краснов':r'Краснов(?:а|у|ым|е)?',
 'Александр Бортников':r'Бортников(?:а|у|ым|е)?',
 'Виктор Золотов':r'Золотов(?:а|у|ым|е)?',
 'Элла Памфилова':r'Памфилов(?:а|ой|у|е)',
 'Эльвира Набиуллина':r'Набиуллин(?:а|ой|у|е)',
 'Антон Силуанов':r'Силуанов(?:а|у|ым|е)?',
 'Сергей Лавров':r'Лавров(?:а|у|ым|е)?',
 'Николай Патрушев':r'Патрушев(?:а|у|ым|е)?',
 'Сергей Кириенко':r'Кириенко',
 'Рамзан Кадыров':r'Кадыров(?:а|у|ым|е)?',
 'Алексей Навальный':r'Навальн(?:ый|ого|ому|ым|ом)',
 'Евгений Пригожин':r'Пригожин(?:а|у|ым|е)?',
 'Мария Львова-Белова':r'Львов[а-яё]*[-‑–]Белов[а-яё]*',
 'Татьяна Голикова':r'Голиков(?:а|ой|у|е)',
 'Антон Котяков':r'Котяков(?:а|у|ым|е)?',
 'Владимир Колокольцев':r'Колокольцев(?:а|у|ым|е)?',
 'Владимир Мединский':r'Мединск(?:ий|ого|ому|им|ом)',
 'Вячеслав Гладков':r'Гладков(?:а|у|ым|е)?',
 'Константин Чуйченко':r'Чуйченко',
 'Сергей Боярский':r'Боярск(?:ий|ого|ому|им|ом)',
 'Андрей Красов':r'Красов(?:а|у|ым|е)?',
 'Андрей Макаров':r'Андре[йяюем]+ (?:Михайлович[а-яё]* )?Макаров[а-яё]*',
 'Андрей Климов':r'Андре[йяюем]+ (?:Аркадьевич[а-яё]* )?Климов[а-яё]*',
 'Дмитрий Козак':r'Козак(?:а|у|ом|е)?',
 'Александр Гуцан':r'Гуцан(?:а|у|ом|е)?',
 'Юлия Навальная':r'Навальн(?:ая|ой|ую)',
 'Екатерина Дунцова':r'Дунцов(?:а|ой|у|е)',
 'Анна Кузнецова':r'Анн[а-яё]+ (?:Юрьевн[а-яё]+ )?Кузнецов[а-яё]+',
 'Антон Вайно':r'Вайно',
 'Сергей Чемезов':r'Чемезов(?:а|у|ым|е)?',
 'Алексей Дюмин':r'Дюмин(?:а|у|ым|е)?',
 'Дмитрий Рогозин':r'Рогозин(?:а|у|ым|е)?',
 'Сергей Миронов':r'Миронов(?:а|у|ым|е)?',
 'Борис Надеждин':r'Надеждин(?:а|у|ым|е)?',
 'Дональд Трамп':r'Трамп(?:а|у|ом|е)?',
 'Владимир Зеленский':r'Зеленск(?:ий|ого|ому|им|ом)',
 'Валерий Герасимов':r'Герасимов(?:а|у|ым|е)?',
 'Ольга Баталина':r'Баталин(?:а|ой|у|е)',
 'Ирина Яровая':r'Яров(?:ая|ой|ую)',
 'Елена Мизулина':r'Елен[а-яё]* (?:Борисовн[а-яё]* )?Мизулин[а-яё]+',
 'Екатерина Мизулина':r'Екатерин[а-яё]* (?:Михайловн[а-яё]* )?Мизулин[а-яё]+',
}
KNOWN = {k:re.compile(r'(?<![\w-])(?:'+v+r')(?![\w-])') for k,v in KNOWN.items()}
KNOWN_NAME = {k.split()[-1].casefold(): k for k in KNOWN if k.split()[-1]!='Мизулина'}
NONACTORS = {'Курников','Шульман','Александрович','Владимирович','Владиленович','Михайлович','Михайловна'}
REVIEWED_NAMES = {
    'Эльвира Аиткулов':'Эльвира Аиткулова','Исаев Андрей':'Андрей Исаев',
    'Ольга Баталов':'Ольга Баталина','Иванов Сергей Борисович':'Сергей Иванов',
    'Генрих Бёлля':'Генрих Бёлль','Александр Гениса':'Александр Генис',
    'Александр Кынева':'Александр Кынев','Наталья Комаров':'Наталья Комарова',
    'Клаудия Голдин Клаудия':'Клаудия Голдин','Мартин Лернер Лернер':'Мартин Лернер',
    'Ольга Миримский':'Ольга Миримская','Лида Мониава':'Лидия Мониава',
    'Лидий Мониава':'Лидия Мониава','Алла Пугачёв':'Алла Пугачёва',
    'Ксения Петров':'Ксения Петрова','Ирина Подносов':'Ирина Подносова',
    'Ксения Разуваев':'Ксения Разуваева','Илоно Маск':'Илон Маск',
    'Аня Журавлёв':'Анна Журавлёва','Тимур Иванов Обратить':'Тимур Иванов',
    'Юлий Цветков':'Юлия Цветкова','Юлия Цветков':'Юлия Цветкова',
    'Владимир Кара-мурза':'Владимир Кара-Мурза',
    'Дарья Дугин Платонов':'Дарья Дугина',
    'Кадыров Вот':'Рамзан Кадыров','Цаликов Помнить':'Руслан Цаликов',
    'Мацоцкий Потом':None,'Перерассадка Традиционно':None,'Алёхин Это':None,
    'Игорь Чуять':None,'Анатолий Картопол':None,'Елена Подносов':None,
}

STAGES = {
 'Внесение':r'\b(?:внес[её]н[а-яё]*|вн[её]с(?:ла|ли)?|вноси(?:т|ла|ли)|зарегистрирова[а-яё]+)\b',
 'Первое чтение':r'\bперв[а-яё]+ чтени[а-яё]+',
 'Второе чтение':r'\bвтор[а-яё]+ чтени[а-яё]+',
 'Третье чтение':r'\bтрет[а-яёь]+ чтени[а-яё]+',
 'Одобрение':r'\b(?:одобри[а-яё]+|одобр[её]н[а-яё]*|утвердил[а-яё]*|утвержд[её]н[а-яё]*)\b',
 'Принятие':r'\b(?:приня[лт][а-яё]*)\b',
 'Подписание':r'\b(?:подписа[лн][а-яё]*)\b',
 'Вступление в силу':r'\b(?:вступи[а-яё]+|вступа[а-яё]+|вош[её]л) в силу\b',
 'Обсуждение или предложение':r'\b(?:предлож[а-яё]+|предлага[а-яё]+|инициатив[а-яё]+|планиру[а-яё]+|проект[а-яё]*)\b',
}
STAGES = {k:re.compile(v,re.I) for k,v in STAGES.items()}
LEGAL = re.compile(r'\b(?:закон(?:опроект)?[а-яё]*|указ[а-яё]*|постановлени[а-яё]*|кодекс[а-яё]*|поправк[а-яё]*|приказ[а-яё]*)\b',re.I)
LEGAL_TITLE = re.compile(r'(?:федеральн[а-яё]+ )?(?:закон(?:опроект)?|указ|постановлени|приказ)[а-яё]*(?: (?:РФ|России|президента|правительства|Минюста|МВД|Российской Федерации)){0,3}(?: от [^,«»]{5,35})?(?: №\s*[\w-]+)?\s*[«"]((?:О|Об|О внесении|Об утверждении|Конституция|Кодекс)\b[^»"\n]{8,245})[»"]',re.I)
LEGAL_NUM = re.compile(r'(?:№\s*)?\b\d{1,4}[-‑–](?:ФКЗ|ФЗ)\b|№\s*\d{4,8}-\d{1,2}\b|(?:законопроект[а-яё]*|проект[а-яё]* закона)\s+(?:№\s*)?\d{4,8}-\d{1,2}\b|(?:указ|постановлени|приказ)[а-яё]*(?: (?:президента|правительства|Минюста|РФ|России|Российской Федерации)){0,3}\s+№\s*\d{1,5}\b',re.I)
LEGAL_LINK = re.compile(r'(?:sozd\.duma\.gov\.ru/(?:bill|oz)|(?:publication\.)?pravo\.gov\.ru|kremlin\.ru/acts|regulation\.gov\.ru|consultant\.ru/document/)',re.I)
MONTHS = dict(zip('января февраля марта апреля мая июня июля августа сентября октября ноября декабря'.split(), range(1,13)))
DATE_RU = re.compile(r'\b([0-3]?\d)[ -]+('+'|'.join(MONTHS)+r')(?:[ -]+(\d{4})(?:\s*(?:г\.|года))?)?\b',re.I)
DATE_NUM = re.compile(r'\b([0-3]?\d)\.([01]?\d)\.(20\d{2})\b')
STRONG = re.compile(r'\b(?:вн[её]с[а-яё]*|одобри[а-яё]+|подписа[а-яё]+|приня[лт][а-яё]*|вступ[иа][а-яё]+ в силу|изда[лт][а-яё]*|назнач[иье][а-яё]+|отмен[иеё][а-яё]+|утверди[а-яё]+|призн[а-яё]+|возбуд[иае][а-яё]+|запрет[иае][а-яё]+|разреш[иае][а-яё]+|ввел[а-яё]*|вв[её]л[а-яё]*|введ[её][а-яё]*|отправ[иа][а-яё]+|проголосова[а-яё]+|задержа[а-яё]+|приговор[ие][а-яё]+|постановил[а-яё]*|объяви[а-яё]+|предложи[а-яё]+|уволи[а-яё]+|увеличи[а-яё]+|повыс[иа][а-яё]+|сниз[иа][а-яё]+)\b',re.I)
NONFACT = re.compile(r'\b(?:якобы|предполож\w*|вероятно|возможно|кажется|вроде|по слухам|я думаю|мы думаем|неясно|если б[ыу]|гипотетич\w*|не факт|может быть)\b',re.I)
FUTURE = re.compile(r'\b(?:внес[её]т|подпиш[её]т|прим[её]т|будет|будут|планиру[а-яё]+|ожида[а-яё]+)\b',re.I)
QUOTE = re.compile(r'[«»“”"]')
BAD_START = re.compile(r'^(?:ну\b|да\b|нет\b|так вот\b|вообще\b|и вот\b|это\b|он\b|она\b|они\b|мы\b|я\b|кто\b|зачем\b|как\b|а вот\b|во-первых\b|напомн\w*)',re.I)
STOP_HEAD = re.compile(r'^не новости,?\s*но события$|^события$|^вступительн|^сегодня в программ',re.I)
ANY_WORD = re.compile(r'[А-ЯЁа-яё][А-ЯЁа-яё-]*')
SEG = Segmenter()
NER = NewsNERTagger(NewsEmbedding())
MORPH = MorphAnalyzer()

@lru_cache(maxsize=18000)
def normal(word):
    results = MORPH.parse(word)
    preferred = [p for p in results if 'Name' in p.tag or 'Surn' in p.tag or 'Patr' in p.tag]
    return (preferred or results)[0].normal_form.capitalize()

def person_key(raw):
    words = ANY_WORD.findall(raw)
    if not words or any(w.capitalize() in NONACTORS for w in words):
        return None
    for person, matcher in KNOWN.items():
        if matcher.search(raw):
            return person
    words = [normal(x) for x in words if len(x)>1]
    if not words:
        return None
    if len(words)==1:
        return None
    if len(words)>2 and words[1].endswith(('вич','вна','ич','ична','оглы')):
        words.pop(1)
    if len(words)>=2 and (any(len(w)<3 for w in words) or (len(words)==2 and words[-1].endswith(('ович','евич','овна','евна')))):
        return None
    if len(words)==2 and words[1].lower() in ('россия','госдума','российский','собрание','область'):
        return None
    if len(words)==2 and all(MORPH.word_is_known(w.lower()) for w in words):
        # A recognised first name reduces newspaper, organisation and place false positives.
        if not any('Name' in p.tag for p in MORPH.parse(words[0])):
            if any('Name' in p.tag for p in MORPH.parse(words[1])):
                words = words[::-1]
            else:
                return None
    key=' '.join(words[:3])
    return REVIEWED_NAMES.get(key,key)

def people(text):
    found = {k for k,rx in KNOWN.items() if rx.search(text)}
    if len(text)>20:
        doc=Doc(text)
        doc.segment(SEG)
        doc.tag_ner(NER)
        for span in doc.spans:
            if span.type=='PER':
                k=person_key(span.text)
                if k:
                    found.add(k)
    return sorted(found,key=lambda x:x.split()[-1])

def dates(text):
    values = []
    for pattern in (DATE_RU,DATE_NUM):
        for m in pattern.finditer(text):
            d, mo, y = m.groups()
            month = MONTHS.get(mo.lower()) if pattern is DATE_RU else int(mo)
            try:
                now=date(int(y or 2000),month,int(d))
            except (TypeError,ValueError):
                continue
            values.append({'text':m[0],'iso':now.isoformat() if y else None})
    return list({x['text']:x for x in values}.values())

def flags(text, heading=False):
    result=[]
    if not LEGAL.search(text) and not (STAGES['Вступление в силу'].search(text) or any(
        STAGES[k].search(text) for k in ('Первое чтение','Второе чтение','Третье чтение')
    )):
        return result
    lower=text.lower()
    if re.search(r'рекоменд[а-яё]* (?:к|приня|рассмотр)|ид[её]т к первому чтению|готов[а-яё]* к [а-яё]+ чтению',lower):
        return ['Рекомендация комитета']
    unconfirmed=NONFACT.search(text) or '?' in text
    if unconfirmed:
        return result
    if FUTURE.search(text) and not STRONG.search(text):
        return ['Обсуждение или предложение']
    negated = bool(re.search(r'\bне\s+(?:подписа|приня|одобри|вн[её]с|вступи|прош[её]л)',lower))
    if negated:
        return []
    if re.search(r'\b(?:под ним|под проектом|под законопроектом|под поправками)\b',lower):
        lower=lower.replace('подпис','распис')
        text=lower
    for stage, regex in STAGES.items():
        if stage in ('Первое чтение','Второе чтение','Третье чтение'):
            if regex.search(text) and re.search(r'\b(?:рекоменд|готов|планир|предсто|буд[еу]т|намеч|назнач)', lower):
                continue
            if regex.search(text) and not re.search(r'\b(?:приня|одобри|прош|проголос|рассмотре|провод)[а-яё]*', lower):
                continue
        elif stage not in ('Обсуждение или предложение','Вступление в силу') and not LEGAL.search(text):
            continue
        if regex.search(text):
            result.append(stage)
    if any('чтение' in s for s in result) and 'Принятие' in result:
        result.remove('Принятие')
    if len(result)>1 and 'Обсуждение или предложение' in result:
        result.remove('Обсуждение или предложение')
    return result

def score(text, key):
    n=len(text)
    if n<38 or n>720 or '?' in text or 'Прим.,' in text or re.search(r'[\w.-]+\.(?:com|ru|org)/',' '+text):
        return -20
    governing = sum(bool(v.search(text)) for v in AGENCIES.values())
    surnames = sum(bool(v.search(text)) for v in KNOWN.values())
    repetition = len(set(ANY_WORD.findall(text.casefold())) & key)
    return (3.4*bool(STRONG.search(text)) + 2.6*bool(LEGAL_TITLE.search(text) or LEGAL_NUM.search(text))
            + 1.2*bool(LEGAL.search(text)) + 1.6*min(2,governing+surnames)
            + 1.05*min(repetition,6) + 1.5*bool(DATE_RU.search(text) or DATE_NUM.search(text))
            - 2.3*bool(BAD_START.search(text)) - 2.9*bool(NONFACT.search(text)) - max(0,n-260)/220)


PARTY_NAMES = {
    'Единая Россия': r'един(?:ая|ой|ую)\s+росси(?:я|и|ю|ей)|единоросс[а-яё]*',
    'КПРФ': r'КПРФ|коммунистическ[а-яё]+\s+парти[а-яё]+\s+(?:российской\s+федерации|рф)',
    'ЛДПР': r'ЛДПР|либерально[-–]демократическ[а-яё]+\s+парти[а-яё]+\s+россии|лдпровц[а-яё]*',
    'Справедливая Россия': r'справедлив(?:ая|ой|ую)\s+росси(?:я|и|ю|ей)(?:\s+[—–-]\s*патриоты\s*[—–-]?)?(?:\s*(?:[—–-]\s*)?за\s+правду)?|СРЗП',
    'Новые люди': r'[«„“"]\s*нов(?:ые|ых|ым|ыми)\s+люд(?:и|ей|ям|ьми)\s*[»“”"]|(?:парти[а-яё]+|фракци[а-яё]+)\s+нов(?:ые|ых|ым|ыми)\s+люд(?:и|ей|ям|ьми)',
    'Яблоко': r'[«„“"]\s*яблок(?:о|а|у|ом|е)\s*[»“”"]|(?:парти[а-яё]+|фракци[а-яё]+)\s+яблок(?:о|а|у|ом|е)|яблочник[а-яё]*',
    'Партия роста': r'парти[яиюе]\s+роста|партией\s+роста',
    'Партия пенсионеров': r'(?:российск[а-яё]+\s+)?парти[а-яё]+\s+пенсионеров(?:\s+за\s+социальную\s+справедливость)?|РППСС',
    'Коммунисты России': r'коммунист(?:ы|ов|ам|ами|ах)\s+россии',
    'Гражданская инициатива': r'гражданск(?:ая|ой|ую)\s+инициатив(?:а|ы|у|е|ой)',
    'Гражданская платформа': r'гражданск(?:ая|ой|ую)\s+платформ(?:а|ы|у|е|ой)',
    'Родина': r'(?:парти[а-яё]+|фракци[а-яё]+)\s+[«„“"]?родин(?:а|ы|у|е|ой)|[«„“"]родин(?:а|ы|у|е|ой)[»“”"](?=\s+(?:—\s*)?(?:парти|фракци))',
    'Зелёные': r'российск[а-яё]+\s+экологическ[а-яё]+\s+парти[а-яё]+\s+[«„“"]?\s*зел[её]н(?:ые|ых)[»“”"]?|парти[а-яё]+\s+[«„“"]\s*зел[её]н(?:ые|ых)\s*[»“”"]',
    'Зелёная альтернатива': r'зел[её]н(?:ая|ой|ую)\s+альтернатив(?:а|ы|у|е|ой)',
    'ПАРНАС': r'(?-i:ПАРНАС)|парти[а-яё]+\s+народной\s+свободы',
    'Российская партия свободы и справедливости': r'российск[а-яё]+\s+парти[а-яё]+\s+свободы\s+и\s+справедливости|РПСС',
    'Партия дела': r'(?-i:Парти[яиюе]\s+дела|[Пп]арти[яиюе]\s+[«„“"]Дела[»“”"])',
    'Партия прямой демократии': r'парти[а-яё]+\s+прямой\s+демократии',
    'Партия За правду': r'парти[а-яё]+\s+[«„“"]за\s+правду[»“”"]',
}
# Require party context for names that can also be ordinary phrases.
for party in ('Гражданская инициатива','Гражданская платформа','Зелёная альтернатива'):
    alias=PARTY_NAMES[party]
    PARTY_NAMES[party]=rf'(?:[«„“"]\s*(?:{alias})\s*[»“”"]|(?:парти[а-яё]+|фракци[а-яё]+)\s+(?:{alias}))'
PARTY_NAMES['Единая Россия']+=r'|[«„“"](?-i:ЕР)[»“”"]|(?:парти[а-яё]+|фракци[а-яё]+)\s+(?-i:ЕР)'
CORPORATION_NAMES = {
    'Ростех': r'ростех(?:а|у|ом|е)?|ростехнологи(?:и|й|ям|ями|ях)|rostec(?:h)?',
    'Росатом': r'росатом(?:а|у|ом|е)?|rosatom',
    'Роскосмос': r'роскосмос(?:а|у|ом|е)?|roscosmos',
    'ВЭБ.РФ': r'вэб(?:[.\s]+рф\b|(?:а|у|ом|е)?\b)|внешэкономбанк(?:а|у|ом|е)?|veb\.rf',
    'Агентство по страхованию вкладов': r'агентств[а-яё]+\s+по\s+страхованию\s+вкладов|(?-i:АСВ)',
    'Фонд содействия реформированию ЖКХ': r'фонд(?:а|у|ом|е)?\s+содействия\s+реформированию\s+(?:жкх|жилищно[-–]коммунального\s+хозяйства)|фонд(?:а|у|ом|е)?\s+жкх',
}

def compile_names(names):
    return {name:re.compile(r'(?<![\w-])(?:'+pattern+r')(?![\w-])',re.I) for name,pattern in names.items()}

PARTY_PATTERNS=compile_names(PARTY_NAMES)
CORPORATION_PATTERNS=compile_names(CORPORATION_NAMES)

def entity_hits(paragraphs, patterns):
    found={}
    for paragraph in paragraphs:
        text=paragraph['t']
        for name, pattern in patterns.items():
            matches=list(pattern.finditer(text))
            if not matches:
                continue
            if name not in found:
                start=matches[0].start()
                sentence=next((s.text for s in sentenize(text) if s.start<=start<s.stop),text)
                if len(sentence)>300:
                    start_in_sentence=max(0,sentence.casefold().find(matches[0][0].casefold()))
                    left=max(0,start_in_sentence-90)
                    right=min(len(sentence),left+280)
                    sentence=('…' if left else '')+sentence[left:right]+('…' if right<len(sentence) else '')
                found[name]={'name':name,'count':0,'anchor':paragraph['a'],'text':sentence}
            found[name]['count']+=len(matches)
    return sorted(found.values(),key=lambda x:(-x['count'],x['name']))


def glean(section, post, index):
    heading=clean(section['h'])
    if STOP_HEAD.search(heading):
        heading=''
    tokens={w for w in ANY_WORD.findall(heading.casefold().replace('ё','е')) if len(w)>3}
    alltext=' '.join(p['t'] for p in section['p'])
    sentences=[]
    for idx, paragraph in enumerate(section['p']):
        for sentence in sentenize(paragraph['t']):
            txt=clean(sentence.text)
            if txt[0:1].islower() and not txt.startswith('iPhone'):
                continue
            rated=score(txt,tokens)
            if rated>=-1:
                sentences.append((rated - min(idx,25)*.10,idx,txt,paragraph['a']))
    ranked=sorted(sentences,key=lambda x:x[0],reverse=True)
    chosen=[]
    for row in ranked:
        _, i, s, a=row
        if len(chosen)>=3:
            break
        if len(chosen)>=1 and row[0]<1.5:
            break
        if len(chosen)>=2 and row[0]<4.5:
            break
        if (any(r[1]==i for r in chosen) and len({r[1] for r in chosen}) < 2 and len(ranked)>4):
            continue
        if not any(s in r[2] or r[2] in s for r in chosen):
            chosen.append(row)
    if not chosen and ranked:
        chosen=[ranked[0]]
    if not heading:
        if chosen:
            heading=chosen[0][2]
            if len(heading)>115:
                heading=heading[:113].rsplit(' ',1)[0]+'…'
        else:
            heading=post['subtitle'] or 'События выпуска'
    points=[{'text':s,'anchor':a} for _,_,s,a in sorted(chosen,key=lambda x:x[1])]
    evidence=heading+' '+ ' '.join(x['text'] for x in points)
    persons=sorted(set(people(evidence)) | {k for k,rx in KNOWN.items() if rx.search(alltext)},
                   key=lambda x:x.split()[-1])
    persons=[k for k in persons if k not in ('Владимир Владимирович','Сергей Владиленович')]
    agency=[k for k,rx in AGENCIES.items() if rx.search(evidence)]
    mention_text=heading+' '+alltext
    without_office=PRESIDENTIAL_OFFICE.sub(' ',mention_text)
    mention_agencies=[k for k,rx in GRAPH_PUBLIC_BODIES.items()
                      if rx.search(without_office if k=='Президент РФ' else mention_text)]
    refs=dates(evidence)
    docs=list(dict.fromkeys([m[1] for m in LEGAL_TITLE.finditer(alltext+' '+heading)]
                            +[clean(m[0]) for m in LEGAL_NUM.finditer(alltext+' '+heading)]))
    quoted=re.findall(r'(?:закон(?:опроект)?[а-яё]*|кодекс[а-яё]*|указ[а-яё]*)[^«»\n.;]{0,65}«((?:О |Об |Внесение изменений в |Внести изменения в )[^«»]{8,220})»',alltext+' '+heading,re.I)
    article=[]
    for pattern in (r'(?:стать[яиюе]|ст\.)\s*\d{1,3}(?:\.\d{1,2})?(?:\s+част[ьи]\s+\d+)?\s*(?:УК|КоАП|УПК)(?:\s+РФ)?\b',r'(?:УК|КоАП|УПК)(?:\s+РФ)?\s*[,]?\s*(?:стать[яиюе]|ст\.)\s*\d{1,3}(?:\.\d{1,2})?'):
        article.extend(x[0] for x in re.finditer(pattern,alltext+' '+heading,re.I))
    docs=list(dict.fromkeys(clean(x) for x in docs+quoted+article if x))[:9]
    links=list(dict.fromkeys((url, label) for p in section['p'] for url,label in p['l'] if LEGAL_LINK.search(url)))
    topic_rows=[]
    for name,pattern in TOPICS.items():
        head=len(pattern.findall(heading))
        body=len(pattern.findall(' '.join(x['text'] for x in points)))
        rest=len(pattern.findall(alltext))
        topic_rows.append((head*4 + min(body,6)*1.15 + min(rest,8)*.27,name))
    ts=sorted(topic_rows,reverse=True)
    tags=[topic for rating,topic in ts if rating>=3.15][:3]
    if not tags:
        tags=[ts[0][1]] if ts[0][0]>=1.45 else ['Другие сюжеты']
    stage=list(dict.fromkeys(s for t in [heading]+[p['text'] for p in points] for s in flags(t)))
    explicit = set()
    for line in points:
        t=line['text']
        verb=STRONG.search(t)
        if not verb or NONFACT.search(t) or FUTURE.search(t) or '?' in t:
            continue
        for k in persons:
            matcher=KNOWN.get(k)
            start=t[:verb.start()]
            ms=matcher.search(start) if matcher else None
            surn=k.split()[-1]
            # Restrict automatic attribution to an adjacent, nominative surname.
            if ms and ms[0]==surn and len(start[ms.end():].split())<=3:
                if not re.search(r'(?:\bот|\bпо|\bслова\b|\bдля|\bбез|\bпротив|\bу|\bк|\bо|\bоб|\bза|\bкак)\s+(?:[А-ЯЁ][а-яё]+ )?$',start[:ms.start()],re.I):
                    explicit.add(k)
    return {
       'id':f"{post['slug']}:{index}",'slug':post['slug'],'date':post['date'],'title':heading,
       'anchor':section['a'] or (points[0]['anchor'] if points else None),'tags':tags,
       'people':persons,'agency':agency,'mentionAgencies':mention_agencies,'actors':sorted(explicit), 'dateRefs':refs,
       'stages':stage,'documents':docs,'links':[{'url':u,'text':t} for u,t in links],'points':points,
       'words':len(alltext.split()), 'parties':entity_hits(section['p'],PARTY_PATTERNS),
       'corporations':entity_hits(section['p'],CORPORATION_PATTERNS),
    }

if __name__=='__main__':
    data=json.loads((WORK/'episodes.json').read_text())
    out=[]
    for i,p in enumerate(data['posts'],1):
        rows=[glean(s,p,j) for j,s in enumerate(p['sections'],1)]
        out.extend(rows)
        if i%20==0 or i==len(data['posts']):print(i,len(out),flush=True)
    (WORK/'evidence.json').write_text(json.dumps(out,ensure_ascii=False),encoding='utf8')
    canonical={p['slug'] for p in data['posts'] if not p.get('duplicateOf')}
    rows=[r for r in out if r['slug'] in canonical]
    for key in ('tags','people','agency','actors','stages','documents'):
        print(key,len({v for r in rows for v in r[key]}),Counter(v for r in rows for v in r[key]).most_common(12),flush=True)
