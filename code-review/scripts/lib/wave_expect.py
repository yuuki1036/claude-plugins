"""期待 wave 本数の式（**正本**）。

`wave-split`（一括発行の規約違反）は「実 wave 本数が期待本数を超えた」で立てる。
規約そのものは `references/orchestration-guide.md` の `## 0`（同一フェーズの agent は
1 メッセージで一括発行する）。

**式を使う経路が 3 つある**:

- `publish-review-event.sh` … `wave-split` を立てて `waves_expected` を payload に焼く
- `review-backfill.sh` … `dispatch` の無い過去イベントに後付けする
- `review-retro.sh` … 集計時に**再計算して判定する**（GitHub issue #200）

以前は publish と backfill に式の複製があり、一致を回帰テストで縛っていた。retro が
3 つ目の消費者になった時点で複製を持たせる理由が無くなったので、ここへ寄せた。

**retro が payload の値をそのまま使わない理由**（#200）: `waves_expected` は publish
時点の式で焼き付くが、**式の版マーカーが無い**（`dispatch.schema` は `measure-tokens.sh`
が持つ版で、publish 側の式変更では上げない契約）。式を直しても過去のイベントは旧値のまま
数え続けられるので、**一度出た偽陽性が固定化する** — 実測で `[6,10,4,1]` の回が
#166 で解決済みの偽陽性なのに違反として数え続けられていた。再計算に必要な入力
（`agents` / `meta_reviewer` / `recall_skeptic` / `wave_sizes`）はすべて payload にある。

**層の同定はしない。** `subagents/*.meta.json` の `description` は LLM の自由文で書式が
安定せず（実測 25 セッションで大半が分類不能）、分類器を置くと**静かに何も検出しない**
方向に倒れる。既存フィールドの算術だけで見る。
"""

def _layer_n(agents, key):
    """`agents[key]` を非負整数として読む（欠測・型違い・bool は 0）。"""
    v = agents.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        return 0
    return max(v, 0)


def meta_added_findings(payload):
    """meta が指摘を足した回か（GitHub issue #166）。

    meta 由来の `[meta]` タグ付き指摘を反証にかける追加バッチは、**meta の出力が存在しない
    時点では発行できない**ので構造的な直列であって一括発行違反ではない。`meta_reviewer` は
    `agents` に計上しない契約なので、この 1 本は他のどの項にも現れない。

    **`findings_added` が 1 以上**を条件にする。追加バッチは「足した指摘のうち反証ゲートに
    該当する分があるとき」だけ起動するので、これは見込みの上側（保守側）。
    """
    m = payload.get("meta_reviewer")
    if not isinstance(m, dict) or m.get("fired") is not True:
        return False
    n = m.get("findings_added")
    if isinstance(n, bool) or not isinstance(n, int):
        return False
    return n > 0


def skeptic_tail_solo(payload, wave_sizes):
    """skeptic の fallback 起動で 1 本増えた形か（GitHub issue #172 / #200）。

    fallback 起動は `triage-dynamic-gates.md ## 8.5` で **reviewer 完了後の単独 1 体**と
    規約で決まっている。`recall_skeptic.fired` に無条件で +1 すると、実データで
    **偽陽性 1 件を消す代わりに本物 3 件が消える**ので、形も見る。

    判定は「**末尾から連続する単独 wave の並びがあり、それより前に単独 wave が無い**」。
    末尾の単独 wave は skeptic fallback・反証・meta 反証のように**入力が揃うまで発行できない
    層**が並ぶ場所で、そこ以外の単独 wave は層の分割を意味する。控除は**常に 1 本だけ**
    （見込むのは fallback の 1 本で、末尾の連なりの本数ではない）。

    **末尾 1 本だけを見て切ってはならない** — 初版（v2.91.0）の `sizes[-1] == 1 and
    1 not in sizes[:-1]` は `[1,1,6,1]`（explorer が先頭で 2 wave に割れた本物の違反）を
    正しく残す一方、`[2,5,1,1]`（skeptic の後ろに反証 wave が 1 本付いた形）で控除が
    効かず偽陽性を出していた。#172 が「既知の残存限界②」として予告していた形そのもの。

    **残る限界**（→ `design-notes/orchestration-rationale.md`）: skeptic の既定経路は
    fallback ではなく **reviewer wave への相乗り**なので、`fired` は追加 wave の存在を
    含意しない。また末尾に固まった単独 wave が本当に構造的な直列かは位置からは決まらない
    （末尾で分割された reviewer wave を控除で 1 本ぶん見逃す余地がある）。構造的な解は
    `recall_skeptic` に起動経路を自己申告させること。
    """
    sk = payload.get("recall_skeptic")
    if not isinstance(sk, dict) or sk.get("fired") is not True:
        return False
    if not isinstance(wave_sizes, list) or not wave_sizes:
        return False
    tail = 0     # 末尾から連続する単独 wave の本数
    while tail < len(wave_sizes) and wave_sizes[-1 - tail] == 1:
        tail += 1
    if tail == 0:
        return False
    return 1 not in wave_sizes[:len(wave_sizes) - tail]


def expected_waves(payload, wave_sizes):
    """payload から期待 wave 本数を出す。

    見込みは**保守側**（増やす方向）に倒す。取り逃しは出るが偽陽性は出にくく、
    「⚠️ が出たときだけ行動する」契約を守る側に効く。

    - explorer 層があれば 1 本（無ければ 0 本）
    - reviewer 層は常に 1 本（`agents` が空でも review は必ず走る）
    - 反証層（`verify`）があれば 1 本
    - Round 2 は再起動なので 2 本（`triage-dynamic-gates.md ## 8`）
    - meta が指摘を足した回は追加の反証バッチで 1 本
    - skeptic の fallback 起動で 1 本
    """
    agents = payload.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    return ((1 if _layer_n(agents, "explorer") > 0 else 0) + 1
            + (1 if _layer_n(agents, "verify") > 0 else 0)
            + (2 if _layer_n(agents, "round2") > 0 else 0)
            + (1 if meta_added_findings(payload) else 0)
            + (1 if skeptic_tail_solo(payload, wave_sizes) else 0))
