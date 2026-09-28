#!/usr/bin/env python3
"""公開先ガード（`detect-public-leak.py`）用の bash 部分集合パーサ.

**なぜ shlex では足りないか**: 公開される本文は `--body "$(cat <<'EOF' … EOF)"` の形で
渡されることが最も多い。shlex はコマンド置換も heredoc も知らないので、本文の中の `)` や
改行でトークン化が崩れる。ここでは次を解釈する:

- 引用符（'…' / "…" / $'…'）とバックスラッシュ、行継続
- `$(…)` / `` `…` `` / `<(…)`（再帰的に解析して、中身をコマンドとして返す）
- heredoc（`<<` / `<<-`、引用付き区切りは展開なし）と here-string（`<<<`）
- リダイレクト（`>` / `>>` / `>|` / `&>` / `<` / fd 付き）
- `;` `&&` `||` `|` `&` 改行 と `( )` `{ }` による区切り（制御構造は平坦化する）

**解決できないものは解決できないと返す**（`Word.static()` が None）。推測で埋めない —
呼び出し側はそれを「本文を静的に決められない」として fail-closed に扱う。
"""

from __future__ import annotations

import re

#: `$VAR` / `${…}` / `$(…)` / バッククォートのいずれか（引用なし heredoc の展開検出用）
EXPANSION_RE = re.compile(r"(?<!\\)(\$[A-Za-z_{(0-9@*#?$!-]|`)")

ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
REDIR_RE = re.compile(r"(\d+|&)?(>>|>\||>&|&>|>|<<<|<<-|<<|<>|<&|<)")

ANSI_C = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"',
          "a": "\a", "b": "\b", "f": "\f", "v": "\v", "e": "\x1b", "E": "\x1b", "0": "\0"}


class Part:
    """語の構成要素. kind: lit / param / cmdsub / procsub / arith."""

    __slots__ = ("kind", "text", "script", "name", "quoted")

    def __init__(self, kind, text="", script=None, name=None, quoted=False):  # mutation-ok: 既定値に頼るのは procsub と引用なしの `…` だけで、Part.quoted を読むのは lit 同士を結合する add_lit だけ
        self.kind = kind
        self.text = text          # lit: 値 / param: 元の表記
        self.script = script      # cmdsub / procsub: 中身の Script
        self.name = name          # param: 単純な変数名（`$X` / `${X}`）なら名前、それ以外は None
        self.quoted = quoted


class Word:
    def __init__(self):
        self.parts: list[Part] = []
        self.raw = ""
        self.quoted = False       # 引用符・エスケープを含んだか
        self.glob = False         # 引用なしの * ? [ を含むか
        self.tilde = False        # 引用なしの ~ で始まるか

    def add_lit(self, text, quoted=False):
        if self.parts and self.parts[-1].kind == "lit" and self.parts[-1].quoted == quoted:
            self.parts[-1].text += text
        else:
            self.parts.append(Part("lit", text, quoted=quoted))

    def static(self, env=None):
        """展開後の値。展開できない部分があれば None.

        `env` を渡すと `$NAME` / `${NAME}` をその値で解決する（同じコマンド内の代入を追う用）。
        """
        out = []
        for p in self.parts:
            if p.kind == "lit":
                out.append(p.text)
            elif p.kind == "param" and env is not None and p.name is not None and p.name in env \
                    and env[p.name] is not None:
                out.append(env[p.name])
            else:
                return None
        return "".join(out)

    def literal_text(self):
        """展開部分を除いた字面（検査用の近似。展開部分は元の表記のまま残す）."""
        out = []
        for p in self.parts:
            out.append(p.text if p.kind in ("lit", "param", "arith") else "")
        return "".join(out)

    def substitutions(self):
        return [p for p in self.parts if p.kind in ("cmdsub", "procsub")]

    def __repr__(self):
        return "Word(%r)" % self.raw


class Heredoc:
    def __init__(self, delim, strip_tabs, quoted):
        self.delim = delim
        self.strip_tabs = strip_tabs
        self.quoted = quoted
        self.body = None           # 読み終えるまで None

    @property
    def dynamic(self):
        """引用なし区切りで本文に展開があるか（展開後の値は静的に決まらない）."""
        return (not self.quoted) and self.body is not None and bool(EXPANSION_RE.search(self.body))


class Redir:
    def __init__(self, fd, op, target=None, heredoc=None):
        self.fd = fd
        self.op = op
        self.target = target       # Word（heredoc では区切り語）
        self.heredoc = heredoc


