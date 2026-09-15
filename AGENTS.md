# Repository guidance

- This repository mirrors approved public Aurato assets. Do not modify production Supabase as part of repository maintenance.
- Preserve category folders at the root and descriptive lowercase hyphenated filenames. Keep stable Aurato IDs and exact Supabase object paths in catalog metadata, not public filenames. `cards/` is the explicit aspect-ratio exception.
- Keep PNG bytes identical to the committed catalog's SHA-256 and byte size. Do not hide image shape problems with CSS clipping.
- Preserve provenance and distinguish generated artwork from recorded brand sources. Do not apply the code license to third-party assets.
- Run the collection validator and script tests after changes affecting assets or maintenance code. Inspect the gallery on desktop and mobile after UI changes.
- Use the existing plain HTML/CSS/JavaScript gallery. No frontend build pipeline is required.
