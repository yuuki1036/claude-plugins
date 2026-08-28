#!/usr/bin/env perl
# detect-commit-bypass.pl
#
# 標準入力から受け取ったコマンド列を解析し、git hook を迂回するパターンを
# 検出したら理由文字列を stdout に出力する（検出なしなら何も出さない）。
# 常に exit 0（呼び出し側の set -e を踏まないため）。
#
# 検出対象:
#   - --no-verify / その git 省略形（--no-ver, --no-veri, ...）
#   - -n を含む短フラグクラスタ（-n, -nm, -anm ...。値を取る短オプション m/F/C/t で打ち切り）
#   - core.hooksPath 上書き（`git -c core.hooksPath=...` / 引用符付き / GIT_CONFIG_* env）
#   - `sh -c '...'` / `bash -xc "..."` / `eval "..."` 等に埋め込まれた上記（再帰解析）
#   - `command git` / `\git` 等の前置
#   - バックスラッシュ改行継続で分割された迂回
#   - guardrail-protect.json 自体を Bash（リダイレクト/sed -i/mv/rm 等）で改変する試み
#     （**ファイル名の言及では発火しない** — トークン準拠で判定する）
#
# 設計:
#   1. シェル準拠のトークナイザ（'...' / "..." / $'...' / バックスラッシュを解釈し、
#      引用符を除去してトークン化）で「引用符=メッセージ」の素朴前提を廃す
#   2. git commit の引数モデル（-m/-F/-C/-t 等は次トークンを値として消費）で、
#      メッセージに --no-verify 等が入っても誤検知せず、裸/引用符付きのフラグは検出する
#   3. pipeline/list セグメント単位で判定し、他コマンドの -n（git log -n 5 等）を誤爆しない

use strict;
use warnings;

my $cmd = do { local $/; <STDIN> };
$cmd = '' unless defined $cmd;

# 0. バックスラッシュ改行継続を空白へ畳む（`git commit \<改行>-n` を 1 コマンド扱い）
$cmd =~ s/\\\n/ /g;

# --- ANSI-C ($'...') エスケープの最小展開 ---
sub ansi_c {
    my ($c) = @_;
    my %map = ("n"=>"\n","t"=>"\t","r"=>"\r","\\"=>"\\","'"=>"'","\""=>"\"","a"=>"\a","b"=>"\b","f"=>"\f","v"=>"\013","0"=>"\0");
    return exists $map{$c} ? $map{$c} : $c;
}

# --- シェル準拠トークナイザ ---
# 戻り値: セグメントの配列。各セグメントは word トークンの配列 [ [w1,w2,...], ... ]
# 区切り: ; | & && || 改行（引用符外のもの）。引用符は除去する。
sub tokenize_segments {
    my ($s) = @_;
    my @segments;
    my @cur;
    my $word;                       # undef = word 未開始
    my $i = 0; my $n = length $s;
    my $flush_word = sub { if (defined $word) { push @cur, $word; $word = undef } };
    my $flush_seg  = sub { $flush_word->(); if (@cur) { push @segments, [@cur]; @cur = () } };
    while ($i < $n) {
        my $ch = substr($s, $i, 1);
        if ($ch eq "'") {                                   # 単一引用符: 次の ' までリテラル
            $word = '' unless defined $word;
            my $j = index($s, "'", $i + 1);
            $j = $n if $j < 0;
            $word .= substr($s, $i + 1, $j - $i - 1);
            $i = $j + 1; next;
        }
        if ($ch eq '"') {                                   # 二重引用符: 次の " まで（\" を解釈）
            $word = '' unless defined $word;
            $i++;
            while ($i < $n) {
                my $c = substr($s, $i, 1);
                if ($c eq '\\' && $i + 1 < $n) { $word .= substr($s, $i + 1, 1); $i += 2; next; }
                last if $c eq '"';
                $word .= $c; $i++;
            }
            $i++; next;
        }
        if ($ch eq '$' && $i + 1 < $n && substr($s, $i + 1, 1) eq "'") {  # $'...' ANSI-C
            $word = '' unless defined $word;
            my $j = $i + 2;
            while ($j < $n) {
                my $c = substr($s, $j, 1);
                if ($c eq '\\' && $j + 1 < $n) { $word .= ansi_c(substr($s, $j + 1, 1)); $j += 2; next; }
                last if $c eq "'";
                $word .= $c; $j++;
            }
            $i = $j + 1; next;
        }
        if ($ch eq '\\') {                                  # バックスラッシュエスケープ
            if ($i + 1 < $n) { $word = '' unless defined $word; $word .= substr($s, $i + 1, 1); $i += 2; next; }
            $i++; next;
        }
        if ($ch eq ';' || $ch eq "\n") { $flush_seg->(); $i++; next; }
        if ($ch eq '&') { $flush_seg->(); $i++; $i++ if $i < $n && substr($s, $i, 1) eq '&'; next; }
        if ($ch eq '|') {
            # `>|`（clobber 強制リダイレクト）は pipe ではない。直前の word が
            # リダイレクト演算子で終わっていれば、区切らずに演算子の一部として繋ぐ
            # （分割すると `echo x >| cfg` のリダイレクト先が次セグメントへ落ち、
            #  自己保護の検出が漏れる）
            if (defined $word && $word =~ /^>>?$/) { $word .= '|'; $i++; next; }
            $flush_seg->(); $i++; $i++ if $i < $n && substr($s, $i, 1) eq '|'; next;
        }
        if ($ch =~ /\s/) { $flush_word->(); $i++; next; }
        $word = '' unless defined $word; $word .= $ch; $i++;
    }
    $flush_seg->();
    return @segments;
}

