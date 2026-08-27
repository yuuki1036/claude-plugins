#!/usr/bin/env python3
"""プラグイン品質の決定的チェック.

/quality-check skill の検査項目のうち、機械的に検証可能なものを実行する.
validate_ssot.py がカバーする項目（SSoT 同期、schema、_requirements、hooks.json）
は対象外. 純粋に LLM 判定が必要な項目（CLAUDE.md 品質 等）はスキップ.

検査項目（errors = 違反, exit 1）:
  - allowed-tools 存在: 全 SKILL.md に allowed-tools が定義されているか
  - allowed-tools 一致: command <-> skill ペアの allowed-tools が完全一致か
  - hooks 安全性: hook スクリプトが safe_hook_init を呼んでいるか
  - hook 参照の実在: hooks.json が参照する `.sh` が実在するか. 実在しない参照は解決側が
    黙って落とすので, パスのタイポやスクリプト移動で hooks 安全性 / hook 自己判定の検査が
    **無言で対象ゼロ**になる（hook は配布されたまま検査だけ消える / issue #176）.
  - safe-hook.sh 同期: 各プラグインの replica が canonical と byte-identical か
  - routing-axes 同期: spec ルーティング 3 軸コアの delimiter 区間が正本と一致するか（dedent 比較）
  - schema-markers 同期: code-review の版マーカー定数（publish-review-event.sh の SCHEMA_MARKERS）が
    orchestration-measurement.md `## 16`「版マーカーの現行値」表と同値か. 注入方式（v2.65.0）で
    「2 箇所を人手で揃える」関係が script <-> doc へ移ったが, SSoT pin は md 限定でこの関係を
    宣言できない（issue #134）. doc がずれても実データは壊れないぶん気づけないので機械検証に寄せる.
  - SSoT pin: `<!-- SSOT: <path>#<anchor> @<hash8> -->` の pin が正本の実ハッシュと一致するか.
    routing-axes は「区間が byte-identical」を検証するが, doc → doc の伝播関係の多くは
    言い換え / 要約なので一致比較にできない. pin は内容の一致ではなく『正本が変わったら
    消費サイトを確認して打ち直す』手順を強制する（v2.63.0 のセルフレビューで検出した
    欠陥 11 件中 6 件が「正本を直したが複製先に伝播していない」型だった）.
    打ち直し: `python3 validate_plugin_quality.py --update-ssot-pins`（明示操作。
    pre-commit では走らせない — 自動更新すると確認の強制力が消える）.
    新規 pin は hash を手計算せず `@00000000` で宣言して上記で確定させる.
    記法不正 / anchor の曖昧一致 / pin した節が pin を含む（打ち直しが収束しない）も
    ここで error にする — 「宣言はあるが一度も検証されない」状態を作らないため.
  - event-bus 同期: 実 publish される event（grep 実測=正本）と、それを記載する doc が一致するか
    （CLAUDE.md 表 / INDEX.md 表の event 集合 + INDEX.md publishes 行の plugin×event ペア）
  - references 参照整合性: SKILL.md / commands/*.md / agents/*.md 内 ${CLAUDE_PLUGIN_ROOT}/... が実在するか
  - トリガーフレーズ: SKILL.md description に 'トリガー:' が含まれているか
  - doc 構造: 番号見出しの重複（他 doc からの番号参照が曖昧になる）と, blockquote を
    分断した孤立 `>` 行. どちらもセルフレビューが見逃した / agent 8 体を要した型で,
    判定は行走査だけで決まる（「lint が見つけるべきものを agent に探させない」）.
  - テスト収集: `if __name__` より後ろの TestCase（直接実行で静かに件数が減り `OK` が出る）.
  - テスト重複: 同一クラス内で本体が同一のテストメソッド（名前が主張する内容を検証していない）.
  - 版プレースホルダ: bump 済みのプラグインに `vNEXT` が残っていないか. `vNEXT` は
    「この変更が入る版」を書くためのもので bump 時に解決される（版ラベルを手書きすると
    書いた時点で値が未確定＝構造的に古くなる。3 回再発し検出側の機械化も 2 度失敗した）.
    **開発中の残存は正常**なので bump が起きた作業ツリーでだけ判定する.
  - シェル構文: 同梱スクリプト（*/scripts/**.sh, */hooks/**.sh）が `bash -n` を通るか.
    CI は manifest と doc しか見ておらず, LLM が書いたスクリプトは構文検証を一度も
    経ずに配布されていた（issue #123 の meta-review）.
  - シェル多バイト展開: `"$VAR（..."` のような**波括弧なしの展開 + 直後の非 ASCII**.
    UTF-8 ロケールの bash が非 ASCII の 1 バイト目まで変数名に取り込むため, `set -u`
    下では診断を出さず exit 1 する. **C ロケールでは再現しない**ので開発機のシェル設定
    次第で見えなくなる（実測: detect-recent-review.sh の WARN が丸ごと死んでいた / #138）.

検査項目（warnings = 助言, exit code に影響しない）:
  - allowed-tools 最小性 (#14b): frontmatter 宣言ツールが本文で未言及（未使用候補）.
    Read/Write/Edit/Glob/Grep/Bash や MCP ツールは日本語表現・記述的言及の偽陽性が
    あるため『要確認』に留め, LLM/人手の最終判断を残す (#14b の偽陽性除外規約に準拠).
  - hook 自己判定: PreToolUse/PostToolUse の hook スクリプトが stdin（safe_hook_input）
    を参照しているか. hooks.json の if:/matcher は実行環境で評価されないことが実測
    されており（2026-07 push-reminder 暴発）, フィルタ単独依存の注入 hook は全ツール
    呼び出しへの暴発リスクになる.
  - コンテキスト予算: skill description の単体上限（600 chars）と全プラグイン合計上限
    （15,000 chars）. description は毎セッションのシステムプロンプトに常駐するため,
    肥大化は合計で判断品質を劣化させる.
  - skill 本文サイズ: SKILL.md 本文の行数上限（500 行）. 超過は references への
    progressive disclosure を促す（規模目安の正本は component-addition-advisor,
    執筆指針は docs/skill-writing.md）.

実行: python3 validate_plugin_quality.py [plugin_dir ...]
  引数無し: 全プラグイン
  引数あり: 指定プラグインディレクトリのみ

Exit code: 0 (pass / warning のみ) / 1 (errors あり)
  warnings (allowed-tools 最小性) は exit code に影響しない（助言のみ）.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SAFE_HOOK = ROOT / ".claude-plugin" / "lib" / "safe-hook.sh"

# spec ルーティング 3 軸コア（WHAT/HOW/WHY → プラグイン対応）の正本と消費サイト.
# 各ファイルの ROUTING-AXES:START / END マーカー区間を dedent 後に比較する
# （消費サイトはリスト内などで一様なインデントを付けてよい）.
# 設計判断: .claude/designs/20260708-spec-routing-ssot.md
CANONICAL_ROUTING_AXES = ROOT / ".claude-plugin" / "lib" / "routing-axes.md"
ROUTING_AXES_CONSUMERS = [
    ROOT / "spec-advisor" / "skills" / "spec-advise" / "references" / "routing-rubric.md",
    ROOT / "issue-workflow" / "skills" / "issue-create" / "SKILL.md",
]
ROUTING_AXES_START = "<!-- ROUTING-AXES:START -->"
ROUTING_AXES_END = "<!-- ROUTING-AXES:END -->"

# 版マーカー定数（`SCHEMA_MARKERS`）の script <-> doc 同期.
# SSoT pin は md 限定なのでこの関係を宣言できない（Gotchas / ADR-20260813223000）.
# 注入方式（v2.65.0 / issue #125）で「2 箇所を人手で揃える」関係が SKILL<->doc から
# script<->doc へ移っただけで, 強制力がコード内コメント 1 行しか無かった（issue #134）.
SCHEMA_MARKERS_SCRIPT = ROOT / "code-review" / "scripts" / "publish-review-event.sh"
SCHEMA_MARKERS_DOC = ROOT / "code-review" / "references" / "orchestration-measurement.md"
SCHEMA_MARKERS_DOC_ANCHOR = "版マーカーの現行値"
# skip の判定は「関係の両端が揃っているか」ではなく「**検証対象のプラグインが在るか**」で行う.
# 両端で見ると, 片方をリネーム / 移動しただけで保護が無言で外れる（`check_safe_hook_sync` が
# hooks ディレクトリの存在でゲートし, 正本・複製の欠落は error にしているのと同じ流儀）.
SCHEMA_MARKERS_PLUGIN = ROOT / "code-review" / ".claude-plugin" / "plugin.json"

# 正本 → 消費サイトの伝播関係を宣言する pin.
#   <!-- SSOT: <repo ルート相対の md パス>#<見出しの前方一致 anchor> @<hash8> -->
# anchor 省略でファイル全体. 検証対象は「pin を置いた場所」で決まる（scanner は repo 全体を舐める）.
SSOT_PIN_RE = re.compile(
    r"<!--\s*SSOT:\s*(?P<path>[^\s#>]+?)(?:#(?P<anchor>[^\s@>]+))?\s+@(?P<hash>[0-9a-f]+)\s*-->"
)
# 厳密パターンに落ちた宣言を「pin ではない」と黙って捨てないための緩い検出.
# hash が hex でない / `@` 前の空白欠落 などの記法ミスは pin を無警告で無効化するため,
# 「SSOT: と書いたのに検証されない」状態を error にする（新規 pin は手書きなので現実的に踏む）.
SSOT_PIN_LOOSE_RE = re.compile(r"<!--\s*SSOT:")
# doc が書式を説明する `<!-- SSOT: ... -->` を pin と誤認しないため, 行内コード片は除去して走査する
# （フェンス付きコードブロックは `_iter_unfenced_lines` 側で除外済み）.
INLINE_CODE_RE = re.compile(r"`[^`]*`")
SSOT_PIN_LEN = 8

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
REF_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}(/[^\s)`'\"]+)")

# Event Bus: 実際に publish される event 名 ⇔ event を記載する doc の同期検証.
# publisher は skill(SKILL.md) / command(commands/*.md) / hook スクリプト(hooks/scripts/*.sh)
# の 4 種に分散するため、宣言 frontmatter は置かず `event_bus_publish "<event>"` の
# リテラル呼び出しを grep 実測（=正本）し、event を記載する 3 系統の doc と照合する
# （宣言⇔実装の二重管理を作らない）:
#   1. CLAUDE.md イベント表（event 集合）
#   2. INDEX.md イベント表（event 集合）
#   3. INDEX.md 各プラグイン詳細の `**publishes**:` 行（plugin×event ペア）
CLAUDE_MD = ROOT / "CLAUDE.md"
INDEX_MD = ROOT / "INDEX.md"
EVENT_PUBLISH_RE = re.compile(r'event_bus_publish\s+"([a-z][a-z_]*:[a-z][a-z_]*)"')
EVENT_TABLE_ROW_RE = re.compile(r"^\|\s*`([a-z][a-z_]*:[a-z][a-z_]*)`\s*\|")
EVENT_INLINE_RE = re.compile(r"`([a-z][a-z_]*:[a-z][a-z_]*)`")
INDEX_SECTION_RE = re.compile(r"^### ([a-z][a-z-]+)\s*$")
# publish は skill 本文 / hook / **プラグイン同梱スクリプト** のいずれからも行われる.
# scripts/ を外すと, publish 処理をスクリプトへ切り出したプラグインの publisher を
# 見失い「表に載っているが publish されていない」の偽陽性になる（code-review v2.48.0 で実際に発生）.
EVENT_PUBLISHER_GLOBS = [
    "*/skills/**/SKILL.md",
    "*/commands/*.md",
    "*/hooks/scripts/*.sh",
    "*/scripts/*.sh",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(path: Path) -> str | None:
    m = FRONTMATTER_RE.match(read_text(path))
    return m.group(1) if m else None


def parse_tools(fm: str) -> list[str] | None:
    """allowed-tools: または tools: の値をソート済みリストで返す. キーが無ければ None.

    frontmatter 末尾は `\n---\n` で切り出されるため末尾改行が無い場合がある.
    YAML リストの終端は (\n|$) 両方を許容する.
    """
    m = re.search(
        r"^(allowed-tools|tools):\s*\n((?:[ \t]+-[ \t].+(?:\n|$))+)",
        fm,
        re.MULTILINE,
    )
    if m:
        items = []
        for ln in m.group(2).splitlines():
            s = ln.strip()
            if s.startswith("- "):
                items.append(s[2:].strip())
        return sorted(items)
    m = re.search(r"^(allowed-tools|tools):\s*\[(.*?)\]", fm, re.MULTILINE)
    if m:
        return sorted(t.strip().strip("\"'") for t in m.group(2).split(",") if t.strip())
    m = re.search(r"^(allowed-tools|tools):\s*(.+)$", fm, re.MULTILINE)
    if m:
        value = m.group(2).strip()
        if value and not value.startswith("[") and value != "|":
            return sorted(t.strip() for t in value.split(",") if t.strip())
    return None


def check_allowed_tools_exists(plugin_dir: Path, errors: list[str]) -> None:
    name = plugin_dir.name
    for skill_md in sorted((plugin_dir / "skills").glob("*/SKILL.md")):
        fm = parse_frontmatter(skill_md)
        if fm is None or parse_tools(fm) is None:
            errors.append(f"[tools:{name}] SKILL.md missing allowed-tools: {skill_md.relative_to(ROOT)}")


# command 名と skill 名が同名でないペアの対応表（(plugin, command stem) -> skill dir 名）.
# 同名ペアのみ検証すると、これらの別名ペアが allowed-tools 一致チェックの盲点になるため明示する.
# command 専用プラグイン（feature-dev / plugin-manager）はペアが存在しないので載せない.
COMMAND_SKILL_ALIASES: dict[tuple[str, str], str] = {
    ("bdd-spec", "bdd-spec-create"): "create-spec",
    ("bdd-spec", "bdd-spec-evaluate"): "evaluate-spec",
    ("claude-meta", "catch-up"): "cc-catch-up",
    ("claude-meta", "revise-claude-md"): "claude-md-improver",
    ("dev-workflow", "commit"): "git-commit-helper",
    ("dev-workflow", "pr"): "pr-creator",
    ("doc-freshness", "doc-freshness-check"): "doc-freshness",
    ("notebooklm-workflow", "notebook-add-source"): "notebook-source-adder",
    ("notebooklm-workflow", "notebook-query"): "notebook-query-assistant",
    ("plugin-feedback", "feedback"): "feedback-issue",
}


def check_allowed_tools_pair(plugin_dir: Path, errors: list[str]) -> None:
    """command と同名（または COMMAND_SKILL_ALIASES で対応づけた）skill の allowed-tools が一致するか."""
    name = plugin_dir.name
    cmd_dir = plugin_dir / "commands"
    skill_dir = plugin_dir / "skills"
    if not cmd_dir.is_dir():
        return
    for cmd_md in sorted(cmd_dir.glob("*.md")):
        stem = cmd_md.stem
        skill_md = skill_dir / stem / "SKILL.md"
        if not skill_md.is_file():
            alias = COMMAND_SKILL_ALIASES.get((name, stem))
            if alias is None:
                continue
            skill_md = skill_dir / alias / "SKILL.md"
            if not skill_md.is_file():
                errors.append(
                    f"[tools:{name}] COMMAND_SKILL_ALIASES の参照先 skill が存在しない: "
                    f"'{stem}' -> skills/{alias}/SKILL.md"
                )
                continue
        cmd_fm = parse_frontmatter(cmd_md) or ""
        skill_fm = parse_frontmatter(skill_md) or ""
        cmd_tools = parse_tools(cmd_fm)
        skill_tools = parse_tools(skill_fm)
        if cmd_tools != skill_tools:
            errors.append(
                f"[tools:{name}] allowed-tools mismatch for '{stem}' "
                f"(command={cmd_tools} skill={skill_tools})"
            )


def check_hooks_safety(plugin_dir: Path, errors: list[str]) -> None:
    """hooks.json で参照されているスクリプトが safe_hook_init を呼んでいるか検証する.

    hooks/scripts/ 直下の helper スクリプト（hooks.json に登場しないもの）は検査対象外.
    パス解決は _hook_script_paths（args[] exec 形式 / legacy command 文字列の両対応）に
    委譲する. 旧実装は command フィールドのみを正規表現で走査していたため, 全プラグインが
    exec 形式（CC 2.1.139+）へ移行した後は参照が常に空＝検証が空振りしていた.
    """
    name = plugin_dir.name
    for script in _hook_script_paths(plugin_dir, None):
        if "safe_hook_init" not in read_text(script):
            errors.append(f"[hooks:{name}] hook script missing safe_hook_init: {script.relative_to(ROOT)}")


def check_safe_hook_sync(plugin_dir: Path, errors: list[str]) -> None:
    name = plugin_dir.name
    hooks_dir = plugin_dir / "hooks"
    if not hooks_dir.is_dir():
        return
    if not CANONICAL_SAFE_HOOK.is_file():
        errors.append(f"[safe-hook-sync] canonical missing: {CANONICAL_SAFE_HOOK.relative_to(ROOT)}")
        return
    replica = hooks_dir / "lib" / "safe-hook.sh"
    if not replica.is_file():
        errors.append(f"[safe-hook-sync:{name}] replica missing: {replica.relative_to(ROOT)}")
        return
    if replica.read_bytes() != CANONICAL_SAFE_HOOK.read_bytes():
        errors.append(f"[safe-hook-sync:{name}] diverged from canonical: {replica.relative_to(ROOT)}")


def _normalize_section(text: str) -> str:
    """節本文を hash 可能な正規形にする（行末空白の除去 + 前後の空行の除去）.

    末尾空白やファイル末尾の改行だけで pin が壊れると, 実質無変更の編集で
    消費サイト確認を強要することになるため, そこだけは吸収する.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _iter_unfenced_lines(lines: list[str]) -> list[tuple[int, str]]:
    """フェンス付きコードブロックの外にある行だけを (行 index, 本文) で返す.

    見出し検出と pin 収集の両方がこれを通る. 片方だけフェンスを追跡していると,
    「解説のコードブロックに書いた記法例が生きた pin になる」ような非対称が生まれる.
    """
    out: list[tuple[int, str]] = []
    fence: str | None = None
    for i, line in enumerate(lines):
        fm = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fm:
            tok = fm.group(1)
            if fence is None:
                fence = tok
            elif tok[0] == fence[0] and len(tok) >= len(fence):
                fence = None
            continue
        if fence is None:
            out.append((i, line))
    return out


