#!/usr/bin/env python3
"""mutation-nightly の比較起点と、晩をまたいで持ち越す状態（GitHub issue #288）.

予算や上限で打ち切った変異は、起点を前の晩の head に進めると二度と回らない。そこで「全件を回し切った
最後の head（base）」と「その範囲で実行済みの変異のキー（done）」を状態として artifact に残し、翌晩は
base から回して done を飛ばす。起点だけを持ち越すと、変異の並びと `--max` / 予算での切り方が毎晩同じなので、
範囲が 1 晩で回せる数を超えると同じ先頭を回し直すだけで進まない。

  mutation-nightly-state.py resolve-base [--input-base <ref>] --run-id <id> --repo <owner/repo> \\
      --state-dir <dir> --env-file "$GITHUB_ENV"
  mutation-nightly-state.py advance --prev <state.json|""> --summary mutation-summary.json \\
      --base <sha> --head <sha> --out mutation-state.json

resolve-base は起点を次の順に決め、`MUT_BASE=<sha>`（変更が無ければ `SKIP=1`）を `--env-file` に追記する:
  1. `--input-base` が空でなければそれ（手動起動での回収用）。解決できなければ exit 1
  2. 状態（artifact `mutation-state`）を残した最新の schedule run の base。`MUT_SKIP_KEYS`（done を
     1 行 1 キーで書いたファイル）と `STATE_PREV`（その状態）も書く
  3. 状態が無ければ、変異テストの集計（artifact `mutation-summary`）を残した最新の schedule run の
     headSha。**run の conclusion では判定しない**: failure には生存（範囲は回した）と、変異前のテストが
     赤い晩（集計を書かずに exit 2 = 範囲を回していない）が混ざる
  4. 集計を残した run も無ければ、success / failure で終わった最新の schedule run の headSha
  5. どれも無いときは従来の 24h 窓
状態を使えなかった晩は `::warning::` を出す。状態があったのに使えない（壊れている・base が祖先でない）
（期限切れを含む）ときは `STATE_LOST=1` を書いて起票させる。API が失敗した晩は `STATE_HOLD=1` も書き、
新しい状態を上げない — 前の状態が最新のまま残るので、翌晩にそこから再開できる。
**番兵は `1` にする**: ワークフローの `if:` は型が違えば数値に寄せて比べ、未設定の env は null = 0 になる。
`env.X != '0'` と書くと未設定の晩に偽になり、毎晩 step が飛ぶ（docs.github.com の expressions）。
2〜4 では HEAD の祖先でない head を飛ばして古い方へさかのぼる（古い run の re-run は新しい晩の
head を持ち、force push の後は書き換え前の head が残る）。

advance は、この晩の集計（keys_all / keys_executed）で状態を進める:
  done' = (前の done ∩ keys_all) ∪ keys_executed。keys_all がすべて done' に入り、中断していなければ
  base を head に進めて done を空にする。そうでなければ base を据え置き、done' を残す。
  集計が無い晩（赤い baseline・skip）は前の状態をそのまま残す。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ARTIFACT = "mutation-summary"
STATE_ARTIFACT = "mutation-state"
STATE_FILE = "mutation-state.json"
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


def is_ancestor(sha: str) -> bool:
    return git("merge-base", "--is-ancestor", sha, "HEAD").returncode == 0


def gh(*args: str) -> str:
    """gh を叩いて stdout を返す。失敗は RuntimeError（呼び出し側で状態を使わない側へ倒す）."""
    try:
        res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("gh %s: %s" % (args[0], e)) from e
    if res.returncode != 0:
        raise RuntimeError("gh %s が exit %d: %s" % (args[0], res.returncode, res.stderr.strip()[:300]))
    return res.stdout


def gh_json(*args: str):
    try:
        return json.loads(gh(*args))
    except ValueError as e:
        raise RuntimeError("gh %s の出力が JSON でない" % args[0]) from e


def load_state(path: Path) -> dict | None:
    """状態を読む。形が違えば None（壊れた状態から done を読むと未検証の変異を済み扱いにする）."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("base"), str) or not isinstance(d.get("done"), list):
        return None
    if not all(isinstance(k, str) for k in d["done"]):
        return None
    return d


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
        if sha is None or not is_ancestor(sha):
            print("run %s の head %s は HEAD の祖先でないので飛ばす（古い run の re-run・force push）"
                  % (r.get("databaseId"), str(r["headSha"])[:12]))
            continue
        out.append((r, sha))
    return out


