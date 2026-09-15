# Changelog

## 2026.09.15

- Synchronized the latest approved Aurato snapshot: 8,089 PNG assets across 10 categories.
- Removed the retired Compliance, Identifiers and Standards categories and made snapshot imports reject missing active categories instead of silently retaining stale folders.
- Added the latest 25 published PSP icons.
- Updated 1,485 existing records with current image bytes, added 60 newly published records and retired 48 records no longer in the approved snapshot.
- Migrated public filenames from internal record keys to descriptive lowercase slugs such as `payment-methods/apple-pay.png`.
- Added aliases and separate upstream object paths to catalog schema v2, keeping repository paths readable without losing traceability.
- Added searchable category indexes and the Aurato Global Payment Icon Pack banner.
- Improved snapshot reuse so shared artwork hashes avoid unnecessary upstream downloads.

## 2026.09.12

- Initial public snapshot: 8,284 PNG assets across 13 categories.
- 2,274 rounded-square icons at 256 × 256 and 6,010 card images at 406 × 256.
- Flat category folders using stable Aurato record IDs.
- JSON and CSV catalogs with names, dimensions, sizes, hashes and recorded provenance.
- Searchable responsive gallery with background previews and individual downloads.
- Read-only upstream export, hash-pinned downloads, image validation, contribution guidance and CI.