def _markdown_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """フェンス付きコードブロックの外にある見出しだけを (行 index, レベル, テキスト) で返す.

    フェンスを追跡しないと, bash コードブロック内のコメント行（`# ...`）が
    level 1 の見出しとして拾われ, 節がそこで打ち切られる. このリポジトリの
    references は実行手順として bash 片を多用するため, 構造的に踏みやすい.
    """
    heads: list[tuple[int, int, str]] = []
    for i, line in _iter_unfenced_lines(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    return heads


def _anchor_matches(anchor: str, htext: str) -> bool:
    """見出しテキストが anchor に一致するか（番号 anchor の前方一致の暴発を両側から塞ぐ）.

    anchor の直後に区切り（`.` / 空白）を要求し, **さらにその次が数字でないこと**を求める:

    - `1` は `13. …` に当たらない（区切り要求。従来から）
    - `8` は `8.5. …` に当たらない（数字の除外。`8. …` にだけ当たる）

    後者が無いと, 正本から `## 8.` が消えた・節を並べ替えたといった通常の編集で
    `#8` の pin が黙って `## 8.5` へ吸着し, 「pin は ok なのに本体は無保護」になる.
    """
    if htext == anchor:
        return True
    if not htext.startswith(anchor):
        return False
    rest = htext[len(anchor) :]
    if rest[0] not in ". ":
        return False
    return not (len(rest) > 1 and rest[1].isdigit())


def _anchor_hit_count(path: Path, anchor: str) -> int:
    heads = _markdown_headings(read_text(path).splitlines())
    return sum(1 for _, _, htext in heads if _anchor_matches(anchor, htext))


def _slice_section(path: Path, anchor: str | None) -> str | None:
    """正本 md から `anchor` の節を切り出す（anchor が None ならファイル全体）.

    anchor は見出しテキストの前方一致で当てる（`## 3.5. 可変部の…` に対し `3.5`）.
    一致規則は `_anchor_matches`（`1` は `13.` に, `8` は `8.5.` に当たらない）.
    節の範囲は見出し行から, 同レベル以上の次の見出しの直前まで.
    見出しの判定は `_markdown_headings` に委ね, フェンス内の `#` 行は見出しにしない.
    **一致が 0 件でも 2 件以上でも None**（呼び出し側が理由を分けて error にする）.

    **`## 8` は同レベルの `## 8.5` を含まない**（節の区切りは見出しレベルで決まり,
    anchor 番号の階層では決まらない）. `8.5` を保護したいなら別 pin を打つ.
    """
    text = read_text(path)
    if anchor is None:
        return _normalize_section(text)
    lines = text.splitlines()
    heads = _markdown_headings(lines)
    hits = [pos for pos, (_, _, htext) in enumerate(heads) if _anchor_matches(anchor, htext)]
    if len(hits) != 1:
        return None
    start, level, _ = heads[hits[0]]
    end = next((i for i, lv, _ in heads[hits[0] + 1 :] if lv <= level), len(lines))
    return _normalize_section("\n".join(lines[start:end]))


def _has_live_pin(text: str) -> bool:
    """本文に「生きた」pin 宣言が含まれるか（フェンス内・行内コード片の記法例は数えない）."""
    return any(
        SSOT_PIN_RE.search(INLINE_CODE_RE.sub("", raw))
        for _, raw in _iter_unfenced_lines(text.splitlines())
    )


def _digest_section(section: str) -> str:
    return hashlib.sha256(section.encode("utf-8")).hexdigest()[:SSOT_PIN_LEN]


def _canonical_digest(path: Path, anchor: str | None) -> str | None:
    section = _slice_section(path, anchor)
    return None if section is None else _digest_section(section)


def _iter_ssot_pins() -> tuple[list[tuple[Path, int, re.Match[str]]], list[str]]:
    """リポジトリ内の全 md から SSOT pin 宣言を収集する（配置場所で運用範囲を決める）.

    戻り値は (収集できた pin, 記法不正の位置). **フェンス内と行内コード片は走査しない** —
    doc に書いた記法例が「生きた pin」になると, 正本の編集で無関係な作業まで止まり,
    `--update-ssot-pins` が解説文中のハッシュを黙って書き換えてしまう.
    """
    hits: list[tuple[Path, int, re.Match[str]]] = []
    malformed: list[str] = []
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        for i, raw in _iter_unfenced_lines(read_text(path).splitlines()):
            line = INLINE_CODE_RE.sub("", raw)
            found = list(SSOT_PIN_RE.finditer(line))
            for m in found:
                hits.append((path, i + 1, m))
            if len(SSOT_PIN_LOOSE_RE.findall(line)) > len(found):
                malformed.append(f"{path.relative_to(ROOT)}:{i + 1}")
    return hits, malformed


def check_ssot_pins(errors: list[str], update: bool = False) -> int:
    """`<!-- SSOT: <path>#<anchor> @<hash> -->` を正本の実ハッシュと突合する.

    routing-axes 同期は「区間が byte-identical であること」を検証するが,
    doc → doc の伝播関係の多くは **言い換え / 要約** なので一致比較にはできない.
    pin は「正本のこの節を見て書いた」という状態を持たせ, 正本が変わったら
    消費サイトを確認して pin を打ち直す, という手順を機械強制するためのもの
    （内容の一致は要求しない。git 履歴に依存しないので後追い・CI でも検出できる）.

    update=True のとき pin を実ハッシュへ書き換える（明示操作。pre-commit では行わない）.
    戻り値は書き換えた pin の数.
    """
    updated = 0
    per_file: dict[Path, list[tuple[re.Match[str], str]]] = {}
    pins, malformed = _iter_ssot_pins()
    for bad in malformed:
        errors.append(
            "[ssot-pin] pin 記法が不正で検証されない（hash は 8 桁の小文字 hex。"
            f"新規 pin は @00000000 で置いて `--update-ssot-pins` で確定させる）: {bad}"
        )
    for path, lineno, m in pins:
        rel = path.relative_to(ROOT)
        raw_path, anchor, pinned = m.group("path"), m.group("anchor"), m.group("hash")
        canonical = ROOT / raw_path
        loc = f"{rel}:{lineno}"
        if not canonical.is_file():
            errors.append(f"[ssot-pin] canonical missing (repo ルート相対で書く): {raw_path} <- {loc}")
            continue
        if canonical.suffix != ".md":
            errors.append(f"[ssot-pin] canonical は md のみ対応: {raw_path} <- {loc}")
            continue
        if canonical.resolve() == path.resolve():
            errors.append(f"[ssot-pin] 自己参照の pin は無意味: {loc}")
            continue
        section = _slice_section(canonical, anchor)
        if section is None:
            hit = _anchor_hit_count(canonical, anchor) if anchor else 0
            if hit > 1:
                errors.append(
                    f"[ssot-pin] anchor '{anchor}' が {raw_path} の見出し {hit} 件に一致（曖昧）。"
                    f"どの節を指すか一意になる anchor にする <- {loc}"
                )
            else:
                errors.append(f"[ssot-pin] anchor '{anchor}' が {raw_path} に見つからない <- {loc}")
            continue
        if _has_live_pin(section):
            # pin した節が自身も pin を含むと, 相手の pin を打ち直すたびに正本の内容が変わり,
            # こちらの pin も stale になる（相互 pin では打ち直しが収束しない）.
            # anchor の有無に依らず掛ける: 「pin は節の直上に置く」という自然な整理をした瞬間に
            # 3 経路が恒久的に赤になり, --update-ssot-pins を何度打っても解けなくなるため.
            errors.append(
                f"[ssot-pin] pin した節が自身も pin を含む（打ち直しが収束しない）。"
                f"pin 宣言を含まない節を指すか, 宣言をファイル冒頭（最初の見出しより前）へ寄せる:"
                f" {raw_path} <- {loc}"
            )
            continue
        actual = _digest_section(section)
        if actual == pinned:
            continue
        if update:
            per_file.setdefault(path, []).append((m, actual))
            continue
        errors.append(
            f"[ssot-pin] 正本 {raw_path}"
            + (f" `{anchor}`" if anchor else "")
            + f" が pin @{pinned} から変わっている（実 @{actual}）。"
            f"消費サイトへ伝播したか確認し pin を打ち直す: {loc}"
        )

    for path, pins in per_file.items():
        text = read_text(path)
        for m, actual in pins:
            text = text.replace(m.group(0), m.group(0).replace(f"@{m.group('hash')}", f"@{actual}"))
            updated += 1
        path.write_text(text, encoding="utf-8")
        print(f"  updated {len(pins)} pin(s): {path.relative_to(ROOT)}", file=sys.stderr)
    return updated


def _extract_routing_axes(path: Path, errors: list[str]) -> str | None:
    """ROUTING-AXES マーカー区間の内容を dedent して返す（マーカー行は含めない）.

    消費サイトはリスト内などで一様なインデントを付けてよいため、
    textwrap.dedent で共通インデントを外してから比較する（それ以外の差分は fail）.
    """
    rel = path.relative_to(ROOT)
    lines = read_text(path).splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip() == ROUTING_AXES_START]
    ends = [i for i, l in enumerate(lines) if l.strip() == ROUTING_AXES_END]
    if len(starts) != 1 or len(ends) != 1:
        errors.append(
            f"[routing-axes-sync] marker count invalid (START={len(starts)}, END={len(ends)}, 期待は各1): {rel}"
        )
        return None
    if ends[0] <= starts[0]:
        errors.append(f"[routing-axes-sync] END marker precedes START: {rel}")
        return None
    region = lines[starts[0] + 1 : ends[0]]
    return textwrap.dedent("\n".join(region))


