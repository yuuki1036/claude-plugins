#!/usr/bin/env python3
"""dev-workflow の説明図の書き出し（svg-to-png.sh）の CLI 境界テスト.

pr-creator Step 4.6 が PR に添付する図を PNG にする（GitHub issue #287）。測るもの:

- 変換手段の選び方: rsvg-convert → Chrome の順。CHROME_BIN があればそれだけを使う
  （実行できなければ Chrome 無し。PATH や macOS のアプリへ探しに行かない）。
  手段が 1 つも無ければ exit 2 で FATAL を出す（SVG のまま添付するかは呼び出し側が決める）
- **Chrome を残さない**: 撮影後も終わらない Chrome（と、同じプロファイルを指す子プロセス）を、
  PNG ができた時点で止める。書かないまま居座る Chrome は SVG_TO_PNG_TIMEOUT で打ち切る
- 撮影範囲: ルートの width / height、無ければ viewBox の幅・高さを --window-size に渡す
- 1 件ずつ png= / failed= を出し、失敗が混ざれば exit 1（他のファイルの変換は続ける）

開発機には本物の Chrome がある（/Applications）ので、Chrome の経路は必ず CHROME_BIN か
PATH の stub で固定する（環境の不在に頼らない）。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "dev-workflow" / "scripts" / "svg-to-png.sh"

SIZED_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="240"><rect width="640" height="240"/></svg>\n'

# --screenshot / --user-data-dir を拾い、STUB_MODE に応じて振る舞う Chrome の代役。
# write-hang は本物の Chrome が撮影後も終わらない形を再現する: 同じプロファイルを引数に持つ
# 子プロセスを残し、自分は exec で sleep に置き換わって居座る。
CHROME_STUB = r"""
for a in "$@"; do
  case "$a" in
    --screenshot=*) out="${a#--screenshot=}" ;;
    --user-data-dir=*) prof="${a#--user-data-dir=}" ;;
  esac
done
printf '%s\n' "$@" > "$STUB_DIR/chrome-args"
echo $$ > "$STUB_DIR/chrome.pid"
case "${STUB_MODE:-write-exit}" in
  write-exit) printf 'PNGDATA' > "$out" ;;
  write-hang)
    bash -c 'echo $$ > "$1"; while :; do sleep 1; done' _ "$STUB_DIR/child.pid" "$prof" &
    printf 'PNGDATA' > "$out"
    exec sleep 60 ;;
  exit-nowrite) exit 0 ;;
  hang-nowrite) exec sleep 60 ;;
