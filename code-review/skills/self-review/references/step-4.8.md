### 4.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

reviewer wave への相乗りで起動し、4.6 + 4.9 の一括発行より前に統合する。**high-risk surface を含む変更に限り**、reviewer の findings も推論も渡さない独立 skeptic を 1 体起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで探す（`${CLAUDE_PLUGIN_ROOT}/references/triage-dynamic-gates.md` `## 8.5 冷や読み skeptic ラウンド`）。反証レイヤー(4.9)が偽陽性を潰す係なのに対し、本フェーズは見落とし（false negative）を独立読み直しで足す係。self-review は PR を持たないため surface 判定は diff 正規表現 + reviewer の `[surface:high-risk]` フラグで行う（PR 自己申告 D1-High は無い）。

**スキップ条件**（いずれか満たせばスキップして 4.6 + 4.9 の一括発行へ）:
- userConfig `enable_recall_skeptic` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` / `medium` / `high`（**xhigh / max だけ起動する**。v2.52.0 で high 起点に昇格したが、ロールバック条件に該当したので戻した — opus-5-5 の high 起動 13 件で価値率 15%。根拠: triage-dynamic-gates.md `## 8.5` / #264）
- `--focus` / `--exclude` でスコープを絞り込んでいる
- high-risk surface（triage-dynamic-gates.md `## 8.5` の surface 判定。`--since` の回は delta で判定する）を含まない

**スキップ時も surface 判定は必ず実施（silent skip 防止・issue #85）**: 上記スキップ条件（effort / config / scope）に該当して skeptic agent を起動しない場合でも、surface 判定（triage-dynamic-gates.md `## 8.5` の正規表現。diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** する。surface=true なら skeptic 未起動の事実と skip_reason（`effort` / `config` / `scope`）を Step 6 レポートの「動的ラウンド」行に必ず出す（`--embed` の有無に依存しない human レポート契約。JSON payload の `recall_skeptic` 記録と対を成す）。

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 9` の手順に従う。**起動は Step 4 の reviewer 一括発行に相乗り済み**（Step 2.4 で surface 判定・ゲート通過を確認している）なので、本フェーズで行うのは **結果の統合**（`[recall-skeptic]` / `[recall-skeptic:dup]` タグ付き指摘を dedup して統合し、反証レイヤー(4.9)の対象にも含める）。**この統合は 4.6 + 4.9 の同一 wave 発行より前に済ませる**（skeptic の指摘を反証対象に含めるため。統合はメインコンテキストの作業で agent を要さない）。

**fallback（直列起動）**: reviewer の `[surface:high-risk]` フラグ由来で**ここで初めて** surface=true になった場合のみ（`--since` の回はフラグが delta の hunk を指すときだけ）、skeptic を 1 体 `model: opus`, `effort: max` で単独起動する（**findings / reviewer の推論は渡さない**のが独立性の核）。**この経路で起動した場合は回収した直後に `mark wave` を記録し、publish の `recall_skeptic.launch` を `"fallback"` にする**（相乗り経路では `mark wave` は Step 4 で記録済みなので不要。`launch` は `"rider"`。期待 wave 本数の skeptic 控除はこの自己申告だけで決まり、`wave_sizes` の位置からは推定しない / #216）。正規表現で事前に HIT していれば相乗り済みなのでこの経路は走らない。

**失敗時 / スキップ時**: skeptic の失敗は `missing_coverage` に追記して続行。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・effort/config/scope スキップのいずれでも Step 6 レポートに必ず出す**（silent skip で「守ったつもり」の偽の安心を防ぐ）。

**次は Step 4.6**（SKILL.md に戻り、その見出しを見る）