def check_routing_axes_sync(errors: list[str]) -> None:
    """spec ルーティング 3 軸コアの delimiter 区間が正本と一致するかを検証する（plugin 跨ぎ）."""
    if not CANONICAL_ROUTING_AXES.is_file():
        errors.append(f"[routing-axes-sync] canonical missing: {CANONICAL_ROUTING_AXES.relative_to(ROOT)}")
        return
    canonical = _extract_routing_axes(CANONICAL_ROUTING_AXES, errors)
    if canonical is None:
        return
    for consumer in ROUTING_AXES_CONSUMERS:
        if not consumer.is_file():
            errors.append(f"[routing-axes-sync] consumer missing: {consumer.relative_to(ROOT)}")
            continue
        region = _extract_routing_axes(consumer, errors)
        if region is None:
            continue
        if region != canonical:
            errors.append(
                f"[routing-axes-sync] diverged from canonical "
                f"({CANONICAL_ROUTING_AXES.relative_to(ROOT)}): {consumer.relative_to(ROOT)}"
            )


def _parse_schema_markers_script(text: str) -> tuple[dict[tuple[str, str], int] | None, str]:
    """`SCHEMA_MARKERS = {...}` を python リテラルとして読む（実装側 = 実データの正）.

    失敗時は `(None, 理由)` を返す. **理由を分けるのは誤診断を避けるため** — 一律
    「記法変更か構文エラー」と言うと, 値の型が違うだけの回に対して誤った是正先を指す.

    `bool` を弾くのは Python の `isinstance(True, int)` が真になるため.
    `{"schema": True}` は doc の `1` と `True == 1` で**一致扱いのまま素通り**し,
    publish される JSON には `true` が入る（値の誤りを黙って通す唯一の経路だった）.
    """
    m = re.search(r"^SCHEMA_MARKERS\s*=\s*(\{.*?^\})", text, re.S | re.M)
    if not m:
        return None, "`SCHEMA_MARKERS = {` から行頭 `}` までを見つけられない（記法変更か閉じ括弧のインデント）"
    try:
        raw = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError) as e:
        return None, f"python リテラルとして評価できない（{e}）"
    if not isinstance(raw, dict):
        return None, f"dict ではない（{type(raw).__name__}）"
    out: dict[tuple[str, str], int] = {}
    for field, marks in raw.items():
        if not isinstance(marks, dict):
            return None, f"`{field}` の値が dict ではない（{type(marks).__name__}）"
        for key, value in marks.items():
            if isinstance(value, bool) or not isinstance(value, int):
                return None, f"`{field}.{key}` の値が整数ではない（{value!r}）"
            out[(str(field), str(key))] = value
    return out, ""