class Command:
    def __init__(self):
        self.assigns: list[tuple[str, Word]] = []
        self.words: list[Word] = []
        self.redirs: list[Redir] = []
        self.piped = False         # 直前のコマンドの stdout がこのコマンドの stdin に繋がる
        self.prev = None           # パイプ元の Command

    def empty(self):
        return not (self.assigns or self.words or self.redirs)


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, src: str):
        self.s = src
        self.n = len(src)
        self.i = 0
        self.pending: list[Heredoc] = []

    # ---- 入口 ---------------------------------------------------------------
    def parse(self):
        cmds = self.parse_script(None)
        if self.pending:
            # 改行が来ないまま終わった heredoc は本文が空（bash も同じく EOF まで）
            for hd in self.pending:
                hd.body = hd.body or ""
            self.pending = []
        return cmds

    def parse_script(self, stop):
        """`stop` は None（末尾まで）/ ')'（`$(`・`<(` の中）/ '`'（バッククォートの中）."""
        cmds: list[Command] = []
        cur = Command()
        pipe_next = False

        def finish():
            nonlocal cur, pipe_next
            if not cur.empty():
                if pipe_next and cmds:
                    cur.piped = True
                    cur.prev = cmds[-1]
                cmds.append(cur)
            cur = Command()
            pipe_next = False

        s = self.s
        while self.i < self.n:
            c = s[self.i]
            if stop == ")" and c == ")":
                self.i += 1
                finish()
                return cmds
            if stop == "`" and c == "`":
                self.i += 1
                finish()
                return cmds
            if c in " \t":
                self.i += 1
                continue
            if c == "\\" and self.i + 1 < self.n and s[self.i + 1] == "\n":
                self.i += 2
                continue
            if c == "\n":
                self.i += 1
                self.read_heredocs(stop)
                finish()
                continue
            if c == "#":
                while self.i < self.n and s[self.i] != "\n":
                    self.i += 1
                continue
            m = REDIR_RE.match(s, self.i)
            if m is not None:
                fd, op = m.group(1), m.group(2)
                if op in ("<", ">") and fd is None and m.end() < self.n and s[m.end()] == "(":
                    m = None       # `<(` / `>(` はプロセス置換（語として読む）
                elif fd == "&" and op not in (">", ">>"):
                    m = None
            if m is not None:
                self.parse_redirect(m, cur, stop)
                continue
            if c in ";&|":
                two = s[self.i:self.i + 2]
                if two in ("&&", "||", ";;", ";&", "|&"):
                    self.i += 2
                    if two == "|&":
                        finish()
                        pipe_next = True
                        continue
                else:
                    self.i += 1
                    if c == "|":
                        finish()
                        pipe_next = True
                        continue
                finish()
                continue
            if c in "()":
                # サブシェル・グループ・関数定義。中身は平坦化して順に並べる
                self.i += 1
                finish()
                continue
            w = self.parse_word(stop, at_command_start=not cur.words)
            if w is None:
                continue
            if not cur.words and getattr(w, "assign_name", None):
                cur.assigns.append((w.assign_name, w))
            else:
                cur.words.append(w)
        if stop is not None:
            raise ParseError("unterminated %s" % stop)
        finish()
        return cmds

    # ---- heredoc -------------------------------------------------------------
    def read_heredocs(self, stop):
        s = self.s
        while self.pending:
            hd = self.pending.pop(0)
            lines = []
            while True:
                if self.i >= self.n:
                    break
                j = s.find("\n", self.i)
                line = s[self.i:] if j < 0 else s[self.i:j]
                cmp = line.lstrip("\t") if hd.strip_tabs else line
                if cmp == hd.delim:
                    self.i = self.n if j < 0 else j + 1
                    break
                if stop == ")" and cmp.startswith(hd.delim) and cmp[len(hd.delim):].lstrip().startswith(")"):
                    # `EOF)` の形（区切り語の直後で置換が閉じる）
                    self.i += (len(line) - len(cmp)) + len(hd.delim)
                    break
                lines.append(cmp)
                self.i = self.n if j < 0 else j + 1
            hd.body = "".join(line + "\n" for line in lines)

    # ---- リダイレクト --------------------------------------------------------
    def parse_redirect(self, m, cur, stop):
        fd, op = m.group(1), m.group(2)
        self.i = m.end()
        if op == "&>" or (fd == "&" and op in (">", ">>")):
            fd, op = "&", ">>" if op == ">>" else ">"
        while self.i < self.n and self.s[self.i] in " \t":
            self.i += 1
        target = self.parse_word(stop, at_command_start=False, allow_assign=False)
        if target is None:
            raise ParseError("redirect without target")
        if op in ("<<", "<<-"):
            delim = "".join(p.text if p.kind == "lit" else p.text for p in target.parts)
            hd = Heredoc(delim, op == "<<-", target.quoted)
            self.pending.append(hd)
            cur.redirs.append(Redir(fd, op, target, hd))
        else:
            cur.redirs.append(Redir(fd, op, target))

    # ---- 語 ------------------------------------------------------------------
    def parse_word(self, stop, at_command_start=False, allow_assign=True):
        s = self.s
        w = Word()
        start = self.i
        if allow_assign and at_command_start:
            m = ASSIGN_RE.match(s, self.i)
            if m:
                w.assign_name = m.group(0).rstrip("=").rstrip("+")
                self.i = m.end()
        # プロセス置換 `<(…)` / `>(…)`
        if self.i + 1 < self.n and s[self.i] in "<>" and s[self.i + 1] == "(":
            self.i += 2
            sub = self.parse_script(")")
            w.parts.append(Part("procsub", "", script=sub))
            w.raw = s[start:self.i]
            return w
        if self.i < self.n and s[self.i] == "~":
            w.tilde = True
        while self.i < self.n:
            c = s[self.i]
            if c in " \t\n;&|()<>":
                break
            if stop == "`" and c == "`":
                break
            if c == "\\":
                if self.i + 1 < self.n:
                    if s[self.i + 1] == "\n":
                        self.i += 2
                        continue
                    w.add_lit(s[self.i + 1], quoted=True)
                    w.quoted = True
                    self.i += 2
                else:
                    self.i += 1
                continue
            if c == "'":
                j = s.find("'", self.i + 1)
                if j < 0:
                    raise ParseError("unterminated single quote")
                w.add_lit(s[self.i + 1:j], quoted=True)
                w.quoted = True
                self.i = j + 1
                continue
            if c == "$" and self.i + 1 < self.n and s[self.i + 1] == "'":
                self.i += 2
                buf = []
                while self.i < self.n and s[self.i] != "'":
                    if s[self.i] == "\\" and self.i + 1 < self.n:
                        m = re.compile(r"x([0-9A-Fa-f]{1,2})|([0-7]{1,3})").match(s, self.i + 1)
                        if m:
                            buf.append(chr(int(m.group(1), 16) if m.group(1) else int(m.group(2), 8)))
                            self.i = m.end()
                            continue
                        buf.append(ANSI_C.get(s[self.i + 1], s[self.i + 1]))
                        self.i += 2
                        continue
                    buf.append(s[self.i])
                    self.i += 1
                if self.i >= self.n:
                    raise ParseError("unterminated $'")
                self.i += 1
                w.add_lit("".join(buf), quoted=True)
                w.quoted = True
                continue
            if c == "$" and self.i + 1 < self.n and s[self.i + 1] == '"':
                self.i += 1
                continue       # $"…"（ロケール文字列）は "…" と同じに扱う
            if c == '"':
                self.parse_dquote(w)
                continue
            if c == "$":
                self.parse_dollar(w, quoted=False)
                continue
            if c == "`":
                self.i += 1
                sub = self.parse_script("`")
                w.parts.append(Part("cmdsub", "", script=sub))
                continue
            if c in "*?[":
                w.glob = True
            w.add_lit(c)
            self.i += 1
        w.raw = s[start:self.i]
        if not w.parts and not getattr(w, "assign_name", None) and self.i == start:
            # 進めない文字（呼び出し側の分岐漏れ）。無限ループを避ける
            self.i += 1
            return None
        return w

    def parse_dquote(self, w):
        s = self.s
        self.i += 1
        w.quoted = True
        while self.i < self.n:
            c = s[self.i]
            if c == '"':
                self.i += 1
                return
            if c == "\\" and self.i + 1 < self.n:
                nxt = s[self.i + 1]
                if nxt == "\n":
                    self.i += 2
                    continue
                if nxt in '$`"\\':
                    w.add_lit(nxt, quoted=True)
                    self.i += 2
                    continue
                w.add_lit("\\", quoted=True)
                self.i += 1
                continue
            if c == "$":
                self.parse_dollar(w, quoted=True)
                continue
            if c == "`":
                self.i += 1
                sub = self.parse_script("`")
                w.parts.append(Part("cmdsub", "", script=sub, quoted=True))
                continue
            w.add_lit(c, quoted=True)
            self.i += 1
        raise ParseError("unterminated double quote")

    def parse_dollar(self, w, quoted):
        s = self.s
        start = self.i
        nxt = s[self.i + 1] if self.i + 1 < self.n else ""
        if s.startswith("$((", self.i):
            depth = 0
            j = self.i + 1
            while j < self.n:
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            self.i = min(j + 1, self.n)
            w.parts.append(Part("arith", s[start:self.i], quoted=quoted))
            return
        if nxt == "(":
            self.i += 2
            sub = self.parse_script(")")
            w.parts.append(Part("cmdsub", "", script=sub, quoted=quoted))
            return
        if nxt == "{":
            depth = 0
            j = self.i + 1
            while j < self.n:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                elif s[j] == "\\":
                    j += 1
                j += 1
            if j >= self.n:
                raise ParseError("unterminated ${")
            self.i = j + 1
            inner = s[start + 2:j]
            name = inner if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", inner) else None
            w.parts.append(Part("param", s[start:self.i], name=name, quoted=quoted))
            return
        m = re.compile(r"[A-Za-z_][A-Za-z0-9_]*").match(s, self.i + 1)
        if m:
            self.i = m.end()
            w.parts.append(Part("param", s[start:self.i], name=m.group(0), quoted=quoted))
            return
        if nxt and nxt in "0123456789@*#?$!-":
            self.i += 2
            w.parts.append(Part("param", s[start:self.i], quoted=quoted))
            return
        w.add_lit("$", quoted=quoted)
        self.i += 1


def parse(src: str):
    """コマンド文字列を解析して Command の列を返す. 解析できなければ ParseError."""
    return Parser(src).parse()
