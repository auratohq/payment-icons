# Contributing

An improvement can be a corrected icon, better provenance, a new payment entity, a gallery fix or clearer documentation.

## Propose an asset

1. Search the catalog first to avoid a duplicate record.
2. Open an issue with the entity name, category, official public source and proposed file path.
3. Explain whether the artwork is official, adapted, generated or a designed category symbol. Include any relevant rights information; do not assume every logo has the same license.
4. Keep the stable Aurato ID as the filename. Primary icons are 256 × 256 PNGs with an opaque rounded-square interior and transparent exterior corners. Cards are 406 × 256 PNGs and retain their card proportions.

Files live directly in category folders at the repository root. Do not introduce `v1/`, `primary-icons/`, backup folders or copies at extra nesting levels.

## Maintain the snapshot

The repository is a versioned mirror of the approved public Aurato asset catalog. Production Supabase Storage is upstream. Repository scripts never write to Supabase.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

For a new upstream snapshot, an authorized maintainer runs the read-only query in `scripts/export.sql` using the existing Supabase connection, saves the result rows as a JSON array, then runs:

```sh
python scripts/collection.py import /path/to/snapshot.json
python scripts/collection.py download
python scripts/collection.py validate
python -m unittest discover -s scripts -p 'test_*.py'
```

Review the catalog diff, provenance, bytes, and retired paths. Remove retired files explicitly; the validator rejects unlisted files. The import command does not delete anything. Set `catalog.json`'s version and add a changelog entry when preparing a release.

Commit the approved catalog and matching PNGs together when working locally. The **Sync approved snapshot** workflow can also materialize the exact catalog on `main`: it only downloads bytes matching the committed SHA-256 and size, validates the collection, then commits missing or changed PNGs. It cannot discover a new upstream catalog or silently accept changed bytes. Its concurrency group serializes synchronization runs; a competing branch update causes a normal push rejection rather than a forced overwrite.

## Check code and gallery changes

```sh
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/collection.py validate
python -m http.server 8000
```

Open `http://localhost:8000`. Check desktop and mobile, search, category and source filters, preview backgrounds, keyboard navigation, the detail dialog and PNG downloads. The gallery uses browser JavaScript and CSS with no build step, analytics or third-party runtime requests.

For the automated browser checks (Node.js 24):

```sh
npm ci --ignore-scripts
npx playwright install --with-deps chromium
npm run test:gallery
```

These development-only dependencies are not used by the served gallery. CI keeps desktop and mobile screenshots as temporary build artifacts.

## Pull requests

Describe the problem, the change, and what you verified. Asset changes should identify their source and include updated hashes and byte sizes. Keep corrections focused. Never commit credentials, service-role keys, database dumps or unrelated production data.