SCHEMA_MARKERS_ROW_RE = re.compile(
    r"^\|\s*`([A-Za-z0-9_]+)`\s*\|\s*`([A-Za-z0-9_]+)`\s*\|\s*(\d+)\s*\|\s*$"
)


def _parse_schema_markers_doc(section: str) -> tuple[dict[tuple[str, str], int], list[str]]:
    """doc の「版マーカーの現行値」表を読む（| `field` | `marker` | N |）.

    **節全体ではなく「最初のテーブルブロック」だけを見る**. anchor の節は次の同レベル以上の
    見出しまで（実測 193 行）に及び, `## 16` は payload 契約の本体なので同型の表が今後
    増えうる. 節全体に findall を掛けると **後方の同型行が dict の後勝ちで正本を上書きする**
    （実測: 節末尾に 1 行足すと `gate_schema` が 3 → 2 に化けた）.

    重複キーは呼び出し側で error にする（黙って後勝ちにしない）.
    """
    lines = section.splitlines()
    start = next((i for i, l in enumerate(lines) if l.lstrip().startswith("|")), None)
    if start is None:
        return {}, []
    out: dict[tuple[str, str], int] = {}
    dups: list[str] = []
    for line in lines[start:]:
        if not line.lstrip().startswith("|"):
            break                      # テーブルブロックの終わり
        m = SCHEMA_MARKERS_ROW_RE.match(line)
        if not m:
            continue                   # 区切り行（|---|）とヘッダ行
        key = (m.group(1), m.group(2))
        if key in out:
            dups.append(f"{key[0]}.{key[1]}")
        out[key] = int(m.group(3))
    return out, dups


def check_schema_markers_sync(errors: list[str]) -> None:
    """版マーカー定数が script と doc で同値かを検証する（GitHub issue #134）.

    **doc がずれても実データは壊れない**（注入するのはスクリプト）が, `## 16` は
    「どの版バケツが何を意味するか」の正本なので, ずれた時点で下流の層別解釈が誤る.
    実行時に即壊れないぶん気づけないので機械検証に寄せる（CLAUDE.md「決定的 hook > LLM 判定」）.

    **黙るのは「プラグインごと無い」ときだけ**（code-review 固有のチェックなので, プラグインを
    削除した repo で誤爆させない）. **片方だけ欠けているのは error** — script か doc の一方を
    リネーム / 移動しただけで保護が無言で外れると, #134 が塞いだ「強制力がコメント 1 行しかない」
    状態にリネーム 1 回で戻る（縮退の向きは `check_safe_hook_sync` / `check_routing_axes_sync`
    と揃える: 対象の存在でゲートし, 欠落は落とす）.
    """
    if not SCHEMA_MARKERS_PLUGIN.is_file():
        return
    missing = [p for p in (SCHEMA_MARKERS_SCRIPT, SCHEMA_MARKERS_DOC) if not p.is_file()]
    if missing:
        for p in missing:
            errors.append(
                f"[schema-markers] 突合対象が見つからない（移動・改名ならパス定数も直す）: "
                f"{p.relative_to(ROOT)}"
            )
        return
    script, why = _parse_schema_markers_script(read_text(SCHEMA_MARKERS_SCRIPT))
    if script is None:
        errors.append(
            f"[schema-markers] SCHEMA_MARKERS を読めない — {why}: "
            f"{SCHEMA_MARKERS_SCRIPT.relative_to(ROOT)}"
        )
        return
    section = _slice_section(SCHEMA_MARKERS_DOC, SCHEMA_MARKERS_DOC_ANCHOR)
    if section is None:
        errors.append(
            f"[schema-markers] doc に「{SCHEMA_MARKERS_DOC_ANCHOR}」節が無い（または複数ある）: "
            f"{SCHEMA_MARKERS_DOC.relative_to(ROOT)}"
        )
        return
    doc, dups = _parse_schema_markers_doc(section)
    rel_s, rel_d = SCHEMA_MARKERS_SCRIPT.relative_to(ROOT), SCHEMA_MARKERS_DOC.relative_to(ROOT)
    if not doc:
        errors.append(
            f"[schema-markers] doc の表を 1 行も読めない（`| \\`field\\` | \\`marker\\` | N |` 形式）: "
            f"{rel_d} `{SCHEMA_MARKERS_DOC_ANCHOR}`"
        )
        return
    for dup in dups:
        errors.append(f"[schema-markers] doc の表に `{dup}` が重複している（後勝ちで黙らせない）: {rel_d}")
    for key in sorted(script.keys() | doc.keys()):
        label = f"{key[0]}.{key[1]}"
        if key not in doc:
            errors.append(f"[schema-markers] `{label}` = {script[key]} が doc の表に無い: {rel_d}")
        elif key not in script:
            errors.append(f"[schema-markers] `{label}` が doc にあるが SCHEMA_MARKERS に無い: {rel_s}")
        elif script[key] != doc[key]:
            errors.append(
                f"[schema-markers] `{label}` の値がずれている（script={script[key]} / doc={doc[key]}）: "
                f"{rel_s} <-> {rel_d}"
            )


HEADING_NUM_RE = re.compile(r"^#{2,6}\s+(\d+(?:\.\d+)*)\.?\s")
ORPHAN_QUOTE_RE = re.compile(r"^>\s*$")
# 「この doc は番号見出しで参照される」規約が効く範囲. SKILL / references は
# `## 16` のような番号で相互参照するので, 重複は SSoT pin の anchor 曖昧一致と同型の実害になる.
DOC_LINT_GLOBS = ["*/references/**/*.md", "*/skills/*/SKILL.md"]


