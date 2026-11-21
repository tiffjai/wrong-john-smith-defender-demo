"""Implementation of the supplied identity SOP; no practice-label access."""
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
import json
import re
import unicodedata
from resolver import read_rows


def norm(v):
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in unicodedata.normalize('NFKD', str(v or '')).casefold() if not unicodedata.combining(c))))


@lru_cache(maxsize=20000)
def date(v):
    if not v:
        return None
    s = str(v).strip()
    if re.fullmatch(r'\d{4}', s):
        return (int(s),)
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y', '%B %Y', '%b %Y', '%Y-%m'):
        try:
            d = datetime.strptime(s, fmt)
            return (d.year, d.month) if fmt in ('%B %Y', '%b %Y', '%Y-%m') else (d.year, d.month, d.day)
        except ValueError:
            pass
    return None


def agrees(a, b):
    return bool(a and b and all(x == y for x, y in zip(a, b)))


def contradicts(a, b):
    if not a or not b:
        return False
    return abs(a[0] - b[0]) > 1 or (a[0] == b[0] and any(x != y for x, y in zip(a[1:], b[1:])))


COUNTRIES = {
 'United Kingdom':['GB','GBR','UK','British','England','English','Scotland','Scottish','Wales','Welsh','Northern Ireland'],
 'United States':['US','USA','American','United States of America'], 'Nigeria':['NG','NGA','Nigerian'],
 'Pakistan':['PK','PAK','Pakistani'], 'Bangladesh':['BD','BGD','Bangladeshi'], 'India':['IN','IND','Indian'],
 'Germany':['DE','DEU','German'], 'France':['FR','FRA','French'], 'Spain':['ES','ESP','Spanish'],
 'Italy':['IT','ITA','Italian'], 'Portugal':['PT','PRT','Portuguese'], 'Brazil':['BR','BRA','Brazilian'],
 'Canada':['CA','CAN','Canadian'], 'Australia':['AU','AUS','Australian'], 'Ireland':['IE','IRL','Irish'],
 'Netherlands':['NL','NLD','Dutch'], 'Belgium':['BE','BEL','Belgian'], 'Austria':['AT','AUT','Austrian'],
 'Sweden':['SE','SWE','Swedish'], 'Norway':['NO','NOR','Norwegian'], 'Denmark':['DK','DNK','Danish'],
 'Finland':['FI','FIN','Finnish'], 'Poland':['PL','POL','Polish'], 'Romania':['RO','ROU','Romanian'],
 'Greece':['GR','GRC','Greek'], 'Switzerland':['CH','CHE','Swiss'], 'Turkey':['TR','TUR','Turkish','Türkiye'],
 'China':['CN','CHN','Chinese'], 'Hong Kong':['HK','HKG','Hong Kong SAR'], 'Singapore':['SG','SGP','Singaporean'],
 'Malaysia':['MY','MYS','Malaysian'], 'Indonesia':['ID','IDN','Indonesian'], 'Philippines':['PH','PHL','Filipino'],
 'Japan':['JP','JPN','Japanese'], 'South Korea':['KR','KOR','Korean','Republic of Korea'],
 'Russia':['RU','RUS','Russian','Russian Federation'], 'Ukraine':['UA','UKR','Ukrainian'],
 'United Arab Emirates':['AE','ARE','UAE','Emirati'], 'Saudi Arabia':['SA','SAU','Saudi'],
 'South Africa':['ZA','ZAF','South African'], 'Kenya':['KE','KEN','Kenyan'], 'Ghana':['GH','GHA','Ghanaian'],
 'Egypt':['EG','EGY','Egyptian'], 'Cote D\'Ivoire':['CI','CIV','Ivorian','Ivory Coast','Côte d’Ivoire'],
 'Colombia':['CO','COL','Colombian'], 'Mexico':['MX','MEX','Mexican'], 'Argentina':['AR','ARG','Argentinian'],
 'New Zealand':['NZ','NZL','New Zealander'], 'Taiwan':['TW','TWN','Taiwanese'], 'Czech Republic':['CZ','CZE','Czechia','Czech'],
 'Serbia':['RS','SRB','Serbian'], 'Slovenia':['SI','SVN','Slovenian'], 'Croatia':['HR','HRV','Croatian'],
 'Israel':['IL','ISR','Israeli'], 'Iran':['IR','IRN','Iranian'], 'Iraq':['IQ','IRQ','Iraqi'],
 'Venezuela':['VE','VEN','Venezuelan'], 'Chile':['CL','CHL','Chilean'], 'Peru':['PE','PER','Peruvian'],
}
COUNTRY_MAP = {norm(alias): norm(c) for c, aliases in COUNTRIES.items() for alias in [c] + aliases}


