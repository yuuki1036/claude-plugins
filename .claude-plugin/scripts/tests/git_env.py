#!/usr/bin/env python3
"""git が hook 実行時に子プロセスへ渡す環境変数のスクラブ（本スイート共通の正本）.

**本スイートは pre-commit / CI / Stop hook / self-review 前段から強制される**。
そのうち pre-commit 経路では git 自身が hook に環境変数を渡すので、テストが
`cwd=<使い捨て dir>` を指定しても **`GIT_DIR` 等が cwd 探索より優先される**。
落とさないと、使い捨てリポジトリのつもりで叩いた git が**外側のリポジトリ**に当たる。

実測した壊れ方は 2 通りで、**worktree かどうかで非対称**なのが厄介な点:

- **メインリポジトリで commit したとき**: `GIT_DIR=.git` / `GIT_INDEX_FILE=.git/index` の
  **相対パス**。使い捨て dir から見ると `<tmp>/.git` に解決されるので実害は出ないが、
  index だけは外側を掴もうとして落ちる（実測: pre-commit から本スイートを走らせると
  `fatal: .git/index: index file open failed: Not a directory` で 21 件失敗した）
- **linked worktree で commit したとき**: `GIT_DIR=/path/to/repo/.git/worktrees/<name>` の
  **絶対パス**。どの cwd から叩いても実リポジトリに当たる（実測 / GitHub issue #158:
  作業ブランチの ref がテスト由来の `init` コミット列に乗っ取られ、メインリポジトリの
  `core.bare` が `true` に書き換わって `git status` すら通らなくなった）

**この規約の定義を複製しない**（同じ規約の複製は必ずずれる）。実際、複製された 4 箇所の
うち `_env()` 系にだけ対策が入り、**`setUp` の `git init` には入っていなかった**のが
issue #158 の直接原因。新しくテストが git を叩くなら `scrub()` を通すこと。
`test_git_env_isolation.py` が「実リポジトリを掴んでいないこと」を実行して確かめる。
"""

from __future__ import annotations

import os

#: git が hook から子プロセスへ引き継ぐ変数（すべて落とす）
GIT_HOOK_ENV = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                "GIT_PREFIX", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_QUARANTINE_PATH", "GIT_REFLOG_ACTION", "GIT_EDITOR")


def scrub(base: dict[str, str] | None = None, **extra: str) -> dict[str, str]:
    """`base`（既定は `os.environ`）から git hook 由来の変数を落とした env を返す."""
    env = {k: v for k, v in (os.environ if base is None else base).items()
           if k not in GIT_HOOK_ENV}
    env.update(extra)
    return env
