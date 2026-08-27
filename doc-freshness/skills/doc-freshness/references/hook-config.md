# hook 設定（Phase 2 — イベント駆動の鮮度検知）

doc-freshness は手動走査（`/doc-freshness-check` スキル）に加えて、2 つの hook でイベント駆動の鮮度検知を行う。設定は skill と同じ `.claude/doc-freshness.json` に置く。

## hook の役割分担

| hook | イベント | 役割 | 既定 |
|---|---|---|---|
| `frontmatter-guard.sh` | PostToolUse (Edit/Write/MultiEdit) | frontmatter 必須の project doc に `last-validated` / `phase` が欠落したら非ブロッキング警告 | 常時 on（対象 dir 限定） |
| `stale-check.sh` | SessionStart (once) | 対象 doc の stale をセッション開始時にまとめて 1 回警告 | **opt-in**（既定 off） |

> **決定的検証 > LLM 判定**（ルート CLAUDE.md「ルール配置の意思決定」）: frontmatter キーの存在は grep で書ける決定的判定なので Hook に置いて遵守率 100% に寄せる。昇格するのは「frontmatter 欠落の検知」のみで、stale 判定の閾値運用・修正提案は既存 skill 側に残す（hook は軽量読み出しに徹する）。

## 設定キー

`.claude/doc-freshness.json`（thresholds.md の既存キーに以下を追加）:

```json
{
  "hookTargets": [".claude/designs/", ".claude/adr/", ".claude/living-specs/"],
  "postToolUseCheck": true,
  "sessionStartCheck": false
}
```

| キー | デフォルト | 意味 |
|---|---|---|
| `hookTargets` | `[".claude/designs/", ".claude/adr/", ".claude/living-specs/"]` | frontmatter 必須とみなす project doc の path prefix（project root 相対）。両 hook が共有 |
| `postToolUseCheck` | `true` | `false` で PostToolUse frontmatter 警告を無効化 |
| `sessionStartCheck` | `false` | `true` で SessionStart の stale 一括警告を有効化（opt-in） |

- stale 閾値（`thresholds.current` / `thresholds.target`）は skill と共有する（thresholds.md 参照）。`stale-check.sh` は hook 側でもこの 2 キーを読む。
- `hookTargets` を指定すると両 hook の対象がその配列で**置き換わる**（部分追加ではない）。
- **`jq` の有無で解釈の深さが変わる**（GitHub issue #181）:
  - `jq` あり — 上表のすべてを解釈する
  - `jq` なし — `postToolUseCheck: false` の opt-out だけを grep で尊重する。`hookTargets` は
    配列を正しく読めないため、**宣言されている場合は既定の対象で走らせずに no-op** する
    （利用者が対象を絞っているのに既定の広い対象で警告するのは誤警告になるため）。
    `stale-check.sh` は `jq` 不在で明示的に skip する（そちらは設定必須の opt-in なので）

## 対象範囲の設計判断

**なぜ `.claude/designs/` `.claude/adr/` `.claude/living-specs/` に限定するか**:

- この 3 dir は adr-keeper / design-doc / living-spec-workflow が鮮度 lint を委譲する「frontmatter 必須の project doc」置き場（skill Phase 1 の走査対象と一致）。
- **プラグイン内部 doc（SKILL.md / references/ / README）は対象に含めない**。ルート CLAUDE.md の規約どおり、これらの鮮度はバージョンバンプ + CHANGELOG + pre-commit hook で管理され、`last-validated`（current 閾値）を付けると恒常 stale 化して逆効果になるため。
- 別の project doc 置き場（例: `docs/adr/`）を使う場合は `hookTargets` で明示的に追加する。

**委譲元プラグインを追加するときは、この 6 箇所を同時に更新する**（1 箇所でも漏れると、委譲を宣言した側は「鮮度 lint に守られている」と思い込むのに実際は走査されない silent な不成立になる。**0.1.0 で実際に踏み 0.2.0 で修正した**）:

**挙動に効く 4 箇所**（漏れると走査されない）

1. skill `SKILL.md` Phase 1 の**走査対象リスト**と、その直後の**除外規則**（「〜を除く `.claude/` 配下」という反対向きの規定なので、追加側だけ直しても効かない）
2. `hooks/scripts/frontmatter-guard.sh` の `DEFAULT_TARGETS`
3. `hooks/scripts/stale-check.sh` の `TARGETS` フォールバック
4. 本ファイルの既定値と本節

**記述に効く 2 箇所**（漏れても動くが、doc が実態と食い違う）

5. `README.md` の hook 説明と走査対象セクション
6. `.claude-plugin/plugin.json` の description（+ `.claude-plugin/marketplace.json` の同期。version bump と CHANGELOG も必須）

> 5・6 は機械検証の死角。`validate_ssot.py` は marketplace の description 一致と INDEX/CLAUDE.md の一覧表しか照合せず、README 本文は誰も見ていない。挙動側だけ直して doc を取り残すのは、silent 不成立と同じ「守られているつもり」を別の形で作る。

受け入れ条件は**実測**にする（宣言の追加だけで済ませない）: 対象 dir に doc を 1 本置いて `/doc-freshness-check` が実際に拾うことを確認する。

## 免除ルール（stale-check.sh）

skill Phase 3 と同基準:

- `append_only: true` の frontmatter を持つ doc は stale 判定を免除（ADR のような決定時点の記録）。
- `phase: superseded` は stale 判定対象外。
- `last-validated` 欠落・frontmatter 無しの doc は stale-check では扱わない（frontmatter-guard.sh の領分）。

## PreToolUse を採用しない理由

新規 doc 作成時に frontmatter 不在で即 error になる failure mode を避けるため、frontmatter 検知は **PostToolUse のみ**（書き込み後に警告、ブロックしない）とする。PostToolUse の block は編集を巻き戻さないため、警告は「次の一手を促すシグナル」として機能する。
