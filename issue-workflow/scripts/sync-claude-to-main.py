#!/usr/bin/env python3
"""worktree の .claude/ にある git 未追跡のファイルを、メインのチェックアウトの .claude/ へ写す。

issue-maintain が Issue を completed / canceled にしたとき、worktree の中で動いていれば呼ぶ。
.claude/ を gitignore している repo では、worktree で書いた knowledge・follow-up・ADR・journal などが
ブランチに乗らず、worktree を消すとそのまま失われる。追跡済みのファイルはブランチのマージで届くので扱わない。

  sync-claude-to-main.py [--dry-run]

出力（1 件 1 行。--dry-run でも同じ行を出し、何も書かない）:
  in_worktree=0|1           0 ならメインのチェックアウト（何もしない）
  main_root=<絶対パス>
  copied=<相対パス>          メインに無かったので写した
  appended=<相対パス> <行数>  .jsonl はメインに無い行だけを末尾に足した（追記型のログを上書きしない）
  overwritten=<相対パス>     内容が違い、worktree の方が新しい（mtime）ので上書きした。前の版は backup= に残す
  kept_main=<相対パス>       内容が違い、メインの方が新しいので触っていない
  tracked_in_main=<相対パス> worktree では未追跡だがメインでは追跡している。マージに任せて触らない
  skipped=<相対パス>         写さない種類（session-context.md・settings.local.json・worktrees/ 配下・symlink）
  uncommitted=<相対パス>     追跡済みで未コミットの変更がある。写さないので、worktree を消す前にコミットする
  backup=<絶対パス>          overwritten の前の版を置いた dir（overwritten が 1 件以上のときだけ）
  unchanged=<件数>           同じ内容で何もしなかった件数

exit 0 成功（worktree の外も 0）/ 2 git リポジトリの外・git の失敗
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

# session-context.md はチェックアウトごとの作業状態（start が worktree 側に書く）で、メインの値を上書きすると
# メインのセッションの文脈が別の作業に化ける。settings.local.json はチェックアウトごとの権限設定
SKIP_NAMES = {".claude/session-context.md", ".claude/settings.local.json"}
SKIP_PREFIXES = (".claude/worktrees/",)


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"ERROR: git {' '.join(args)}: {res.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return res.stdout


def append_missing_lines(src: Path, dst: Path, dry_run: bool) -> int:
    have = set(dst.read_bytes().splitlines())
    new = [ln for ln in src.read_bytes().splitlines() if ln.strip() and ln not in have]
    if new and not dry_run:
        body = dst.read_bytes()
        with dst.open("ab") as f:
            if body and not body.endswith(b"\n"):
                f.write(b"\n")
            f.write(b"\n".join(new) + b"\n")
    return len(new)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if probe.returncode != 0:
        print("ERROR: git リポジトリの中で実行する", file=sys.stderr)
        return 2
    wt_root = Path(probe.stdout.strip())
    git_dir = Path(git(wt_root, "rev-parse", "--absolute-git-dir").strip())
    common = Path(git(wt_root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    if git_dir == common:
        print("in_worktree=0")
        return 0
    main_root = common.parent
    print("in_worktree=1")
    print(f"main_root={main_root}")

    # 引数なしの --others は ignored も含めて未追跡を全部出す（--exclude-standard を付けると ignored が落ちる）
    untracked = [p for p in git(wt_root, "ls-files", "--others", "-z", "--", ".claude").split("\0") if p]
    tracked_main = set(p for p in git(main_root, "ls-files", "-z", "--", ".claude").split("\0") if p)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = common / "issue-workflow" / "wt-sync-backup" / stamp
    overwrote = False
    unchanged = 0
    for rel in sorted(untracked):
        src = wt_root / rel
        dst = main_root / rel
        if rel in SKIP_NAMES or rel.startswith(SKIP_PREFIXES) or src.is_symlink() or not src.is_file():
            print(f"skipped={rel}")
            continue
        if rel in tracked_main:
            print(f"tracked_in_main={rel}")
            continue
        if not dst.exists():
            if not args.dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            print(f"copied={rel}")
            continue
        if not dst.is_file():
            print(f"kept_main={rel}")
            continue
        if src.read_bytes() == dst.read_bytes():
            unchanged += 1
            continue
        if rel.endswith(".jsonl"):
            n = append_missing_lines(src, dst, args.dry_run)
            if n:
                print(f"appended={rel} {n}")
            else:
                unchanged += 1
            continue
        if src.stat().st_mtime > dst.stat().st_mtime:
            if not args.dry_run:
                saved = backup_dir / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, saved)
                shutil.copy2(src, dst)
            overwrote = True
            print(f"overwritten={rel}")
        else:
            print(f"kept_main={rel}")

    entries = iter(git(wt_root, "status", "--porcelain", "-z", "--", ".claude").split("\0"))
    for entry in entries:
        if not entry:
            continue
        xy, path = entry[:2], entry[3:]
        if "R" in xy or "C" in xy:
            next(entries, None)  # -z の rename / copy は元のパスが次の要素に来る
        if xy != "??" and not path.startswith(SKIP_PREFIXES):
            print(f"uncommitted={path}")

    if overwrote:
        print(f"backup={backup_dir}")
    print(f"unchanged={unchanged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
