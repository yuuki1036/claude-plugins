#!/usr/bin/env python3
"""
Eval runner: トリガーフレーズ→期待スキル起動の回帰テスト + 多層 grader。

claude CLI を headless モードで起動し、ユーザープロンプトに対して
Claude がどのスキルを選択するかを検証する。副作用を避けるため、
実際の実行ではなく「どのスキルを呼ぶか」を JSON で応答させる形に
プロンプトを変形して評価する。

Grader（waza 風の多層判定）:
  - skill_invocation: expected_skill との一致（自動付与）
  - text:             stdout の regex match (mode=must_match | must_not_match)
  - behavior:         latency / stdout 文字数の上限

Tags（hold-out 機構）:
  - case に tags: [...] を付け、--exclude-tag / --only-tag でフィルタ
  - デフォルトで holdout を除外する（改訂サイクルで参照禁止のホールドアウト）

Models（モデル間比較）:
  - --models opus-4-7,sonnet-4-6 で複数モデル実行
  - レポートに比較表を出力

Usage:
    python3 evals/runner.py                                  # 全ケース実行
    python3 evals/runner.py --plugin dev-workflow            # プラグイン絞り込み
    python3 evals/runner.py --case commit-ja                 # ケース ID 絞り込み
    python3 evals/runner.py --k 1                            # k=1 に上書き（スモーク）
    python3 evals/runner.py --models opus-4-7,sonnet-4-6     # モデル比較
    python3 evals/runner.py --only-tag holdout               # ホールドアウトのみ
    python3 evals/runner.py --exclude-tag holdout,slow       # 除外タグ追加
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
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

DEFAULT_EXCLUDE_TAGS = ["holdout"]


# ---------- Data classes ----------


@dataclass
class Case:
    plugin: str
    id: str
    prompt: str
    expected_skill: str | list[str] | None
    k: int = 3
    tags: list[str] = field(default_factory=list)
    graders: list[dict] = field(default_factory=list)
    # skill_json: PROMPT_WRAPPER で包みスキル選択 JSON を要求（デフォルト）
    # none:       prompt をそのまま実行（判定校正ケース用。expected_skill とは併用不可）
    wrapper: str = "skill_json"

    @property
    def expected_list(self) -> list[str]:
        if self.expected_skill is None:
            return []
        if isinstance(self.expected_skill, list):
            return list(self.expected_skill)
        return [self.expected_skill]


@dataclass
class AttemptObservation:
    skill: str | None
    stdout: str
    latency_ms: int
    error: str | None = None


@dataclass
class GraderResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    case: Case
    model: str
    attempts: list[AttemptObservation] = field(default_factory=list)
    grader_results: list[list[GraderResult]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if len(self.attempts) < self.case.k:
            return False
        for attempt_graders in self.grader_results[: self.case.k]:
            if not all(g.passed for g in attempt_graders):
                return False
        return True


# ---------- Graders ----------


class Grader:
    name: str = "grader"

    def grade(self, obs: AttemptObservation) -> GraderResult:
        raise NotImplementedError


class SkillInvocationGrader(Grader):
    def __init__(self, expected: list[str]):
        self.expected = expected
        self.name = "skill_invocation"

    def grade(self, obs: AttemptObservation) -> GraderResult:
        if obs.error:
            return GraderResult(self.name, False, f"runtime error: {obs.error}")
        if obs.skill is None:
            return GraderResult(self.name, False, "no skill detected in response")
        observed_tail = obs.skill.split(":", 1)[-1]
        for exp in self.expected:
            if obs.skill == exp:
                return GraderResult(self.name, True, f"matched {exp}")
            if exp.split(":", 1)[-1] == observed_tail:
                return GraderResult(self.name, True, f"tail-matched {exp}")
        return GraderResult(self.name, False, f"got {obs.skill!r}, expected {self.expected}")


class TextGrader(Grader):
    def __init__(self, name: str, pattern: str, mode: str = "must_match"):
        self.name = f"text:{name}"
        self.pattern = re.compile(pattern, re.MULTILINE | re.DOTALL)
        if mode not in {"must_match", "must_not_match"}:
            raise ValueError(f"text grader mode must be must_match|must_not_match, got {mode}")
        self.mode = mode

    def grade(self, obs: AttemptObservation) -> GraderResult:
        if obs.error:
            return GraderResult(self.name, False, f"runtime error: {obs.error}")
        match = self.pattern.search(obs.stdout)
        if self.mode == "must_match":
            ok = match is not None
            return GraderResult(self.name, ok, "matched" if ok else "no match")
        ok = match is None
        return GraderResult(self.name, ok, "no match" if ok else f"unexpected match: {match.group(0)[:60]!r}")


class BehaviorGrader(Grader):
    def __init__(
        self,
        name: str,
        max_latency_ms: int | None = None,
        max_stdout_chars: int | None = None,
    ):
        self.name = f"behavior:{name}"
        self.max_latency_ms = max_latency_ms
        self.max_stdout_chars = max_stdout_chars

    def grade(self, obs: AttemptObservation) -> GraderResult:
        if obs.error:
            return GraderResult(self.name, False, f"runtime error: {obs.error}")
        if self.max_latency_ms is not None and obs.latency_ms > self.max_latency_ms:
            return GraderResult(
                self.name, False, f"latency {obs.latency_ms}ms > {self.max_latency_ms}ms"
            )
        if self.max_stdout_chars is not None and len(obs.stdout) > self.max_stdout_chars:
            return GraderResult(
                self.name,
                False,
                f"stdout {len(obs.stdout)} chars > {self.max_stdout_chars}",
            )
        return GraderResult(self.name, True, f"latency={obs.latency_ms}ms chars={len(obs.stdout)}")


def build_graders(case: Case) -> list[Grader]:
    graders: list[Grader] = []
    if case.expected_skill is not None:
        graders.append(SkillInvocationGrader(case.expected_list))
    for raw in case.graders:
        gtype = raw.get("type")
        name = raw.get("name", gtype or "anon")
        if gtype == "text":
            graders.append(
                TextGrader(name, raw["pattern"], raw.get("mode", "must_match"))
            )
        elif gtype == "behavior":
            graders.append(
                BehaviorGrader(
                    name,
                    max_latency_ms=raw.get("max_latency_ms"),
                    max_stdout_chars=raw.get("max_stdout_chars"),
                )
            )
        else:
            raise ValueError(f"unknown grader type: {gtype!r} (case={case.id})")
    return graders


# ---------- Loader ----------


def parse_cases(paths: list[Path]) -> list[Case]:
    cases: list[Case] = []
    for path in paths:
        data = load_yaml(path)
        plugin = data.get("plugin") or path.stem
        for raw in data.get("cases", []):
            wrapper = raw.get("wrapper", "skill_json")
            if wrapper not in {"skill_json", "none"}:
                raise ValueError(
                    f"wrapper must be skill_json|none, got {wrapper!r} (case={raw['id']})"
                )
            if wrapper == "none" and raw.get("expected_skill") is not None:
                raise ValueError(
                    f"wrapper: none は expected_skill と併用できません (case={raw['id']})"
                )
            cases.append(
                Case(
                    plugin=plugin,
                    id=raw["id"],
                    prompt=raw["prompt"],
                    expected_skill=raw.get("expected_skill"),
                    k=int(raw.get("k", 3)),
                    tags=list(raw.get("tags", []) or []),
                    graders=list(raw.get("graders", []) or []),
                    wrapper=wrapper,
                )
            )
    return cases


def load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        return _fallback_yaml(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _fallback_yaml(text: str) -> dict:
    """
    pyyaml が無い環境向けの最小ローダー。
    トップ key: value と cases リストの flat フィールドのみ対応。
    graders / tags 等のネスト構造は pyyaml 必須。
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
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1]
        return [_coerce(item) for item in inner.split(",") if item.strip()]
    if val.isdigit():
        return int(val)
    return val


