#!/usr/bin/env bash
# self-review の Markdown 推敲（GitHub issue #243）の対象行を決定的に切り出す。
#
# 対象は「diff で追加・変更された *.md の行のうち、推敲してよい散文」だけ。フェンス内の
# コード（字下げ・引用の中を含む）・frontmatter・HTML コメント（SSoT pin を含む）・
# `<!-- NAME:START -->` 〜 `END` の複製区間・見出し（ATX と setext。アンカーとして参照される）・
# 表の区切り行・リンクだけの行・vendored / 生成物の md は、書き換えると別の検査や参照を
# 壊すので最初から渡さない。4 桁字下げのコードブロック（フェンス無し）は箇条の続きと
# 見分けられないので外さない（既知の限界）。これを LLM に判定させると、フェンスの開閉を読み違えた回に
# コード片まで推敲へ流れる。
#
# 行番号は**最終状態のファイル**に対する番号。self-review の diff ファイルは 3 本の連結
# （BASE..HEAD / --cached / unstaged）で、同じファイルの hunk が別の版の行番号で並ぶため
# 使えない。ここでは `git diff <base>`（作業ツリー対 base）を取り直す。`--staged` のときは
# `git diff --cached` と index の内容を使う。
#
# 使い方:
#   md-prose-lines.sh --base <ref> [--staged] [--cap N]   # 対象行を TSV で出す
#   md-prose-lines.sh --base <ref> [--staged] --count     # Step 1 用の要約だけを出す
#
# 出力（既定）: `<path>\t<行番号>\t<行の本文>` を 1 行ずつ。上限（既定 300 行）を超えた分は
#   出さず、末尾に `# truncated\t<出さなかった行数>` を 1 行置く（黙って切らない）。
# 出力（--count）: `## md-polish` の見出しの後に `md_prose_lines=<総数>` と
#   `writing_polish=<1|0>`（writing-polish がユーザー設定かプロジェクト設定で有効か）。
set -uo pipefail

BASE=""; STAGED=0; CAP=300; COUNT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base)   [ $# -ge 2 ] || { echo "FATAL: --base に値が必要" >&2; exit 2; }; BASE="$2"; shift 2 ;;
    --staged) STAGED=1; shift ;;
    --cap)    [ $# -ge 2 ] || { echo "FATAL: --cap に値が必要" >&2; exit 2; }; CAP="$2"; shift 2 ;;
    --count)  COUNT=1; shift ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
case "$CAP" in ''|*[!0-9]*) echo "FATAL: --cap は数値のみ（受領: '${CAP}'）" >&2; exit 2 ;; esac
if [ "$STAGED" = "0" ] && [ -z "$BASE" ]; then
  echo "FATAL: --base か --staged のどちらかが必要" >&2; exit 2
fi
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が無い" >&2; exit 2; }

TOP=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "FATAL: git リポジトリの外" >&2; exit 2; }

# 非 ASCII パスを C クォートさせない（triage-signals.sh と同じ理由）。接頭辞は明示して固定する —
# `diff.noprefix` / `diff.mnemonicPrefix` を設定した環境では `+++ b/` が付かず、全ファイルを落とす
GDIFF="-c core.quotePath=false diff -U0 --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/"
if [ "$STAGED" = "1" ]; then
  DIFF=$(git -C "$TOP" $GDIFF --cached -- '*.md') \
    || { echo "FATAL: git diff --cached に失敗した" >&2; exit 1; }
else
  DIFF=$(git -C "$TOP" $GDIFF "$BASE" -- '*.md') \
    || { echo "FATAL: git diff ${BASE} に失敗した" >&2; exit 1; }
fi

# writing-polish が有効か。**優先順位の高い設定から見て、最初に値を持つファイルで決める**
# （プロジェクトのローカル設定 → プロジェクト設定 → ユーザー設定。ユーザー設定で有効でも
# ローカル設定で `false` にしていれば無効）。キーの存在ではなく値を見る
WP=0
for f in "$TOP/.claude/settings.local.json" "$TOP/.claude/settings.json" "$HOME/.claude/settings.json"; do
  v=$(grep -Eo '"writing-polish@[^"]*"[[:space:]]*:[[:space:]]*(true|false)' "$f" 2>/dev/null | head -1)
  if [ -n "$v" ]; then
    case "$v" in *true) WP=1 ;; esac
    break
  fi
done

printf '%s' "$DIFF" | TOP="$TOP" STAGED="$STAGED" CAP="$CAP" COUNT="$COUNT" WP="$WP" python3 -c '
import os, re, subprocess, sys

top, staged = os.environ["TOP"], os.environ["STAGED"] == "1"
cap, count_only = int(os.environ["CAP"]), os.environ["COUNT"] == "1"

# vendored・生成物の md は第三者の文書なので推敲しない（triage-signals.sh の gen と同じ判定）
GEN = re.compile(r"(^|/)(dist|build|vendor|node_modules)/|\.generated\.")
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