def check_doc_structure(plugin_dir: Path, errors: list[str]) -> None:
    """番号見出しの重複と blockquote の分断を検出する（doc lint）.

    どちらも**セルフレビューが実際に見逃した / 検出に agent 8 体を要した**型で,
    判定は行の走査だけで決まる（CLAUDE.md「決定的 hook > LLM 判定」）:

    - **番号見出しの重複**: 同一ファイルに `## 5` が 2 つあると, 他 doc からの
      `## 5` 参照がどちらを指すか決まらない（SSoT pin の anchor 曖昧一致と同型）.
    - **孤立した `>` 行**: blockquote の途中に見出しや段落を挿入すると, 継続行の
      `>` だけが残り, 後続の規範段落が別の節へ再親子化する.

    フェンス内は見ない（`_iter_unfenced_lines`）— コード例の `#` や `>` は見出し
    でも引用でもない.
    """
    name = plugin_dir.name
    seen: set[Path] = set()
    for pattern in DOC_LINT_GLOBS:
        for md in sorted(plugin_dir.glob(pattern.split("/", 1)[1])):
            if md in seen:
                continue
            seen.add(md)
            lines = read_text(md).splitlines()
            unfenced = _iter_unfenced_lines(lines)
            nums: dict[str, list[int]] = {}
            for i, line in unfenced:
                m = HEADING_NUM_RE.match(line)
                if m:
                    nums.setdefault(m.group(1), []).append(i + 1)
            for num, at in sorted(nums.items()):
                if len(at) > 1:
                    errors.append(
                        f"[doc-structure:{name}] 番号見出し `{num}` が重複している"
                        f"（他 doc からの番号参照が曖昧になる。行 {at}）: {md.relative_to(ROOT)}"
                    )
            for pos, (i, line) in enumerate(unfenced):
                if not ORPHAN_QUOTE_RE.match(line):
                    continue
                # **探索は次の見出しまで**. 節境界を越えて探すと,「引用が節末尾で終わり
                # 次が見出し」という正常な形まで孤立扱いになる（誤検知の主因）
                nxt = ""
                for _, l in unfenced[pos + 1:]:
                    if not l.strip():
                        continue
                    nxt = "" if l.lstrip().startswith("#") else l
                    break
                if nxt and not nxt.startswith(">"):
                    errors.append(
                        f"[doc-structure:{name}] 孤立した `>` 行（blockquote が分断されている）: "
                        f"{md.relative_to(ROOT)}:{i + 1}"
                    )


def _test_files() -> list[Path]:
    return sorted(p for p in ROOT.glob("**/tests/test_*.py") if ".git" not in p.parts)


def check_test_collection(errors: list[str]) -> None:
    """`if __name__ == "__main__"` より後ろの TestCase を検出する.

    `unittest.main()` は `sys.exit()` するので, **後ろに置いたクラスは定義自体が
    評価されない**. discover 経路（pre-commit / CI / Stop hook）は無事なので
    **直接実行だけ静かに件数が減り, しかも `OK` が出る**（実測: discover 41 /
    直接実行 33）. 「壊れているのに緑」の典型なのでファイル走査で潰す.
    """
    for path in _test_files():
        lines = read_text(path).splitlines()
        main_at = next((i for i, l in enumerate(lines) if l.startswith("if __name__")), None)
        if main_at is None:
            continue
        late = [i + 1 for i, l in enumerate(lines) if l.startswith("class ") and i > main_at]
        if late:
            errors.append(
                f"[test-collection] `if __name__` より後ろに TestCase がある"
                f"（直接実行で収集されない。行 {late}）: {path.relative_to(ROOT)}"
            )


def check_duplicate_test_bodies(errors: list[str]) -> None:
    """同一クラス内で本体が同一のテストメソッドを検出する.

    名前が別の主張をしているのに中身が同じ＝**独立に失敗しうる条件を持たない**.
    実測 2 回とも「別のことを検証しているつもり」の空振りテストだった.
    docstring は比較から外す（説明だけ違うのは同一とみなす）.

    **decorator と引数はキーに含める**: `@patch("mod.a")` / `@patch("mod.b")` や
    `@unittest.skipIf(...)` の有無は**本体が同じでも独立に失敗しうる**正当なテストで,
    これを重複と呼ぶと errors（= pre-commit ブロック）で正しいテストを止める.

    **本体が `pass` だけのものは対象外**: プレースホルダは「名前が主張する内容を
    検証していない」の対象ではないうえ, 3 つあると 2 件目以降が全部 1 件目の重複として
    報告される（実測）.
    """
    for path in _test_files():
        try:
            tree = ast.parse(read_text(path))
        except SyntaxError as e:
            errors.append(f"[test-duplicate] パースできない: {path.relative_to(ROOT)} ({e})")
            continue
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            seen: dict[str, str] = {}
            for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]:
                body = [
                    n for n in fn.body
                    if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                            and isinstance(n.value.value, str))
                ]
                if all(isinstance(n, ast.Pass) for n in body):
                    continue          # プレースホルダ（`pass` のみ）は比較対象にしない
                key = "|".join([
                    ast.dump(ast.Module(body=body, type_ignores=[])),
                    ast.dump(fn.args),
                    *(ast.dump(d) for d in fn.decorator_list),
                ])
                if key in seen:
                    errors.append(
                        f"[test-duplicate] `{cls.name}.{fn.name}` の本体が "
                        f"`{seen[key]}` と同一（名前が主張する内容を検証していない）: "
                        f"{path.relative_to(ROOT)}"
                    )
                else:
                    seen[key] = fn.name


VERSION_PLACEHOLDER = "vNEXT"


def read_plugin_version(plugin_dir: Path) -> str | None:
    try:
        return json.loads(read_text(plugin_dir / ".claude-plugin" / "plugin.json")).get("version")
    except (OSError, ValueError):
        return None


# 比較基準。既定は HEAD（＝作業ツリーとの差 ＝ pre-commit 用途）。
# **CI では作業ツリー == HEAD なので既定のままだと構造的に必ず no-op になる**
# （「検査を足したのに一度も発火しない」型）。CI は push / PR の範囲の起点を渡す。
VERSION_BASE = os.environ.get("QUALITY_VERSION_BASE") or "HEAD"


def _version_at_head(plugin_dir: Path) -> str | None:
    """比較基準時点の plugin.json の version（取れなければ None）."""
    rel = (plugin_dir / ".claude-plugin" / "plugin.json").relative_to(ROOT).as_posix()
    try:
        proc = subprocess.run(["git", "show", f"{VERSION_BASE}:{rel}"], cwd=ROOT,
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout).get("version")
    except ValueError:
        return None


def check_pending_version_placeholder(plugin_dir: Path, errors: list[str]) -> None:
    """bump 済みのプラグインに `vNEXT` が残っていないかを見る.

    `vNEXT` は「この変更が入る版」を書くためのプレースホルダで, `bump-version.sh` が
    bump 時に**そのプラグイン配下だけ**を実版へ置換する（版ラベルは書く時点では確定して
    いない, という構造的な race を消すため / 経緯は code-review の
    `design-notes/pending-optimizations.md ## 9`）.

    **開発中は `vNEXT` が残っていて正常**なので, 無条件に鳴らすと毎ターン鳴る warning に
    なる（このリポジトリが繰り返し避けてきた形）. **bump が起きたときだけ**判定する
    — version が HEAD と違う ＝ この変更で bump 済み ＝ プレースホルダは解決済みのはず.
    取りこぼす典型は「別のプラグインを bump したので自分の `vNEXT` が残った」ケース.

    比較基準は `QUALITY_VERSION_BASE`（既定 HEAD）. **CI では作業ツリー == HEAD なので
    既定のままでは永久に発火しない** — CI 側が push / PR 範囲の起点を渡す.
    """
    head = _version_at_head(plugin_dir)
    if head is None or head == read_plugin_version(plugin_dir):
        return
    for f in sorted(plugin_dir.rglob("*")):
        if f.suffix not in (".md", ".sh", ".py") or not f.is_file():
            continue
        # **行内コード / フェンス内は対象外**（規約そのものを説明する文章が引っかかる /
        # SSoT pin と同じ扱い）。生きたプレースホルダは裸で書く
        lines = read_text(f).splitlines()
        live = "\n".join(
            INLINE_CODE_RE.sub("", line) for _, line in _iter_unfenced_lines(lines)
        )
        if VERSION_PLACEHOLDER in live:
            errors.append(
                f"[version-placeholder] bump 済みなのに `{VERSION_PLACEHOLDER}` が残っている"
                f"（`bump-version.sh {plugin_dir.name}` は自分のプラグイン配下しか解決しない）: "
                f"{f.relative_to(ROOT).as_posix()}"
            )


def _collect_published_pairs() -> set[tuple[str, str]]:
    """コードベースの実 publish 箇所から (plugin, event) ペアを収集する（=正本）.

    plugin 名は発行元ファイルの相対パス先頭ディレクトリから導出する.
    """
    pairs: set[tuple[str, str]] = set()
    for pattern in EVENT_PUBLISHER_GLOBS:
        for path in ROOT.glob(pattern):
            plugin = path.relative_to(ROOT).parts[0]
            # pathlib の glob は先頭ドットのディレクトリを除外しないため
            # `.claude-plugin/scripts/*.sh` 等が混ざる. plugin 名を導出できない
            # ものは publisher として扱わない（INDEX.md の見出し規約 `^### [a-z]`
            # にも載せられず, 恒久エラーになる）
            if not (ROOT / plugin / ".claude-plugin" / "plugin.json").is_file():
                continue
            for event in EVENT_PUBLISH_RE.findall(read_text(path)):
                pairs.add((plugin, event))
    return pairs


