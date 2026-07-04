#!/bin/bash
# Fill missing pattern_type x purpose combinations (skip types already covered).
set -e
cd "$(dirname "$0")/.."

TYPES=(yun ruyi-cloud huiwen juancao interlocking-lotus tuanlong baoxianghua \
       lianhua mudan seawater-cliff eight-treasures phoenix dragon \
       geometric-border shanshui)

# Per-purpose targets and which types we already have
have() {
  # $1 = purpose, $2 = type_key (English)
  python -c "
import sqlite3
with sqlite3.connect('db/patterns.db') as c:
    n = c.execute('SELECT COUNT(*) FROM patterns WHERE purpose=? AND source_ref LIKE ?', ('$1', '$2#%')).fetchone()[0]
print(n)
"
}

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== Phase B fill: element-corner ==="
for t in "${TYPES[@]}"; do
  n=$(have "element-corner" "$t")
  if [ "$n" -lt 2 ]; then
    need=$((2 - n))
    log "  $t: have=$n, generating $need more"
    python scripts/ai_generate.py --purpose=element-corner --type="$t" --count="$need" --vectorize --concurrency=3 2>&1 | grep -E "^\[(gen|ok|err|summary)\]" | tail -5
  fi
done

log "=== Phase C fill: element-filler ==="
for t in "${TYPES[@]}"; do
  n=$(have "element-filler" "$t")
  if [ "$n" -lt 2 ]; then
    need=$((2 - n))
    log "  $t: have=$n, generating $need more"
    python scripts/ai_generate.py --purpose=element-filler --type="$t" --count="$need" --vectorize --concurrency=3 2>&1 | grep -E "^\[(gen|ok|err|summary)\]" | tail -5
  fi
done

log "=== Phase D fill: element-border ==="
for t in "${TYPES[@]}"; do
  n=$(have "element-border" "$t")
  if [ "$n" -lt 2 ]; then
    need=$((2 - n))
    log "  $t: have=$n, generating $need more"
    python scripts/ai_generate.py --purpose=element-border --type="$t" --count="$need" --vectorize --concurrency=3 2>&1 | grep -E "^\[(gen|ok|err|summary)\]" | tail -5
  fi
done

log "=== Phase E fill: tile ==="
for t in "${TYPES[@]}"; do
  n=$(have "tile" "$t")
  if [ "$n" -lt 1 ]; then
    log "  $t: have=$n, generating 1"
    python scripts/ai_generate.py --purpose=tile --type="$t" --count=1 --concurrency=3 2>&1 | grep -E "^\[(gen|ok|err|summary)\]" | tail -5
  fi
done

log "=== Phase F fill: hero ==="
for t in "${TYPES[@]}"; do
  n=$(have "hero" "$t")
  if [ "$n" -lt 1 ]; then
    log "  $t: have=$n, generating 1"
    python scripts/ai_generate.py --purpose=hero --type="$t" --count=1 --concurrency=3 2>&1 | grep -E "^\[(gen|ok|err|summary)\]" | tail -5
  fi
done

log "=== ALL FILLS DONE ==="
python scripts/stats.py