def country(v):
    n = norm(re.sub(r'\([^)]*\)|\[[^]]*\]', '', str(v or '')).split(',')[-1])
    return '' if n in ('', 'international', 'europe', 'unknown', 'na', 'n a') else COUNTRY_MAP.get(n, n)


def country_mentions(text):
    n = ' ' + norm(text) + ' '
    # Natural-language mentions only; two-letter codes are too ambiguous in prose.
    return {target for alias, target in COUNTRY_MAP.items() if len(alias) > 3 and ' ' + alias + ' ' in n}


def edits(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (x != y)))
        row = nxt
    return row[-1]


class Names:
    def __init__(self, variants):
        self.variants = {norm(v): i for i, group in enumerate(variants.get('groups', [])) for v in group}
        self.legal = set(norm(v) for v in variants.get('company_legal_forms', variants.get('legal_forms', [])))
        self.legal |= {'ltd','limited','inc','incorporated','gmbh','sa','ab','llc','plc','ag','co','corp','corporation'}

    @lru_cache(maxsize=100000)
    def parts(self, text, company=False):
        text = re.sub(r'\([^)]*\)|\[[^]]*\]', ' ', text or '')
        return tuple(sorted({p for p in norm(text).split() if len(p) > 1 and not p.isdigit() and p not in {'na','n','a','test','unknown','xxx','none','null'} and (not company or p not in self.legal)}))

    @lru_cache(maxsize=200000)
    def part_match(self, a, b):
        if a == b or (a in self.variants and self.variants[a] == self.variants.get(b)):
            return True
        size = min(len(a), len(b))
        limit = 0 if size < 4 else 1 if size <= 6 else 2
        return abs(len(a) - len(b)) <= limit and edits(a, b) <= limit

    @lru_cache(maxsize=100000)
    def match(self, a, b, company=False):
        aa, bb = self.parts(a, company), self.parts(b, company)
        if not aa or not bb:
            return False
        # Disjoint coverage also handles together/apart forms, counted as one part.
        edges = []
        for i, x in enumerate(aa):
            for j, y in enumerate(bb):
                if self.part_match(x, y): edges.append((1 << i, 1 << j))
            for j in range(len(bb)):
                for k in range(j + 1, len(bb)):
                    if x in (bb[j] + bb[k], bb[k] + bb[j]): edges.append((1 << i, (1 << j) | (1 << k)))
        for j, y in enumerate(bb):
            for i in range(len(aa)):
                for k in range(i + 1, len(aa)):
                    if y in (aa[i] + aa[k], aa[k] + aa[i]): edges.append(((1 << i) | (1 << k), 1 << j))
        def search(start, amask, bmask, count):
            if count >= 2 or amask == (1 << len(aa)) - 1 or bmask == (1 << len(bb)) - 1:
                return True
            for index in range(start, len(edges)):
                x, y = edges[index]
                if not (x & amask or y & bmask) and search(index + 1, amask | x, bmask | y, count + 1):
                    return True
            return False
        return search(0, 0, 0, 0)


MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
DATE = rf'(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|{MONTH} \d{{1,2}}, \d{{4}}|\d{{1,2}} {MONTH} \d{{4}})'


