#!/usr/bin/env python3
"""mutation-nightly の比較起点を決める（GitHub issue #288）.

起点を「24 時間前より古い最新のコミット」に置くと、前の晩の head と 24h の境界の間に落ちたコミットが
どちらの晩の範囲にも入らない。schedule の起動が cron から数時間揺れて間隔が 24h を超えた晩と、
committer date より後に main へ入ったコミット（PR のマージ）で起きる。実測で 39 晩の間に 4 回あり、
10-07 は PR #281 のマージ分（35 ファイル）が変異テストを一度も通らなかった。
前の晩が実際に回した木（run の headSha）を起点にすれば、どちらの型も塞げる。

  mutation-nightly-state.py resolve-base [--input-base <ref>] --run-id <id> --repo <owner/repo> \\
      --env-file "$GITHUB_ENV"

起点の決め方（上から順に）:
  1. `--input-base` が空でなければそれ（手動起動での回収用）。解決できなければ exit 1
  2. schedule で起動し、変異テストの集計を artifact に残した最新の run の headSha。
     **run の conclusion では判定しない**: failure には生存（範囲は回した）と、変異前のテストが赤い晩
     （集計を書かずに exit 2 = 範囲を回していない）が混ざる。集計を残していない晩（赤い baseline・
     依存のインストール失敗・job の timeout で cancelled）の範囲は翌晩へ繰り越す
  3. 集計を残した run が無ければ、success / failure で終わった最新の schedule run の headSha。
     artifact を上げ始める前の run（導入した最初の晩）がこれに当たる。赤い baseline の晩も
     回したものとして扱うので `::warning::` を出す
  4. 3 も無い・API が失敗したときは従来の 24h 窓に戻し、`::warning::` を出す（窓の隙間が戻る）
2・3 では HEAD の祖先でない head を飛ばして古い方へさかのぼる（古い run の re-run は新しい晩の
head を持ち、force push の後は書き換え前の head が残る）。
起点が無いか HEAD と同じなら `SKIP=1`、それ以外は `MUT_BASE=<sha>` を `--env-file` に追記する。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ARTIFACT = "mutation-summary"
WORKFLOW = "mutation-nightly.yml"
#: さかのぼる run の数。毎晩 1 run なので、30 晩ぶん
RUN_LIMIT = 30
#: 範囲を回した可能性がある conclusion（cancelled / skipped 等は回していない）
RAN = ("success", "failure")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def commit_of(ref: str) -> str | None:
    res = git("rev-parse", "--verify", "-q", ref + "^{commit}")
    return res.stdout.strip() if res.returncode == 0 else None


def gh_json(*args: str):
    """gh を叩いて JSON を返す。失敗・壊れた出力は RuntimeError（呼び出し側で 24h 窓へ戻す）."""
    try:
        res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("gh %s: %s" % (args[0], e)) from e
    if res.returncode != 0:
        raise RuntimeError("gh %s が exit %d: %s" % (args[0], res.returncode, res.stderr.strip()[:300]))
    try:
        return json.loads(res.stdout)
    except ValueError as e:
        raise RuntimeError("gh %s の出力が JSON でない" % args[0]) from e


def candidates(repo: str, run_id: str) -> list[tuple[dict, str]]:
    """終わった schedule run のうち head が HEAD の祖先のものを、新しい順に (run, sha) で返す."""
    runs = gh_json("run", "list", "--repo", repo, "--workflow", WORKFLOW, "--event", "schedule",
                   "--status", "completed", "--limit", str(RUN_LIMIT),
                   "--json", "databaseId,headSha,status,conclusion,createdAt")
    if not isinstance(runs, list):
        raise RuntimeError("gh run list の出力が配列でない")
    out = []
    # **実行中の自分自身を候補にしない**（`--status completed` に加えて手元でも外す。
    # 自分を拾うと起点が HEAD になり、毎晩 SKIP する）
    for r in sorted((r for r in runs if isinstance(r, dict)),
                    key=lambda r: str(r.get("createdAt", "")), reverse=True):
        if r.get("status") != "completed" or str(r.get("databaseId")) == run_id or not r.get("headSha"):
            continue
        sha = commit_of(r["headSha"])
        if sha is None or git("merge-base", "--is-ancestor", sha, "HEAD").returncode != 0:
            print("run %s の head %s は HEAD の祖先でないので飛ばす（古い run の re-run・force push）"
                  % (r.get("databaseId"), str(r["headSha"])[:12]))
            continue
        out.append((r, sha))
    return out


def has_summary(repo: str, run: dict) -> bool:
    arts = gh_json("api", "repos/%s/actions/runs/%s/artifacts?per_page=100" % (repo, run["databaseId"]))
    if not isinstance(arts, dict):
        raise RuntimeError("artifact 一覧の出力がオブジェクトでない")
    return any(isinstance(a, dict) and a.get("name") == ARTIFACT for a in arts.get("artifacts") or [])


def window_base() -> str | None:
    return git("rev-list", "-1", "--before=24 hours ago", "HEAD").stdout.strip() or None


def resolve(input_base: str, repo: str, run_id: str) -> tuple[str | None, str]:
    """(起点, 由来の説明)。起点が None なら比べる相手が無い."""
    if input_base:
        sha = commit_of(input_base)
        if sha is None:
            raise SystemExit("FATAL: 指定した起点を解決できない: %s" % input_base)
        return sha, "手動指定"
    try:
        cands = candidates(repo, run_id)
        for r, sha in cands:
            if has_summary(repo, r):
                return sha, "集計を残した直近の nightly（run %s）の head" % r["databaseId"]
    except RuntimeError as e:
        print("::warning::前回の nightly を引けないので 24h 窓に戻す（窓の隙間が戻る）: %s" % e)
        return window_base(), "24h 窓（API の失敗）"
    ran = [(r, sha) for r, sha in cands if r.get("conclusion") in RAN]
    if ran:
        r, sha = ran[0]
        print("::warning::集計の artifact を残した schedule run が直近 %d 件に無いので、最新の run %s の"
              " head を起点にする（変異前のテストが赤かった晩の範囲は繰り越さない。導入した最初の晩なら"
              "想定どおり、続くなら upload-summary の配線を確かめる）" % (RUN_LIMIT, r["databaseId"]))
        return sha, "最新の nightly（run %s・集計なし）の head" % r["databaseId"]
    print("::warning::起点にできる schedule run が直近 %d 件に無いので 24h 窓に戻す（窓の隙間が戻る）"
          % RUN_LIMIT)
    return window_base(), "24h 窓（起点にできる run なし）"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("resolve-base", help="比較起点を決めて env ファイルに書く")
    rb.add_argument("--input-base", default="", help="手動起動の入力（空なら自動で決める）")
    rb.add_argument("--run-id", required=True, help="この run の id（候補から外す）")
    rb.add_argument("--repo", required=True, help="owner/repo")
    rb.add_argument("--env-file", required=True, help="KEY=VALUE を追記するファイル（$GITHUB_ENV）")
    args = ap.parse_args(argv)

    head = commit_of("HEAD")
    base, origin = resolve(args.input_base.strip(), args.repo, args.run_id)
    with Path(args.env_file).open("a", encoding="utf-8") as f:
        if base is None or base == head:
            print("起点から変更が無いので skip（起点: %s）" % origin)
            f.write("SKIP=1\n")
        else:
            print("比較起点: %s（%s）" % (base, origin))
            f.write("MUT_BASE=%s\n" % base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
