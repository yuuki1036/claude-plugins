#!/usr/bin/env python3
"""salt の作成（`code-review/scripts/lib/machine_label.py` の `load_salt`）の単体テスト.

publish / retro の CLI 側の統合は `test_code_review_scripts.py` の `ProvenanceInjectionTest` /
`RetroProvenanceTest` が持つ。ここでは CLI からは起こせない失敗（書き込み途中の失敗・並行作成）を見る。
設定 dir は `CLAUDE_REVIEW_CONFIG_DIR` で使い捨ての dir へ向ける（実機の `~/.config/claude-review` に触れない）。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import errno
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "code-review" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import machine_label  # noqa: E402

SALT_SHAPE = re.compile(r"[0-9a-f]{64}")


class _FailingFile:
    """`os.fdopen` の代わり。書き込みが失敗する（ディスクフル相当）。fd は閉じる."""

    def __init__(self, fd: int, *args, **kwargs) -> None:
        self.fd = fd

    def __enter__(self) -> "_FailingFile":
        return self

    def __exit__(self, *exc) -> None:
        os.close(self.fd)

    def write(self, _data) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")


class LoadSaltTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = Path(tmp.name).resolve() / "cfg"
        env = mock.patch.dict(os.environ, {"CLAUDE_REVIEW_CONFIG_DIR": str(self.cfg)})
        env.start()
        self.addCleanup(env.stop)
        self.salt = self.cfg / "salt"

    def load(self) -> tuple[str | None, str]:
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            value = machine_label.load_salt()
        return value, err.getvalue()

    def leftovers(self) -> list[str]:
        """salt と lock 以外に残ったファイル（一時ファイルの消し忘れ）."""
        return sorted(p.name for p in self.cfg.iterdir() if p.name not in ("salt", "salt.lock"))

    def test_a_missing_salt_is_created_whole(self):
        value, err = self.load()
        self.assertRegex(value, SALT_SHAPE)
        self.assertEqual(self.salt.read_text(encoding="ascii"), value + "\n")
        self.assertEqual(self.salt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(err, "")
        self.assertEqual(self.load()[0], value, "2 回目に別の salt を作った")

    def test_a_failed_write_leaves_no_empty_salt(self):
        """**書き込みの途中で失敗しても空の salt を残さない**（以前は `O_EXCL` で作ってから書いていた）."""
        with mock.patch.object(os, "fdopen", _FailingFile):
            value, _ = self.load()
        self.assertIsNone(value)
        self.assertFalse(self.salt.exists(), "書き込みに失敗した salt が残っている")
        self.assertEqual(self.leftovers(), [], "一時ファイルが残っている")
        value, _ = self.load()
        self.assertRegex(value, SALT_SHAPE, "失敗の後に作り直せない")

    def test_an_empty_or_malformed_salt_is_recreated_with_a_warning(self):
        """空・形の違う salt は WARN を出して作り直す。**元の値は WARN に出さない**."""
        for bad in (b"", b"\n", b"AcmeCorpSecret\n", b"AB" * 32 + b"\n", b"\xff\xfe" * 40):
            with self.subTest(bad=bad[:16]):
                self.cfg.mkdir(exist_ok=True)
                self.salt.write_bytes(bad)
                value, err = self.load()
                self.assertRegex(value, SALT_SHAPE)
                self.assertEqual(self.salt.read_text(encoding="ascii").strip(), value)
                self.assertIn("WARN", err)
                self.assertIn(str(self.salt), err)
                self.assertNotIn("AcmeCorp", err)
                self.assertEqual(self.salt.stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.leftovers(), [])
                self.assertEqual(self.load(), (value, ""), "作り直した salt をもう一度作り直した")

    def test_the_warning_shows_the_salt_under_home_with_a_tilde(self):
        """WARN は貼られることがあるので、`$HOME` 配下の salt は `~` で出す（ユーザー名入りの絶対パスを残さない）."""
        self.cfg.mkdir()
        self.salt.write_text("", encoding="ascii")
        with mock.patch.dict(os.environ, {"HOME": str(self.cfg.parent)}):
            value, err = self.load()
        self.assertRegex(value, SALT_SHAPE)
        self.assertIn("WARN: ~/cfg/salt が空か", err)
        self.assertNotIn(str(self.cfg.parent), err)

    def test_a_valid_salt_is_used_as_is(self):
        self.cfg.mkdir()
        self.salt.write_text("5a" * 32 + "\n", encoding="ascii")
        self.assertEqual(self.load(), ("5a" * 32, ""))

    def test_an_unreadable_salt_is_not_replaced(self):
        """読めない（dir になっている等）salt は作り直さない。利用者の置いたものを壊さない."""
        self.salt.mkdir(parents=True)
        self.assertEqual(self.load(), (None, ""))
        self.assertTrue(self.salt.is_dir())

    def test_concurrent_creators_agree_on_one_salt(self):
        """並行に初回の label を求めた publish / retro が、全員同じ salt（同じ label）を使う."""
        env = dict(os.environ, CLAUDE_REVIEW_CONFIG_DIR=str(self.cfg), PYTHONDONTWRITEBYTECODE="1")
        code = ("import sys; sys.path.insert(0, %r); import machine_label; "
                "print(machine_label.load_salt())" % str(LIB))
        procs = [subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) for _ in range(12)]
        outs = [p.communicate(timeout=60) for p in procs]
        values = {out.strip() for out, _ in outs}
        self.assertEqual(len(values), 1, "並行作成で salt が割れた")
        self.assertRegex(values.pop(), SALT_SHAPE)
        self.assertEqual([err for _, err in outs if err], [])
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
