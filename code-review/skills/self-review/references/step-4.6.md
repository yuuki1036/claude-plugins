### 4.6 Meta-reviewer ラウンド（v2.12.0 / 動的・**4.9 反証と同一 wave**。実行順は `4.5 → 4.8 の skeptic 統合 → 4.6 meta + 4.9 反証を同一メッセージで一括発行 → mark wave → [meta 由来の追加反証バッチ] → 4.7 → Step 5`。両者は互いの出力に依存しないので直列に置かない / **片方がスキップでも他方はそのまま発行する** / #122）

**スキップ条件**（いずれか満たせばスキップし、同一 wave の 4.9 だけを発行する）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- **severity 側の起動条件を満たさない**（`skip_reason: "no-high-severity"` / `gate_schema: 3`）。起動条件は「Step 4.5 後の全指摘（フィルタリング前）に **BLOCKER** が 1 件以上」∨「**CRITICAL** が 1 件以上」∨「**報告マトリクス通過見込みの MAJOR が 3 件以上**」。MAJOR 経路は v2.62.0 で追加した（旧ゲートは高 severity の存在だけを条件にしていたため実測 14 件中 `fired=1` とほぼ常時不発だった / GitHub issue #123 C）
- **`size_tier` が `small` かつ BLOCKER が 1 件もない**（v2.60.0 / `skip_reason: "size-tier"`）。BLOCKER があれば帯に関わらず起動する。**この 1 条件だけが規模帯に連動する例外**で（triage-guide.md `## 6.3`）、根拠が n=1 のため**ロールバック条件つきの暫定ゲート** → `design-notes/triage-rationale.md`

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 7` の手順に従う（meta-reviewer を 1 体 `model: opus`, `effort: max` で **Step 4.9 の反証バッチと同一メッセージ内で**起動 → 追加指摘を dedup して統合。失敗時は missing_coverage に追記して続行）。**回収した直後に `mark wave` を記録する**（Step 4 と同じ呼び出し。後勝ち。反証と同一 wave なので打点は 1 回で足りる）。

**起動はここでは発行しない**: 起動すると決めたら、そのことを持って Step 4.9 へ進み、反証バッチと同じメッセージで発行する（4.9 がスキップでも、4.9 の手順で meta だけを発行する）。Step ごとにファイルを読む構成では、4.6 を読んだ時点で 4.9 の本文はまだ読んでいない（GitHub issue #426）

**次は Step 4.9**（SKILL.md に戻り、その見出しを見る）