def _events_in_table(path: Path) -> set[str] | None:
    """`| \\`event\\` | ...` 形式の表行から event 名集合を収集する（読めなければ None）."""
    if not path.is_file():
        return None
    return {
        m.group(1)
        for line in read_text(path).splitlines()
        if (m := EVENT_TABLE_ROW_RE.match(line))
    }


def _collect_index_publishes() -> set[tuple[str, str]] | None:
    """INDEX.md 各プラグイン詳細の `**publishes**:` 行から (plugin, event) ペアを収集する."""
    if not INDEX_MD.is_file():
        return None
    pairs: set[tuple[str, str]] = set()
    current: str | None = None
    for line in read_text(INDEX_MD).splitlines():
        m = INDEX_SECTION_RE.match(line)
        if m:
            current = m.group(1)
            continue
        if current and "**publishes**" in line:
            for event in EVENT_INLINE_RE.findall(line):
                pairs.add((current, event))
    return pairs


def check_event_bus_sync(errors: list[str]) -> None:
    """実 publish される event と、それを記載する 3 系統の doc の同期を検証する（plugin 跨ぎ）.

    正本 = 実 `event_bus_publish` の (plugin, event) ペア. 以下と双方向照合する:
      1. CLAUDE.md イベント表（event 集合）
      2. INDEX.md イベント表（event 集合）
      3. INDEX.md の `**publishes**:` 行（plugin×event ペア）
    """
    tag = "event-bus-sync"
    published_pairs = _collect_published_pairs()
    published_events = {event for _, event in published_pairs}

    # doc 1 & 2: event 集合の双方向照合
    for label, table in (
        ("CLAUDE.md イベント表", _events_in_table(CLAUDE_MD)),
        ("INDEX.md イベント表", _events_in_table(INDEX_MD)),
    ):
        if table is None:
            errors.append(f"[{tag}] {label} が読めない（ファイル欠落）")
            continue
        for event in sorted(published_events - table):
            errors.append(
                f"[{tag}] event '{event}' が実 publish されているが {label} に未記載 "
                f"（表に追記するか publish を削除）"
            )
        for event in sorted(table - published_events):
            errors.append(
                f"[{tag}] event '{event}' が {label} に記載されているが publish 箇所がない "
                f"（表から削除するか publisher を実装）"
            )

    # doc 3: plugin×event ペアの双方向照合
    index_pairs = _collect_index_publishes()
    if index_pairs is None:
        errors.append(f"[{tag}] INDEX.md が読めない（ファイル欠落）")
        return
    for plugin, event in sorted(published_pairs - index_pairs):
        errors.append(
            f"[{tag}] {plugin} が '{event}' を publish するが INDEX.md の '### {plugin}' 詳細に "
            f"`**publishes**: \\`{event}\\``（Event Bus）行がない（追記する）"
        )
    for plugin, event in sorted(index_pairs - published_pairs):
        errors.append(
            f"[{tag}] INDEX.md が '{plugin} publishes {event}' と記載するが実際には publish しない "
            f"（publishes 行を削除するか publisher を実装）"
        )


# `<focus>` / `{{PLUGIN_ROOT}}` / `*` を含むパスはテンプレート表記なので実在検査から外す
PLACEHOLDER_RE = re.compile(r"[<>*]|\{\{")


def check_doc_anchors(plugin_dir: Path, errors: list[str]) -> None:
    """`<file>.md ## <番号>` 形式の相互参照が実在の見出しを指すか検証する.

    参照ドキュメントを利用タイミング別に分冊すると, 節番号を維持したまま本文だけが
    別ファイルへ移る. このとき参照側のファイル名を張り替え忘れても
    「ファイルは実在する」ので check_references は素通りし, 遅延読み込みの導線だけが
    静かに切れる（code-review v2.47.0 の分割で実際に 11 箇所発生）.
    """
    tag = "doc-anchor"
    ref_dir = plugin_dir / "references"
    if not ref_dir.is_dir():
        return
    # 見出しの節番号を収集（`## 8.5. xxx` / `### 6.2 xxx` / `### 8a. xxx` を許容）
    heading_re = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)?|\d+[ab])[.\s]", re.M)
    anchors: dict[str, set[str]] = {}
    for md in ref_dir.rglob("*.md"):
        anchors[md.name] = set(heading_re.findall(read_text(md)))
    # 参照側: `foo.md ## 8.5` / `foo.md \`## 8.5\`` の両形式
    ref_re = re.compile(r"([a-z][a-z0-9-]*\.md)\s*`?##\s+(\d+(?:\.\d+)?)`")
    targets = sorted(ref_dir.rglob("*.md"))
    targets += sorted((plugin_dir / "skills").glob("*/SKILL.md"))
    targets += sorted((plugin_dir / "scripts").glob("*.sh"))
    for path in targets:
        for fname, sec in ref_re.findall(read_text(path)):
            if fname not in anchors:
                continue  # references/ 外のファイル名は対象外
            if sec not in anchors[fname]:
                errors.append(
                    f"[{tag}] {path.relative_to(ROOT)}: `{fname} ## {sec}` は実在しない節を指す "
                    f"（分割で移動した可能性. ファイル名を張り替えるか節を復元する）"
                )


def check_references(plugin_dir: Path, errors: list[str]) -> None:
    """${CLAUDE_PLUGIN_ROOT}/... の参照切れを検査する.

    対象: skills/*/SKILL.md, commands/*.md, agents/*.md.
    どのファイル種別でも同一規則（参照パスがプラグイン配下に実在するか）を適用する.
    """
    name = plugin_dir.name
    targets: list[Path] = []
    targets += sorted((plugin_dir / "skills").glob("*/SKILL.md"))
    targets += sorted((plugin_dir / "commands").glob("*.md"))
    targets += sorted((plugin_dir / "agents").glob("*.md"))
    # references/ 配下も対象にする. 参照の重心がここへ移った以上,
    # SKILL.md だけを見ていては参照切れを検出できない
    targets += sorted((plugin_dir / "references").rglob("*.md"))
    for md in targets:
        text = read_text(md)
        seen: set[str] = set()
        for m in REF_RE.finditer(text):
            ref = m.group(1).rstrip(".,);")
            if PLACEHOLDER_RE.search(ref):
                continue  # `<focus>` 等のテンプレート表記は実在検査の対象外
            if ref in seen:
                continue
            seen.add(ref)
            target = plugin_dir / ref.lstrip("/")
            if not target.exists():
                errors.append(
                    f"[refs:{name}] missing reference ${{CLAUDE_PLUGIN_ROOT}}{ref} "
                    f"(in {md.relative_to(ROOT)})"
                )


def check_trigger_phrases(plugin_dir: Path, errors: list[str]) -> None:
    name = plugin_dir.name
    for skill_md in sorted((plugin_dir / "skills").glob("*/SKILL.md")):
        fm = parse_frontmatter(skill_md)
        if fm is None:
            continue
        dm = re.search(r"^description:(.*?)(?=^\S|\Z)", fm, re.MULTILINE | re.DOTALL)
        if dm and "トリガー:" not in dm.group(1):
            errors.append(
                f"[trigger:{name}] description missing 'トリガー:' — {skill_md.relative_to(ROOT)}"
            )


# 未使用検出で『要確認』に留めるツール（日本語のファイル操作表現で間接言及されうる）.
SOFT_FILE_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "NotebookEdit", "NotebookRead", "LS"}

# Bash を『使用』とみなすシェルコマンドの痕跡（fence 言語 / コマンド置換 / 代表的コマンド先頭）.
SHELL_FENCE_RE = re.compile(r"```(?:bash|sh|shell|zsh|console)\b", re.IGNORECASE)
SHELL_HINT_RE = re.compile(
    r"\$\(|(?<![\w/])(?:git|python3?|npm|npx|bash|cd|grep|find|cat|echo|jq|yq|sed|awk|diff|md5|sha256sum)\s"
)


def _tool_mentioned(body: str, tool: str) -> bool:
    """本文に tool 名が単語境界でリテラル出現するか."""
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(tool) + r"(?![A-Za-z0-9_])", body) is not None


