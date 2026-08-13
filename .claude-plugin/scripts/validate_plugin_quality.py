#!/usr/bin/env python3
"""プラグイン品質の決定的チェック.

/quality-check skill の検査項目のうち、機械的に検証可能なものを実行する.
validate_ssot.py がカバーする項目（SSoT 同期、schema、_requirements、hooks.json）
は対象外. 純粋に LLM 判定が必要な項目（CLAUDE.md 品質 等）はスキップ.

検査項目（errors = 違反, exit 1）:
  - allowed-tools 存在: 全 SKILL.md に allowed-tools が定義されているか
  - allowed-tools 一致: command <-> skill ペアの allowed-tools が完全一致か
  - hooks 安全性: hook スクリプトが safe_hook_init を呼んでいるか
  - safe-hook.sh 同期: 各プラグインの replica が canonical と byte-identical か
  - routing-axes 同期: spec ルーティング 3 軸コアの delimiter 区間が正本と一致するか（dedent 比較）
  - SSoT pin: `<!-- SSOT: <path>#<anchor> @<hash8> -->` の pin が正本の実ハッシュと一致するか.
    routing-axes は「区間が byte-identical」を検証するが, doc → doc の伝播関係の多くは
    言い換え / 要約なので一致比較にできない. pin は内容の一致ではなく『正本が変わったら
    消費サイトを確認して打ち直す』手順を強制する（v2.63.0 のセルフレビューで検出した
    欠陥 11 件中 6 件が「正本を直したが複製先に伝播していない」型だった）.
    打ち直し: `python3 validate_plugin_quality.py --update-ssot-pins`（明示操作。
    pre-commit では走らせない — 自動更新すると確認の強制力が消える）.
  - event-bus 同期: 実 publish される event（grep 実測=正本）と、それを記載する doc が一致するか
    （CLAUDE.md 表 / INDEX.md 表の event 集合 + INDEX.md publishes 行の plugin×event ペア）
  - references 参照整合性: SKILL.md / commands/*.md / agents/*.md 内 ${CLAUDE_PLUGIN_ROOT}/... が実在するか
  - トリガーフレーズ: SKILL.md description に 'トリガー:' が含まれているか
  - シェル構文: 同梱スクリプト（*/scripts/**.sh, */hooks/**.sh）が `bash -n` を通るか.
    CI は manifest と doc しか見ておらず, LLM が書いたスクリプトは構文検証を一度も
    経ずに配布されていた（issue #123 の meta-review）.

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

import hashlib
import json
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

# 正本 → 消費サイトの伝播関係を宣言する pin.
#   <!-- SSOT: <repo ルート相対の md パス>#<見出しの前方一致 anchor> @<hash8> -->
# anchor 省略でファイル全体. 検証対象は「pin を置いた場所」で決まる（scanner は repo 全体を舐める）.
SSOT_PIN_RE = re.compile(
    r"<!--\s*SSOT:\s*(?P<path>[^\s#>]+?)(?:#(?P<anchor>[^\s@>]+))?\s+@(?P<hash>[0-9a-f]+)\s*-->"
)
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


def _markdown_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """フェンス付きコードブロックの外にある見出しだけを (行 index, レベル, テキスト) で返す.

    フェンスを追跡しないと, bash コードブロック内のコメント行（`# ...`）が
    level 1 の見出しとして拾われ, 節がそこで打ち切られる. このリポジトリの
    references は実行手順として bash 片を多用するため, 構造的に踏みやすい.
    """
    heads: list[tuple[int, int, str]] = []
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
        if fence is not None:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    return heads


def _slice_section(path: Path, anchor: str | None) -> str | None:
    """正本 md から `anchor` の節を切り出す（anchor が None ならファイル全体）.

    anchor は見出しテキストの前方一致で当てる（`## 3.5. 可変部の…` に対し `3.5`）.
    節の範囲は見出し行から, 同レベル以上の次の見出しの直前まで.
    見出しの判定は `_markdown_headings` に委ね, フェンス内の `#` 行は見出しにしない.
    見つからなければ None（呼び出し側が error にする）.

    **`## 8` は同レベルの `## 8.5` を含まない**（節の区切りは見出しレベルで決まり,
    anchor 番号の階層では決まらない）. `8.5` を保護したいなら別 pin を打つ.
    """
    text = read_text(path)
    if anchor is None:
        return _normalize_section(text)
    lines = text.splitlines()
    heads = _markdown_headings(lines)
    start = level = None
    for pos, (i, lv, htext) in enumerate(heads):
        # `1` が `13. …` に当たる事故を防ぐため, anchor の直後に区切り（`.` / 空白）を要求する
        if htext == anchor or htext.startswith(f"{anchor}.") or htext.startswith(f"{anchor} "):
            start, level = i, lv
            rest = heads[pos + 1 :]
            break
    if start is None:
        return None
    end = next((i for i, lv, _ in rest if lv <= level), len(lines))
    return _normalize_section("\n".join(lines[start:end]))


def _canonical_digest(path: Path, anchor: str | None) -> str | None:
    section = _slice_section(path, anchor)
    if section is None:
        return None
    return hashlib.sha256(section.encode("utf-8")).hexdigest()[:SSOT_PIN_LEN]


def _iter_ssot_pins() -> list[tuple[Path, int, re.Match[str]]]:
    """リポジトリ内の全 md から SSOT pin 宣言を収集する（配置場所で運用範囲を決める）."""
    hits: list[tuple[Path, int, re.Match[str]]] = []
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            for m in SSOT_PIN_RE.finditer(line):
                hits.append((path, lineno, m))
    return hits


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
    for path, lineno, m in _iter_ssot_pins():
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
        if anchor is None and SSOT_PIN_RE.search(read_text(canonical)):
            # ファイル全体 pin の正本が自身も pin を持つと, 相手の pin 更新で正本の内容が
            # 変わる → こちらの pin も stale, が循環しうる（相互 pin では打ち直しが収束しない）.
            errors.append(
                f"[ssot-pin] ファイル全体 pin の正本が自身も pin を持つ（打ち直しが収束しない）。"
                f"節 anchor を指定するか pin を持たないファイルを正本にする: {raw_path} <- {loc}"
            )
            continue
        actual = _canonical_digest(canonical, anchor)
        if actual is None:
            errors.append(f"[ssot-pin] anchor '{anchor}' が {raw_path} に見つからない <- {loc}")
            continue
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


def _hook_script_paths(plugin_dir: Path, events: tuple[str, ...] | None) -> list[Path]:
    """hooks.json から指定イベントの hook スクリプトパスを解決する（args[] / legacy command 両対応）.

    events=None で全イベントを対象にする. 同一スクリプトの重複参照は 1 回に dedup する.
    """
    hooks_json = plugin_dir / "hooks" / "hooks.json"
    if not hooks_json.is_file():
        return []
    try:
        data = json.loads(read_text(hooks_json))
    except json.JSONDecodeError:
        return []  # JSON 破損は schema 検証（validate_ssot）の領分
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return []
    scripts: list[Path] = []
    seen: set[Path] = set()
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
                    script = plugin_dir / c.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                    if script.is_file() and script not in seen:
                        seen.add(script)
                        scripts.append(script)
    return scripts


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


CHECKS = [
    check_allowed_tools_exists,
    check_allowed_tools_pair,
    check_hooks_safety,
    check_safe_hook_sync,
    check_references,
    check_doc_anchors,
    check_trigger_phrases,
    check_shell_syntax,
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
    if args:
        return [Path(a).resolve() for a in args]
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
            continue
        for check in CHECKS:
            check(plugin_dir, errors)
        check_allowed_tools_minimality(plugin_dir, warnings)
        check_agent_sync_launch(plugin_dir, warnings)
        check_hook_self_judgement(plugin_dir, warnings)

    check_routing_axes_sync(errors)
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
