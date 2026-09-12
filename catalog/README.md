# Catalog format

`/catalog.json` is the versioned index. Each item in `categories` points to one JSON array at `/catalog/<category>.json`. `/catalog.csv` combines all records for spreadsheet use.

| Field | Meaning |
| --- | --- |
| `id` | Stable Aurato record ID |
| `name` | Display name from the source catalog |
| `category` | Root asset folder |
| `path` | Repository-relative PNG path, also the upstream bucket-relative path |
| `width`, `height` | Native PNG pixel dimensions |
| `bytes` | Exact file size |
| `sha256` | Lowercase SHA-256 of the complete file bytes |
| `source.kind` | Recorded provenance label; labels containing `generated` identify generated artwork |
| `source.url` | Recorded absolute HTTP(S) source URL, or `null` |
| `source.reference` | Optional older relative source reference, retained as text |

Names are not necessarily unique. Use `path` to identify a file and `id` to connect it to the Aurato record. Several records may intentionally use identical image bytes, which is reflected in their shared hash. Counts describe records/files, not distinct logo designs.

All paths are one category plus one filename. Primary icons are 256 × 256; cards are 406 × 256. Every primary icon contains a rounded-square base in its alpha channel. The gallery does not add a CSS radius to disguise a different underlying silhouette.

The index's `updatedAt` describes the snapshot date; `version` identifies the maintained collection version. `sourceBaseUrl` is the upstream public bucket URL, and each `path` can be appended to it. Source URLs and origin labels describe provenance rather than licensing; see [RIGHTS.md](../RIGHTS.md).