def check_allowed_tools_minimality(plugin_dir: Path, warnings: list[str]) -> None:
    """#14b 未使用ツール検出. frontmatter 宣言ツールが本文で未言及なら候補として warning.

    対象は SKILL.md と agents/*.md のみ. commands/*.md は除外する:
    本リポジトリは「command と skill の allowed-tools を一致させる」ルールを課しており
    （check_allowed_tools_pair で検証）, コマンドのツールは本文の必要性ではなくペア一致で
    決まる. コマンド本文は skill へ委譲するスタブが多く, 本文ベースの未使用判定は
    構造的に偽陽性になるため対象外とする.

    偽陽性除外（#14b 規約）:
      - Bash: 本文にシェルコマンドの痕跡があれば使用とみなす.
      - Read/Write/Edit/Glob/Grep 等のファイル操作系: 日本語表現の可能性があるため『要確認』.
      - MCP ツール (mcp__... / __ を含む): 記述的言及の可能性があるため『要確認』.
      - その他（Agent / Task / WebFetch / WebSearch / TodoWrite / AskUserQuestion 等）: 『未使用候補』.
    いずれも errors ではなく warnings（exit code 非影響）.
    """
    name = plugin_dir.name
    targets: list[Path] = []
    targets += sorted((plugin_dir / "skills").glob("*/SKILL.md"))
    targets += sorted((plugin_dir / "agents").glob("*.md"))
    for md in targets:
        fm = parse_frontmatter(md)
        if fm is None:
            continue
        tools = parse_tools(fm)
        if not tools:
            continue
        body = FRONTMATTER_RE.sub("", read_text(md), count=1)
        rel = md.relative_to(ROOT)
        for tool in tools:
            if " " in tool:
                # 散文的な tools 宣言（"All tools except ..." 等）のトークンは対象外.
                continue
            if _tool_mentioned(body, tool):
                continue
            if tool == "Bash":
                if SHELL_FENCE_RE.search(body) or SHELL_HINT_RE.search(body):
                    continue
                # シェル痕跡が無くても rm/mv 等の操作が日本語（「削除」等）で記述される
                # ことがあるため断定せず『要確認』に留める.
                warnings.append(
                    f"[minimality:{name}] 要確認 'Bash'（本文にシェルコマンドの痕跡なし。"
                    f"ファイル削除/移動が日本語で記述されている可能性—人手確認）: {rel}"
                )
            elif tool in SOFT_FILE_TOOLS:
                warnings.append(
                    f"[minimality:{name}] 要確認 '{tool}'（本文に直接言及なし。日本語のファイル操作表現の可能性—人手確認）: {rel}"
                )
            elif "__" in tool or tool.startswith("mcp"):
                warnings.append(
                    f"[minimality:{name}] 要確認 '{tool}'（MCP ツール—記述的言及の可能性、人手確認）: {rel}"
                )
            else:
                warnings.append(f"[minimality:{name}] 未使用候補 '{tool}'（frontmatter 宣言だが本文に言及なし）: {rel}")


