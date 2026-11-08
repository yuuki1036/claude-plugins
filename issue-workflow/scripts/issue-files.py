#!/usr/bin/env python3
"""maintain 系が Issue ファイルを消す・書き換える前に、git から戻せるかを確かめる（GitHub issue #422）。

issue-maintain / maintain / linear-maintain は「起動＝実行確定」で、承認を取らずに完了 Issue を
削除・圧縮する。その前提は「操作対象が git 管理下で復元できる」ことだが、DATA_DIR を
gitignore や .git/info/exclude で外している repo では、消したファイルを git から戻せない。
3 スキルが同じ判定を使うよう、判定と削除・控えをここに置く。

  issue-files.py check PATH...
      PATH ごとに状態を 1 行出す:
        tracked=<PATH>    git の追跡下で、作業ツリーと index が HEAD と一致している（今の内容を git から戻せる）
        dirty=<PATH>      git の追跡下だが、HEAD と一致しない（未コミットの変更がある・add しただけでコミットしていない）
        untracked=<PATH>  git の追跡外（ignore されている・add していない・git 管理外の dir）
  issue-files.py backup [--archive-dir DIR] PATH...
      最初の書き換えの前に呼ぶ。tracked の PATH は何もせず `tracked=<PATH>` を出す。
      dirty / untracked の PATH は DIR へ複製し、`backed_up=<PATH>` と `backed_up_to=<複製した先>` を続けて出す
  issue-files.py retire [--archive-dir DIR] PATH...
      HEAD に版がある PATH（tracked と、HEAD にある dirty）は削除して `deleted=<PATH>` を出す。
      それ以外（untracked と、add しただけで HEAD に無い dirty）は削除せず DIR へ移し、
      `archived=<PATH>` と `archived_to=<移した先>` を続けて出す

backup が dirty を控えるのは、書き換えるとコミットしていない内容がどこにも残らないため。
retire が HEAD にある dirty を削除するのは、maintain 系が backup の後の同じ実行で書き換えた
ファイル（status の遷移・圧縮・更新履歴）だから。この実行より前の内容は HEAD（backup の時点で
tracked だった）か backup の控え（dirty だった）に残り、失うのはこの実行で入れた書き換えだけ
（2026-11-08 決定。追跡下の repo で完了 Issue が毎回 archive/ に溜まらないように）。
DIR を省くと PATH の親の親の `archive/`（`{DATA_DIR}/{slug}/issues/X.md` なら `{DATA_DIR}/{slug}/archive/`）。
判定は PATH の親 dir で git を叩いて行う（cwd ではない）。worktree のセッションがメインのチェックアウトの
DATA_DIR を絶対パスで渡す回に、worktree 側の index を見ないため。ファイル名は literal の pathspec として渡す
（`[` `*` を含む名前が別の追跡済みファイルに一致して tracked と判定されないように）。
DIR に同じ名前があれば名前に日時を付け、先に置いたものを上書きしない。
PATH が無い・ファイルでないときは `missing=<PATH>` を出して何もせず、残りの PATH は処理したうえで exit 2。
exit 0 成功 / 2 入力不正・PATH が無い。
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path


def _git(path: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git", "--literal-pathspecs", *args],
            cwd=path.parent, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def in_head(path: Path) -> bool:
    res = _git(path, "cat-file", "-e", f"HEAD:./{path.name}")
    return res is not None and res.returncode == 0


def state(path: Path) -> str:
    res = _git(path, "ls-files", "--error-unmatch", "--", path.name)
    if res is None or res.returncode != 0:
        return "untracked"
    # 追跡下でも HEAD と一致しなければ、今の内容は git から戻せない。
    # status が空なら作業ツリー・index・HEAD が一致している（add しただけの新規は `A ` が出る）
    res = _git(path, "status", "--porcelain", "--", path.name)
    if res is None or res.returncode != 0 or res.stdout.strip():
        return "dirty"
    return "tracked"


def archive_dest(archive_dir: Path, path: Path) -> Path:
    dest = archive_dir / path.name
    if not dest.exists():
        return dest
    # 同じ ID を 2 回退避した回（書き換え前の控えの後に retire した・canceled を再開して再び閉じた等）に先のものを上書きしない
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = archive_dir / f"{path.stem}.{stamp}{path.suffix}"
    n = 1
    while dest.exists():
        dest = archive_dir / f"{path.stem}.{stamp}-{n}{path.suffix}"
        n += 1
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("paths", nargs="+")
    for name in ("backup", "retire"):
        p = sub.add_parser(name)
        p.add_argument("--archive-dir")
        p.add_argument("paths", nargs="+")
    args = ap.parse_args()

    missing = False
    for raw in args.paths:
        path = Path(raw).resolve()
        if not path.is_file():
            print(f"missing={raw}")
            missing = True
            continue
        st = state(path)
        if args.cmd == "check":
            print(f"{st}={raw}")
            continue
        if args.cmd == "backup" and st == "tracked":
            print(f"tracked={raw}")
            continue
        if args.cmd == "retire" and (st == "tracked" or (st == "dirty" and in_head(path))):
            path.unlink()
            print(f"deleted={raw}")
            continue
        archive_dir = Path(args.archive_dir) if args.archive_dir else path.parent.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dest(archive_dir, path)
        if args.cmd == "retire":
            shutil.move(str(path), str(dest))
            print(f"archived={raw}")
            print(f"archived_to={dest}")
        else:
            shutil.copy2(str(path), str(dest))
            print(f"backed_up={raw}")
            print(f"backed_up_to={dest}")
    return 2 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