def note_check(note):
    text = note['text']
    if re.search(r'reject|expired|failed|not verified|not approved', text, re.I):
        return None
    if not re.search(r'verif|validated|confirmed|accepted|approved|passed|check complete|successful|completed', text, re.I):
        return None
    dob = re.search(rf'(?:\bDOB\b|date of birth(?: on document)?|birth date(?: of)?|\bborn\b)[\s:;]*(?:(?:recorded|confirmed|verified)(?: as)?[\s:]*)?({DATE})', text, re.I)
    if not dob:
        dob = re.search(rf'\(({DATE})\)', text, re.I)
    if not dob:
        return None
    # Verified legal names are capitalised in provider notes; require a multiword span.
    tokens = re.findall(r"[^\W\d_]+(?:['’.-][^\W\d_]+)*", text)
    spans, current = [], []
    for token in tokens + ['end']:
        if token.isupper() and token not in ('ID','DOB','KYC'):
            current.append(token)
        else:
            if len(current) >= 2: spans.append(' '.join(current))
            current = []
    names = spans
    if not names:
        return None
    return {'check_id':note['note_id'], 'verified_name':max(names, key=len).removesuffix("'s"), 'verified_dob':dob[1], 'checked_at':note['created_at'], 'countries':country_mentions(text), 'note':True}


def age_years(text):
    years = re.findall(rf'{MONTH}\s+(?:\d{{1,2}},?\s+)?((?:19|20)\d{{2}})', text, re.I)
    ages = re.findall(r'(?:\baged?\s+|age of\s+|\b(?:he|she) was\s+)(\d{1,3})\b|\b(\d{1,3})[ -]year[ -]old\b|(?<=[^\W\d_]),\s*(\d{1,3})\s*,(?!\d)|\b(\d{1,3}) years old\b', text, re.I)
    if not years or not ages:
        return []
    age = int(next(x for x in ages[0] if x))
    year = int(years[0])
    return [(year-age-1,), (year-age,)] if 0 <= age <= 120 else []


