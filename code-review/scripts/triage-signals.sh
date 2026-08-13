#!/usr/bin/env bash
# Phase 0 用の決定的シグナルダイジェストを出力する。
#
# 目的: オーケストレーター（メインコンテキスト）に diff 全文を載せずに Phase 0 を回す。
# diff はファイルへ保存し、本スクリプトは「事実」だけを compact に出力する。
# モード決定・体数決定は triage-guide.md が行う。**ただし `size_tier` の帯境界だけは
# 本スクリプトに複製されている**（正本は triage-guide.md `## 6.2`。変更時は両方直すこと）。
# 語彙は triage-guide.md `## 3`（観点判定表 / red-flag）と
# triage-dynamic-gates.md `## 8.5`（surface 判定）に一致させること。
# 一時ファイルのパス導出は lib/review-paths.sh が正本（式をここに複製しない）。
#
# 使い方:
#   triage-signals.sh --pr <N> [--out <diff path>]      # review: gh pr diff で取得
#   triage-signals.sh --base <ref> [--out <diff path>]  # self-review: base..HEAD + staged + unstaged
#   triage-signals.sh --base <ref> --staged             # self-review --staged: staged のみ
#
# 出力は stdout（セクション区切りの plain text）。diff 本体は stdout に出さない。
set -uo pipefail

PR=""; BASE=""; OUT=""; STAGED=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pr)     [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    --base)   [ $# -ge 2 ] || { echo "FATAL: --base に値が必要" >&2; exit 2; }; BASE="$2"; shift 2 ;;
    --out)    [ $# -ge 2 ] || { echo "FATAL: --out に値が必要" >&2; exit 2; }; OUT="$2"; shift 2 ;;
    --staged) STAGED=1; shift ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "$PR" || exit 2
WT="$REVIEW_WT"
[ -n "$OUT" ] || OUT=$(review_path diff)

# ---- diff の取得 -----------------------------------------------------------
# **取得前に $OUT を必ず消す**。残したまま取得に失敗すると、`mv` されないだけで
# 前回実行の diff が残り、下の `-s` チェックを通過して「古い diff で完走」する
# （成功時のみ mv するガードは空ファイル対策であって stale 対策ではない）。
trap 'rm -f "$OUT.tmp"' EXIT
rm -f "$OUT"
if [ -n "$PR" ]; then
  BASE=$(gh pr view "$PR" --json baseRefName -q .baseRefName 2>/dev/null)
  gh pr diff "$PR" > "$OUT.tmp" || { echo "FATAL: gh pr diff に失敗した (PR=${PR})" >&2; exit 1; }
  mv "$OUT.tmp" "$OUT"
elif [ "$STAGED" = "1" ]; then
  # ステージ済みのみ（未ステージ・コミット済みは対象外）
  git diff --cached > "$OUT.tmp" || { echo "FATAL: git diff --cached に失敗した" >&2; exit 1; }
  mv "$OUT.tmp" "$OUT"
else
  [ -n "$BASE" ] || { echo "FATAL: --pr か --base のどちらかが必須" >&2; exit 2; }
  # base ref を先に解決する。ブレースグループの終了ステータスは**最後のコマンド**の
  # ものになるため、1 本目が fatal でも 3 本目が成功すれば `&&` が通ってしまい、
  # コミット済み分が欠落した部分 diff が「正常な diff」として確定していた
  git rev-parse --verify -q "${BASE}^{commit}" >/dev/null \
    || { echo "FATAL: base ref を解決できない: ${BASE}" >&2; exit 2; }
  # base..HEAD（2 ドット = 直接比較。従来挙動）+ staged + unstaged の 3 系統。
  # 3 系統が重なるファイルは行数が重複計上されうるが、帯を分けるには十分な粗さ
  : > "$OUT.tmp"
  git diff "${BASE}..HEAD" >> "$OUT.tmp" || { echo "FATAL: git diff ${BASE}..HEAD に失敗した" >&2; exit 1; }
  git diff --cached      >> "$OUT.tmp" || { echo "FATAL: git diff --cached に失敗した" >&2; exit 1; }
  git diff               >> "$OUT.tmp" || { echo "FATAL: git diff に失敗した" >&2; exit 1; }
  mv "$OUT.tmp" "$OUT"
