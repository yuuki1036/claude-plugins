#!/usr/bin/env python3
"""
Eval runner: トリガーフレーズ→期待スキル起動の回帰テスト。

claude CLI を headless モードで起動し、ユーザープロンプトに対して
Claude がどのスキルを選択するかを検証する。副作用を避けるため、
実際の実行ではなく「どのスキルを呼ぶか」を JSON で応答させる形に
プロンプトを変形して評価する。

Usage:
    python3 evals/runner.py                           # 全ケース実行
    python3 evals/runner.py --plugin dev-workflow     # プラグイン絞り込み
    python3 evals/runner.py --case commit-ja          # ケース ID 絞り込み
    python3 evals/runner.py --k 1                     # k=1 に上書き（スモーク）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
CASES_DIR = EVALS_DIR / "cases"
REPORTS_DIR = EVALS_DIR / "reports"

PROMPT_WRAPPER = """{user_prompt}

---
重要: 上記リクエストに対して、実際にはスキルやツールを実行しないでください。
どのスキルを呼び出すのが適切かだけを判断し、最終行に次の JSON 形式で一行だけ出力してください。

{{"skill": "plugin-name:skill-name"}}

該当スキルがない場合:

{{"skill": null}}

JSON 以外のテキストは出力前に説明として書いて構いませんが、最終行は必ず JSON 一行のみにしてください。
"""


@dataclass
class Case:
    plugin: str
    id: str
    prompt: str
    expected_skill: str
    k: int = 3


@dataclass
class CaseResult:
    case: Case
    attempts: list[str | None] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if len(self.attempts) < self.case.k:
            return False
        return all(self._matches(a) for a in self.attempts[: self.case.k])

    def _matches(self, observed: str | None) -> bool:
        if observed is None:
            return False
        expected = self.case.expected_skill
        # suffix match: "plugin:skill" == "skill" も許容
        if observed == expected:
            return True
        exp_tail = expected.split(":", 1)[-1]
        obs_tail = observed.split(":", 1)[-1]
        return exp_tail == obs_tail


def parse_cases(paths: list[Path]) -> list[Case]:
    cases: list[Case] = []
    for path in paths:
        data = load_yaml(path)
        plugin = data.get("plugin") or path.stem
        for raw in data.get("cases", []):
            cases.append(
                Case(
                    plugin=plugin,
                    id=raw["id"],
                    prompt=raw["prompt"],
                    expected_skill=raw["expected_skill"],
                    k=int(raw.get("k", 3)),
                )
            )
    return cases


def load_yaml(path: Path) -> dict:
    """Minimal YAML subset loader (key: value, '- ' list items, 2-space indent)."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return _fallback_yaml(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _fallback_yaml(text: str) -> dict:
    """
    pyyaml が無い環境向けの小さなローダー。
    本 evals で使う形式（トップ key: value と cases: リスト）のみ対応。
    """
    root: dict = {}
    cases: list[dict] = []
    current: dict | None = None
    in_cases = False
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0:
            in_cases = False
            if line == "cases:":
                in_cases = True
                root["cases"] = cases
                continue
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            if m:
                key, val = m.group(1), m.group(2)
                root[key] = _coerce(val)
        elif in_cases:
            if line.startswith("- "):
                current = {}
                cases.append(current)
                line = line[2:].strip()
                if not line:
                    continue
            if current is None:
                continue
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            if m:
                current[m.group(1)] = _coerce(m.group(2))
    return root


def _coerce(val: str):
    val = val.strip()
    if not val:
        return ""
    if val.startswith(('"', "'")) and val.endswith(val[0]):
        return val[1:-1]
    if val.isdigit():
        return int(val)
    return val


