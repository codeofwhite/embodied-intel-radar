#!/usr/bin/env python3
"""Export allowlisted public records; never read personal inboxes or secrets."""
import argparse
import datetime as dt
import ipaddress
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
JOB_FIELDS = {'id', 'company', 'title', 'location', 'category', 'employmentType',
              'education', 'experience', 'datePosted', 'lastSeen', 'sourceTier',
              'verification', 'listingStatus', 'workSummary', 'entryBarrier'}
COMPANY_FIELDS = {'id', 'name', 'city', 'companyType', 'focus', 'careerKind'}
EVENT_FIELDS = {'id', 'title', 'domain', 'sourceTier', 'verification', 'publishedAt',
                'discoveredAt', 'company', 'eventType', 'project', 'whatHappened'}
SOCIAL_FIELDS = {'id', 'title', 'domain', 'platform', 'sourceTier', 'publishedAt',
                 'discoveredAt', 'company', 'signalType'}


def text(value):
    return value[:1200] if isinstance(value, str) else ''


def public_url(value):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password:
            return ''
        if host == 'localhost' or '.' not in host or host.endswith(('.local', '.internal')):
            return ''
        try:
            if not ipaddress.ip_address(host).is_global:
                return ''
        except ValueError:
            pass
        sensitive = {'token', 'key', 'api_key', 'access_token', 'auth', 'authorization', 'secret', 'password', 'signature'}
        if any(k.lower() in sensitive for k, _ in parse_qsl(parsed.query)):
            return ''
        return value[:4000]
    except ValueError:
        return ''


def records(items, fields, url_fields=('url',), lists=()):
    if not isinstance(items, list):
        raise ValueError('Expected a list of public records')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Malformed record')
        clean = {k: text(item[k]) for k in sorted(fields) if k in item}
        for key in url_fields:
            clean[key] = public_url(item.get(key))
        if not any(clean.get(k) for k in url_fields):
            continue
        for key in lists:
            clean[key] = [text(v) for v in item.get(key, []) if isinstance(v, str)][:30] if isinstance(item.get(key, []), list) else []
        result.append(clean)
    return result


def timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing source collection timestamp')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10):
        raise ValueError('Invalid source collection timestamp')
    return parsed.isoformat()


def build_snapshot(jobs, events=None, social=None, previous=None):
    previous = previous or {}
    if not isinstance(jobs, dict):
        raise ValueError('Missing jobs envelope')
    collected = timestamp(jobs.get('meta', {}).get('generatedAt'))
    job_items = records(jobs.get('jobs'), JOB_FIELDS, lists=('skills', 'qualityFlags', 'responsibilities', 'requirements', 'entryBasis'))
    if not job_items:
        raise ValueError('Refusing to replace a valid snapshot with empty jobs')
    if not all(item.get('id') and item.get('title') and item.get('company') for item in job_items):
        raise ValueError('Job identity, title and company are required')
    job_items.sort(key=lambda j: (j.get('company', ''), j.get('title', ''), j.get('id', '')))
    payload = {
        'schemaVersion': 1,
        'generatedAt': collected,
        'jobs': job_items,
        'companies': records(jobs.get('companies', []), COMPANY_FIELDS, ('careerUrl', 'officialUrl')),
        'events': records(previous.get('events', []), EVENT_FIELDS),
        'social': records(previous.get('social', []), SOCIAL_FIELDS),
        'sectionUpdatedAt': {'jobs': collected},
    }
    for name, source, fields in [('events', events, EVENT_FIELDS), ('social', social, SOCIAL_FIELDS)]:
        if source is not None:
            date = timestamp(source.get('meta', {}).get('generatedAt'))
            items = records(source.get('items', []), fields)
            if name == 'social':
                for item in items:
                    item['verification'] = '搜索索引线索·待核实'
            payload[name] = items
            payload['sectionUpdatedAt'][name] = date
        elif previous.get('sectionUpdatedAt', {}).get(name):
            payload['sectionUpdatedAt'][name] = previous['sectionUpdatedAt'][name]
    for item in payload['social']:
        item['verification'] = '搜索索引线索·待核实'
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'collector/data')
    parser.add_argument('--output', type=Path, default=ROOT / 'site/data/snapshot.json')
    args = parser.parse_args()
    def read(path, optional=False):
        if optional and not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    try:
        payload = build_snapshot(read(args.data_dir / 'jobs.json'),
                                 read(args.data_dir / 'events.json', True),
                                 read(args.data_dir / 'social.json', True),
                                 read(args.output, True))
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix('.json.tmp')
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(args.output)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        parser.exit(1, f'Public snapshot unchanged: {exc}\n')
    print(f'Public snapshot: {len(payload["jobs"])} jobs, {len(payload["companies"])} companies, {len(payload["events"])} events')


if __name__ == '__main__':
    main()
