"""`severity_threshold` の形の正規化（publish / retro が共有 / GitHub issue #252）。

契約はトップレベルの 1 キー（`orchestration-measurement.md ## 16`。v2.58.0〜必須）で、retro の
歩留まり・検出 → 報告の内訳の層別キーになる。LLM がテンプレートを埋めるときに直前の
`below_threshold_counts` / `pre_adjust_counts` の中へ 1 段深く書く回があり（版付き 47 件中 5 件。
値はすべて `MAJOR`）、その回は理由なしに主層から `threshold=?` 層へ落ちていた。

**救う理由は報告件数の入れ子（`lib/report_counts.py`）と同じ**。層別キーが 1 つ落ちるだけで
その回が主層から丸ごと外れ、救った事実は別識別子（`payload:severity_threshold.nested`）で残せる。

**推測はしない**。語彙外の値と、2 つの親で食い違う値は昇格しない（どれが実効値か決められない）。
"""

from __future__ import annotations

THRESHOLDS = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR")
#: 入れ子の親として見るキー。実データの 5 件中 4 件が前者
NESTED_PARENTS = ("below_threshold_counts", "pre_adjust_counts")


def lift_nested_threshold(payload: dict) -> str | None:
    """入れ子の `severity_threshold` をトップレベルへ昇格する。昇格したら親キー名、しなければ None。

    トップレベルに値があれば（語彙外でも）触らない — 語彙の検証は呼び出し側の責務。
    親オブジェクトの中の値は残す（払い出した形の証拠）。
    """
    if payload.get("severity_threshold") is not None:
        return None
    found = []
    for parent in NESTED_PARENTS:
        nested = payload.get(parent)
        if isinstance(nested, dict) and nested.get("severity_threshold") is not None:
            found.append((parent, nested["severity_threshold"]))
    # 語彙外の値を先に捨ててから食い違いを見ると、`MAJOR` と `minor` のような組が 1 値に見えて
    # 昇格してしまう（実効値が MINOR だった可能性を消す）。書かれた値はすべて突合に入れる
    if (not found or any(value not in THRESHOLDS for _, value in found)
            or len({value for _, value in found}) != 1):
        return None
    payload["severity_threshold"] = found[0][1]
    return found[0][0]


# ---- 閾値の出どころ（GitHub issue #277） ----------------------------------------
# `severity_threshold` は実効値しか持たない。v2.140.0（#275）から doc だけの diff は既定の MAJOR が
# MINOR に下がるので、同じ MINOR でも「利用者が選んだ」と「doc_only で自動に下がった」が payload
# からは区別できなかった。retro の層別と #275 の効果測定にこの区別が要る。
# **SKILL からは渡させない**（`dispatch` / `invocation` と同じく機械判定だけを載せる）。
SOURCES = ("default", "user_config", "doc_only", "unknown")
#: userConfig のキー名（plugin.json の `userConfig`）
USER_CONFIG_KEY = "review_severity_threshold"


def user_threshold(settings: object, plugin: str = "code-review") -> str | None:
    """user settings（`settings.json` を読んだ dict）から userConfig の閾値を引く。無ければ None。

    CC は非 sensitive な userConfig を `pluginConfigs["<plugin>@<marketplace>"].options` に保存する。
    publish はモデルの Bash から呼ばれ、hook と違って `CLAUDE_PLUGIN_OPTION_*` を受け取らないので
    ここを直接読む。**複数のマーケットプレイスから入っていて値が食い違うときは None**
    （どれが効いているか決められない。推測しない）。語彙外の値も None — CC は選択肢を検証しない
    文字列型なので、`major` のような値は SKILL 側の解釈次第になる。
    """
    if not isinstance(settings, dict):
        return None
    configs = settings.get("pluginConfigs")
    if not isinstance(configs, dict):
        return None
    found = set()
    for key, entry in configs.items():
        if not isinstance(key, str) or key.split("@", 1)[0] != plugin or not isinstance(entry, dict):
            continue
        options = entry.get("options")
        if isinstance(options, dict) and options.get(USER_CONFIG_KEY) is not None:
            found.add(options[USER_CONFIG_KEY])
    if len(found) != 1:
        return None
    value = found.pop()
    return value if value in THRESHOLDS else None


def threshold_source(effective: str | None, user_value: str | None,
                     doc_only: int | None) -> str | None:
    """実効閾値の出どころを決める。実効値が無い回は None（フィールドごと載せない）。

    規則の正本は orchestration-guide.md `## 2`: userConfig が既定の MAJOR（未設定を含む）で、
    doc だけの diff なら MINOR に下げる。明示した MAJOR 以外の値は下げない。

    **規則と実効値が食い違う回は `unknown`**（オーケストレーターが規則を適用し損ねた・userConfig が
    読めなかった等。どちらかに寄せると #275 の効果測定がその回を誤った側に数える）。
    doc_only が分からない（triage を経ていない・一時ファイルが消えた）回は、下げたかどうかが
    分からない MINOR だけを `unknown` にする。
    """
    if effective is None:
        return None
    if user_value is not None and user_value != "MAJOR":
        return "user_config" if effective == user_value else "unknown"
    if doc_only == 1:
        return "doc_only" if effective == "MINOR" else "unknown"
    if effective != "MAJOR":
        return "unknown"
    return "user_config" if user_value is not None else "default"
