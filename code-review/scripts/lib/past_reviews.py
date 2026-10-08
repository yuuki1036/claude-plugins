#!/usr/bin/env python3
"""同じファイルを触った過去の merged PR のレビューコメントを集める（GitHub issue #286）.

PR 会話の取得（`fetch-pr-context.sh`）と re-flag の判定は**対象 PR の中だけ**を見るので、
別の PR で指摘されて直した事柄をこの diff がまた壊しても、拾う経路が無かった。

手順: core の変更ファイル（変更行の多い順）ごとに、base の履歴でそのファイルを触った直近の
コミットを引き、そのコミットを含む merged PR を GitHub API で引く。その PR の行単位レビュー
コメントのうち、同じファイルに付いたもの（返信を除く）を集める。

API 呼び出しの数は「ファイル数 × ファイルあたりのコミット数 + PR 数」で頭打ちになる
（既定 8 × 5 + 最大 24）。同じコミット・同じ PR は 1 回しか引かない。

終了コード: 0 = 取得した（コメントが 0 件なら stdout は空）/ 3 = 取得できないので飛ばした
（GitHub のリモートが無い・gh の認証が無い等。理由は stderr）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

SKIPPED = 3


def run(cmd: list[str]) -> str | None:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout if res.returncode == 0 else None


def loads_many(text: str) -> list:
    """`gh api --paginate` はページごとの配列を連結して出す（`[...][...]`）。全部をつないで返す."""
    out, dec, i = [], json.JSONDecoder(), 0
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return out
        value, i = dec.raw_decode(text, i)
        if isinstance(value, list):
            out.extend(value)


def resolve_base(base: str) -> str:
    """review は base のブランチ名を渡す。ローカルの base は古いことがあるので origin 側を優先する."""
    if run(["git", "rev-parse", "--verify", "-q", "origin/%s^{commit}" % base]):
        return "origin/" + base
    return base


def one_line(body: str, limit: int) -> str:
    s = " ".join(body.split())
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


def collect(files: list[str], repo: str, base: str, exclude_pr: int | None, commits_per_file: int,
            prs_per_file: int) -> list[tuple[str, list[int], list[tuple[int, dict]]]]:
    commit_prs: dict[str, list[int]] = {}
    pr_comments: dict[int, list] = {}
    sections = []
    for f in files:
        shas = (run(["git", "log", "--format=%H", "-n", str(commits_per_file), base, "--", f]) or "").split()
        prs: list[int] = []
        for sha in shas:
            if len(prs) >= prs_per_file:
                break  # mutation-ok: continue でも残りの周はこの判定で抜けるだけで API を引かない
            if sha not in commit_prs:
                raw = run(["gh", "api", "repos/%s/commits/%s/pulls" % (repo, sha)])
                try:
                    pulls = loads_many(raw) if raw else []
                except ValueError:
                    pulls = []
                commit_prs[sha] = [p["number"] for p in pulls
                                   if isinstance(p, dict) and p.get("merged_at") and "number" in p]
            for n in commit_prs[sha]:
                if n != exclude_pr and n not in prs:
                    prs.append(n)
        prs = prs[:prs_per_file]
        found = []
        for n in prs:
            if n not in pr_comments:
                raw = run(["gh", "api", "--paginate", "repos/%s/pulls/%d/comments" % (repo, n)])
                try:
                    pr_comments[n] = loads_many(raw) if raw else []
                except ValueError:
                    pr_comments[n] = []
            for c in pr_comments[n]:
                if isinstance(c, dict) and c.get("path") == f and not c.get("in_reply_to_id"):
                    found.append((n, c))
        sections.append((f, prs, found))
    return sections


def render(sections, max_comments: int, body_chars: int, n_files: int, prs_per_file: int) -> str:
    total = sum(len(found) for _, _, found in sections)
    if total == 0:
        return ""
    lines = ["## 過去 PR のレビューコメント（同じファイル / GitHub issue #286）", "",
             "対象: core の変更ファイルのうち変更行の多い順に %d 件。各ファイルを触った直近の merged PR を"
             "最大 %d 件。コメントは計 %d 件まで、本文は %d 字で切る。返信は含めない"
             % (n_files, prs_per_file, max_comments, body_chars)]
    left = max_comments
    for f, prs, found in sections:
        if not found:
            continue
        lines += ["", "### `%s`（%s）" % (f, ", ".join("PR #%d" % n for n in prs))]
        for n, c in found[:left]:
            user = (c.get("user") or {}).get("login") or "unknown"
            line = c.get("line") or c.get("original_line") or "?"
            lines.append("- [PR #%d @%s L%s] %s" % (n, user, line, one_line(c.get("body") or "", body_chars)))
        left -= min(len(found), left)
        if left <= 0:
            break
    if total > max_comments:
        lines += ["", "（ほか %d 件は上限で省いた）" % (total - max_comments)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--core-list", required=True, help="core の変更ファイル（1 行 1 パス・変更行の多い順）")
    ap.add_argument("--base", required=True, help="履歴を引く起点（ブランチ名かコミット）")
    ap.add_argument("--exclude-pr", type=int, default=None, help="レビュー対象の PR 番号（自分自身を拾わない）")
    ap.add_argument("--max-files", type=int, default=8)
    ap.add_argument("--commits-per-file", type=int, default=5)
    ap.add_argument("--prs-per-file", type=int, default=3)
    ap.add_argument("--max-comments", type=int, default=40)
    ap.add_argument("--body-chars", type=int, default=300)
    args = ap.parse_args(argv)

    try:
        with open(args.core_list, encoding="utf-8") as fh:
            files = [ln.strip() for ln in fh if ln.strip()][: args.max_files]
    except OSError:
        print("skip: core の変更ファイルの一覧を読めない: %s" % args.core_list, file=sys.stderr)
        return SKIPPED
    if not files:
        return 0
    repo = (run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]) or "").strip()
    if not repo:
        print("skip: GitHub のリポジトリを特定できない（GitHub のリモートが無いか、gh の認証が無い）",
              file=sys.stderr)
        return SKIPPED
    sections = collect(files, repo, resolve_base(args.base), args.exclude_pr, args.commits_per_file,
                       args.prs_per_file)
    sys.stdout.write(render(sections, args.max_comments, args.body_chars, len(files), args.prs_per_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
