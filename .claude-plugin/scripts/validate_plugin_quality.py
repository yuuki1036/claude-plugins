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
  - event-bus 同期: 実 publish される event（grep 実測=正本）と、それを記載する doc が一致するか
    （CLAUDE.md 表 / INDEX.md 表の event 集合 + INDEX.md publishes 行の plugin×event ペア）
  - references 参照整合性: SKILL.md / commands/*.md / agents/*.md 内 ${CLAUDE_PLUGIN_ROOT}/... が実在するか
  - トリガーフレーズ: SKILL.md description に 'トリガー:' が含まれているか

検査項目（warnings = 助言, exit code に影響しない）:
  - allowed-tools 最小性 (#14b): frontmatter 宣言ツールが本文で未言及（未使用候補）.
    Read/Write/Edit/Glob/Grep/Bash や MCP ツールは日本語表現・記述的言及の偽陽性が
    あるため『要確認』に留め, LLM/人手の最終判断を残す (#14b の偽陽性除外規約に準拠).

実行: python3 validate_plugin_quality.py [plugin_dir ...]
  引数無し: 全プラグイン
  引数あり: 指定プラグインディレクトリのみ

Exit code: 0 (pass / warning のみ) / 1 (errors あり)
  warnings (allowed-tools 最小性) は exit code に影響しない（助言のみ）.
"""

from __future__ import annotations

import json
import re
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
    ROOT / "linear-workflow" / "skills" / "issue-create" / "SKILL.md",
    ROOT / "indie-workflow" / "skills" / "indie-issue-create" / "SKILL.md",
]
ROUTING_AXES_START = "<!-- ROUTING-AXES:START -->"
ROUTING_AXES_END = "<!-- ROUTING-AXES:END -->"

# 両プラグインで byte-identical であるべき共有 references（(canonical, replica) のペア）.
# issue-design の普遍部分（9 セクションテンプレ / 設計判断ルール）は linear / indie で同一内容を共有する.
SHARED_REFERENCES = [
    (
        ROOT / "linear-workflow" / "skills" / "issue-design" / "references" / "template-9sections.md",
        ROOT / "indie-workflow" / "skills" / "issue-design" / "references" / "template-9sections.md",
    ),
    (
        ROOT / "linear-workflow" / "skills" / "issue-design" / "references" / "design-rules.md",
        ROOT / "indie-workflow" / "skills" / "issue-design" / "references" / "design-rules.md",
    ),
]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
REF_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}(/[^\s)`'\"]+)")

# Event Bus: 実際に publish される event 名 ⇔ event を記載する doc の同期検証.
# publisher は skill(SKILL.md) / command(commands/*.md) / hook スクリプト(hooks/scripts/*.sh)
# の 3 種に分散するため、宣言 frontmatter は置かず `event_bus_publish "<event>"` の
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
EVENT_PUBLISHER_GLOBS = ["*/skills/**/SKILL.md", "*/commands/*.md", "*/hooks/scripts/*.sh"]


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
    """
    name = plugin_dir.name
    hooks_json = plugin_dir / "hooks" / "hooks.json"
    if not hooks_json.is_file():
        return
    try:
        data = json.loads(read_text(hooks_json))
    except json.JSONDecodeError:
        return
    referenced: set[Path] = set()
    cmd_re = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}(/[^\s;|&]+\.sh)")
    for event_matchers in data.get("hooks", {}).values():
        if not isinstance(event_matchers, list):
            continue
        for matcher in event_matchers:
            for h in matcher.get("hooks", []):
                cmd = h.get("command", "")
                for m in cmd_re.finditer(cmd):
                    referenced.add(plugin_dir / m.group(1).lstrip("/"))
    for script in sorted(referenced):
        if not script.is_file():
            continue
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


def check_shared_references_sync(errors: list[str]) -> None:
    """両プラグインで共有する references が byte-identical かを検証する（plugin 跨ぎ）."""
    for canonical, replica in SHARED_REFERENCES:
        if not canonical.is_file():
            errors.append(f"[shared-ref-sync] canonical missing: {canonical.relative_to(ROOT)}")
            continue
        if not replica.is_file():
            errors.append(f"[shared-ref-sync] replica missing: {replica.relative_to(ROOT)}")
            continue
        if canonical.read_bytes() != replica.read_bytes():
            errors.append(
                f"[shared-ref-sync] diverged: {replica.relative_to(ROOT)} "
                f"!= {canonical.relative_to(ROOT)}"
            )


def _collect_published_pairs() -> set[tuple[str, str]]:
    """コードベースの実 publish 箇所から (plugin, event) ペアを収集する（=正本）.

    plugin 名は発行元ファイルの相対パス先頭ディレクトリから導出する.
    """
    pairs: set[tuple[str, str]] = set()
    for pattern in EVENT_PUBLISHER_GLOBS:
        for path in ROOT.glob(pattern):
            plugin = path.relative_to(ROOT).parts[0]
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
    for md in targets:
        text = read_text(md)
        seen: set[str] = set()
        for m in REF_RE.finditer(text):
            ref = m.group(1).rstrip(".,);")
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


CHECKS = [
    check_allowed_tools_exists,
    check_allowed_tools_pair,
    check_hooks_safety,
    check_safe_hook_sync,
    check_references,
    check_trigger_phrases,
]


# linear-workflow / indie-workflow はミラー構造. 共通機能は片方の変更を必ず他方へ対称反映する規約
# （CLAUDE.md「linear-workflow / indie-workflow はミラー規約」）. このチェックは skill の存在・分類の
# 対称性を機械検証し、片側だけの追加・削除（取り残し）と対応表の stale を warning で拾う.
# 命名が異なるペアは MIRROR_SKILL_PAIRS で明示. 意図的な片側限定は *_ONLY で except 登録する
# （未登録の非対称＝取り残し疑い）. 構造差分（Phase 構成・dormant 連携）までは踏み込まない.
MIRROR_SKILL_PAIRS: dict[str, str] = {
    # linear skill 名 -> indie skill 名
    "follow-up": "indie-follow-up",
    "init": "indie-init",
    "issue-create": "indie-issue-create",
    "issue-design": "issue-design",
    "issue-maintain": "indie-issue-maintain",
    "knowledge": "knowledge",
    "knowledge-lint": "knowledge-lint",
    "linear-maintain": "indie-maintain",
    "session-start": "indie-start",
}
# 意図的な片側限定 skill（CLAUDE.md「意図的な非対称」）. ここに載らない片側 skill は取り残し疑いとして warning.
MIRROR_INTENTIONAL_LINEAR_ONLY: set[str] = {
    "dashboard",  # indie では indie-start が main ダッシュボードを兼ねるため linear のみ
}
MIRROR_INTENTIONAL_INDIE_ONLY: set[str] = {
    "indie-issue-discover",  # 「次に何をやるか」を一人で回す個人開発特化（linear 展開は必要顕在化まで保留）
    "retrospective",         # 「何を学んだか」の振り返り. 同上
}


def check_mirror_symmetry(warnings: list[str]) -> None:
    """linear-workflow / indie-workflow のミラー skill 対称性を検証する（非ブロッキング warning）.

    片側だけに追加・削除された skill（取り残し疑い）と、対応表 / except の stale を検出する.
    存在・分類の対称性に絞り、構造差分（Phase 構成・dormant 連携）までは踏み込まない.
    """
    linear_dir = ROOT / "linear-workflow" / "skills"
    indie_dir = ROOT / "indie-workflow" / "skills"
    if not linear_dir.is_dir() or not indie_dir.is_dir():
        return  # 片方でも未導入なら検証しない（後方互換・プラグイン独立性）

    linear_skills = {p.name for p in linear_dir.iterdir() if (p / "SKILL.md").is_file()}
    indie_skills = {p.name for p in indie_dir.iterdir() if (p / "SKILL.md").is_file()}
    tag = "mirror-symmetry"

    # 1. ペアの片側欠落（対応表にあるのに一方が実在しない）
    for lin, ind in sorted(MIRROR_SKILL_PAIRS.items()):
        lin_ok, ind_ok = lin in linear_skills, ind in indie_skills
        if lin_ok and not ind_ok:
            warnings.append(
                f"[{tag}] ミラーペアの indie 側が欠落: linear '{lin}' に対応する indie '{ind}' が無い"
                "（取り残し疑い. 対称実装するか対応表を見直す）"
            )
        elif ind_ok and not lin_ok:
            warnings.append(
                f"[{tag}] ミラーペアの linear 側が欠落: indie '{ind}' に対応する linear '{lin}' が無い"
                "（取り残し疑い. 対称実装するか対応表を見直す）"
            )

    # 2. 分類の網羅性（対応表にも except にも無い skill ＝ 新規片側追加の疑い）
    paired_linear = set(MIRROR_SKILL_PAIRS.keys())
    paired_indie = set(MIRROR_SKILL_PAIRS.values())
    for s in sorted(linear_skills - paired_linear - MIRROR_INTENTIONAL_LINEAR_ONLY):
        warnings.append(
            f"[{tag}] 未分類の linear skill '{s}'（ミラー対応表にも意図的非対称 except にも無い. "
            "indie 側に対称実装するか MIRROR_SKILL_PAIRS / MIRROR_INTENTIONAL_LINEAR_ONLY に登録）"
        )
    for s in sorted(indie_skills - paired_indie - MIRROR_INTENTIONAL_INDIE_ONLY):
        warnings.append(
            f"[{tag}] 未分類の indie skill '{s}'（ミラー対応表にも意図的非対称 except にも無い. "
            "linear 側に対称実装するか MIRROR_SKILL_PAIRS / MIRROR_INTENTIONAL_INDIE_ONLY に登録）"
        )

    # 3. 対応表 / except の stale（登録されているが実在しない）
    for s in sorted(MIRROR_INTENTIONAL_LINEAR_ONLY - linear_skills):
        warnings.append(f"[{tag}] MIRROR_INTENTIONAL_LINEAR_ONLY の '{s}' が実在しない（対応表を掃除）")
    for s in sorted(MIRROR_INTENTIONAL_INDIE_ONLY - indie_skills):
        warnings.append(f"[{tag}] MIRROR_INTENTIONAL_INDIE_ONLY の '{s}' が実在しない（対応表を掃除）")
    for lin, ind in sorted(MIRROR_SKILL_PAIRS.items()):
        if lin not in linear_skills and ind not in indie_skills:
            warnings.append(f"[{tag}] MIRROR_SKILL_PAIRS の '{lin}<->{ind}' が両側とも実在しない（対応表を掃除）")


def resolve_plugins(args: list[str]) -> list[Path]:
    if args:
        return [Path(a).resolve() for a in args]
    return sorted(p.parent.parent for p in ROOT.glob("*/.claude-plugin/plugin.json"))


def main() -> int:
    plugins = resolve_plugins(sys.argv[1:])
    errors: list[str] = []
    warnings: list[str] = []
    for plugin_dir in plugins:
        if not (plugin_dir / ".claude-plugin" / "plugin.json").is_file():
            continue
        for check in CHECKS:
            check(plugin_dir, errors)
        check_allowed_tools_minimality(plugin_dir, warnings)

    check_shared_references_sync(errors)
    check_routing_axes_sync(errors)
    check_event_bus_sync(errors)
    check_mirror_symmetry(warnings)

    if warnings:
        # 助言（非ブロッキング）. errors と分離して常に出力する.
        print("Plugin quality warnings (allowed-tools 最小性 / ミラー対称性 / 非ブロッキング):", file=sys.stderr)
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