def artifact_names(repo: str, run: dict) -> tuple[set[str], set[str]]:
    """(取れる artifact の名前, 期限切れの artifact の名前)。一覧は期限切れも返すが、download は失敗する."""
    arts = gh_json("api", "repos/%s/actions/runs/%s/artifacts?per_page=100" % (repo, run["databaseId"]))
    if not isinstance(arts, dict):
        raise RuntimeError("artifact 一覧の出力がオブジェクトでない")
    live, expired = set(), set()
    for a in arts.get("artifacts") or []:
        if isinstance(a, dict):
            (expired if a.get("expired") is True else live).add(a.get("name"))
    return live, expired


def window_base() -> str | None:
    return git("rev-list", "-1", "--before=24 hours ago", "HEAD").stdout.strip() or None


def resolve(input_base: str, repo: str, run_id: str, state_dir: Path) -> tuple[str | None, str, dict]:
    """(起点, 由来の説明, 追加で env に書く値)。起点が None なら比べる相手が無い."""
    if input_base:
        sha = commit_of(input_base)
        if sha is None:
            raise SystemExit("FATAL: 指定した起点を解決できない: %s" % input_base)
        return sha, "手動指定", {}
    state_seen = False
    summary_pick = None
    try:
        cands = candidates(repo, run_id)
        for r, sha in cands:
            names, expired = artifact_names(repo, r)
            if STATE_ARTIFACT in expired:
                # 期限切れの状態を取りに行くと download が失敗し、API の失敗として毎晩 hold し続ける
                state_seen = True
                print("run %s の状態は期限切れなので飛ばす" % r["databaseId"])
            if STATE_ARTIFACT in names:
                state_seen = True
                dest = state_dir / ("run-%s" % r["databaseId"])
                dest.mkdir(exist_ok=True)
                gh("run", "download", str(r["databaseId"]), "--repo", repo, "-n", STATE_ARTIFACT,
                   "-D", str(dest))
                st = load_state(dest / STATE_FILE)
                base = commit_of(st["base"]) if st else None
                if base is not None and is_ancestor(base):
                    keys = state_dir / "done-keys.txt"
                    keys.write_text("".join(k + "\n" for k in st["done"]), encoding="utf-8")
                    return base, "持ち越しの状態（run %s・済み %d 個）" % (r["databaseId"], len(st["done"])), \
                        {"MUT_SKIP_KEYS": str(keys), "STATE_PREV": str(dest / STATE_FILE)}
                print("run %s の状態を使えないので飛ばす（壊れている・起点が HEAD の祖先でない）"
                      % r["databaseId"])
            # 集計は「その晩の範囲を回した」印なので、期限切れでも数える
            if summary_pick is None and ARTIFACT in names | expired:
                summary_pick = (r, sha)
    except RuntimeError as e:
        print("::warning::前回の nightly を引けないので 24h 窓に戻す（窓の隙間が戻る。持ち越しの状態は"
              "上書きせず、翌晩に再開する）: %s" % e)
        return window_base(), "24h 窓（API の失敗）", {"STATE_LOST": "1", "STATE_HOLD": "1"}
    extra = {}
    if state_seen:
        print("::warning::持ち越しの状態を使えなかった（持ち越していた未実行の変異は回らない）")
        extra["STATE_LOST"] = "1"
    else:
        print("::warning::持ち越しの状態を残した schedule run が直近 %d 件に無い（入れた最初の晩なら想定どおり）"
              % RUN_LIMIT)
    if summary_pick is not None:
        r, sha = summary_pick
        return sha, "集計を残した直近の nightly（run %s）の head" % r["databaseId"], extra
    ran = [(r, sha) for r, sha in cands if r.get("conclusion") in RAN]
    if ran:
        r, sha = ran[0]
        print("::warning::集計の artifact を残した schedule run も無いので、最新の run %s の head を起点にする"
              "（変異前のテストが赤かった晩の範囲は繰り越さない）" % r["databaseId"])
        return sha, "最新の nightly（run %s・集計なし）の head" % r["databaseId"], extra
    print("::warning::起点にできる schedule run が直近 %d 件に無いので 24h 窓に戻す（窓の隙間が戻る）"
          % RUN_LIMIT)
    return window_base(), "24h 窓（起点にできる run なし）", extra