def _hook_script_decls(plugin_dir: Path, events: tuple[str, ...] | None):
    """hooks.json の宣言から `.sh` 参照を (宣言文字列, 解決先) で順に返す（**実在は見ない**）."""
    hooks_json = plugin_dir / "hooks" / "hooks.json"
    if not hooks_json.is_file():
        return
    try:
        data = json.loads(read_text(hooks_json))
    except json.JSONDecodeError:
        return  # JSON 破損は schema 検証（validate_ssot）の領分
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return
    for event in (events if events is not None else tuple(hooks.keys())):
        entries = hooks.get(event, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            for h in entry.get("hooks", []):
                candidates = list(h.get("args", []))
                if not candidates and isinstance(h.get("command"), str):
                    candidates = h["command"].split()
                for c in candidates:
                    if not c.endswith(".sh"):
                        continue
                    yield c, plugin_dir / c.replace("${CLAUDE_PLUGIN_ROOT}/", "")


def _hook_script_paths(plugin_dir: Path, events: tuple[str, ...] | None) -> list[Path]:
    """hooks.json から指定イベントの hook スクリプトパスを解決する（args[] / legacy command 両対応）.

    events=None で全イベントを対象にする. 同一スクリプトの重複参照は 1 回に dedup する.
    **実在しない参照はここで落ちる** — 宣言と実体のずれは `check_hook_script_refs` が error にする.
    """
    scripts: list[Path] = []
    seen: set[Path] = set()
    for _raw, script in _hook_script_decls(plugin_dir, events):
        if script.is_file() and script not in seen:
            seen.add(script)
            scripts.append(script)
    return scripts


def check_hook_script_refs(plugin_dir: Path, errors: list[str]) -> None:
    """hooks.json が参照する `.sh` が実在すること（GitHub issue #176）.

    実在しない参照は `_hook_script_paths` が**黙って落とす**ので、パスのタイポや
    スクリプトの移動で `check_hooks_safety`（safe_hook_init 必須）と
    `check_hook_self_judgement`（自己判定）が無言で対象ゼロになる。
    hook は配布されたまま、検査だけが消える型なのでここで止める.
    """
    name = plugin_dir.name
    for raw, script in _hook_script_decls(plugin_dir, None):
        if script.is_file():
            continue
        try:
            shown = script.relative_to(ROOT)
        except ValueError:
            shown = script
        errors.append(
            f"[hook-ref:{name}] hooks.json が参照するスクリプトが無い: {raw} → {shown}")


def check_hook_self_judgement(plugin_dir: Path, warnings: list[str]) -> None:
    """PreToolUse/PostToolUse hook スクリプトの stdin 自己判定を検証する（非ブロッキング warning）.

    hooks.json の `if:`（CC 2.1.85+）や matcher によるフィルタは実行環境によって
    評価されないことが実測されている（2026-07: `if: "Bash(git push *)"` の
    push-reminder が全 Bash 呼び出しで発火）. tool イベントの hook は
    `safe_hook_input` で tool_input を取得し発火条件を自己判定しなければ,
    フィルタ不発時に全ツール呼び出しへの注入・誤 block になる.
    SessionStart / FileChanged 等は対象外（tool_input が無い・低頻度）.
    スキーマ検証は `if` を正当なフィールドとして通すため, この暴発モードは
    本チェックでしか拾えない.
    """
    name = plugin_dir.name
    for script in _hook_script_paths(plugin_dir, ("PreToolUse", "PostToolUse")):
        if "safe_hook_input" not in read_text(script):
            warnings.append(
                f"[hook-self-judge:{name}] {script.relative_to(ROOT)} が safe_hook_input を参照していない"
                "（if:/matcher 単独依存は暴発リスク。tool_input を自己判定すること）"
            )


# skill description は毎セッションのシステムプロンプトに常駐する（本文は遅延ロード）.
# 単体上限はルーティング（いつ起動するか）に必要な情報量の目安, 合計上限は
# マーケットプレイス全体としての常駐コンテキスト予算（超過は skill 選択品質を劣化させる）.
SKILL_DESC_CHAR_LIMIT = 600
SKILL_DESC_TOTAL_LIMIT = 15000
DESC_RE = re.compile(r"^description:(.*?)(?=^\S|\Z)", re.MULTILINE | re.DOTALL)


def check_context_budget(warnings: list[str]) -> None:
    """skill description の常駐コンテキスト予算を検証する（非ブロッキング warning）."""
    total = 0
    for skill_md in sorted(ROOT.glob("*/skills/*/SKILL.md")):
        fm = parse_frontmatter(skill_md)
        if fm is None:
            continue
        dm = DESC_RE.search(fm)
        if not dm:
            continue
        desc = re.sub(r"\s+", " ", dm.group(1)).strip()
        total += len(desc)
        if len(desc) > SKILL_DESC_CHAR_LIMIT:
            warnings.append(
                f"[context-budget] description {len(desc)} chars > {SKILL_DESC_CHAR_LIMIT}"
                f"（ルーティングに不要な設計背景は本文へ）: {skill_md.relative_to(ROOT)}"
            )
    if total > SKILL_DESC_TOTAL_LIMIT:
        warnings.append(
            f"[context-budget] 全 skill description 合計 {total} chars > {SKILL_DESC_TOTAL_LIMIT}"
            "（常駐コンテキスト予算超過。上位の description をダイエットすること）"
        )


# SKILL.md 本文は起動時に全文ロードされる. 500 行以上は references への
# progressive disclosure を検討するサイン（規模目安は component-addition-advisor
# の「500 行以上 → references に分割」, 執筆指針は docs/skill-writing.md）.
# frontmatter は context-budget 側で別途計上するため本文行数から除外する.
SKILL_BODY_LINE_LIMIT = 500


def check_skill_body_size(warnings: list[str]) -> None:
    """SKILL.md 本文（frontmatter を除く）の行数を検証する（非ブロッキング warning）."""
    for skill_md in sorted(ROOT.glob("*/skills/*/SKILL.md")):
        lines = read_text(skill_md).splitlines()
        if lines and lines[0].strip() == "---":
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    lines = lines[i + 1 :]
                    break
        n = len(lines)
        if n >= SKILL_BODY_LINE_LIMIT:
            warnings.append(
                f"[skill-size] SKILL.md 本文 {n} 行 >= {SKILL_BODY_LINE_LIMIT}"
                f"（一部 branch しか使わない定義・表は references へ — docs/skill-writing.md）: "
                f"{skill_md.relative_to(ROOT)}"
            )


def check_shell_syntax(plugin_dir: Path, errors: list[str]) -> None:
    """同梱シェルスクリプトの構文を `bash -n` で検証する.

    LLM が書いたスクリプトは「構文は通るが動かない」より前に「そもそも構文エラー」で
    配布されうるのに、CI は manifest と doc しか見ていなかった（issue #123 の meta-review）.
    `bash -n` は決定的・高速なので errors 扱いにする（CLAUDE.md「決定的 hook > LLM 判定」）.
    shellcheck のような深い解析は未導入環境があるため対象外.
    """
    if not shutil.which("bash"):
        return
    for sh in sorted(plugin_dir.glob("scripts/**/*.sh")) + sorted(plugin_dir.glob("hooks/**/*.sh")):
        rel = sh.relative_to(ROOT)
        proc = subprocess.run(
            ["bash", "-n", str(sh)], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().splitlines()
            errors.append(
                "[shell-syntax] bash -n が失敗: %s%s"
                % (rel, (" — " + detail[0]) if detail else "")
            )


# `"$VAR（..."` のように**裸の変数展開の直後が非 ASCII**だと、UTF-8 ロケールの bash が
# その 1 バイト目まで変数名に取り込む（実測: `LC_CTYPE=C.UTF-8` / `ja_JP.UTF-8` /
# `en_US.UTF-8` で `DIFF<0xef>: unbound variable`。C / POSIX では**再現しない**）。
# `set -u` と組み合わさると、そのメッセージを出さずに exit 1 する。
#
# 昇格根拠: detect-recent-review.sh の WARN が丸ごと死んでいた（`--diff` 明示指定の
# 不在を「黙らない」ための経路が、まさに黙っていた）。**開発者のシェルが C ロケールだと
# 再現しない**ので人手レビューで見つかりにくい一方、判定は正規表現で決まる。
# 既存 repo での実測は 1 件（この欠陥そのもの）＋ コメント行 1 件で、後者は除外規則で落ちる。
BARE_EXPANSION_BEFORE_MULTIBYTE_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*(?=[^\x00-\x7f])")


def check_shell_multibyte_expansion(plugin_dir: Path, errors: list[str]) -> None:
    """`${VAR}` の波括弧が無い展開の直後に非 ASCII 文字が来る箇所を検出する."""
    for sh in sorted(plugin_dir.glob("scripts/**/*.sh")) + sorted(plugin_dir.glob("hooks/**/*.sh")):
        for lineno, line in enumerate(read_text(sh).splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue  # コメント行は展開されない
            # 行内コメント以降も展開されないので落とす（`code # 説明の $VAR（...）`）
            code = line.split(" #", 1)[0]
            match = BARE_EXPANSION_BEFORE_MULTIBYTE_RE.search(code)
            if match is None:
                continue
            errors.append(
                "[shell-multibyte] %s:%d 展開 `%s` の直後が非 ASCII。UTF-8 ロケールの bash が"
                "変数名に取り込み `set -u` で落ちる（`${%s}` と波括弧で囲む）"
                % (sh.relative_to(ROOT), lineno, match.group(0), match.group(0)[1:])
            )


CHECKS = [
    check_allowed_tools_exists,
    check_allowed_tools_pair,
    check_hooks_safety,
    check_hook_script_refs,
    check_safe_hook_sync,
    check_references,
    check_doc_anchors,
    check_trigger_phrases,
    check_shell_syntax,
    check_shell_multibyte_expansion,
    check_doc_structure,
    check_pending_version_placeholder,
]


# Agent fanout の同期起動明示: CC 2.1.198 で Agent tool の既定が background 実行に
# 変わったため、fanout して結果を待つ設計の skill/command は各 Agent call に
# `run_in_background: false` を明示する必要がある（CLAUDE.md Gotchas 参照）。
# 「fanout して結果を待つ構造か」は文脈判断だが、「並列 Agent 起動の記述があるのに
# run_in_background にファイル内で一度も言及しない」は grep で近似できるため
# 非ブロッキング warning として検出する（8 箇所修正・2 箇所取り残しの実績が昇格根拠）。
AGENT_FANOUT_RE = re.compile(
    r"並列[^\n]{0,20}(?:Agent|agent|エージェント)"  # 「並列で Agent を起動」「並列 Agent」
    r"|(?:Agent|agent|エージェント)[^\n]{0,20}並列"  # 「Agent tool call を…並列」「explorer 並列起動」
    r"|multiple Agent tool calls"
    r"|agents?[^\n]{0,30}in parallel",
    re.IGNORECASE,
)
# 起動動詞が同一行に無い記述（用語説明・Phase 一覧の要約等）は起動指示でないため除外.
AGENT_LAUNCH_VERB_RE = re.compile(r"起動|走査|実行|launch|spawn", re.IGNORECASE)
RUN_IN_BACKGROUND_RE = re.compile(r"run_in_background")


def _check_agent_sync_in(files: list[Path], tag: str, warnings: list[str]) -> None:
    for md in files:
        body = read_text(md)
        if RUN_IN_BACKGROUND_RE.search(body):
            continue
        hit_line = next(
            (
                i
                for i, line in enumerate(body.splitlines(), start=1)
                if AGENT_FANOUT_RE.search(line) and AGENT_LAUNCH_VERB_RE.search(line)
            ),
            None,
        )
        if hit_line is None:
            continue
        rel = md.relative_to(ROOT)
        warnings.append(
            f"[agent-sync:{tag}] 要確認: 並列 Agent 起動の記述があるが `run_in_background` に言及なし"
            f"（CC 2.1.198+ は既定 background。結果を待つ設計なら `run_in_background: false` を明示—人手確認）: {rel}:{hit_line}"
        )


def check_agent_sync_launch(plugin_dir: Path, warnings: list[str]) -> None:
    """並列 Agent 起動を指示する SKILL.md / command が run_in_background に言及しているか."""
    targets: list[Path] = []
    targets += sorted((plugin_dir / "skills").glob("*/SKILL.md"))
    targets += sorted((plugin_dir / "commands").glob("*.md"))
    _check_agent_sync_in(targets, plugin_dir.name, warnings)


def check_agent_sync_launch_repo_local(warnings: list[str]) -> None:
    """repo ローカル（プラグイン外）の .claude/skills / .claude/commands も同様に検査."""
    targets: list[Path] = []
    targets += sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    targets += sorted((ROOT / ".claude" / "commands").glob("*.md"))
    _check_agent_sync_in(targets, "repo-local", warnings)


def resolve_plugins(args: list[str]) -> list[Path]:
    """引数のプラグイン名 / パスを解決する（引数なしなら全プラグイン）.

    **相対パスは CWD ではなく ROOT 基準で解く**（GitHub issue #176）: CWD 相対だと
    リポジトリ外から `validate_plugin_quality.py code-review` を起動したときに
    存在しないディレクトリへ解決され、**プラグイン別検査を 1 つも走らせずに passed** になる.
    """
    if args:
        return [Path(a).resolve() if Path(a).is_absolute() else (ROOT / a).resolve()
                for a in args]
    return sorted(p.parent.parent for p in ROOT.glob("*/.claude-plugin/plugin.json"))


def main() -> int:
    args = sys.argv[1:]
    update_pins = "--update-ssot-pins" in args
    args = [a for a in args if a != "--update-ssot-pins"]
    if update_pins:
        print("Updating SSoT pins (正本を確認済みとして打ち直す):", file=sys.stderr)
        # errors を捨てない: 打ち直しは pin 記法のミスが最も起きる操作なので,
        # canonical 欠落 / anchor 不明などをその場で出さないと次の pre-commit まで露見しない
        pin_errors: list[str] = []
        n = check_ssot_pins(pin_errors, update=True)
        print(f"  total: {n} pin(s) updated", file=sys.stderr)
        for e in pin_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1 if pin_errors else 0
    plugins = resolve_plugins(args)
    errors: list[str] = []
    warnings: list[str] = []
    for plugin_dir in plugins:
        if not (plugin_dir / ".claude-plugin" / "plugin.json").is_file():
            # **黙って飛ばさない**（GitHub issue #176）: 綴り間違いや別 cwd からの起動で
            # 「検査を 1 つも走らせずに passed」になる。指定したのに見つからないのは違反
            errors.append(f"[args] 指定されたプラグインが無い（plugin.json を見つけられない）: {plugin_dir}")
            continue
        for check in CHECKS:
            check(plugin_dir, errors)
        check_allowed_tools_minimality(plugin_dir, warnings)
        check_agent_sync_launch(plugin_dir, warnings)
        check_hook_self_judgement(plugin_dir, warnings)

    check_routing_axes_sync(errors)
    check_schema_markers_sync(errors)
    check_test_collection(errors)
    check_duplicate_test_bodies(errors)
    check_ssot_pins(errors)
    check_event_bus_sync(errors)
    check_agent_sync_launch_repo_local(warnings)
    check_context_budget(warnings)
    check_skill_body_size(warnings)

    if warnings:
        # 助言（非ブロッキング）. errors と分離して常に出力する.
        print("Plugin quality warnings (allowed-tools 最小性 / 非ブロッキング):", file=sys.stderr)
        print("", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  total: {len(warnings)} warning(s)", file=sys.stderr)
        print("", file=sys.stderr)

    if errors:
        print("Plugin quality validation failed:", file=sys.stderr)
        print("", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  total: {len(errors)} issue(s)", file=sys.stderr)
        return 1

    print(f"Plugin quality validation passed ({len(plugins)} plugins, {len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