# ---------- Filtering ----------


def filter_by_tags(
    cases: list[Case],
    only_tags: list[str],
    exclude_tags: list[str],
) -> list[Case]:
    out: list[Case] = []
    only_set = set(only_tags)
    exclude_set = set(exclude_tags)
    for c in cases:
        case_tags = set(c.tags)
        if only_set and not (case_tags & only_set):
            continue
        if exclude_set and (case_tags & exclude_set):
            continue
        out.append(c)
    return out


# ---------- Execution ----------


def run_case(
    case: Case,
    model: str | None,
    timeout: int = 120,
    dry_run: bool = False,
) -> CaseResult:
    graders = build_graders(case)
    result = CaseResult(case=case, model=model or "default")
    if case.wrapper == "none":
        prompt = case.prompt
    else:
        prompt = PROMPT_WRAPPER.format(user_prompt=case.prompt)
    for attempt in range(case.k):
        if dry_run:
            fake_skill = case.expected_list[0] if case.expected_list else None
            obs = AttemptObservation(
                skill=fake_skill,
                stdout=f"(dry-run)\n{json.dumps({'skill': fake_skill})}\n",
                latency_ms=0,
            )
        else:
            try:
                obs = invoke_claude(prompt, model=model, timeout=timeout)
            except subprocess.TimeoutExpired:
                obs = AttemptObservation(
                    skill=None,
                    stdout="",
                    latency_ms=timeout * 1000,
                    error=f"timeout after {timeout}s",
                )
            except Exception as exc:  # noqa: BLE001
                obs = AttemptObservation(
                    skill=None, stdout="", latency_ms=0, error=str(exc)
                )
        result.attempts.append(obs)
        graded = [g.grade(obs) for g in graders]
        result.grader_results.append(graded)
        # 早期終了: pass^k は連続成功なので一度失敗したら残り不要
        if not all(g.passed for g in graded):
            break
    return result