class BankResolver:
    def __init__(self, folder):
        self.folder = folder
        self.names = Names(json.loads((folder/'name_variants.json').read_text()))
        self.data = {n:read_rows(folder,n) for n in ('alerts','hits','customers','accounts','onboarding','kyc_checks','notes','search_results')}
        self.customers = {c['record_id']:c for c in self.data['customers']}
        self.parent = {cid:cid for cid in self.customers}
        self.accounts = defaultdict(list); self.logins = defaultdict(list); self.emails = defaultdict(list)
        self.checks = defaultdict(list); self.notes = defaultdict(list); self.search = defaultdict(list)
        applicants = defaultdict(list)
        self.paths = defaultdict(list)
        for a in self.data['accounts']:
            if a['customer_id'] not in self.customers: continue
            self.accounts[a['account_id']].append(a['customer_id'])
            if a.get('login_handle'): self.logins[norm(a['login_handle'])].append(a['customer_id'])
            self.paths[a['customer_id']].append(a['account_id'])
        for o in self.data['onboarding']:
            if o.get('customer_id') in self.customers:
                applicants[o['kyc_applicant_id']].append(o['customer_id'])
        docs = {}; phones = {}
        for k in self.data['kyc_checks']:
            if k.get('result') != 'approved': continue
            for cid in applicants.get(k['applicant_id'], []):
                self.checks[cid].append(k)
                doc = norm(k.get('document_number'))
                if doc:
                    if doc in docs: self.union(cid, docs[doc])
                    docs[doc] = cid
        for cid, c in self.customers.items():
            if c.get('email'): self.emails[c['email'].casefold()].append(cid)
            d = date(c.get('dob')); phone = re.sub(r'\D','',c.get('phone') or '')
            if phone and d and len(d) == 3:
                key = (phone,d)
                if key in phones: self.union(cid, phones[key])
                phones[key] = cid
        self.groups = defaultdict(list)
        for cid in self.customers: self.groups[self.root(cid)].append(cid)
        for n in self.data['notes']:
            self.notes[n['requester_email'].casefold()].append(n)
        for r in self.data['search_results']: self.search[' '.join(sorted(norm(r['query']).split()))].append(r)
        self.token_index = defaultdict(set)
        for cid, c in self.customers.items():
            for field in ('full_name','preferred_name','login_name'):
                for token in self.names.parts(c.get(field), c.get('entity_type') == 'Company'):
                    self.token_index[token].add(cid)
        self.trace = {}

    def root(self, cid):
        while self.parent[cid] != cid:
            self.parent[cid] = self.parent[self.parent[cid]]
            cid = self.parent[cid]
        return cid

    def union(self,a,b):
        ra, rb = self.root(a), self.root(b)
        if ra != rb: self.parent[max(ra,rb)] = min(ra,rb)

    def fits(self, c, screened):
        company = c.get('entity_type') == 'Company'
        if screened.get('entity_type') and c.get('entity_type') != screened['entity_type']: return False
        if not any(self.names.match(c.get(f),screened.get('name'),company) for f in ('full_name','preferred_name','login_name')): return False
        if screened.get('dob') and not agrees(date(c.get('dob')),date(screened['dob'])): return False
        if screened.get('country') and country(screened['country']) not in {country(c.get('residence_country')),country(c.get('nationality'))}: return False
        if screened.get('city') and norm(screened['city']) not in norm(str(c.get('city') or '')+' '+str(c.get('address') or '')): return False
        return True

    def candidates(self, a):
        ids = set()
        if a.get('account_ref'): ids.update(self.accounts[a['account_ref']])
        if a.get('login_handle'): ids.update(self.logins[norm(a['login_handle'])])
        if a.get('email'): ids.update(self.emails[a['email'].casefold()])
        linked = bool(ids)
        if not linked:
            for token in self.names.parts(a['customer'].get('name')):
                for variant, cids in self.token_index.items():
                    if self.names.part_match(token,variant): ids.update(cids)
        if not linked or len({self.root(cid) for cid in ids}) > 1:
            ids = {cid for cid in ids if self.fits(self.customers[cid],a['customer'])}
        return sorted({self.root(cid) for cid in ids})

    @lru_cache(maxsize=10000)
    def picture(self, root):
        records = [self.customers[cid] for cid in sorted(self.groups[root])]
        checks = [k for c in records for k in self.checks[c['record_id']]]
        notes = [n for c in records for n in self.notes[c['email'].casefold()] if c.get('email')]
        checks += [k for n in notes if (k := note_check(n))]
        checks.sort(key=lambda k:(k.get('checked_at') or '', k['check_id']), reverse=True)
        latest = checks[0] if checks else None
        countries = {country(c.get(f)) for c in records for f in ('residence_country','nationality')} - {''}
        country_ids = {c['record_id'] for c in records if c.get('residence_country') or c.get('nationality')}
        for k in checks:
            countries.update(k.get('countries',set()) or {country(k.get('document_country'))} - {''})
            if k.get('countries') or k.get('document_country'): country_ids.add(k['check_id'])
        for n in notes:
            if re.search(r'liv|residen|home|relocat|mov|based|work|job',n['text'],re.I):
                mentions = country_mentions(n['text'])
                if mentions: countries.update(mentions); country_ids.add(n['note_id'])
        record = records[0]
        return {'records':records,'check':latest,'name':latest.get('verified_name') if latest else record['full_name'],
                'dob':date(latest.get('verified_dob')) if latest else date(record.get('dob')),
                'countries':countries,'country_ids':sorted(country_ids),'type':record['entity_type']}

    def hit_facts(self,h):
        countries = {country(x) for f in ('countries','nationality','citizenship') for x in h.get(f,[]) if isinstance(x,str)}
        countries.update(country(x.split(',')[-1]) for x in h.get('addresses',[]) if isinstance(x,str))
        if h.get('place_of_birth'): countries.add(country(h['place_of_birth'].split(',')[-1]))
        countries.discard('')
        dobs = [d for raw in h.get('dobs',[]) if (d := date(raw))]
        ids = [h['hit_id']]
        text = h.get('profile_notes') or ''
        if not dobs and h.get('entity_type') != 'Company':
            dobs = age_years(text.split('\n\n')[0])
        if not dobs and h.get('entity_type') != 'Company':
            category = h.get('primary_category') or next(iter(h.get('categories',[])), '')
            phrase = {'Sanctions':'a sanctioned individual','PEP':'a politically exposed person','Enforcement':'the subject of enforcement action','Adverse Media':'named in adverse media','SOE':'a state-owned enterprise official'}.get(category,'named on a watchlist')
            key = ' '.join(sorted(norm(h['name']).split()))
            for r in self.search[key]:
                snippet = r['snippet']
                if phrase in snippet.casefold() and countries & country_mentions(snippet):
                    years = age_years(snippet)
                    if years: dobs.extend(years); ids.append(r['result_id'])
        reports = []
        for raw in re.findall(rf'^According to [^\n;]+;\s*({MONTH} \d{{1,2}}, \d{{4}}):',text,re.M):
            if d := date(raw): reports.append(d)
        return {'countries':countries,'dobs':dobs,'evidence':ids,'report':min(reports) if reports else None}

    def compare(self, a, h, root):
        p = self.picture(root); hf = self.hit_facts(h)
        record_ids = [c['record_id'] for c in p['records']]
        evidence = record_ids + [h['hit_id']]
        if p['check']: evidence.append(p['check']['check_id'])
        company = p['type'] == 'Company'
        aliases = [x if isinstance(x,str) else x.get('name','') for x in h.get('aliases',[])]
        names = [h['name']] + aliases
        enough = company or len(self.names.parts(p['name'])) >= 2
        name_match = enough and any(self.names.match(p['name'],n,company) for n in names)
        dob_match = any(agrees(p['dob'],d) for d in hf['dobs'])
        dob_conflict = bool(p['dob'] and hf['dobs'] and all(contradicts(p['dob'],d) for d in hf['dobs']))
        location_conflict = bool(p['countries'] and hf['countries'] and not p['countries'] & hf['countries'])
        common = p['countries'] & hf['countries']
        decision, code, reason = 'REVIEW','INSUFFICIENT_DATA',f"Customer {root} has resolved name {p['name']}, date {p['dob']} and countries {sorted(p['countries'])}; hit {h['hit_id']} has name {h['name']}, dates {hf['dobs']} and countries {sorted(hf['countries'])}. These facts do not establish a decisive contradiction or sufficient identity agreement; missing components remain unknown."
        if p['type'] != h['entity_type']:
            decision,code,reason = 'DIFFERENT_ENTITY','ENTITY_TYPE_MISMATCH',f"The resolved customer is {p['type']}; the listed subject is {h['entity_type']}. The entity types contradict."
        elif (death := date(h.get('deceased_date'))) and (screened := date(a.get('screened_at'))) and len(death) == len(screened) == 3 and death < screened:
            decision,code,reason = 'DIFFERENT_ENTITY','DECEASED',f"The profile records death on {h['deceased_date']}, before screening on {a['screened_at']}. The deceased listed subject cannot be the active customer under the SOP."
        elif p['dob'] and hf['report'] and ((company and p['dob'] > hf['report'][:len(p['dob'])]) or (not company and (hf['report'][0] - p['dob'][0] < 16 or (len(p['dob']) == 3 and hf['report'][0] - p['dob'][0] == 16 and hf['report'][1:] < p['dob'][1:])))):
            decision,code,reason = 'DIFFERENT_ENTITY','TEMPORAL_IMPOSSIBILITY',f"The customer's birth/incorporation date is {p['dob']}; the earliest qualifying report is {hf['report']}. The customer was under 16 or not incorporated at that time."
        elif dob_conflict:
            decision,code,reason = 'DIFFERENT_ENTITY','DOB_MISMATCH',f"The resolved customer birth/incorporation date is {p['dob']}; the hit gives {hf['dobs']}. Every supplied hit date contradicts it under the SOP's one-year tolerance."
            evidence += hf['evidence']
        elif enough and p['check'] and not name_match:
            decision,code,reason = 'DIFFERENT_ENTITY','NAME_MISMATCH_VERIFIED',f"The latest approved identity evidence names the customer {p['name']}. It agrees with none of the listed names or aliases: {', '.join(names)}."
        elif location_conflict:
            evidence += p['country_ids']
            if name_match and dob_match:
                reason = f"Name and birth date agree, but customer countries {sorted(p['countries'])} and hit countries {sorted(hf['countries'])} conflict. The SOP requires human review rather than location-based clearance."
            else:
                decision,code,reason = 'DIFFERENT_ENTITY','LOCATION_MISMATCH',f"All known customer countries {sorted(p['countries'])} differ from all hit countries {sorted(hf['countries'])}. There is no agreeing name-and-DOB combination to prevent location exclusion."
        elif name_match and ((company and common) or (not company and dob_match)):
            decision = 'SAME_ENTITY'
            code = 'NAME_LOCATION_MATCH' if company else 'NAME_DOB_LOCATION_MATCH' if common else 'NAME_DOB_MATCH'
            evidence += hf['evidence'] + (p['country_ids'] if common else [])
            agreement = "Company countries agree" if company else f"Customer DOB {p['dob']} agrees with one of {hf['dobs']}"
            reason = f"The resolved name {p['name']} agrees with the hit's names. {agreement}{' and countries overlap at ' + ', '.join(sorted(common)) if common else ''}; no decisive contradiction was found."
        elif not enough:
            reason = 'The customer has fewer than two real name parts. Identity cannot be confirmed or excluded on name; other available evidence is insufficient.'
        self.trace[h['hit_id']+':'+root] = {'customer':{'name':p['name'],'dob':p['dob'],'countries':sorted(p['countries']),'verified':bool(p['check']),'records':record_ids},'watchlist':{'name':h['name'],'dobs':hf['dobs'],'countries':sorted(hf['countries']),'report':hf['report']},'path':[a['alert_id']]+[x for c in p['records'] for x in self.paths[c['record_id']]]+record_ids+([p['check']['check_id']] if p['check'] else []),'gaps':[x for x,missing in [('Customer birth date missing',not p['dob']),('Hit birth date missing',not hf['dobs']),('Customer country missing',not p['countries']),('Hit country missing',not hf['countries']),('No approved identity check',not p['check'])] if missing]}
        return {'hit_id':h['hit_id'],'alert_id':a['alert_id'],'decision':decision,'reason_code':code,'customer_record_id':root,'reason':reason,'evidence':sorted(set(evidence))}

    def run(self):
        hits = {h['hit_id']:h for h in self.data['hits']}
        outputs = []
        for a in sorted(self.data['alerts'], key=lambda a:a['alert_id']):
            roots = self.candidates(a)
            for hid in sorted(a['hit_ids']):
                h = hits[hid]
                if not roots:
                    row = {'hit_id':hid,'alert_id':a['alert_id'],'decision':'REVIEW','reason_code':'INSUFFICIENT_DATA','customer_record_id':None,'reason':'No customer person could be resolved from the available link and screened details. Human review is required before comparing identities.','evidence':[a['alert_id'],hid]}
                else:
                    answers = [self.compare(a,h,r) for r in roots]
                    row = answers[0]
                    if len(answers) > 1:
                        row = dict(row,customer_record_id='AMBIGUOUS',evidence=sorted({e for r in answers for e in r['evidence']}))
                        if len({r['decision'] for r in answers}) > 1:
                            row.update(decision='REVIEW',reason_code='AMBIGUOUS_CUSTOMER_RECORD',reason='Several distinct customer people fit the screened details. Their hit decisions disagree, so a reviewer must resolve the customer identity.')
                        else:
                            row['reason'] = f"All {len(answers)} candidate people lead to {row['decision']}. " + row['reason']
                outputs.append(row)
        if len(outputs) != len(hits) or len({r['hit_id'] for r in outputs}) != len(hits):
            raise ValueError('Alert references must cover each hit exactly once')
        return outputs
