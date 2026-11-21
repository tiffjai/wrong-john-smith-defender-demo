"""Conservative identity resolver. No network, models, current time or randomness."""
import json
import re
import unicodedata
from pathlib import Path


def normal(value):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', str(value or '')).casefold()))


def value(row, *keys):
    return next((row[k] for k in keys if row.get(k) not in (None, '')), None)


def record_id(row, kind):
    return value(row, f'{kind}_id', 'id')


def read_rows(folder, name):
    path = folder / f'{name}.jsonl'
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f'{path.name}:{line_no}: invalid JSON') from error
        if not isinstance(row, dict):
            raise ValueError(f'{path.name}:{line_no}: expected an object')
        rows.append(row)
    return rows


def date_parts(raw):
    # Only explicit ISO dates/years are compared. No imputation or fuzzy date parsing.
    text = str(raw or '')
    if not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', text):
        return None
    parts = tuple(map(int, text.split('-')))
    try:
        from datetime import date
        date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except ValueError:
        return None
    return parts


def dates_conflict(left, right):
    a, b = date_parts(left), date_parts(right)
    return bool(a and b and any(x != y for x, y in zip(a, b)))


def load_policy(folder):
    path = folder / 'POLICY.md'
    if not path.is_file():
        raise ValueError('POLICY.md is required; bank policy must not be guessed.')
    text = path.read_text()
    codes = set(re.findall(r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b', text))
    adapter_path = folder / 'policy_adapter.json'
    if adapter_path.exists():
        adapter = json.loads(adapter_path.read_text())
        if not isinstance(adapter, dict):
            raise ValueError('policy_adapter.json must be an object')
    else:
        review_codes = sorted(codes & {'INSUFFICIENT_EVIDENCE', 'INSUFFICIENT_DATA', 'REVIEW_REQUIRED', 'UNRESOLVED_IDENTITY'})
        if not review_codes:
            raise ValueError('Map the bank SOP review reason in policy_adapter.json; no recognised review code found.')
        adapter = {'review_code': review_codes[0]}
    for key in ('review_code', 'dob_mismatch_code', 'same_entity_code'):
        if key in adapter and adapter[key] not in codes:
            raise ValueError(f'{key} must be a reason code in POLICY.md')
    if not adapter.get('review_code'):
        raise ValueError('policy_adapter.json requires review_code')
    for key in ('allow_verified_dob_exclusion', 'allow_exact_name_full_dob_match'):
        if key in adapter and not isinstance(adapter[key], bool):
            raise ValueError(f'{key} must be a boolean')
    return adapter


def resolve_customer(alert, data):
    customers, accounts = data['customers'], data['accounts']
    account_keys = ('account_id', 'account_number', 'login_id', 'login')
    matches = [a for a in accounts if any(alert.get(k) is not None and alert[k] == a.get(k) for k in account_keys)]
    ids = {a.get('customer_id') for a in matches if a.get('customer_id')}
    direct = alert.get('customer_id')
    if direct:
        ids.add(direct)
    email = value(alert, 'email', 'customer_email')
    # Include all matching people, even when another key already linked a record.
    found = [c for c in customers if record_id(c, 'customer') in ids or (email and str(c.get('email', '')).casefold() == str(email).casefold())]
    unique = {record_id(c, 'customer'): c for c in found if record_id(c, 'customer')}
    trail = [record_id(a, 'account') for a in matches if record_id(a, 'account')]
    if len(unique) != 1:
        return None, 'AMBIGUOUS' if len(unique) > 1 else None, trail, []
    cid, customer = next(iter(unique.items()))
    linked_accounts = [a for a in accounts if a.get('customer_id') == cid]
    account_ids = {record_id(a, 'account') for a in linked_accounts}
    onboard = [o for o in data['onboarding'] if o.get('account_id') in account_ids and o.get('applicant_id')]
    applicants = {o['applicant_id'] for o in onboard}
    checks = [k for k in data['kyc_checks'] if k.get('applicant_id') in applicants and str(value(k, 'result', 'status') or '').lower() in ('passed', 'pass', 'approved', 'verified')]
    path = [cid] + [record_id(a, 'account') for a in linked_accounts] + [record_id(o, 'onboarding') for o in onboard]
    return customer, cid, [x for x in path if x], checks


def predict(alert, hit, data, policy):
    customer, cid, trail, checks = resolve_customer(alert, data)
    hid, aid = record_id(hit, 'hit'), record_id(alert, 'alert')
    base = {'hit_id': hid, 'alert_id': aid, 'decision': 'REVIEW', 'reason_code': policy['review_code'], 'customer_record_id': cid,
            'reason': '', 'evidence': []}
    evidence = [aid, hid] + trail
    if customer is None:
        base['reason'] = ('Multiple customer records fit the alert linkage. The customer identity cannot be selected safely.' if cid else 'No customer record can be linked to this alert using an explicit account, login, customer ID or email. Identity remains unresolved.')
    else:
        cdob = value(customer, 'dob', 'date_of_birth')
        cname = value(customer, 'name', 'full_name')
        verified = [(value(k, 'verified_dob', 'dob', 'date_of_birth'), k) for k in checks if date_parts(value(k, 'verified_dob', 'dob', 'date_of_birth'))]
        conflicting = any(dates_conflict(a[0], b[0]) for a in verified for b in verified)
        # Most precise compatible passed check wins; rejected checks never enter this set.
        verified.sort(key=lambda item: (-len(date_parts(item[0])), str(record_id(item[1], 'check'))))
        check = verified[0][1] if verified else None
        if check:
            cdob = verified[0][0]
            cname = value(check, 'verified_name', 'name', 'full_name') or cname
            evidence.append(record_id(check, 'check'))
        hdob = value(hit, 'dob', 'date_of_birth')
        hname = value(hit, 'name', 'full_name')
        if conflicting:
            evidence += [record_id(k, 'check') for _, k in verified]
            base['reason'] = 'Passed identity checks contain contradictory birth dates. Human review must resolve the conflicting verified evidence.'
        elif check and dates_conflict(cdob, hdob) and policy.get('allow_verified_dob_exclusion') and policy.get('dob_mismatch_code'):
            base.update(decision='DIFFERENT_ENTITY', reason_code=policy['dob_mismatch_code'], reason=f'The passed KYC check gives the customer birth date as {cdob}; the listed profile gives {hdob}. The known date components conflict under the configured identity SOP.')
        elif check and date_parts(cdob) and date_parts(hdob) and len(date_parts(cdob)) == len(date_parts(hdob)) == 3 and cdob == hdob and normal(cname) and normal(cname) == normal(hname) and policy.get('allow_exact_name_full_dob_match') and policy.get('same_entity_code'):
            base.update(decision='SAME_ENTITY', reason_code=policy['same_entity_code'], reason=f'The passed KYC name {cname} and full birth date {cdob} agree with the listed profile. The configured SOP accepts this combination; this is an identity finding and makes no compliance disposition.')
        else:
            base['reason'] = f'The linked customer has birth date {cdob or "unknown"}; the listed profile has {hdob or "unknown"}. Evidence does not satisfy an enabled policy rule; missing values and unparsed profile text are not treated as mismatches.'
    base['evidence'] = list(dict.fromkeys(x for x in evidence if x is not None))
    return base


def run(folder):
    policy = load_policy(folder)
    data = {name: read_rows(folder, name) for name in ('alerts', 'hits', 'customers', 'accounts', 'onboarding', 'kyc_checks', 'notes', 'search_results')}
    hit_map = {}
    for hit in data['hits']:
        hid = record_id(hit, 'hit')
        if not isinstance(hid, str) or hid in hit_map:
            raise ValueError('Every watchlist hit needs a unique string hit_id or id')
        hit_map[hid] = hit
    outputs, seen = [], set()
    for alert in data['alerts']:
        aid = record_id(alert, 'alert')
        if not isinstance(aid, str):
            raise ValueError('Every alert needs a string alert_id or id')
        refs = value(alert, 'hit_ids', 'hits')
        if refs is None:
            refs = [record_id(h, 'hit') for h in data['hits'] if h.get('alert_id') == aid]
        if not isinstance(refs, list) or not refs:
            raise ValueError(f'Alert {aid} has no supported hit references; adapt the input schema before running')
        for ref in refs:
            hid = value(ref, 'hit_id', 'id') if isinstance(ref, dict) else ref
            if hid not in hit_map:
                raise ValueError(f'Alert {aid} references missing hit {hid}')
            key = (aid, hid)
            if key in seen:
                raise ValueError(f'Duplicate alert/hit pair: {aid}/{hid}')
            seen.add(key)
            outputs.append(predict(alert, hit_map[hid], data, policy))
    return sorted(outputs, key=lambda r: (r['alert_id'], r['hit_id']))


def execute(folder, output):
    folder = folder.resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Data folder must be a directory')
    # Prevent symlinks from reading beyond the supplied data room.
    for path in folder.iterdir():
        if path.is_symlink() and not path.resolve().is_relative_to(folder):
            raise ValueError(f'External symlink is not allowed: {path.name}')
    if (folder / 'name_variants.json').exists():
        from bank_resolver import BankResolver
        if not (folder / 'POLICY.md').is_file():
            raise ValueError('POLICY.md is required')
        rows = BankResolver(folder).run()
    else:
        rows = run(folder)
    if output.resolve() in {p.resolve() for p in folder.iterdir()}:
        raise ValueError('Output must not overwrite an input file')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows))