added = {}   # path -> 追加行の行番号（最終状態のファイルでの番号）
path, in_header = None, False  # mutation-ok: git の diff は必ず diff --git の行から始まり、そこで両方とも設定し直すので初期値は読まれない
# UTF-8 でない md が混ざっても落ちない（ロケールに依存させずバイトで読む）
for line in sys.stdin.buffer.read().decode("utf-8", "replace").splitlines():
    if line.startswith("diff --git "):
        path, in_header = None, True
        continue
    if in_header:
        # **ヘッダの中でだけ `+++ ` を読む**。本文の `++ ` で始まる追加行は diff 上で `+++ ` になる
        if line.startswith("+++ "):
            # 空白を含むパスには git が末尾にタブを付ける
            target = line[4:].rstrip("\t")
            path = target[2:] if target.startswith("b/") else None   # /dev/null は削除
            continue
        if not line.startswith("@@"):
            continue
        in_header = False
    m = HUNK.match(line)
    if m and path is not None and not GEN.search(path):
        start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        added.setdefault(path, set()).update(range(start, start + n))

# フェンスは字下げ・引用・箇条の記号の後ろも数える（箇条の中のコードは 4 桁以上字下げされる）
FENCE = re.compile(r"^[ \t]*(?:>[ \t]?)*[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^ {0,3}#{1,6}(\s|$)")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
LINK_ONLY = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?\[[^\]]*\]\([^)]*\)\s*$")
LINK_DEF = re.compile(r"^\s*\[[^\]]+\]:\s")
HAS_WORD = re.compile(r"[^\s|>*+\-=_]")
INLINE_CODE = re.compile(r"``.*?``|`[^`]*`")
# byte 一致を検証される複製区間（`<!-- NAME:START -->` 〜 `<!-- NAME:END -->`）の本文
REGION_START = re.compile(r"<!--\s*[A-Za-z0-9_-]+:START\b")
REGION_END = re.compile(r"<!--\s*[A-Za-z0-9_-]+:END\b")


def is_fence(m):
    """バッククォートのフェンスの info に `` ` `` は入らない（行頭の行内コードをフェンスと取り違えない）."""
    return m is not None and not (m.group(1)[0] == "`" and "`" in m.group(2))


def paragraph_line(s):
    """段落（setext 見出しの本文になれる）の行か。引用・表・HTML・箇条・字下げの続き・ATX 見出しは違う."""
    return (bool(s) and not s[0].isspace() and s[0] not in ">|<"
            and not LIST_ITEM.match(s) and not HEADING.match(s))


def prose_lines(text):
    """推敲してよい行の行番号（1 始まり）を返す.

    行は git と同じく LF で数える（CRLF の CR だけ落とす。行の途中の CR で割ると行番号がずれる）。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    ok, normal, fence, in_comment, in_region = set(), set(), None, False, False
    fm_end = 0
    if lines and lines[0] == "---":
        for i in range(1, len(lines)):
            if lines[i] in ("---", "..."):
                fm_end = i + 1
                break
    for i, s in enumerate(lines, 1):
        if i <= fm_end:
            continue
        if fence is not None:
            m = FENCE.match(s)
            if is_fence(m) and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = None
            continue
        m = FENCE.match(s)
        if is_fence(m):
            fence = m.group(1)
            continue
        # 行内コードの中の `<!--` はコメントではない
        bare = INLINE_CODE.sub("", s)
        if in_comment:
            if "-->" in bare:
                in_comment = False
            continue
        if REGION_START.search(bare):
            in_region = True
            continue
        if REGION_END.search(bare):
            in_region = False
            continue
        if "<!--" in bare:
            in_comment = "-->" not in bare[bare.index("<!--"):]
            continue
        if in_region:
            continue
        normal.add(i)
        if HEADING.match(s) or TABLE_SEP.match(s) or LINK_ONLY.match(s) or LINK_DEF.match(s):
            continue
        if not HAS_WORD.search(s):
            continue
        ok.add(i)
    # setext 見出し（段落の直後の `===` / `---`）の本文も見出しなので外す。箇条の直後の `---` は区切り線
    for i in sorted(normal):
        if not SETEXT.match(lines[i - 1]) or i < 2 or not paragraph_line(lines[i - 2]):
            continue
        # 段落の全行が見出しの本文になる（リンクだけの行のように対象外の行も段落の一部）
        j = i - 1
        while j in normal and paragraph_line(lines[j - 1]):
            ok.discard(j)
            j -= 1
    return ok, lines


rows = []
for p in sorted(added):
    try:
        if staged:
            raw = subprocess.run(["git", "-C", top, "show", ":" + p], capture_output=True,
                                 check=True).stdout  # mutation-ok: 失敗は例外で飛ばすか空の本文で 0 行になるかの違いで、どちらも対象行は出ない
        else:
            with open(os.path.join(top, p), "rb") as f:
                raw = f.read()
        # UTF-8 でない md は推敲に渡さない（化けた文字のまま渡すと、化けた行だけの diff でも起動する）
        text = raw.decode("utf-8")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        continue
    ok, lines = prose_lines(text)
    for n in sorted(added[p] & ok):
        # 本文はそのまま出す（Step 7 は行の全文で位置を決めるので、タブを置き換えると当たらない）。
        # TSV の区切りは先頭 2 つのタブだけなので、本文にタブがあっても列は崩れない
        rows.append((p, n, lines[n - 1]))

if count_only:
    print("## md-polish")
    print("md_prose_lines=%d" % len(rows))
    print("writing_polish=%s" % os.environ["WP"])
    sys.exit(0)
for p, n, s in rows[:cap]:
    print("%s\t%d\t%s" % (p, n, s))
if len(rows) > cap:
    print("# truncated\t%d" % (len(rows) - cap))
'
