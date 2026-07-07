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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SAFE_HOOK = ROOT / ".claude-plugin" / "lib" / "safe-hook.sh"

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
