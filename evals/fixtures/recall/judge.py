#!/usr/bin/env python3
"""recall fixture の判定: expected.yaml と self-review の markdown レポート k=3 本を突き合わせる（GitHub issue #400）.

使い方:
    python3 evals/fixtures/recall/judge.py <fixture-id> <run1.md> <run2.md> <run3.md>

    <fixture-id> は expected.yaml の id か、その先頭の番号（`08`）。
    レポートは `claude -p "/code-review:self-review" ... > run1.md` で保存したもの（`--embed` は付けない。
    計測条件を runbook のまま保つため。2026-11-07 決定）。

判定規則の正本は README.md の「判定ルール」。ここが決めるのは **[機械]** の条件だけで、**[人]** の条件に
当たりうる指摘は「要確認」に挙げて人に任せる。

exit: 0 PASS / 1 FAIL / 2 判定不能（入力の誤り・PyYAML が無い・k が 3 でない・self-review のレポートでない・
      「指摘件数」の行と読めた指摘の数が合わない）/
      3 要確認（機械で決まる範囲は PASS で、人が読む候補が残る）
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "expected.yaml"

K = 3
RECALL_MIN_HITS = 2

SEVERITY_RANK = {"MINOR": 1, "MAJOR": 2, "CRITICAL": 3, "BLOCKER": 4}

# self-review の Step 6 の定型（code-review/skills/self-review/references/step-6.md）:
#   2. [confidence: 95][severity: CRITICAL][バグ] Missing null check
#      ファイル: src/utils.ts:42
# 🔁 付録は `- [調整前: …]` で始まり番号を持たないので、この形に当たらない（報告外の指摘を数えない）。
FINDING_RE = re.compile(r"^\s*(\d+)\.\s*((?:\[[^\]]*\]\s*)+)(.*)$")
TAG_RE = re.compile(r"\[([^\]]*)\]")
FILE_RE = re.compile(r"^\s*ファイル\s*[:：]\s*(.+?)\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s")
REPORT_MARK = "セルフレビュー結果"
# `path:48` / `path:48-57` / `path:L48`。パスに `[slug]` を含む fixture があるので、パス側は `:` の手前まで何でも取る
PATH_LINE_RE = re.compile(r"^(?P<path>.+?):L?(?P<a>\d+)(?:\s*[-–~〜]\s*L?(?P<b>\d+))?")
BARE_LINE_RE = re.compile(r"^L?(?P<a>\d+)(?:\s*[-–~〜]\s*L?(?P<b>\d+))?")
# `path（48 行目）` / `path L48` は `path:48` に寄せてから読む
LINE_NOTE_RE = re.compile(r"(?:（|\(|\s+)L?(\d+(?:\s*[-–~〜]\s*\d+)?)\s*(?:行目?)?(?:）|\))?$")
# 値に `effort/config/scope` のような `/` を含むので、項目の区切り ` / ` まで取る
SKEPTIC_RE = re.compile(r"冷や読み skeptic\s*(?P<v>.*?)(?:\s/\s|$)")
COUNTS_RE = re.compile(r"\*\*指摘件数\*\*\s*[:：]\s*(?P<v>.+)$")


@dataclass
class Finding:
    number: int
    severity: str
    title: str
    # パス → 主対象の行（範囲は展開済み）。行番号の無いパスは空集合
    files: dict[str, set[int]] = field(default_factory=dict)
    body: list[str] = field(default_factory=list)

    @property
    def rank(self) -> int:
        return SEVERITY_RANK[self.severity]

    @property
    def text(self) -> str:
        # パターンは 1 行の `.*` で書かれているので、本文の改行をまたいで当たるよう 1 行に繋ぐ
        return " ".join([self.title, *self.body])

    @property
    def has_line(self) -> bool:
        return any(self.files.values())

    def lines_in(self, targets: list[str]) -> set[int]:
        out: set[int] = set()
        for path, lines in self.files.items():
            if any(path_matches(path, t) for t in targets):
                out |= lines
        return out

    def label(self) -> str:
        loc = ", ".join(
            f"{p}:{fmt_lines(ls)}" if ls else p for p, ls in self.files.items()
        ) or "（ファイル欄なし）"
        return f"#{self.number} [{self.severity}] {self.title} — {loc}"


@dataclass
class Report:
    path: str
    is_self_review: bool
    findings: list[Finding]
    skeptic: str | None
    # 「**指摘件数**: BLOCKER N 件 / …」の値。行が無ければ None
    declared: dict[str, int] | None = None

    def count_mismatch(self) -> str | None:
        """読めた指摘の数が「指摘件数」の行と合わなければ理由を返す（書式が変わって読めていない回を判定不能にする）."""
        if self.declared is None:
            return "「指摘件数」の行が無い"
        if set(self.declared) != set(SEVERITY_RANK):
            return "「指摘件数」の行から 4 つの severity の件数を読めない"
        got = {s: sum(1 for f in self.findings if f.severity == s) for s in SEVERITY_RANK}
        diff = [f"{s} {got[s]}/{self.declared[s]}" for s in SEVERITY_RANK if got[s] != self.declared[s]]
        return f"読めた指摘の数が「指摘件数」と合わない（{', '.join(diff)}）" if diff else None


def fmt_lines(lines: set[int]) -> str:
    return ",".join(str(n) for n in sorted(lines))


def _span(a: str, b: str | None) -> set[int]:
    lo, hi = int(a), int(b) if b else int(a)
    if hi < lo:  # mutation-ok: hi == lo は入れ替えても同じ範囲になる
        lo, hi = hi, lo
    return set(range(lo, hi + 1))


def parse_file_field(value: str) -> dict[str, set[int]]:
    """`ファイル:` 欄を パス → 行 にする。`a.ts:48, 57` の 2 つ目のように番号だけの項は直前のパスに足す."""
    files: dict[str, set[int]] = {}
    current: str | None = None
    for part in re.split(r"\s*(?:[,、]|\s/\s|と)\s*", value.replace("`", "")):
        part = part.strip()
        if not part:
            continue
        if not PATH_LINE_RE.match(part) and not part[0].isdigit():
            part = LINE_NOTE_RE.sub(lambda m: ":" + m.group(1), part, count=1)
        m = PATH_LINE_RE.match(part)
        if m:
            current = normalize_path(m.group("path"))
            files.setdefault(current, set()).update(_span(m.group("a"), m.group("b")))
            continue
        m = BARE_LINE_RE.match(part)
        if m and current is not None:
            files[current].update(_span(m.group("a"), m.group("b")))
            continue
        # 行の無いパスに付いた括弧書き（`path（catch 節）`）はパスに含めない
        current = normalize_path(re.split(r"[\s（(]", part, maxsplit=1)[0])
        files.setdefault(current, set())
    return files


def normalize_path(path: str) -> str:
    return path.strip().removeprefix("./")


def path_matches(path: str, target: str) -> bool:
    path, target = normalize_path(path), normalize_path(target)
    return path == target or path.endswith("/" + target) or target.endswith("/" + path)


def parse_report(text: str, path: str = "<report>") -> Report:
    findings: list[Finding] = []
    current: Finding | None = None
    skeptic: str | None = None
    declared: dict[str, int] | None = None
    in_report = False
    for line in text.splitlines():
        if REPORT_MARK in line:
            in_report = True
        if not in_report:
            continue
        if skeptic is None:
            m = SKEPTIC_RE.search(line)
            if m:
                skeptic = m.group("v").strip()
        if declared is None:
            m = COUNTS_RE.search(line)
            if m:
                declared = {
                    s: int(n) for s, n in re.findall(r"(BLOCKER|CRITICAL|MAJOR|MINOR)\s*(\d+)\s*件", m.group("v"))
                }
        if HEADING_RE.match(line):
            current = None
            continue  # mutation-ok: 見出し行は FINDING_RE に当たらず current が None なので、下の `if current is None` で読み飛ばされる
        m = FINDING_RE.match(line)
        if m:
            tags = [t.strip() for t in TAG_RE.findall(m.group(2))]
            severity = next(
                (t.split(":", 1)[1].strip().upper() for t in tags if t.lower().startswith("severity:")),
                None,
            )
            if severity in SEVERITY_RANK:
                current = Finding(int(m.group(1)), severity, m.group(3).strip())
                findings.append(current)
            else:
                current = None
            continue
        if current is None:
            continue
        m = FILE_RE.match(line)
        if m:
            for p, ls in parse_file_field(m.group(1)).items():
                current.files.setdefault(p, set()).update(ls)
            continue
        if line.strip():
            current.body.append(line.strip())
    return Report(path, in_report, findings, skeptic, declared)


def _matches_any(text: str, patterns: list[str]) -> list[str]:
    return [p for p in patterns if re.search(p, text)]


@dataclass
class RunResult:
    hits: list[Finding] = field(default_factory=list)
    contrast_fails: list[tuple[Finding, str]] = field(default_factory=list)
    review: list[tuple[Finding, list[str]]] = field(default_factory=list)
    fp: list[tuple[Finding, list[str]]] = field(default_factory=list)


def expected_hit(f: Finding, expect: dict) -> bool:
    if f.rank < SEVERITY_RANK[expect["severity_at_least"]]:
        return False
    targets = expect.get("target_files_any") or []
    if not any(path_matches(p, t) for p in f.files for t in targets):
        return False
    low = f.text.lower()
    if not any(k.lower() in low for k in expect.get("must_mention_any") or []):
        return False
    want = set(expect.get("target_lines_any") or [])
    return not want or bool(f.lines_in(targets) & want)


def judge_contrast(f: Finding, expect: dict, run: RunResult) -> None:
    nf = expect["must_not_flag"]
    if f.rank <= SEVERITY_RANK[nf.get("max_severity_reported", "MINOR")]:
        return
    targets = nf.get("target_files_any") or []
    lines = f.lines_in(targets)
    # 対照のファイルを行番号なしで挙げた指摘は、別ファイルに行があっても「行番号の無い指摘」として扱う
    no_line = not lines and (not f.has_line or any(path_matches(p, t) for p in f.files for t in targets))
    exp_lines = set(expect.get("target_lines_any") or [])
    cleanup = set(expect.get("cleanup_lines") or [])
    patterns = nf.get("false_positive_patterns") or []
    if lines & set(nf.get("target_lines_any") or []) and not lines & exp_lines:
        run.contrast_fails.append((f, "対照の行を指す"))
    elif lines & (exp_lines | cleanup) or no_line:
        # 対照の経路まで要修正と述べているかは本文の読みが要る（README の判定ルール）。パターンは手がかりとして添えるだけ。
        # 絞り込みは期待の行だけを指す指摘に限る（期待指摘そのものを毎回候補にしないため）。後片付けの行・行番号なしは
        # 「closeDialog を無条件に finally へ移す」のように対照に触れずに対照を壊す形があるので、絞らずに全部候補にする
        mentions = nf.get("mentions_any")
        only_expected = bool(lines) and lines <= exp_lines
        low = f.text.lower()
        if not only_expected or mentions is None or any(m.lower() in low for m in mentions):
            run.review.append((f, _matches_any(f.text, patterns)))
    else:
        hit = _matches_any(f.text, patterns)
        if hit:
            run.contrast_fails.append((f, "false_positive_patterns に合致: " + " / ".join(hit)))


def judge_run(report: Report, fx: dict) -> RunResult:
    run = RunResult()
    expect = fx["expect"]
    for f in report.findings:
        if fx["kind"] == "precision":
            if f.rank > SEVERITY_RANK[expect.get("max_severity_reported", "MINOR")]:
                hit = _matches_any(f.text, expect.get("false_positive_patterns") or [])
                if hit:
                    run.fp.append((f, hit))
            continue
        if expected_hit(f, expect):
            run.hits.append(f)
        if "must_not_flag" in expect:
            judge_contrast(f, expect, run)
    return run


@dataclass
class Verdict:
    status: str  # PASS / FAIL / 要確認 / 判定不能
    reasons: list[str]
    runs: list[RunResult]

    @property
    def exit_code(self) -> int:
        return {"PASS": 0, "FAIL": 1, "判定不能": 2, "要確認": 3}[self.status]


def judge(fx: dict, reports: list[Report]) -> Verdict:
    runs = [judge_run(r, fx) for r in reports]
    unusable = [r.path for r in reports if not r.is_self_review]
    if unusable:
        return Verdict("判定不能", [f"self-review のレポートでない（「{REPORT_MARK}」が無い）: {', '.join(unusable)}"], runs)
    broken = [f"{r.path}: {why}" for r in reports if (why := r.count_mismatch())]
    if broken:
        return Verdict("判定不能", broken, runs)
    if len(reports) != K:
        return Verdict("判定不能", [f"k={K} 本のレポートが要る（{len(reports)} 本）"], runs)
    reasons: list[str] = []
    if fx["kind"] == "precision":
        n = sum(1 for r in runs if r.fp)
        if n:
            return Verdict("FAIL", [f"誤検出 {n}/{K}"], runs)
        return Verdict("PASS", [f"0/{K} FP"], runs)
    hits = sum(1 for r in runs if r.hits)
    contrast = sum(1 for r in runs if r.contrast_fails)
    if hits < RECALL_MIN_HITS:
        reasons.append(f"期待指摘 {hits}/{K}（{RECALL_MIN_HITS} 回以上が要る）")
    if contrast:
        reasons.append(f"対照 {contrast}/{K}")
    if reasons:
        return Verdict("FAIL", reasons, runs)
    summary = f"{hits}/{K}" + (f", 対照 0/{K}" if "must_not_flag" in fx["expect"] else "")
    if any(r.review for r in runs):
        return Verdict("要確認", [summary, "本文の読みが要る指摘が残る"], runs)
    return Verdict("PASS", [summary], runs)


def render(fx: dict, reports: list[Report], v: Verdict) -> str:
    short = fx["id"].split("-", 1)[0]
    has_contrast = "must_not_flag" in fx["expect"]
    lines = [
        "| fixture | run | 期待指摘の報告 | severity | skeptic 起動 | 対照 | 判定 | 備考 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, (rep, run) in enumerate(zip(reports, v.runs), 1):
        if fx["kind"] == "precision":
            found = "❌ FP " + ", ".join(f"#{f.number}" for f, _ in run.fp) if run.fp else "✅（FP なし）"
            sev = max((f.severity for f, _ in run.fp), key=SEVERITY_RANK.get, default="-")
        else:
            found = "✅ " + ", ".join(f"#{f.number}" for f in run.hits) if run.hits else "❌"
            sev = max((f.severity for f in run.hits), key=SEVERITY_RANK.get, default="-")
        if fx.get("skeptic_should_fire"):
            skeptic = rep.skeptic or "（行なし）"
            skeptic = ("✅ " if skeptic.startswith("実行") else "❌ ") + skeptic
        else:
            skeptic = "-"
        if not has_contrast:
            contrast = "-"
        elif run.contrast_fails:
            contrast = "❌ " + ", ".join(f"#{f.number}" for f, _ in run.contrast_fails)
        elif run.review:
            contrast = "要確認 " + ", ".join(f"#{f.number}" for f, _ in run.review)
        else:
            contrast = "✅（指摘なし）"
        lines.append(f"| {short} | {i}/{len(reports)} | {found} | {sev} | {skeptic} | {contrast} | - | |")
    lines += ["", f"総合: {short} {v.status} ({', '.join(v.reasons)})"]
    details: list[str] = []
    for i, run in enumerate(v.runs, 1):
        for f, why in run.contrast_fails:
            details.append(f"- run {i} 対照 FAIL（{why}）: {f.label()}")
        for f, why in run.fp:
            details.append(f"- run {i} 誤検出（{' / '.join(why)}）: {f.label()}")
        for f, pats in run.review:
            hint = f"（パターン: {' / '.join(pats)}）" if pats else ""
            details.append(f"- run {i} 要確認{hint}: {f.label()}")
    if details:
        lines += [
            "",
            "要確認は、本文が対照の経路まで欠陥・要修正と述べていれば FAIL、比べるだけなら数えない（README の判定ルール）:",
            *details,
        ]
    return "\n".join(lines)


class UndecidableInput(LookupError):
    """判定の前提が欠けている（依存・expected.yaml の形）。main が exit 2 にする."""


def load_fixture(fixture: str, expected: Path = EXPECTED) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise UndecidableInput(f"PyYAML が要る（pip install pyyaml）: {e}") from e
    try:
        data = yaml.safe_load(expected.read_text(encoding="utf-8"))
        fixtures = data["fixtures"]
        if not all(isinstance(fx, dict) and isinstance(fx.get("id"), str) for fx in fixtures):
            raise TypeError("fixtures の各項目は文字列の id を持つ mapping であること")
    except (yaml.YAMLError, TypeError, KeyError) as e:
        raise UndecidableInput(f"{expected} を読めない: {e}") from e
    matched = [fx for fx in fixtures if fx["id"] == fixture or fx["id"].startswith(fixture + "-")]
    if len(matched) != 1:
        ids = ", ".join(fx["id"] for fx in fixtures)
        raise LookupError(f"fixture {fixture!r} が 1 つに決まらない（{ids}）")
    return matched[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("fixture")
    ap.add_argument("reports", nargs="+", type=Path)
    ap.add_argument("--expected", type=Path, default=EXPECTED)
    args = ap.parse_args(argv)
    try:
        fx = load_fixture(args.fixture, args.expected)
        reports = [parse_report(p.read_text(encoding="utf-8"), str(p)) for p in args.reports]
    except (LookupError, OSError, ValueError) as e:  # ValueError は UnicodeDecodeError を含む
        print(f"judge.py: {e}", file=sys.stderr)
        return 2
    try:
        v = judge(fx, reports)
    except (KeyError, TypeError, AttributeError, re.error) as e:
        # expected.yaml の fixture に判定が読むキーが無い・値の型が違う・パターンが正規表現として壊れている
        print(f"judge.py: expected.yaml の {fx.get('id')} を判定に使えない: {e!r}", file=sys.stderr)
        return 2
    print(render(fx, reports, v))
    return v.exit_code


if __name__ == "__main__":
    sys.exit(main())