def keys_of(summary: dict | None) -> tuple[set[str], set[str]] | None:
    """集計の (keys_all, keys_executed)。無い・形が違えば None（判定できない晩として扱う）."""
    if not isinstance(summary, dict):
        return None
    got = []
    for k in ("keys_all", "keys_executed"):
        v = summary.get(k)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return None
        got.append(set(v))
    return got[0], got[1]


def advance(prev: dict | None, summary: dict | None, base: str, head: str, now: str) -> dict:
    """この晩の集計で状態を進める（純関数）."""
    same = prev is not None and prev["base"] == base
    keys = keys_of(summary)
    if keys is None:
        # 集計が無い晩は何も回していない。前の状態をそのまま残す（範囲は翌晩に繰り越す）
        return dict(prev) if same else {"schema": 1, "base": base, "done": [], "since": now, "remaining": None}
    keys_all, executed = keys
    done = (set(prev["done"]) & keys_all if same else set()) | executed
    remaining = len(keys_all - done)
    if remaining == 0 and summary.get("aborted") is not True:
        return {"schema": 1, "base": head, "done": [], "since": now, "remaining": 0}
    # since は持ち越しが続いている間だけ引き継ぐ。回し切った後の状態（remaining 0）を skip の晩に上げ直すと
    # since が「最後に回し切った時刻」で止まり、持ち越しが始まった最初の晩に「何日も解消しない」と起票する
    carrying = same and isinstance(prev.get("remaining"), int) and prev["remaining"] > 0
    since = prev.get("since") if carrying and isinstance(prev.get("since"), str) else now
    return {"schema": 1, "base": base, "done": sorted(done), "since": since, "remaining": remaining}


def load_json(path: str) -> dict | None:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("resolve-base", help="比較起点を決めて env ファイルに書く")
    rb.add_argument("--input-base", default="", help="手動起動の入力（空なら自動で決める）")
    rb.add_argument("--run-id", required=True, help="この run の id（候補から外す）")
    rb.add_argument("--repo", required=True, help="owner/repo")
    rb.add_argument("--state-dir", required=True, help="前の状態を置くディレクトリ（$RUNNER_TEMP の下）")
    rb.add_argument("--env-file", required=True, help="KEY=VALUE を追記するファイル（$GITHUB_ENV）")
    ad = sub.add_parser("advance", help="この晩の集計で状態を進める")
    ad.add_argument("--prev", required=True, help="前の状態（無ければ空文字）")
    ad.add_argument("--summary", required=True, help="mutation-test.py --summary-json の出力")
    ad.add_argument("--base", required=True, help="この晩の起点")
    ad.add_argument("--head", required=True, help="この晩の head")
    ad.add_argument("--out", required=True, help="新しい状態を書くパス")
    ad.add_argument("--now", default=None, help="現在時刻（ISO 8601。テスト用）")
    args = ap.parse_args(argv)

    if args.cmd == "advance":
        now = args.now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prev = load_state(Path(args.prev)) if args.prev else None
        st = advance(prev, load_json(args.summary), args.base, args.head, now)
        Path(args.out).write_text(json.dumps(st) + "\n", encoding="utf-8")
        if st["base"] == args.head and st["remaining"] == 0:
            print("範囲を回し切った。起点を %s に進める" % args.head[:12])
        else:
            print("持ち越し: 残り %s 個・済み %d 個（起点 %s・%s から）"
                  % (st["remaining"] if st["remaining"] is not None else "?", len(st["done"]),
                     st["base"][:12], st["since"]))
        return 0

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    head = commit_of("HEAD")
    base, origin, extra = resolve(args.input_base.strip(), args.repo, args.run_id, state_dir)
    if extra.get("STATE_LOST") and (base is None or base == head):
        # skip の晩は report が走らない。ここで新しい状態を上げると、失ったことを誰にも知らせないまま
        # 上書きする。前の状態を残し、変更が入った晩に起票させる
        extra["STATE_HOLD"] = "1"
    with Path(args.env_file).open("a", encoding="utf-8") as f:
        for k, v in extra.items():
            f.write("%s=%s\n" % (k, v))
        if base is None or base == head:
            print("起点から変更が無いので skip（起点: %s）" % origin)
            f.write("SKIP=1\n")
        else:
            print("比較起点: %s（%s）" % (base, origin))
            f.write("MUT_BASE=%s\n" % base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
