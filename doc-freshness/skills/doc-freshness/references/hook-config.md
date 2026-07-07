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
  "hookTargets": [".claude/designs/", ".claude/adr/"],
  "postToolUseCheck": true,
  "sessionStartCheck": false
}
```

| キー | デフォルト | 意味 |
|---|---|---|
| `hookTargets` | `[".claude/designs/", ".claude/adr/"]` | frontmatter 必須とみなす project doc の path prefix（project root 相対）。両 hook が共有 |
| `postToolUseCheck` | `true` | `false` で PostToolUse frontmatter 警告を無効化 |
| `sessionStartCheck` | `false` | `true` で SessionStart の stale 一括警告を有効化（opt-in） |

- stale 閾値（`thresholds.current` / `thresholds.target`）は skill と共有する（thresholds.md 参照）。
- `hookTargets` を指定すると両 hook の対象がその配列で**置き換わる**（部分追加ではない）。

## 対象範囲の設計判断

**なぜ `.claude/designs/` と `.claude/adr/` に限定するか**:

- この 2 dir は adr-keeper / design-doc が鮮度 lint を委譲する「frontmatter 必須の project doc」置き場（skill Phase 1 の走査対象と一致）。
- **プラグイン内部 doc（SKILL.md / references/ / README）は対象に含めない**。ルート CLAUDE.md の規約どおり、これらの鮮度はバージョンバンプ + CHANGELOG + pre-commit hook で管理され、`last-validated`（current=5 日閾値）を付けると恒常 stale 化して逆効果になるため。
- 別の project doc 置き場（例: `docs/adr/`）を使う場合は `hookTargets` で明示的に追加する。

## 免除ルール（stale-check.sh）

skill Phase 3 と同基準:

- `append_only: true` の frontmatter を持つ doc は stale 判定を免除（ADR のような決定時点の記録）。
- `phase: superseded` は stale 判定対象外。
- `last-validated` 欠落・frontmatter 無しの doc は stale-check では扱わない（frontmatter-guard.sh の領分）。

## PreToolUse を採用しない理由

新規 doc 作成時に frontmatter 不在で即 error になる failure mode を避けるため、frontmatter 検知は **PostToolUse のみ**（書き込み後に警告、ブロックしない）とする。PostToolUse の block は編集を巻き戻さないため、警告は「次の一手を促すシグナル」として機能する。