esac
"""

RSVG_STUB = r"""
printf '%s\n' "$@" > "$STUB_DIR/rsvg-args"
[ "${RSVG_MODE:-ok}" = fail ] && exit 1
while [ $# -gt 0 ]; do
  if [ "$1" = -o ]; then printf 'RSVGDATA' > "$2"; fi
  shift
done
exit 0
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class SvgToPngTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.stub_dir = self.root / "stub"
        self.stub_dir.mkdir()
        self.work = self.root / "work"
        self.work.mkdir()

    def _stub(self, name: str, body: str) -> Path:
        p = self.bin / name
        p.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
        p.chmod(0o755)
        return p

    def _chrome(self) -> Path:
        return self._stub("fake-chrome", CHROME_STUB)

    def _svg(self, name: str = "flow.svg", body: str = SIZED_SVG) -> Path:
        p = self.work / name
        p.write_text(body)
        return p

    def _env(self, **extra: str) -> dict[str, str]:
        # 引けてよいのは stub と bash / coreutils / pkill だけ。rsvg-convert は置いたときだけ引ける
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "TMPDIR": str(self.root),
            "STUB_DIR": str(self.stub_dir),
        }
        env.update(extra)
        return env

    def _run(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True, env=env, timeout=60, cwd=self.work,
        )

    def _pid(self, name: str) -> int:
        return int((self.stub_dir / name).read_text().strip())

    def _assert_gone(self, pid: int) -> None:
        # 止めた直後は reap 待ちがありうるので少しだけ待つ
        deadline = time.monotonic() + 3
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(_alive(pid), f"pid {pid} が残っている")

    def test_no_args_is_usage_error(self) -> None:
        res = self._run(env=self._env(CHROME_BIN=str(self._chrome())))
        self.assertEqual(res.returncode, 2)

    def test_no_converter_is_fatal(self) -> None:
        svg = self._svg()
        res = self._run(str(svg), env=self._env(CHROME_BIN=str(self.root / "no-such-chrome")))
        self.assertEqual(res.returncode, 2)
        self.assertIn("FATAL:", res.stderr)
        self.assertFalse(svg.with_suffix(".png").exists())

    def test_chrome_bin_not_executable_does_not_fall_back_to_path(self) -> None:
        # CHROME_BIN を指定したら PATH の Chrome は探さない（明示を黙って差し替えない）
        self._stub("google-chrome", CHROME_STUB)
        svg = self._svg()
        res = self._run(str(svg), env=self._env(CHROME_BIN=str(self.root / "no-such-chrome")))
        self.assertEqual(res.returncode, 2)
        self.assertFalse((self.stub_dir / "chrome-args").exists())

    def test_finds_chrome_on_path_when_chrome_bin_unset(self) -> None:
        self._stub("google-chrome", CHROME_STUB)
        self._svg()
        res = self._run("flow.svg", env=self._env())
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "png=flow.png\n")
        self.assertTrue((self.stub_dir / "chrome-args").exists())

    def test_prefers_rsvg_convert(self) -> None:
        self._stub("rsvg-convert", RSVG_STUB)
        svg = self._svg()
        res = self._run("flow.svg", env=self._env(CHROME_BIN=str(self._chrome())))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "png=flow.png\n")
        self.assertEqual(svg.with_suffix(".png").read_text(), "RSVGDATA")
        self.assertFalse((self.stub_dir / "chrome-args").exists())

    def test_falls_back_to_chrome_when_rsvg_fails(self) -> None:
        self._stub("rsvg-convert", RSVG_STUB)
        svg = self._svg()
        res = self._run("flow.svg", env=self._env(CHROME_BIN=str(self._chrome()), RSVG_MODE="fail"))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "png=flow.png\n")
        self.assertEqual(svg.with_suffix(".png").read_text(), "PNGDATA")

    def test_window_size_from_width_and_height(self) -> None:
        self._svg()
        res = self._run("flow.svg", env=self._env(CHROME_BIN=str(self._chrome())))
        self.assertEqual(res.returncode, 0, res.stderr)
        args = (self.stub_dir / "chrome-args").read_text().splitlines()
        self.assertIn("--window-size=640,240", args)
        self.assertIn(f"file://{self.work / 'flow.svg'}", args)

    def test_window_size_from_viewbox_when_no_width_height(self) -> None:
        self._svg(body='<svg xmlns="http://www.w3.org/2000/svg"\n  viewBox="0 0 800.5 300"><rect/></svg>\n')
        res = self._run("flow.svg", env=self._env(CHROME_BIN=str(self._chrome())))
        self.assertEqual(res.returncode, 0, res.stderr)
        args = (self.stub_dir / "chrome-args").read_text().splitlines()
        self.assertIn("--window-size=800,300", args)

    def test_svg_without_size_fails_without_launching_chrome(self) -> None:
        self._svg(body='<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>\n')
        res = self._run("flow.svg", env=self._env(CHROME_BIN=str(self._chrome())))
        self.assertEqual(res.returncode, 1)
        self.assertTrue(res.stdout.startswith("failed=flow.svg\t"), res.stdout)
        self.assertFalse((self.stub_dir / "chrome-args").exists())

    def test_svg_with_width_only_fails_without_launching_chrome(self) -> None:
        # 高さが決まらないまま --window-size=640, で Chrome を起動しない
        self._svg(body='<svg xmlns="http://www.w3.org/2000/svg" width="640"><rect/></svg>\n')
        res = self._run("flow.svg", env=self._env(CHROME_BIN=str(self._chrome())))
        self.assertEqual(res.returncode, 1)
        self.assertTrue(res.stdout.startswith("failed=flow.svg\t"), res.stdout)
        self.assertFalse((self.stub_dir / "chrome-args").exists())

    # 次の 2 本は打ち切りを 6 秒にして、6 秒より十分早く返ることを見る。PNG ができた・Chrome が
    # 終わった時点で待つのをやめず、打ち切りまで待ち続ける実装を落とすため
    def test_stops_chrome_that_keeps_running_after_writing(self) -> None:
        svg = self._svg()
        start = time.monotonic()
        res = self._run("flow.svg", env=self._env(
            CHROME_BIN=str(self._chrome()), STUB_MODE="write-hang", SVG_TO_PNG_TIMEOUT="6"))
        self.assertLess(time.monotonic() - start, 4)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "png=flow.png\n")
        self.assertEqual(svg.with_suffix(".png").read_text(), "PNGDATA")
        self._assert_gone(self._pid("chrome.pid"))
        self._assert_gone(self._pid("child.pid"))

    def test_chrome_exiting_without_png_fails(self) -> None:
        self._svg()
        start = time.monotonic()
        res = self._run("flow.svg", env=self._env(
            CHROME_BIN=str(self._chrome()), STUB_MODE="exit-nowrite", SVG_TO_PNG_TIMEOUT="6"))
        self.assertLess(time.monotonic() - start, 4)
        self.assertEqual(res.returncode, 1)
        self.assertTrue(res.stdout.startswith("failed=flow.svg\t"), res.stdout)

    def test_times_out_chrome_that_never_writes(self) -> None:
        self._svg()
        start = time.monotonic()
        res = self._run("flow.svg", env=self._env(
            CHROME_BIN=str(self._chrome()), STUB_MODE="hang-nowrite", SVG_TO_PNG_TIMEOUT="1"))
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(res.returncode, 1)
        self.assertTrue(res.stdout.startswith("failed=flow.svg\t"), res.stdout)
        self._assert_gone(self._pid("chrome.pid"))

    def test_leaves_no_profile_dir_behind(self) -> None:
        self._svg()
        self._run("flow.svg", env=self._env(CHROME_BIN=str(self._chrome()), STUB_MODE="write-hang"))
        self.assertEqual(sorted(p.name for p in self.root.glob("svg-to-png.*")), [])

    def test_mixed_inputs_continue_and_exit_1(self) -> None:
        self._svg()
        (self.work / "note.txt").write_text("x")
        res = self._run("missing.svg", "note.txt", "flow.svg", env=self._env(CHROME_BIN=str(self._chrome())))
        self.assertEqual(res.returncode, 1)
        lines = res.stdout.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("failed=missing.svg\t"))
        self.assertTrue(lines[1].startswith("failed=note.txt\t"))
        self.assertEqual(lines[2], "png=flow.png")


if __name__ == "__main__":
    unittest.main()