# 先頭の env 代入・command/builtin/exec・\ 前置を剥がして (cmd0, @args) を返す
sub cmd_and_args {
    my (@w) = @_;
    my $i = 0;
    $i++ while $i <= $#w && $w[$i] =~ /^[A-Za-z_][A-Za-z0-9_]*=/;   # env 代入
    while ($i <= $#w && ($w[$i] eq 'command' || $w[$i] eq 'builtin' || $w[$i] eq 'exec')) { $i++; }
    return (undef) if $i > $#w;
    my $cmd0 = $w[$i]; $cmd0 =~ s/^\\//;                            # \git -> git
    return ($cmd0, @w[$i + 1 .. $#w]);
}

sub is_shell {
    my ($c) = @_;
    return 0 unless defined $c;
    return $c =~ m{(^|/)(ba|z|da|a|k|c|tc)?sh$};
}

# シェル -c / -xc / -cSCRIPT の command_string 引数を返す（無ければ undef）
sub shell_script_arg {
    my (@args) = @_;
    for (my $k = 0; $k <= $#args; $k++) {
        my $a = $args[$k];
        if ($a =~ /^-[A-Za-z]*c$/)       { return $args[$k + 1]; }   # -c / -xc / -lc
        if ($a =~ /^-c(.+)/s)            { return $1; }              # -cSCRIPT
    }
    return undef;
}

# git commit セグメントかを判定し、迂回フラグの理由を返す。
# hooksPath は「メッセージ本文に core.hooksPath と書いただけ」を誤検知しないよう、
# -c の値・-c 埋め込み値だけを見る（メッセージ値は引数モデルでスキップされる）。
sub git_commit_reasons {
    my (@args) = @_;
    return () unless grep { $_ eq 'commit' } @args;

    my @reasons;
    # 別トークンを値として消費するオプション（その次トークンはフラグでなく値）
    my %takes_arg = map { $_ => 1 } qw(
        -m --message -F --file -C --reuse-message --reedit-message
        -t --template --author --date --fixup --squash --cleanup --trailer
        --pathspec-from-file
    );

    for (my $k = 0; $k <= $#args; $k++) {
        my $a = $args[$k];
        next if $a eq 'commit';
        if ($a eq '-c' || $a eq '--reedit-message') {                # -c は値を hooksPath 検査してからスキップ
            my $v = $args[$k + 1];
            push @reasons, 'core.hooksPath override' if defined $v && $v =~ /core\.hookspath/i;
            $k++; next;
        }
        if ($a =~ /^-c(.+)/s) {                                       # -cVALUE 埋め込み（git global）
            push @reasons, 'core.hooksPath override' if $1 =~ /core\.hookspath/i;
            next;
        }
        next if $a =~ /^--config=(.+)/ && do { push @reasons, 'core.hooksPath override' if $1 =~ /core\.hookspath/i; 1 };
        if ($takes_arg{$a}) { $k++; next; }                          # 値トークンをスキップ
        next if $a =~ /^--(message|file|reuse-message|reedit-message|template|author|date|fixup|squash|cleanup|trailer|pathspec-from-file|gpg-sign)=/;  # 値埋め込み長形式
        if ($a =~ /^--no-ver[a-z]*$/i) { push @reasons, '--no-verify flag'; next; }
        next if $a =~ /^--/;                                          # 上記以外の長オプションは無害
        if ($a =~ /^-[A-Za-z]/) {                                     # 単一ダッシュ短フラグクラスタ
            for my $ch (split //, substr($a, 1)) {
                if ($ch eq 'n') { push @reasons, '-n short flag'; last; }
                last if $ch =~ /[mFCtcS]/;   # 値を取る短オプションで打ち切り（残りはその値）
            }
        }
    }
    return @reasons;
}

my @all_reasons;

# --- 設定ファイル自体を Bash で改変する試みの検出（自己保護の Bash 経路）---
#
# **$cmd 全体への正規表現で判定しないこと。** 旧実装は引用符を一切見ずに
# 「破壊的な語 → 設定ファイル名」の並びを探しており、**ファイル名を文字列として
# 書いただけのコマンドをブロック**していた。実測の偽陽性:
#
#   echo 'rm は危険。設定は .claude/guardrail-protect.json にある'   → BLOCK
#
# 区切り（| ; &）が間に無ければ距離を問わず一致するため、doc を書く・説明する・
# ログに残すといった無害な操作が止まる。実際に README へ当のファイル名を書こうと
# して作業がブロックされた（GitHub issue #162 の実装中）。
#
# 判定はトークナイザの出力（引用符を除去済みの word 列）に対して行う。
# `sh -c '...'` の中身も analyze() の再帰でここへ届く。
my $CFG_RE = qr{(?:^|/)guardrail-protect\.json$};

#: 内容を書き換え・破壊しうるコマンド（旧正規表現の語彙を踏襲）
my %DESTRUCTIVE = map { $_ => 1 } qw(rm cp mv tee dd truncate ln mktemp install shred);

sub config_write_reasons {
    my (@w) = @_;
    my @reasons;

    # ① リダイレクト先が設定ファイル（`> cfg` / `>>cfg` / `>| cfg`）
    for my $k (0 .. $#w) {
        my $t = $w[$k];
        if ($t =~ /^>>?\|?$/) {                       # 演算子が単独トークン
            push @reasons, 'redirect' if defined $w[$k + 1] && $w[$k + 1] =~ $CFG_RE;
        } elsif ($t =~ /^>>?\|?(.+)$/) {              # `>cfg` のように連結
            push @reasons, 'redirect' if $1 =~ $CFG_RE;
        }
    }

    my ($cmd0, @args) = cmd_and_args(@w);
    return @reasons unless defined $cmd0;
    my $base = $cmd0; $base =~ s{.*/}{};

    # ② 破壊的コマンドの**引数**が設定ファイル
    if ($DESTRUCTIVE{$base} && grep { $_ =~ $CFG_RE } @args) {
        push @reasons, $base;
    }

    # ③ in-place 書き換え（sed -i / perl -i）
    if (($base eq 'sed' || $base eq 'perl')
        && (grep { /^-[A-Za-z]*i/ } @args)
        && (grep { $_ =~ $CFG_RE } @args)) {
        push @reasons, "$base -i";
    }

    return @reasons;
}

sub analyze {
    my ($src, $depth) = @_;
    return if $depth > 4;
    for my $seg (tokenize_segments($src)) {
        my @w = @$seg;
        next unless @w;
        # **`next unless defined $cmd0` より前に置く** — リダイレクトだけのセグメント
        # （`> cfg` 単独）でも自己保護は効かせる
        push @all_reasons, map { "guardrail-protect.json self-modification via Bash ($_)" }
            config_write_reasons(@w);
        my ($cmd0, @args) = cmd_and_args(@w);
        next unless defined $cmd0;
        if (is_shell($cmd0)) {                              # sh -c '<script>' を再帰
            my $inner = shell_script_arg(@args);
            analyze($inner, $depth + 1) if defined $inner;
        } elsif ($cmd0 eq 'eval') {                         # eval '<script>' を再帰
            analyze(join(' ', @args), $depth + 1);
        }
        if ($cmd0 eq 'git' || $cmd0 =~ m{/git$}) {
            my @r = git_commit_reasons(@args);
            if (grep { $_ eq 'commit' } @args) {
                # 先頭の env 代入を検査（GIT_CONFIG_KEY_*=core.hooksPath 等での hooksPath 上書き）
                for my $t (@w) {
                    last unless $t =~ /^[A-Za-z_]\w*=/;
                    push @r, 'core.hooksPath override' if $t =~ /core\.hookspath/i;
                }
            }
            push @all_reasons, @r;
        }
    }
}

analyze($cmd, 0);

if (@all_reasons) {
    my %seen;
    print join('; ', grep { !$seen{$_}++ } @all_reasons);
}

exit 0;
