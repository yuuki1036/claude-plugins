"""`review:completed` の payload を層に分ける判定と、版マーカー・数値の読み方（retro / metrics-update が共有 / GitHub issue #536）。

`review-retro.sh` のヒアドキュメントと `metrics_update.py` が同じ式を別々に持っていたので、ここへまとめた。
"""

from __future__ import annotations

#: tokens.schema 3 で usage の算法が変わり、スケールがおよそ半分になった（transcript の行ごと
#: → message.id 単位の重複排除）。schema 2 以下は行数ぶん膨らんだ値で、倍率も世代で違うので、
#: 中央値・体数相関・1 体あたり cache_read のどれにも混ぜない
TOK_SCALE_MIN_SCHEMA = 3


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def schema_of(d, key):
    """版マーカーを int に寄せる（欠落・解釈不能は 1 = 最古の版として扱う）。"""
    try:
        return int(d.get(key) or 1)
    except (TypeError, ValueError):
        return 1


# ---- モデル世代の層別キー（GitHub issue #169） ------------------------------
# `effort` / `size_tier` の層別は、Opus 5 と 4.8 が混ざった
# 瞬間に成立しなくなる（実測: 2026-08-24 の 1 日で 3 サンプル中 2 件が 4.8 で、
# `sub_cache_read_k / sub_agents` の 7,853k と 3,7xx k の差が tier と世代で完全に交絡していた）。
# 世代はユーザーが実行時に選ぶもの（エイリアスは親世代を継ぐ / `docs/pipeline-design.md`）
# なので、**事故ではなく層別キー**として扱う。
def gen_of(p):
    """payload → 世代ラベル。`unrecorded`（旧版）と `mixed`（切替・引き当て失敗）は
    どちらも既知の世代と同じバケツに入れない。「たぶん opus-5 だった」は観測ではない。"""
    m = p.get("models")
    if not isinstance(m, dict):
        return "unrecorded"
    v = m.get("main")
    if not isinstance(v, str) or not v:
        return "mixed"
    return v[len("claude-"):] if v.startswith("claude-") else v


def is_rereview(p):
    """修正を確かめる再レビューの回か（`invocation.rereview` / GitHub issue #296）。

    呼び出し側の申告（self-review の `--rereview`）を publish が transcript から読んで載せる。
    **鍵が無い回は初回に置く**（申告の仕組みより前の回は区別できない。推定で振り分けない）。
    """
    inv = p.get("invocation")
    return isinstance(inv, dict) and inv.get("rereview") is True


def scope_mode_of(p):
    """`review_scope.mode`。**無い・語彙外の回は full**（実装より前の回は diff 全体を見ている / #313）."""
    sc = p.get("review_scope")
    mode = sc.get("mode") if isinstance(sc, dict) else None
    return mode if mode in ("delta", "full") else "full"
