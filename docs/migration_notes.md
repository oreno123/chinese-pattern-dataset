# Migration Notes — From Wenmai to pattern-dataset

Investigation of the wenmai project's existing pattern/element data structures, captured before writing the migration script. Counts adjusted accordingly.

## Counts (verified 2026-07-04)

| Source | wenmai-qinghua | wenmai-basics | wenmai-shanjing | elements |
|---|---|---|---|---|
| Count | 335 | **21** | 25 | **60** |

Plan originally estimated 17 basics + 54 elements; **actual is 21 + 60**. Update T3 done-criteria accordingly.

## qinghuaPatterns.ts structure

Path: `D:\desktop\纹脉\wenmai\src\data\qinghuaPatterns.ts`

Each record fields (verified):
- `id`: `"qh-1"` (string with non-zero-padded int; numbers skip — qh-1,2,3,4,6,7,8,...)
- `name`: `"缠枝花卉纹"` (Chinese name)
- `type`: one of `"植物纹" | "动物纹" | "几何纹" | "吉祥纹" | "其他"`
- `series`: always `"qinghua"`
- `rarity`: always `"common"`
- `tags`: `string[]`, e.g. `["植物纹", "缠枝花卉", "圆形", "连续纹"]`
- `image`: `"/patterns/qinghua/qh-1.webp"` (relative URL)

TS schema:
```ts
export const QINGHUA_PATTERNS: Pattern[] = [
  { id: "qh-1", name: "...", type: "...", series: "qinghua" as SeriesId, rarity: "common" as Rarity, tags: [...], image: "/patterns/qinghua/qh-1.webp" },
  ...
];
```

**Parsing strategy**: regex-extract each `{ ... }` record (one per line), then key-value parse. Avoid `json.loads` on the whole array — TypeScript uses `as SeriesId` casts that break JSON.

**Mapping**:
- `pattern_id`: zero-pad id → `qh-001`, `qh-002`, ..., `qh-335`
- `source_id`: `wenmai-qinghua`
- `source_ref`: original `id` (`qh-1`)
- `pattern_type`: take from `name` if it ends in `纹` (more specific than `type` field which is just the category); keep `type` as a tag instead
- `title`: `name`
- `tags`: union of `tags` array + `type` field
- `review_status`: `approved` (already human-classified via Opus v5)

## basics (21 patterns in `public/patterns/*.webp`)

Files (21):
```
baoxiang.webp         binglie.webp          duoyun.webp
fengniao_corner.webp  huiwen.webp           juancao-fixed.webp
juancao.webp          kuilong_taotie.webp   lianhua.webp
liuyun.webp           panlong.webp          ruyi_cloud.webp
ruyi_corner.webp      shenglong.webp        taotie_shang.webp
taotie_zhou.webp      tuanlong.webp         wanzi_endless.webp
xiangyun.webp         xinglong.webp         yunlei.webp
```

**No TS metadata file** — these are loose files. Map pattern_type by filename keyword:
- `baoxiang` / `lianhua` → 宝相花
- `huiwen` / `wanzi_endless` → 回纹
- `juancao` / `juancao-fixed` → 卷草纹
- `yunlei` / `duoyun` / `xiangyun` / `liuyun` / `ruyi_cloud` → 云纹
- `tuanlong` / `panlong` / `shenglong` / `xinglong` → 龙纹
- `kuilong_taotie` / `taotie_shang` / `taotie_zhou` → 饕餮纹/龙纹
- `binglie` / `ruyi_corner` / `fengniao_corner` → other / 几何

Mapping can be a lookup dict in the script; unknown → `other`.

## shanjing (25 patterns in `public/patterns/shanjing/*.webp`)

Files are named in Chinese: `人身龙首神·龙吟守山纹.webp`. All 25 are 瑞兽/山海经 type.

**Mapping**:
- `pattern_id`: `shanjing-001` to `shanjing-025` (by alphabetical/sorted order)
- `pattern_type`: `山海经` (per taxonomy.json)
- `title`: filename stem (e.g. `人身龙首神·龙吟守山纹`)

## elements (60 total via manifest.json)

Path: `D:\desktop\纹脉\wenmai\public\elements\manifest.json`

Structure:
```json
{
  "total": 60,
  "sources": ["huiwen", "juanco2", "tuanlong", "yunlei", "shanjing"],
  "bySource": {
    "huiwen":   [{id, file, source}, ...],   // 1 element
    "juanco2":  [...],                        // 1 element
    "tuanlong": [...],                        // 8 elements
    "yunlei":   [...],                        // 25 elements
    "shanjing": [{id, file, source, name}, ...] // 25 elements
  }
}
```

Each element: `{id: "huiwen_elem_00", file: "huiwen_elem_00.webp", source: "huiwen"}`.
Shanjing elements also have `name` (Chinese label).

**approved.json**: plain list of 60 element_id strings. **All 60 are approved.**

**Mapping**:
- `element_id`: directly use `id` (e.g. `huiwen_elem_00`)
- `pattern_id`: map by source prefix:
  - `huiwen` → `basics-huiwen`
  - `juanco2` → `basics-juancao` (note `juancao2` vs `juancao` — script should match either)
  - `tuanlong` → `basics-tuanlong`
  - `yunlei` → `basics-yunlei`
  - `shanjing` → **first shanjing pattern** (since 25 elements don't split by parent pattern, attach to `shanjing-001` as placeholder; refine later when individual element-to-pattern mapping is needed)
- `approved`: all 1 (entire approved.json list = all elements)
- `extractor`: `dbscan-v1` (per wenmai's element pipeline)

## Files this enables

- `scripts/migrate_from_wenmai.py` — full migration
- Tests assert: 335 qinghua, 21 basics, 25 shanjing, 60 elements
