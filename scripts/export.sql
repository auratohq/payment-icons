-- Read-only export of the published public icon snapshot.
-- Save the result rows as a JSON array, then run:
-- python scripts/collection.py import /path/to/snapshot.json
select
  a.target_id as id,
  coalesce(e.name, s.name, r.name, c.name, a.alt_text, a.target_id) as name,
  split_part(a.object_path, '/', 1) as category,
  a.object_path as path,
  a.width, a.height, a.byte_size as bytes, a.sha256,
  a.source_kind, a.source_url
from public.assets a
left join public.entities e on a.target_type = 'entity' and e.id = a.target_id
left join public.standards s on a.target_type = 'standard' and s.id = a.target_id
left join public.regulations r on a.target_type = 'regulation' and r.id = a.target_id
left join public.card_records c on a.target_type = 'card' and c.id = a.target_id
where a.bucket_id = 'entity-assets'
  and a.is_current
  and a.status = 'published'
order by a.object_path;
