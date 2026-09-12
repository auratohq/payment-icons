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
import sys
import time
from urllib.request import Request, urlopen

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://htmonfohxuipdpmznlcj.supabase.co/storage/v1/object/public/entity-assets/'
NAMES = {'banks': 'Banks', 'cards': 'Cards', 'compliance': 'Compliance',
         'currencies': 'Currencies', 'identifiers': 'Identifiers', 'markets': 'Markets',
         'operators': 'Operators', 'payment-methods': 'Payment methods', 'psps': 'PSPs',
         'regulators': 'Regulators', 'schemes': 'Schemes', 'standards': 'Standards', 'systems': 'Systems'}


def check_entry(item):
    category = item['category']
    path = item['path']
    if category not in NAMES or not isinstance(path, str):
        raise ValueError('Unknown category or invalid path')
    parts = PurePosixPath(path).parts
    if len(parts) != 2 or parts[0] != category or not re.fullmatch(r'[a-zA-Z0-9_-]+\.png', parts[1]):
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
    if index.get('schemaVersion') != 1 or index.get('sourceBaseUrl') != SOURCE:
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
    if any(alpha.getpixel(p) != 0 for p in ((0, 0), (width-1, 0), (0, height-1), (width-1, height-1))):
        raise ValueError(f'Corners must be transparent: {item["path"]}')
    if item['category'] == 'cards':
        # Card artwork deliberately keeps its own frame and corner treatment.
        if alpha.getpixel((width//2, height//2)) != 255:
            raise ValueError(f'Card center must be opaque: {item["path"]}')
        return
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
        for candidate in [destination(first), cached]:
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
                    request = Request(SOURCE + first['path'] + suffix, headers={'User-Agent': 'Aurato-Payment-Icons/1.0'})
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
    actual = {p.relative_to(ROOT).as_posix() for cat in NAMES for p in (ROOT/cat).rglob('*') if p.is_file()}
    if expected != actual:
        raise ValueError(f'Missing files: {sorted(expected-actual)[:10]}; unlisted files: {sorted(actual-expected)[:10]}')
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
        writer = csv.writer(stream)
        writer.writerow(['id', 'name', 'category', 'path', 'width', 'height', 'bytes', 'sha256', 'source_kind', 'source_url', 'source_reference'])
        for item in entries:
            writer.writerow([spreadsheet_safe(item[k]) for k in ('id', 'name', 'category', 'path', 'width', 'height', 'bytes', 'sha256')] +
                            [spreadsheet_safe(item['source'].get(k)) for k in ('kind', 'url', 'reference')])


def import_snapshot(path):
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('Expected a nonempty JSON array from scripts/export.sql')
    entries = []
    for row in rows:
        item = {k: row[k] for k in ('id', 'name', 'category', 'path', 'width', 'height', 'bytes', 'sha256')}
        item['source'] = {'kind': row['source_kind'], 'url': row['source_url']}
        if item['source']['url'] and item['source']['url'].startswith('/'):
            item['source']['reference'] = item['source']['url']
            item['source']['url'] = None
        check_entry(item)
        entries.append(item)
    entries.sort(key=lambda x: x['path'])
    if len({x['path'] for x in entries}) != len(entries):
        raise ValueError('Duplicate asset paths in snapshot')
    counts = Counter(x['category'] for x in entries)
    if set(counts) != set(NAMES):
        raise ValueError('Snapshot must contain all 13 categories')
    index, old = load_catalog()
    old_paths = {x['path'] for x in old}
    new_paths = {x['path'] for x in entries}
    index.update(updatedAt=date.today().isoformat(), assetCount=len(entries),
                 primaryIconCount=len(entries)-counts['cards'], cardCount=counts['cards'])
    for category in index['categories']:
        category['count'] = counts[category['id']]
        (ROOT/category['path']).write_text(json.dumps([x for x in entries if x['category'] == category['id']], indent=2, ensure_ascii=False)+'\n')
    (ROOT/'catalog.json').write_text(json.dumps(index, indent=2)+'\n')
    export_csv(entries)
    print(f'Imported {len(entries)} entries. {len(new_paths-old_paths)} new paths, {len(old_paths-new_paths)} removed paths.')
    print('Review the diff, then run download and validate. Remove retired files explicitly; validation detects them.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['download', 'validate', 'export', 'import'])
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
        if not 1 <= args.workers <= 24:
            parser.error('--workers must be between 1 and 24')
        download(entries, args.workers)
    elif args.command == 'validate':
        validate(entries)
    elif args.command == 'export':
        export_csv(entries)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
