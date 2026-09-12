# Runtime Smoke Test — 検出ロジック（Phase 5.5 の詳細手順）

SKILL.md 本文の Phase 5.5 は「smoke test を要否判定 → 必要なら dev-workflow:ui-verify で実行 → findings を triage」の骨格を持つ。本ファイルは (1) 自己再帰防止の self-lock guard と (2) runtime-sensitive な変更を検出する deterministic gate の bash を持つ。Phase 5.5 Step 0 / Step 1 から参照される。

## Step 0: Self-lock guard（PostToolUse 自己再帰防止）

**目的**: 将来 feature-dev に PostToolUse hook が入って Phase 5.5 を自動トリガーする構成になった場合、Phase 5.5 内の Edit / Bash が再度 PostToolUse を発火させ、無限ループに陥る可能性がある。TTL ベースの self-lock を持つことで、同一プロジェクトで短期間に Phase 5.5 が重複起動するのを防ぐ。

**現状の振る舞い**: command 経由の手動実行ではループは発生しないが、PostToolUse hook を将来導入する際に lock 機構が無いと事故るため、template を先に入れる。lock が active な場合は Phase 5.5 全体を skip して Phase 6 へ進む（hook 経由起動の場合は `exit 0` 相当でハーネス側が早期復帰）。

```bash
TARGET_PATH=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
HASH=$(echo "$TARGET_PATH" | shasum | cut -c1-12)
LOCK=/tmp/feature-dev-${HASH}.lock
TTL=600

if [ -f "$LOCK" ]; then
  # macOS BSD: stat -f %m / Linux GNU: stat -c %Y の dual path で portability 確保
  MTIME=$(stat -f %m "$LOCK" 2>/dev/null || stat -c %Y "$LOCK" 2>/dev/null || echo 0)
  AGE=$(($(date +%s) - MTIME))
  if [ "$AGE" -lt "$TTL" ]; then
    echo "[self-lock] active (age=${AGE}s < ttl=${TTL}s), skipping Phase 5.5"
    # command 内実行時は Phase 6 へ進む / hook 経由起動時は ハーネスが exit 0 として扱う
    SKIP_PHASE_5_5=1
  fi
fi

if [ -z "$SKIP_PHASE_5_5" ]; then
  touch "$LOCK"   # 新規取得 or TTL 切れ → 取り直し
fi
```

`SKIP_PHASE_5_5` が `1` の場合は Step 1〜4 を skip して **Phase 6** へ進む。

## Step 1: Deterministic Detection（gate check）

Run the following Bash check to decide whether smoke test is **required** or **optional**:

```bash
# Detect runtime-sensitive changes in the working tree
git diff --name-only HEAD 2>/dev/null > /tmp/feature-dev-changed-files.txt
git diff HEAD 2>/dev/null > /tmp/feature-dev-diff.txt

REQUIRED_REASONS=()

# Pattern 1: DB client / ORM initialization
grep -qE "(PrismaClient|createClient|drizzle\(|new Sequelize|mongoose\.connect|TypeORM)" /tmp/feature-dev-diff.txt && \
  REQUIRED_REASONS+=("DB client / ORM 初期化変更")

# Pattern 2: Environment variable wiring
grep -qE "(process\.env\.|import\.meta\.env\.|getEnv\()" /tmp/feature-dev-diff.txt && \
  REQUIRED_REASONS+=("環境変数依存の追加・変更")

# Pattern 3: Middleware / proxy / lazy-init
grep -qE "(middleware|Proxy\(|defineProxy|lazy\(|createServer|app\.use)" /tmp/feature-dev-diff.txt && \
  REQUIRED_REASONS+=("middleware / proxy / lazy-init 変更")

# Pattern 4: New route files (Next.js / SvelteKit / Remix / generic routes)
grep -qE "(pages/.*\.(tsx?|jsx?)$|app/.*/(page|route)\.(tsx?|jsx?)$|routes/.*\.(ts|js)$)" /tmp/feature-dev-changed-files.txt && \
  REQUIRED_REASONS+=("新規 route の追加・変更")

if [ ${#REQUIRED_REASONS[@]} -gt 0 ]; then
  echo "REQUIRED: smoke test 必須"
  printf '  - %s\n' "${REQUIRED_REASONS[@]}"
else
  echo "OPTIONAL: 静的変換のみの変更。skip 候補だがユーザ判断"
fi
```

