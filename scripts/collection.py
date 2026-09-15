#!/usr/bin/env python3
"""Download and verify the exact public asset snapshot. Python 3.11+."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from functools import lru_cache
from datetime import date
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import time
import unicodedata
from urllib.request import Request, urlopen

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://htmonfohxuipdpmznlcj.supabase.co/storage/v1/object/public/entity-assets/'
NAMES = {'banks': 'Banks', 'cards': 'Cards', 'compliance': 'Compliance',
         'currencies': 'Currencies', 'identifiers': 'Identifiers', 'markets': 'Markets',
         'operators': 'Operators', 'payment-methods': 'Payment methods', 'psps': 'PSPs',
         'regulators': 'Regulators', 'schemes': 'Schemes', 'standards': 'Standards', 'systems': 'Systems'}
PRESERVED_CATEGORIES = {'compliance', 'identifiers', 'standards'}


def check_entry(item):
    category = item['category']
    path = item['path']
    if category not in NAMES or not isinstance(path, str):
        raise ValueError('Unknown category or invalid path')
    parts = PurePosixPath(path).parts
    if len(parts) != 2 or parts[0] != category or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*\.png', parts[1]):
        raise ValueError(f'Unsafe asset path: {path}')
    if path != '/'.join(parts) or not item.get('id') or not item.get('name'):
        raise ValueError(f'Invalid identity: {path}')
    expected = (406, 256) if category == 'cards' else (256, 256)
    if (item['width'], item['height']) != expected:
        raise ValueError(f'Unexpected dimensions in metadata: {path}')
    if not isinstance(item['bytes'], int) or not 0 < item['bytes'] <= 5_000_000:
        raise ValueError(f'Invalid byte size: {path}')
    if not re.fullmatch(r'[a-f0-9]{64}', item['sha256']):
        raise ValueError(f'Invalid SHA-256: {path}')
    if not isinstance(item.get('source'), dict) or not isinstance(item['source'].get('kind'), str):
        raise ValueError(f'Missing provenance: {path}')
    upstream = item.get('upstreamPath')
    upstream_parts = PurePosixPath(upstream).parts if isinstance(upstream, str) else ()
    if (len(upstream_parts) != 2 or upstream_parts[0] != category or
            not re.fullmatch(r'[a-zA-Z0-9_-]+\.png', upstream_parts[1]) or
            upstream != '/'.join(upstream_parts)):
        raise ValueError(f'Unsafe upstream asset path: {upstream}')
    aliases = item.get('aliases', [])
    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
        raise ValueError(f'Invalid aliases: {path}')
    url = item['source'].get('url')
    if url is not None and (not isinstance(url, str) or not re.match(r'^https?://[^\s]+$', url)):
        raise ValueError(f'Unsafe source URL: {path}')


def destination(item):
    check_entry(item)
    path = ROOT / item['path']
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError(f'Symlinks are not supported: {path}')
    return path


def load_catalog():
    index = json.loads((ROOT / 'catalog.json').read_text())
    schema_version = index.get('schemaVersion')
    if schema_version not in (1, 2) or index.get('sourceBaseUrl') != SOURCE:
        raise ValueError('Unsupported catalog schema or source')
    entries, categories = [], set()
    for category in index['categories']:
        cid = category['id']
        if cid not in NAMES or cid in categories or category['path'] != f'catalog/{cid}.json':
            raise ValueError('Invalid catalog category')
        categories.add(cid)
        batch = json.loads((ROOT / category['path']).read_text())
        if len(batch) != category['count'] or any(x['category'] != cid for x in batch):
            raise ValueError(f'Category count or mapping mismatch: {cid}')
        entries.extend(batch)
    if categories != set(NAMES) or len(entries) != index['assetCount']:
        raise ValueError('Incomplete catalog')
    seen = set()
    for item in entries:
        if schema_version == 1:
            legacy = PurePosixPath(item.get('path', '')).parts
            if (len(legacy) != 2 or legacy[0] != item.get('category') or
                    not re.fullmatch(r'[a-zA-Z0-9_-]+\.png', legacy[1])):
                raise ValueError(f'Invalid legacy asset path: {item.get("path")}')
            item.setdefault('upstreamPath', item['path'])
            item.setdefault('aliases', [])
        else:
            check_entry(item)
        if item['path'] in seen:
            raise ValueError(f'Duplicate path: {item["path"]}')
        seen.add(item['path'])
    cards = sum(x['category'] == 'cards' for x in entries)
    if cards != index['cardCount'] or len(entries) - cards != index['primaryIconCount']:
        raise ValueError('Shape counts do not match')
    return index, entries


def check_bytes(data, item):
    if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError(f'Bytes or SHA-256 mismatch: {item["path"]}')


@lru_cache(maxsize=1)
def silhouette_masks():
    inside, outside = bytearray(), bytearray()
    for y in range(256):
        for x in range(256):
            dx = max(43 - (x + 0.5), (x + 0.5) - 213, 0)
            dy = max(43 - (y + 0.5), (y + 0.5) - 213, 0)
            distance = (dx*dx + dy*dy) ** 0.5
            inside.append(255 if distance < 40 else 0)
            outside.append(255 if distance > 46 else 0)
    return Image.frombytes('L', (256, 256), bytes(inside)), Image.frombytes('L', (256, 256), bytes(outside))


def check_image(data, item):
    check_bytes(data, item)
    with Image.open(BytesIO(data)) as original:
        if original.format != 'PNG' or original.size != (item['width'], item['height']):
            raise ValueError(f'PNG format or dimensions mismatch: {item["path"]}')
        original.load()
        alpha = original.convert('RGBA').getchannel('A')
    width, height = alpha.size
    if item['category'] == 'cards':
        # Card artwork deliberately keeps its own frame, transparency and corner treatment.
        return
    if any(alpha.getpixel(p) != 0 for p in ((0, 0), (width-1, 0), (0, height-1), (width-1, height-1))):
        raise ValueError(f'Corners must be transparent: {item["path"]}')
    # Check the rounded-square silhouette independent of a CSS border-radius.
    # A 3-pixel tolerance excludes the anti-aliased edge, not the interior.
    inside, outside = silhouette_masks()
    if ImageChops.multiply(ImageChops.invert(alpha), inside).getbbox():
        raise ValueError(f'Transparent rounded-square interior: {item["path"]}')
    if ImageChops.multiply(alpha, outside).getbbox():
        raise ValueError(f'Square corner outside silhouette: {item["path"]}')


def download(entries, workers):
    groups = defaultdict(list)
    for item in entries:
        groups[item['sha256']].append(item)
    cache = ROOT / '.cache' / 'sha256'
    cache.mkdir(parents=True, exist_ok=True)

    def fetch_group(group):
        first = group[0]
        cached = cache / (first['sha256'] + '.png')
        data = None
        # A shared hash may belong to many records. Reuse any already materialized
        # descriptive path before reaching out to the upstream public bucket.
        for candidate in [*(destination(item) for item in group), cached]:
            if candidate.is_file():
                candidate_data = candidate.read_bytes()
                try:
                    check_bytes(candidate_data, first)
                    data = candidate_data
                    break
                except ValueError:
                    pass
        if data is None:
            for attempt in range(3):
                try:
                    suffix = '' if attempt == 0 else '?v=' + first['sha256']
                    request = Request(SOURCE + first['upstreamPath'] + suffix, headers={'User-Agent': 'Aurato-Payment-Icons/1.0'})
                    with urlopen(request, timeout=30) as response:
                        data = response.read(5_000_001)
                    check_bytes(data, first)
                    cached.write_bytes(data)
                    break
                except Exception:
                    data = None
                    if attempt == 2:
                        raise
                    time.sleep(attempt+1)
        for item in group:
            check_bytes(data, item)
            path = destination(item)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_bytes() != data:
                temp = path.with_suffix('.png.part')
                temp.write_bytes(data)
                temp.replace(path)
        return len(group)

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks = [executor.submit(fetch_group, group) for group in groups.values()]
        for i, task in enumerate(as_completed(tasks), 1):
            completed += task.result()
            if i % 100 == 0 or i == len(tasks):
                print(f'{i}/{len(tasks)} unique images; {completed}/{len(entries)} files ready', flush=True)


def validate(entries):
    expected = {x['path'] for x in entries}
    actual = {p.relative_to(ROOT).as_posix() for cat in NAMES for p in (ROOT/cat).rglob('*.png') if p.is_file()}
    if expected != actual:
        raise ValueError(f'Missing files: {sorted(expected-actual)[:10]}; unlisted files: {sorted(actual-expected)[:10]}')
    unexpected = {p.relative_to(ROOT).as_posix() for cat in NAMES for p in (ROOT/cat).rglob('*')
                  if p.is_file() and p.suffix.lower() != '.png' and p.name != 'README.md'}
    if unexpected:
        raise ValueError(f'Unexpected files in category folders: {sorted(unexpected)[:10]}')
    decoded = set()
    for item in entries:
        data = destination(item).read_bytes()
        check_bytes(data, item)
        # Equal bytes only need one expensive silhouette inspection per shape.
        key = (item['sha256'], item['category'] == 'cards')
        if key not in decoded:
            check_image(data, item)
            decoded.add(key)
    print(f'Validated {len(entries):,} files: paths, SHA-256, bytes, PNG dimensions and alpha silhouettes.')


def spreadsheet_safe(value):
    text = str(value or '')
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text


def export_csv(entries):
    with (ROOT/'catalog.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['id', 'name', 'aliases', 'category', 'path', 'upstream_path', 'width', 'height', 'bytes', 'sha256', 'source_kind', 'source_url', 'source_reference'])
        for item in entries:
            writer.writerow([spreadsheet_safe(item['id']), spreadsheet_safe(item['name']), spreadsheet_safe('; '.join(item.get('aliases', [])))] +
                            [spreadsheet_safe(item[k]) for k in ('category', 'path', 'upstreamPath', 'width', 'height', 'bytes', 'sha256')] +
                            [spreadsheet_safe(item['source'].get(k)) for k in ('kind', 'url', 'reference')])


def slugify(value):
    value = str(value or '').replace('&', ' and ').replace('+', ' plus ')
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')


def clean_aliases(values):
    aliases, seen = [], set()
    for value in values or []:
        value = ' '.join(str(value).split())
        folded = value.casefold()
        if value and folded not in seen:
            aliases.append(value)
            seen.add(folded)
    return aliases


def assign_paths(entries):
    used = defaultdict(set)
    for item in sorted(entries, key=lambda x: (x['category'], x['name'].casefold(), x['id'])):
        candidates = [item.pop('seoSlug', None), item['name'], *item.get('aliases', []), item['id']]
        base = next((slugify(value) for value in candidates if slugify(value)), 'payment-icon')[:180].strip('-')
        stem, number = base, 2
        while stem in used[item['category']]:
            stem = f'{base}-{number}'
            number += 1
        used[item['category']].add(stem)
        item['path'] = f"{item['category']}/{stem}.png"


def materialize_existing(entries, old_entries):
    old_by_id = {(item['category'], item['id']): item for item in old_entries}
    copied = 0
    for item in entries:
        old = old_by_id.get((item['category'], item['id']))
        if not old:
            continue
        source, target = ROOT / old['path'], ROOT / item['path']
        if source == target or not source.is_file() or target.exists():
            continue
        data = source.read_bytes()
        if len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied += 1
    print(f'Reused {copied:,} unchanged PNGs at their descriptive paths.')


def markdown_text(value):
    return (str(value).replace('\\', '\\\\').replace('|', '\\|').replace('[', '\\[').replace(']', '\\]')
            .replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;'))


def export_category_readmes(entries):
    groups = defaultdict(list)
    for item in entries:
        groups[item['category']].append(item)
    for category, label in NAMES.items():
        batch = sorted(groups[category], key=lambda x: (x['name'].casefold(), x['path']))
        title = 'Payment method icons and logos' if category == 'payment-methods' else f'{label} payment icons and assets'
        lines = [f'# {title}', '',
                 f'{len(batch):,} descriptive PNG files from the [Aurato Global Payment Icon Pack](../README.md).', '']
        if category == 'cards':
            lines += ['Card filenames combine market, issuer and product information for discoverability.',
                      'Browse the complete machine-readable [card catalog](../catalog/cards.json) or use the [searchable gallery](../index.html).', '']
        else:
            lines += ['| Name | Aliases | PNG |', '| --- | --- | --- |']
            for item in batch:
                aliases = ', '.join(item.get('aliases', [])) or '—'
                filename = item['path'].split('/')[-1]
                lines.append(f"| {markdown_text(item['name'])} | {markdown_text(aliases)} | [{filename}]({filename}) |")
            lines.append('')
        (ROOT/category/'README.md').write_text('\n'.join(lines), encoding='utf-8')


def prune(entries):
    expected = {item['path'] for item in entries}
    retired = sorted(p for category in NAMES for p in (ROOT/category).rglob('*.png')
                     if p.relative_to(ROOT).as_posix() not in expected)
    for path in retired:
        path.unlink()
    print(f'Removed {len(retired):,} retired or superseded PNG paths.')


def import_snapshot(path):
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('Expected a nonempty JSON array from scripts/export.sql')
    _, old_entries = load_catalog()
    entries = []
    for row in rows:
        item = {k: row[k] for k in ('id', 'name', 'category', 'width', 'height', 'bytes', 'sha256')}
        item['upstreamPath'] = row['upstream_path']
        item['seoSlug'] = row.get('seo_slug')
        item['aliases'] = clean_aliases(row.get('aliases'))
        item['source'] = {'kind': row['source_kind'], 'url': row['source_url']}
        if item['source']['url'] and item['source']['url'].startswith('/'):
            item['source']['reference'] = item['source']['url']
            item['source']['url'] = None
        entries.append(item)
    present = {item['category'] for item in entries}
    missing = set(NAMES) - present
    if not missing <= PRESERVED_CATEGORIES:
        raise ValueError(f'Unexpected missing categories: {sorted(missing)}')
    for old in old_entries:
        if old['category'] in missing:
            preserved = {**old, 'upstreamPath': old.get('upstreamPath', old['path']),
                         'aliases': clean_aliases(old.get('aliases')), 'seoSlug': None}
            preserved.pop('path', None)
            entries.append(preserved)
    assign_paths(entries)
    entries.sort(key=lambda x: x['path'])
    for item in entries:
        check_entry(item)
    if len({x['path'] for x in entries}) != len(entries):
        raise ValueError('Duplicate asset paths in snapshot')
    counts = Counter(x['category'] for x in entries)
    if set(counts) != set(NAMES):
        raise ValueError('Snapshot must contain all 13 categories')
    old_paths = {x['path'] for x in old_entries}
    new_paths = {x['path'] for x in entries}
    index, _ = load_catalog()
    index.update(schemaVersion=2, version=date.today().strftime('%Y.%m.%d'), updatedAt=date.today().isoformat(), assetCount=len(entries),
                 primaryIconCount=len(entries)-counts['cards'], cardCount=counts['cards'])
    materialize_existing(entries, old_entries)
    for category in index['categories']:
        category['count'] = counts[category['id']]
        (ROOT/category['path']).write_text(json.dumps([x for x in entries if x['category'] == category['id']], indent=2, ensure_ascii=False)+'\n')
    (ROOT/'catalog.json').write_text(json.dumps(index, indent=2)+'\n')
    export_csv(entries)
    export_category_readmes(entries)
    print(f'Imported {len(entries)} entries. {len(new_paths-old_paths)} new paths, {len(old_paths-new_paths)} removed paths.')
    print('Review the diff, then run download and validate. Remove retired files explicitly; validation detects them.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['download', 'validate', 'export', 'import', 'prune'])
    parser.add_argument('snapshot', nargs='?', type=Path)
    parser.add_argument('--workers', type=int, default=12)
    args = parser.parse_args()
    if args.command == 'import':
        if not args.snapshot:
            parser.error('import requires a JSON snapshot path')
        import_snapshot(args.snapshot)
        return
    _, entries = load_catalog()
    if args.command == 'download':
        if not 1 <= args.workers <= 48:
            parser.error('--workers must be between 1 and 48')
        download(entries, args.workers)
    elif args.command == 'validate':
        validate(entries)
    elif args.command == 'prune':
        prune(entries)
    elif args.command == 'export':
        export_csv(entries)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