def invoke_claude(
    prompt: str, model: str | None, timeout: int
) -> AttemptObservation:
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "text",
        "--permission-mode",
        "plan",
    ]
    if model:
        cmd.extend(["--model", model])
    t0 = time.monotonic()
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    if completed.returncode != 0:
        # claude CLI はエラーを stdout に出すことがある（例: 未ログイン時の
        # "Not logged in · Please run /login" は stdout・stderr 空・exit 1）。
        # stderr が空のとき stdout を出さないと原因が完全に不可視になる
        detail = (completed.stderr.strip() or completed.stdout.strip())[:200]
        raise RuntimeError(f"claude exited with {completed.returncode}: {detail}")
    return AttemptObservation(
        skill=extract_skill(completed.stdout),
        stdout=completed.stdout,
        latency_ms=latency_ms,
    )


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


# ---------- Reporting ----------


def render_report(results: list[CaseResult], models: list[str]) -> str:
    lines: list[str] = []
    lines.append("# Eval Runner Report")
    lines.append("")

    by_model: dict[str, list[CaseResult]] = {}
    for r in results:
        by_model.setdefault(r.model, []).append(r)
    model_order = models if models else sorted(by_model.keys())

    # Summary（モデル別）
    lines.append("## Summary")
    lines.append("")
    header = ["Plugin"] + model_order
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    plugins = sorted({r.case.plugin for r in results})
    totals = {m: [0, 0] for m in model_order}
    for plugin in plugins:
        row = [plugin]
        for m in model_order:
            items = [r for r in by_model.get(m, []) if r.case.plugin == plugin]
            p = sum(1 for r in items if r.passed)
            f = len(items) - p
            totals[m][0] += p
            totals[m][1] += f
            row.append(f"{p}/{len(items)}")
        lines.append("| " + " | ".join(row) + " |")
    total_row = ["**total**"] + [
        f"**{totals[m][0]}/{totals[m][0] + totals[m][1]}**" for m in model_order
    ]
    lines.append("| " + " | ".join(total_row) + " |")
    lines.append("")

    # モデル比較表
    if len(model_order) > 1:
        lines.append("## Model Comparison")
        lines.append("")
        comp_header = ["Plugin", "Case"] + model_order
        lines.append("| " + " | ".join(comp_header) + " |")
        lines.append("|" + "|".join(["---"] * len(comp_header)) + "|")
        keys = sorted({(r.case.plugin, r.case.id) for r in results})
        for plugin, cid in keys:
            row = [plugin, f"`{cid}`"]
            for m in model_order:
                hit = next(
                    (
                        r
                        for r in by_model.get(m, [])
                        if r.case.plugin == plugin and r.case.id == cid
                    ),
                    None,
                )
                if hit is None:
                    row.append("-")
                else:
                    row.append("PASS" if hit.passed else "FAIL")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    # Details
    lines.append("## Details")
    for m in model_order:
        items = by_model.get(m, [])
        if not items:
            continue
        lines.append("")
        lines.append(f"### Model: {m}")
        by_plugin: dict[str, list[CaseResult]] = {}
        for r in items:
            by_plugin.setdefault(r.case.plugin, []).append(r)
        for plugin, cases in sorted(by_plugin.items()):
            lines.append("")
            lines.append(f"#### {plugin}")
            for r in cases:
                status = "PASS" if r.passed else "FAIL"
                tag_str = f" tags={r.case.tags}" if r.case.tags else ""
                lines.append(
                    f"- [{status}] `{r.case.id}` (k={r.case.k}){tag_str} — expected `{r.case.expected_skill}`"
                )
                lines.append(f"    - prompt: {r.case.prompt}")
                for i, (a, gs) in enumerate(zip(r.attempts, r.grader_results), start=1):
                    lat = f"{a.latency_ms}ms" if a.latency_ms else "—"
                    lines.append(
                        f"    - attempt {i}: skill={a.skill!r} latency={lat}"
                    )
                    if a.error:
                        lines.append(f"        - error: {a.error}")
                    for g in gs:
                        mark = "ok" if g.passed else "FAIL"
                        lines.append(f"        - [{mark}] {g.name}: {g.detail}")
                    # 失敗 attempt は stdout 抜粋を出してデバッグ可能にする
                    if not all(g.passed for g in gs) and a.stdout:
                        snippet = a.stdout.strip().replace("\n", " ⏎ ")[:300]
                        lines.append(f"        - stdout: {snippet!r}")
    return "\n".join(lines) + "\n"