def run_case(case: Case, timeout: int = 120, dry_run: bool = False) -> CaseResult:
    result = CaseResult(case=case)
    prompt = PROMPT_WRAPPER.format(user_prompt=case.prompt)
    for attempt in range(case.k):
        if dry_run:
            result.attempts.append(case.expected_skill)
            continue
        try:
            observed = invoke_claude(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            result.errors.append(f"attempt {attempt + 1}: timeout")
            result.attempts.append(None)
            break
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"attempt {attempt + 1}: {exc}")
            result.attempts.append(None)
            break
        result.attempts.append(observed)
        if not result._matches(observed):
            # 早期終了: pass^k は連続成功なので一度失敗したら残り不要
            break
    return result


def invoke_claude(prompt: str, timeout: int) -> str | None:
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "text",
        "--permission-mode",
        "plan",
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"claude exited with {completed.returncode}: {completed.stderr[:200]}"
        )
    return extract_skill(completed.stdout)


SKILL_RE = re.compile(r'\{\s*"skill"\s*:\s*("([^"\\]*(?:\\.[^"\\]*)*)"|null)\s*\}')


def extract_skill(stdout: str) -> str | None:
    """応答の末尾から JSON 一行を探し skill 値を抽出する。"""
    matches = list(SKILL_RE.finditer(stdout))
    if not matches:
        return None
    last = matches[-1]
    inner = last.group(1)
    if inner == "null":
        return None
    return last.group(2)


def render_report(results: list[CaseResult]) -> str:
    lines: list[str] = []
    lines.append("# Eval Runner Report")
    lines.append("")

    by_plugin: dict[str, list[CaseResult]] = {}
    for r in results:
        by_plugin.setdefault(r.case.plugin, []).append(r)

    lines.append("## Summary")
    lines.append("")
    lines.append("| Plugin | Pass | Fail | Cases |")
    lines.append("|--------|------|------|-------|")
    total_pass = 0
    total_fail = 0
    for plugin, items in sorted(by_plugin.items()):
        p = sum(1 for r in items if r.passed)
        f = len(items) - p
        total_pass += p
        total_fail += f
        lines.append(f"| {plugin} | {p} | {f} | {len(items)} |")
    lines.append(f"| **total** | **{total_pass}** | **{total_fail}** | **{total_pass + total_fail}** |")
    lines.append("")

    lines.append("## Details")
    for plugin, items in sorted(by_plugin.items()):
        lines.append("")
        lines.append(f"### {plugin}")
        for r in items:
            status = "PASS" if r.passed else "FAIL"
            lines.append(
                f"- [{status}] `{r.case.id}` (k={r.case.k}) — expected `{r.case.expected_skill}`"
            )
            lines.append(f"    - prompt: {r.case.prompt}")
            for i, a in enumerate(r.attempts, start=1):
                lines.append(f"    - attempt {i}: {a!r}")
            for e in r.errors:
                lines.append(f"    - error: {e}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", help="プラグイン名で絞り込み")
    parser.add_argument("--case", help="ケース ID で絞り込み")
    parser.add_argument("--k", type=int, help="全ケースの k を上書き")
    parser.add_argument("--timeout", type=int, default=120, help="claude 呼び出しタイムアウト秒")
    parser.add_argument("--dry-run", action="store_true", help="claude を呼ばず全 PASS で通す")
    parser.add_argument("--report", type=Path, help="レポート出力先 (md)")
    args = parser.parse_args()

    paths = sorted(CASES_DIR.glob("*.yaml"))
    if not paths:
        print(f"no case files in {CASES_DIR}", file=sys.stderr)
        return 2

    cases = parse_cases(paths)
    if args.plugin:
        cases = [c for c in cases if c.plugin == args.plugin]
    if args.case:
        cases = [c for c in cases if c.id == args.case]
    if args.k is not None:
        for c in cases:
            c.k = args.k
    if not cases:
        print("no cases matched filter", file=sys.stderr)
        return 2

    results: list[CaseResult] = []
    for c in cases:
        print(f"running {c.plugin}/{c.id} (k={c.k})...", file=sys.stderr)
        results.append(run_case(c, timeout=args.timeout, dry_run=args.dry_run))

    report = render_report(results)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
        print(f"report written: {args.report}", file=sys.stderr)
    else:
        print(report)

    fail_count = sum(1 for r in results if not r.passed)
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