fi
if [ ! -s "$OUT" ]; then
  echo "FATAL: diff が空 (PR=${PR} BASE=${BASE} STAGED=${STAGED})" >&2
  exit 1
fi

# 変更行を「所属ファイルのクラス付き」で取り出す。
# クラスを付けないと md 見出し `## x` を code コメントと誤検出する等の偽陽性が出るため、
# 内容シグナルは必ずクラスで絞ってから grep する。形式は `<class>\t<path>\t<内容>`。
extract() { # extract <+|-> : 追加行 or 削除行
  awk -v sign="$1" '
    /^diff --git / {
      f=$4; sub(/^b\//,"",f)
      if (f ~ /(^|\/)(dist|build|vendor)\/|\.lock$|package-lock\.json$|yarn\.lock$|pnpm-lock\.yaml$|\.snap$|\.generated\./) c="gen"
      else if (f ~ /\.(test|spec)\.|(^|\/)(__tests__|tests)\//) c="test"
      else if (f ~ /\.md$|(^|\/)docs\//) c="doc"
      else c="core"
      next
    }
    substr($0,1,1)==sign && substr($0,1,3)!=sign sign sign {
      printf "%s\t%s\t%s\n", c, f, substr($0,2)
    }' "$OUT"
}
ADDED_ALL=$(extract '+')
REMOVED_ALL=$(extract '-')
# code = gen / doc を除いた行（test は含む: テストコードもコードとして判定対象）
ADDED_CODE=$(printf '%s\n' "$ADDED_ALL" | awk -F'\t' '$1!="gen" && $1!="doc"')
ADDED_DOC=$(printf '%s\n' "$ADDED_ALL" | awk -F'\t' '$1=="doc"')
REMOVED_CODE=$(printf '%s\n' "$REMOVED_ALL" | awk -F'\t' '$1!="gen" && $1!="doc"')

echo "## meta"
echo "diff_file=$OUT"
# 全 agent 共通の可変部を書き出す先。**このスクリプトは中身を作らない**（内容は
# オーケストレーターが組む）。パスだけをここで配って導出式の複製を防ぐ（#124 (c)）
# 配る前に前回の残骸を必ず消す。中身はオーケストレーターが書くので、消さないと
# 「読めるが前回の値」を全 agent が掴む（publish に到達しない回＝掃除が走らない回がある）。
# diff 側と同じ「配る前に消す」規約に揃える — 縮退先は誤値ではなく欠測
rm -f "$(review_path agentctx)"
echo "agent_ctx_file=$(review_path agentctx)"
echo "base=${BASE:-unknown}"
echo "worktree=$WT"

# ---- ファイル分類と規模 ---------------------------------------------------
# 分類: gen（lock・生成物）/ test / doc / core。core の定義は triage-guide `## 6.1`
if [ -n "$PR" ]; then
  NUMSTAT=$(git diff --numstat "origin/${BASE}...HEAD" 2>/dev/null)
  [ -n "$NUMSTAT" ] || NUMSTAT=$(git diff --numstat "${BASE}...HEAD" 2>/dev/null)
elif [ "$STAGED" = "1" ]; then
  NUMSTAT=$(git diff --cached --numstat 2>/dev/null)
else
  NUMSTAT=$({ git diff --numstat "${BASE}..HEAD"; git diff --cached --numstat; git diff --numstat; } 2>/dev/null | grep -v '^$')
fi

# 同一パスが複数系統（base..HEAD / staged / unstaged）に現れるため、パス単位で集約する。
# 集約しないとファイル数が重複計上され size_tier が実態より大きく出る
CLASSIFIED=$(printf '%s\n' "$NUMSTAT" | awk -F'\t' '
  NF>=3 && $1 ~ /^[0-9]+$/ { a[$3]+=$1; d[$3]+=$2 }
  END {
    for (p in a) {
      c="core"
      if (p ~ /(^|\/)(dist|build|vendor)\/|\.lock$|package-lock\.json$|yarn\.lock$|pnpm-lock\.yaml$|\.snap$|\.generated\./) c="gen"
      else if (p ~ /\.(test|spec)\.|(^|\/)(__tests__|tests)\//) c="test"
      else if (p ~ /\.md$|(^|\/)docs\//) c="doc"
      printf "%s\t%s\t%s\t%s\n", c, a[p], d[p], p
    }
  }' | sort -k4)

echo "## size"
printf '%s\n' "$CLASSIFIED" | awk -F'\t' '
  $1=="core" {cf++; cl+=$2+$3}
  {tf++; tl+=$2+$3}
  END {
    printf "core_files=%d\ncore_lines=%d\ntotal_files=%d\ntotal_lines=%d\n", cf+0, cl+0, tf+0, tl+0
  }'
# size_tier は triage-guide.md `## 6.2` の帯定義を機械適用する。
# **判定は large → medium → small の順**（条件が重なる場合は大きい帯が勝つ）。
# large = ファイル > 10 **または** 行数 > 500。ここを OR で書かないと
# 「15 ファイル / 50 行」「2 ファイル / 600 行」が medium へ落ち、規模キャップで
# fleet が無言で半減する（ガイドは後者を large の worked example に挙げている）。
if [ -z "$CLASSIFIED" ]; then
  # numstat が取れなかった場合。「変更 0 件」と同じ small に潰すと、
  # 大規模 PR が最小構成で処理されても誰も気づけない
  echo "size_tier=unknown"
  echo "numstat=failed"
  echo "WARN: numstat が空のため size_tier を判定できない" >&2
else
  printf '%s\n' "$CLASSIFIED" | awk -F'\t' '
    $1=="core" {cf++; cl+=$2+$3}
    END {
      if (cf+0 > 10 || cl+0 > 500) t="large"
      else if (cf+0 >= 4 || cl+0 >= 101) t="medium"
      else t="small"
      printf "size_tier=%s\n", t
    }'
fi
# モード判定の入力比率（判定そのものは triage-guide `## 2.5` が行う）
printf '%s\n' "$CLASSIFIED" | awk -F'\t' '
  {tf++}
  $4 ~ /\.md$/ {md++}
  $1=="gen" {g++}
  $4 ~ /(^|\/)(migrations|db\/migrate)\/|prisma\/migrations\// {mig++}
  END {
    printf "md_ratio=%d%%\ngenerated_ratio=%d%%\nmigration_files=%d\n",
      (tf?md*100/tf:0), (tf?g*100/tf:0), mig+0
  }'

echo "## files"
# 上限を切る。ファイル数に比例して伸びる唯一のセクションで、800 ファイルの PR では
# ここだけで約 19k tokens に達し「ダイジェストを compact に保つ」目的を打ち消す。
# 全件が要るときは `diff-slice.sh --list` を使う（情報は失われない）
printf '%s\n' "$CLASSIFIED" | awk -F'\t' -v cap=80 '
  { n++; if (n <= cap) printf "%-5s +%-6s -%-6s %s\n", $1, $2, $3, $4 }
  END { if (n > cap) printf "... (+%d files 省略。全件は diff-slice.sh --list)\n", n - cap }'

# ---- hunk ヘッダ（関数コンテキスト。core ファイルのみ） -------------------
echo "## hunks"
awk '
  /^diff --git / { f=$4; sub(/^b\//, "", f); next }
  /^@@ / {
    # core（= gen / test / doc を除く）のみ。関数コンテキスト行が Phase 0 の主要な読み物になる
    if (f ~ /(^|\/)(dist|build|vendor)\/|\.lock$|package-lock\.json$|yarn\.lock$|pnpm-lock\.yaml$|\.snap$|\.generated\./) next
    if (f ~ /\.(test|spec)\.|(^|\/)(__tests__|tests)\//) next
    if (f ~ /\.md$|(^|\/)docs\//) next
    # `@@ -a,b +c,d @@ <funcname>` の funcname は「直前の行の実内容」なので、
    # `API_KEY=...` のような代入行が stdout に載りうる。範囲情報だけを出す
    hdr = $0; sub(/@@[^@]*$/, "", hdr)
    print f " " hdr
  }' "$OUT" | head -60

# ---- 観点判定シグナル（triage-guide `## 3` 観点判定表） -------------------
# 出力形式: <focus key>\t<hit数>\t<代表となる根拠>
# sig <key> <ere> [paths|code|doc|removed]
# 正規表現は必ず `-e` で渡す（`--no-verify` のように `-` 始まりのパターンが
# grep のオプションとして解釈されるのを防ぐ）。
sig() {
  local key="$1" re="$2" src="${3:-code}" stream n ex
  case "$src" in
    paths)   stream=$(printf '%s\n' "$CLASSIFIED" | awk -F'\t' '{print "\t" $4 "\t" $4}') ;;
    doc)     stream="$ADDED_DOC" ;;
    removed) stream="$REMOVED_CODE" ;;
    *)       stream="$ADDED_CODE" ;;
  esac
  n=$(printf '%s\n' "$stream" | cut -f3- | grep -c -E -e "$re" 2>/dev/null || true)
  [ "${n:-0}" -gt 0 ] || return 0
  # 根拠は「どのファイルで当たったか」。判定は内容部だけに当て（パス由来の誤マッチを防ぐ）、
  # 行番号でパス列へ引き当てる。awk の正規表現エンジンには渡さない（ERE 互換性の差で落ちるため）
  local ln
  ln=$(printf '%s\n' "$stream" | cut -f3- | grep -n -m1 -E -e "$re" 2>/dev/null | cut -d: -f1)
  ex=$(printf '%s\n' "$stream" | sed -n "${ln:-0}p" | cut -f2)
  printf '%s\t%s\t%s\n' "$key" "$n" "${ex:-?}"
  return 0
}
# 同一 key の複数条件を 1 行に畳む（件数は合算、根拠は最初の 1 件）
merge_sig() { awk -F'\t' '{n[$1]+=$2; if(!(($1) in e)) e[$1]=$3} END {for(k in n) printf "%s\t%s\t%s\n", k, n[k], e[k]}' | sort; }

echo "## focus-signals"
{
  sig error-handling   'try *\{|catch *\(|except |rescue |\.catch\('
  sig comment-accuracy '^[[:space:]]*(//|/\*|\*[^*/]|#[^!#]|<!--|--[^-])'
  sig test-quality     '\.(test|spec)\.|(^|/)(__tests__|tests)/' paths
  sig type-design      '(^|[^a-zA-Z])(type|interface|enum) [A-Za-z_]'
  sig security         '(^|/)(auth|security|crypto)/|middleware/auth' paths
  sig security         'password|secret|token|api_key|eval\(|innerHTML|dangerouslySetInnerHTML|query\('
  sig performance      'SELECT |INSERT |UPDATE |DELETE |\.find\(|\.findMany\(|Promise\.all'
  sig api-design       'router\.(get|post|put|delete)|@(Get|Post|Put|Delete)\(|app\.(get|post|put|delete)\('
  sig dependency       'package\.json$|.*lock.*|Gemfile|requirements\.txt$|go\.mod$|Cargo\.toml$' paths
  sig migration        '(^|/)(migrations|db/migrate)/|prisma/migrations/' paths
  sig config           '\.env|\.config\.|Dockerfile|docker-compose\.|\.github/workflows/' paths
  sig cross-cutting    '(^|/)(utils|helpers|shared|common|lib|core)/' paths
  sig ui-quality       '\.(tsx|jsx|vue|svelte)$|(^|/)(components|pages|app)/' paths
  sig ui-quality       'aria-|role=|<img|<button|tabindex|onClick|onKeyDown'
  sig doc-substance    '(^|/)(CLAUDE|AGENTS|CONTRIBUTING|README)|\.claude/(adr|designs)/' paths
  # 任意 *.md の実質 prose 行（frontmatter / list マーカー / link-only を除く）。
  # 起動閾値（概ね 10 行以上）の判定は triage-guide `## 3` に委ね、ここは件数だけ出す
  sig doc-prose-lines  '[^[:space:]|>*+-]' doc
} | merge_sig

echo "## red-flags"
{
  sig specialist-injection        'eval\(|new Function\(|vm\.runIn|child_process|exec\(|execSync|subprocess\.run|os\.system|shell=True'
  sig specialist-destructive-op   'fs\.unlink|fs\.rm|rmSync|rm -rf|DROP TABLE|TRUNCATE|DELETE FROM'
  sig specialist-secret-handling  '(password|secret|api_key|apiKey|private_key) *=|BEGIN PRIVATE KEY|Authorization:|console\.log\(.*(password|token)'
  sig specialist-input-validation 'JSON\.parse\(.*req\.|parseInt\(.*req\.|RegExp\(.*user'
  sig specialist-guardrail-bypass '--no-verify|--no-gpg-sign|disable_'
  # 骨抜きは「設定ファイルからのルール削除」で起きる。パスで候補を出し、
  # 実際に削除があるかの判定（＝ specialist を起こすか）は triage-guide `## 3` に委ねる
  sig lint-config-changed '\.golangci\.yml|\.eslintrc|lefthook\.yml|pre-commit|redocly\.yaml|tsconfig\.json|ruff\.toml|\.rubocop\.yml' paths
} | merge_sig

echo "## surface"
# triage-dynamic-gates.md `## 8.5` の high-risk surface 判定（正規表現部分のみ。PR 自己申告は別経路）
{
  sig db-write     'INSERT |UPDATE |DELETE |\.create\(|\.update\(|\.save\(|\.insert\(|\.upsert\('
  sig money-numeric 'amount|price|balance|quantity|stock|currency|round\(|toFixed\('
  sig authz        'permission|authorize|isAdmin|hasRole|session|jwt|verifyToken|can[A-Z]'
} | merge_sig

echo "## explorer-signals"
# triage-guide `## 3` explorer の必要性判定
# shared-module には **呼び出し元の概数**を添える（同節の explorer 下限判定 / GitHub issue
# #122）。数えないと「型引数を 1 つ足しただけの共通モジュール変更」にも explorer が 1 体
# 張り付く。**誤差は両方向に出る**: basename の word 一致は doc の言及も拾って過大に振れる
# 一方、**追跡済みファイルの literal 一致しか見ない**ので未追跡ファイル・barrel / path alias
# 経由の import は取り逃して過小にも振れる。**数えられない場合は `?`**（下限判定は起動する側
# に倒す。0 に潰すと下限を最も緩く通してしまう）
printf '%s\n' "$CLASSIFIED" | cut -f4 | grep -E '(^|/)(utils|shared|lib|common|helpers|core)/' | head -10 \
  | while IFS= read -r f; do
      base=$(basename -- "$f"); base="${base%.*}"
      n="?"
      # 3 文字未満の basename（`db` 等）は word 一致でも誤ヒットが多すぎるので数えない。
      # `-w` + 固定文字列で import/require/from のいずれの記法も拾う（言語非依存の粗い近似）
      if [ "${#base}" -ge 3 ]; then
        # **`git grep` の既定 pathspec は cwd**。self-review は worktree に入らず cwd が
        # セッション起動 dir のままなので、リポジトリルート以外から起動すると探索範囲が縮む。
        # `-C "$WT"` + `--full-name` で repo ルート基準に固定する（`$f` も repo ルート相対
        # なので、自己除外の `grep -vxF` はこれで初めて一致する）
        out=$(git -C "$WT" grep --full-name -lwF -e "$base" 2>/dev/null); rc=$?
        # rc は 0=ヒット / 1=該当なし / 2 以上=エラー。**終了ステータスを見ずに `wc -l` へ流すと
        # 計数失敗も 0 になる**（`wc` は上流が失敗しても数値を出す）ため、`?` の縮退が死ぬ
        [ "$rc" -le 1 ] && n=$(printf '%s\n' "$out" | grep -vxF -- "$f" | grep -c .)
      fi
      printf 'shared-module\t%s (importers: %s)\n' "$f" "$n"
    done
printf '%s\n' "$CLASSIFIED" | awk -F'\t' '$1=="core" {print $4}' | while read -r f; do
  # `-f` を先に見る。レビュー対象が `evil.js -> /dev/zero` のような symlink を含むと、
  # 後置きでは wc が EOF に到達せずハングする
  [ -f "$f" ] || continue
  n=$(wc -l < "$f" 2>/dev/null | tr -d ' ')
  [ "${n:-0}" -gt 500 ] && printf 'large-file\t%s (%s lines)\n' "$f" "$n"
done | head -10

echo "## agents-md"
# xargs は入力のクォートを解釈するため、`it's.ts` のようなパスで
# `unterminated quote` を起こし、以降のファイルが丸ごと処理されない
printf '%s\n' "$CLASSIFIED" | cut -f4 | while IFS= read -r p; do
  [ -n "$p" ] && dirname -- "$p"
done | sort -u | while read -r d; do
  while [ "$d" != "." ] && [ "$d" != "/" ]; do
    [ -f "$d/AGENTS.md" ] && echo "$d/AGENTS.md"
    [ -f "$d/CLAUDE.md" ] && echo "$d/CLAUDE.md"
    d=$(dirname "$d")
  done
done | sort -u
[ -f AGENTS.md ] && echo "AGENTS.md"
[ -f CLAUDE.md ] && echo "CLAUDE.md"

echo "## host-deps"
# 子 agent は `isolation: "worktree"` の worktree に入るため、gitignore 対象の依存
# （node_modules / vendor / .venv 等）がそこに存在しない。**ディスク上にある事実を
# agent が「検証不能」と誤申告し、wave を 1 本まるごと回収に費やす**のを防ぐため、
# メインリポジトリの絶対パスを digest に載せてプロンプトへ注入させる（GitHub issue #113）。
#
# 導出は lib/review-paths.sh の `review_main_root` が正本（式をここに複製しない）。
# **導出できないときは行ごと出さない。** `pwd` に倒すと worktree 側のパスが
# 「メインリポジトリ」を名乗って agent プロンプトへ入り、#113 の失敗が無シグナルで
# 再発する（誤値を注入するより注入しないほうが安全側）。
if MAIN_ROOT=$(review_main_root); then
  printf 'main-root\t%s\n' "$MAIN_ROOT"
  # **symlink は列挙しない**（CWE-59）。対象名はすべて gitignore 慣例名なので
  # 同名の symlink がコミットされていても気づかれにくく、`[ -d ]` は解決先を見るため
  # リポジトリ外を「読んでよい依存 dir」として広告してしまう。実体が MAIN_ROOT 配下に
  # 収まることまで確認する。
  for d in node_modules vendor .venv venv .yarn; do
    p="$MAIN_ROOT/$d"
    [ -d "$p" ] || continue
    [ -L "$p" ] && continue
    rp=$(cd "$p" 2>/dev/null && pwd -P) || continue
    case "$rp/" in "$MAIN_ROOT"/*) printf 'dep-dir\t%s\n' "$p" ;; esac
  done
else
  echo "WARN: メイン作業ツリーを導出できないため main-root を出力しない（依存の読み取り先は agent に渡らない）" >&2
fi
# **lockfile が変更に含まれていれば、メイン側の依存は PR 後の状態と一致しない。**
# agent が confidence を下げる判断をできるよう機械的に出す（LLM に lockfile 判定をさせない）。
printf '%s\n' "$CLASSIFIED" | cut -f4 \
  | grep -E '(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Gemfile\.lock|poetry\.lock|go\.sum|Cargo\.lock|composer\.lock)$' \
  | sed 's/^/lockfile-changed\t/' | head -5

echo "## issue-ids"
# Issue ID は大文字限定（`[A-Z]+-[0-9]+`）で抽出する（GitHub issue #107）。
# Linear の Issue ID は慣例的に大文字（例: ENG-123）。ignore-case にすると
# `utf-8` / `sha-1` / `base-64` / `ipv6-1` のような語がブランチ名・ref から誤マッチし、
# triage digest に無関係な「Issue ID」が載る。小文字 ID を使う backend を追加するときは
# ここを見直す（その場合も誤マッチ増を避けるため prefix を絞る等の対策を伴わせる）。
if [ -n "$PR" ]; then
  gh pr view "$PR" --json headRefName,baseRefName -q '.headRefName + " " + .baseRefName' 2>/dev/null \
    | grep -oE '[A-Z]+-[0-9]+' | sort -u
else
  git rev-parse --abbrev-ref HEAD 2>/dev/null | grep -oE '[A-Z]+-[0-9]+' | sort -u
fi
exit 0