# ---------- CLI ----------


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", help="プラグイン名で絞り込み")
    parser.add_argument("--case", help="ケース ID で絞り込み")
    parser.add_argument("--k", type=int, help="全ケースの k を上書き")
    parser.add_argument("--timeout", type=int, default=120, help="claude 呼び出しタイムアウト秒")
    parser.add_argument("--dry-run", action="store_true", help="claude を呼ばず全 PASS で通す")
    parser.add_argument("--report", type=Path, help="レポート出力先 (md)")
    parser.add_argument(
        "--models",
        help="比較対象モデルを CSV で指定 (例: opus-4-7,sonnet-4-6)。省略時は claude のデフォルト",
    )
    parser.add_argument(
        "--only-tag",
        help="指定タグを持つケースのみ実行 (CSV)。--exclude-tag より優先",
    )
    parser.add_argument(
        "--exclude-tag",
        help=f"指定タグを持つケースを除外 (CSV)。デフォルト: {','.join(DEFAULT_EXCLUDE_TAGS)}",
    )
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

    only_tags = _split_csv(args.only_tag)
    exclude_tags = _split_csv(args.exclude_tag) if args.exclude_tag is not None else list(DEFAULT_EXCLUDE_TAGS)
    if only_tags:
        # only-tag 指定時は exclude を無効化（明示的に hold-out を狙うケースのため）
        exclude_tags = []
    cases = filter_by_tags(cases, only_tags, exclude_tags)

    if args.k is not None:
        for c in cases:
            c.k = args.k
    if not cases:
        print("no cases matched filter", file=sys.stderr)
        return 2

    models = _split_csv(args.models) or [None]  # type: ignore[list-item]
    model_labels: list[str] = [m or "default" for m in models]

    results: list[CaseResult] = []
    for model in models:
        for c in cases:
            label = model or "default"
            print(
                f"running [{label}] {c.plugin}/{c.id} (k={c.k}, tags={c.tags})...",
                file=sys.stderr,
            )
            results.append(
                run_case(c, model=model, timeout=args.timeout, dry_run=args.dry_run)
            )

    report = render_report(results, model_labels)
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
