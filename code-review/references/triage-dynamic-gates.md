# 動的ラウンドの起動ゲート（triage-guide 分冊）

**このファイルは、対応するフェーズの起動可否を判断する段になってから Read する。** Phase 0 のエージェント構成決定（Stage 0〜2）には不要 — そちらは `triage-guide.md` だけで完結する。実行手順は `orchestration-dynamic-rounds.md`。

| 節 | 内容 | フェーズ |
|---|---|---|
| `## 8` | 動的ラウンド（Round 2 / meta-reviewer）の起動条件・effort 適応・unmet の repo 内外分類 | 5.5 / 5.6（4.5 / 4.6） |
| `## 8.5` | 冷や読み skeptic ラウンド（surface 判定・起動ゲート・high 昇格の判断基準） | 5.8（4.8） |
| `## 9` | 反証レイヤー（対象指摘の選定・バッチ化・effort 適応） | 5.9（4.9） |

**surface 判定は Phase 0 で必要になるが、`scripts/triage-signals.sh` の `## surface` セクションが正規表現部分を機械適用済み**なので、Phase 0 の時点で本ファイルを読む必要はない（`## 8.5` は判定の定義と偽陰性の保険の正本）。

## 8. 動的ラウンド（Phase 5.5 / 5.6 / v2.12.0 追加）

### Phase 5.5: Adaptive deepening (Round 2 / unmet_information 起点)

**起動条件**: 全 reviewer 完了後、reviewer の出力に `unmet_information` フィールドが 1 件以上あり、**かつ target の少なくとも 1 件が repo 内で到達可能**な場合に起動

**目的**: reviewer が「この観点を確定するには追加の context が必要」と自覚した領域を 1 round だけ深掘りする適応的再評価

**到達不能 target による全件スキップ（GitHub issue #100 C）**: unmet の target が**全件到達不能**なら、追加探索は構造的に空振りするため wave を 1 本まるごと省く。target の分類は文字列を読めば決まるのでメインコンテキストで判定でき、agent を要さない。

**分類は 3 つある（v2.60.0 で「repo 内 / repo 外」の二分から分離）**:

| 分類 | 例 | Round 2 |
|---|---|---|
| **repo 内**（到達可能） | ソース・型定義・設定・マイグレーション・doc・コミット履歴など、Read / Grep / Glob / git で届くもの | 起動する |
| **セッション到達可能**（repo 外だが届く） | **そのサービスの MCP / CLI がこのセッションで利用可能**な外部状態 — API のレスポンス形状・スキーマ・フィールドの実値、issue tracker の実データ、`gh` で取れる GitHub 上の状態 | **メインで直接照会して解決**（下記） |
| **到達不能** | DB / 本番環境の実データ、**利用可能なツールが無い**外部サービスの実挙動（デザインツール・実機描画・ブラウザ実測）、このリポジトリに存在しないコード（他リポジトリ・削除済みの旧実装）、意図的にスキップした実行結果（lint / テスト / ビルドの実走） | スキップ対象 |

- **「repo 外」を「到達不能」と同一視しないこと**（v2.60.0 で追加した区別）。reviewer は `isolation: "worktree"` の子 agent で外部サービスの認証情報を持たないことが多く、**repo 外の外部状態を一律「検証不能」として unmet に落とす**。ところがオーケストレーター側では同じ情報が MCP / CLI で 1〜数コールで取れる場合がある。二分のままだと**取れる情報を「構造的に空振り」と誤判定して wave ごと捨てる**
- **セッション到達可能な target は、Round 2 を起動する前にメインコンテキストで直接照会する**（read-only の照会に限る）。これは Round 2 の代替であって追加ではない: wave を 1 本使わず、agent への受け渡しロスも無く、`duration_fleet_min` を増やさない。解決したら該当指摘の confidence / severity を再評価し、レポートの「動的ラウンド」行に `スキップ（unmet をメインで直接照会して解決）` と出す
  - **実測（v2.60.0 の根拠）**: doc レビューで reviewer 3 体が揃って「Linear MCP 未認証のため検証不能」と unmet に落とした 3 件を、オーケストレーターが 7 コールで確定させた。結果は **MAJOR 1 件の CRITICAL 昇格**（doc の主張が実 API のレスポンス形状と矛盾していた）と **偽陽性 1 件の除去**（懸念した状態名の不一致が実際には存在しなかった）。旧分類では「外部サービスの実挙動」＝全件 repo 外で Round 2 が丸ごとスキップされ、どちらも取り逃していた
  - **書込・破壊的操作は照会に含めない。** 読み取り専用で答えが出るものだけを対象にする
- **1 件でも repo 内 / セッション到達可能があれば、スキップしない** — 実測では unmet 8 件中 7 件が到達不能だったが、残り 1 件（DB 制約）を Round 2 が repo 内 doc で解決した結果、指摘 1 件の severity が MAJOR → MINOR に変わった。判定に迷う target は到達可能側に倒す
- スキップした場合は `missing_coverage` に「Round 2 スキップ: unmet 全件が到達不能（<target 要旨>）」として記録し、レポートの「動的ラウンド」行にも理由を出す（silent に落とさない）

**動作（effort で経路が分かれる。実行手順の正本は orchestration-dynamic-rounds.md `## 6`）**:
- **high（既定）— 1 段圧縮**: 追加 explorer は起動しない。unmet を申告した reviewer のみ再起動し、**unmet ターゲットを自力探索（Read / Grep / Glob）してから初回 confidence を再評価**させる。直列 wave を 2 → 1 に減らし、sonnet 経由の要約受け渡しも省く（的の絞れた追加探索は opus 自身が掘る方が受け渡しロスがない）
- **xhigh / max — 2 段**: `re-explore` フォーカス（explorer-prompts.md 参照）の追加 explorer → 該当 reviewer 再起動。探索を広めに撒く価値がある明示 escalation 時のみ 2 段を使う
- いずれの経路も他の reviewer は再実行しない（コスト抑制）。結果は初回 reviewer 結果と統合（重複指摘は dedup）

**上限**: 1 round のみ（多段化禁止）。再起動 reviewer 上限 3 体（xhigh/max の追加 explorer も上限 3 体）

### Phase 5.6: Meta-reviewer round

**起動条件**: Phase 5.5 完了後、フィルタリング前の指摘に **BLOCKER または CRITICAL** が 1 件以上あり、**かつ `size_tier` が `small` でない（`small` の場合は BLOCKER が 1 件以上ある）**場合に起動（帯連動は v2.60.0 で追加 / `gate_schema: 2`）

**目的**: 高 severity 指摘が出た = 高リスク変更と判定し、別 reviewer に「ここまでの結果を踏まえて、他の reviewer が見落としている観点はないか」を問うメタレビュー

**動作**:
1. meta-reviewer agent (`prompts/meta-reviewer.md`) を 1 体起動
2. 入力: 全 reviewer の指摘リスト（フィルタ前）、diff、explorer 結果
3. 出力: 追加指摘（あれば。なくても OK）
4. meta-reviewer の指摘も通常のスコアリング・フィルタリング対象に含める

**上限**: 1 round のみ。meta-reviewer 1 体のみ

### effort 適応

| effort | Phase 5.5 (adaptive deepening) | Phase 5.6 (meta-reviewer) |
|---|---|---|
| low | スキップ | スキップ |
| medium | スキップ | スキップ |
| high (default) | unmet_information があれば起動（1 段圧縮） | スキップ |
| xhigh | 起動（2 段。**規模キャップが effort 上限を下回る帯は 1 段圧縮**） | 起動（**`small` 帯は BLOCKER 有りのみ**） |
| max | 起動（2 段。**規模キャップが effort 上限を下回る帯は 1 段圧縮**） | 起動（**`small` 帯は BLOCKER 有りのみ**） |

**「起動するか否か」が規模帯に連動するのは Phase 5.6 だけ（v2.60.0）**。5.8 / 5.9 は帯に連動せず、**Phase 5.5 は起動可否こそ帯非連動だが段数は従来から帯連動する**（規模キャップが effort 上限を下回る帯では追加 explorer なしの 1 段圧縮経路 — triage-guide.md `## 6.3` / 同 `## 5.1` の wave 表）。5.6 のスキップは triage-guide.md `## 6.3` の「規模キャップが削るのは breadth だけ」という原則に対する**唯一の例外**（＝ depth 層を帯で止める唯一の例）で、根拠が n=1 と弱いため**ロールバック条件つきの暫定措置**として入れてある（`design-notes/triage-rationale.md`）。他の depth 層（5.8 / 5.9）へ同じ帯連動を横展開しないこと。

### userConfig による無効化

- `enable_adaptive_rounds: false` → Phase 5.5 を強制スキップ
- `enable_meta_reviewer: false` → Phase 5.6 を強制スキップ

両方デフォルト true。トークンコスト・レイテンシが気になる場合は false にする。

## 8.5. 冷や読み skeptic ラウンド（Phase 5.8 / 4.8 / recall 補強）

high-risk surface を含む変更に限り、事前所見と無関係に **findings 非注入の独立 skeptic を 1 体**起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで破る recall 補強フェーズ。反証レイヤー（false-positive 潰し）の鏡像＝ false-negative hunter。meta-reviewer（Phase 5.6）が findings 注入で非独立なため fleet 共通盲点を引きずるのに対し、skeptic は独立読み直しで盲点を破る。

### 起動タイミング: reviewer wave に相乗り（v2.41.0）

**skeptic は reviewer と同一メッセージで一括発行する**（review Step 5 / self-review Step 4 の reviewer 一括発行に相乗り）。結果の統合・dedup だけを従来位置（review=Phase 5.8 / self-review=Phase 4.8）で行う。

根拠: **findings 非注入がこのレイヤーの設計の核**であり、skeptic は reviewer の出力に一切依存しない。にもかかわらず reviewer の後に直列配置されていたため、依存関係が無いのに 1 wave 分の実時間（opus 1 体の全所要）を積み増していた。同時発火なら壁時計への追加はゼロ（wave 内最長が伸びない限り）。

**例外（fallback / 従来どおり直列）**: surface 判定が **reviewer の `[surface:high-risk]` フラグ由来**で事後に true になった場合のみ、reviewer 完了後の 5.8 位置で単独起動する。この経路だけは reviewer 出力に依存するため同時発火できない（正規表現・PR 自己申告で事前に HIT していれば相乗り済みなので、fallback が走るのは正規表現が取り逃した ORM 抽象越えのケースに限られる）。

### high-risk surface 判定

以下のいずれかを含む変更を high-risk surface とみなす（事前所見・severity と無関係に判定）:

1. **DB 書込**: `INSERT` / `UPDATE` / `DELETE` を含む生 SQL、または ORM の書込 API（`.create(` / `.update(` / `.save(` / `.insert(` / `.upsert(` 等）。performance 観点の起動条件（triage-guide.md `## 3` の `INSERT|UPDATE` 正規表現）を surface 判定に転用する
2. **金銭・数量計算**: `amount` / `price` / `balance` / `quantity` / `stock` / 通貨・丸め・課金に関わる numeric 演算
3. **認可・認証**: 権限チェック / セッション / トークン / ロール判定に関わる変更
4. **PR 自己申告 D1-High**: PR 本文・ラベルで著者が「高リスク」「D1-High」「要注意」と申告した変更（`prompts/pr-context-rules.md` の D1-High 検出で拾う。review skill のみ）

**偽陰性の保険**: 正規表現は ORM 抽象の深い経由（動的メソッド・ラッパー越しの書込）を取り逃しうる。reviewer はコード読解で high-risk surface に触れると判断したら `[surface:high-risk]` を申告する（`prompts/reviewer-common.md` の「high-risk surface フラグ」で全 reviewer に指示。PR 自己申告 `prompts/pr-context-rules.md` とは独立経路）。オーケストレーターは **正規表現ヒット ∨ reviewer フラグ ∨ PR 自己申告 D1-High で OR 判定**する。surface 偽陰性は recall 補強が丸ごと不発になるため、網羅は正規表現に依存しきらない。

### 起動ゲート（暴走ガード）

- **effort 適応**: **high 起点**で起動（v2.52.0 で xhigh/max 起点から昇格）。low / medium はスキップ。**meta-reviewer（`## 8`）は xhigh/max 起点のまま**で、skeptic だけ先に昇格している（skeptic は findings 非注入で reviewer wave に相乗りするため**直列 wave を増やさない**が、meta は reviewer 完了後に直列 wave を 1 本足すため。昇格の実測根拠: `design-notes/triage-rationale.md`）
  - **surface 判定は Phase 0 で先に行う**（相乗り発火の可否を reviewer 起動前に決めるため）。正規表現 + PR 自己申告 D1-High は Phase 0 で判定でき、effort ゲートを通過していれば reviewer 一括発行に skeptic を混ぜる
- **上限**: **PR あたり skeptic 1 体・1 round のみ**（per-surface 起動ではない）。skeptic の指摘も通常の scoring・報告マトリクス・反証レイヤーの対象
- **surface 非該当ならスキップ**: high-risk surface を含まない変更では起動しない（noise 爆発を避け high-risk に限定）
- **計測（skip 時も surface 判定は記録する）**: effort / userConfig / scope でスキップした場合も、正規表現部分の surface 判定（diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と独立に必ず実施し、`review:completed` payload の `recall_skeptic` に記録する（SKILL.md Step 7 / Step 6 の payload 規約参照）。加えて surface=true なら、`--embed` / event 発火の有無に依存しない **human レポート（Step 7 / Step 6 の「動的ラウンド」行）にも skeptic の起動有無（未起動時は skip_reason）を必ず出す**（headless 通常実行での silent skip を防ぐ・issue #85）

### 昇格後の監視とロールバック条件（v2.52.0 で high 起点に昇格済み）

**昇格の根拠は `design-notes/triage-rationale.md`**（需要 63% / 価値率 50%、n=8）。ここには昇格後に何を見るかだけを置く。

```bash
# ① 実装が効いているか: 昇格後は skip_reason="effort" が消えるはず。
#    消えなければ SKILL 側のスキップ条件が更新されていない信号。
#    **gate_schema >= 2 の絞り込みは必須**（GitHub issue #115）。昇格前のサンプルは
#    skip_reason="effort" を持ったまま永久に残るため、絞らないと常に「信号あり」を返し
#    本物の実装バグを検知できない。日付では切らない（配布ラグ）
grep '"event":"review:completed"' .claude/events.jsonl | \
  jq -s '[.[] | select(.payload.recall_skeptic.surface == true
           and (.payload.recall_skeptic.gate_schema // 1) >= 2)] |
    group_by(.payload.recall_skeptic.skip_reason // "fired") |
    map({reason: .[0].payload.recall_skeptic.skip_reason // "fired", n: length})'

# ② 価値率が維持されているか（縮小・撤去の判断材料）
#    attribution_schema >= 2 で絞るのは必須（schema 1 は findings_added が壊れている）
grep '"event":"review:completed"' .claude/events.jsonl | \
  jq -s '[.[] | select(.payload.recall_skeptic.fired == true and (.payload.recall_skeptic.attribution_schema // 1) >= 2)] |
    if length == 0 then "no data"
    else {n: length, valuable: ([.[] | select(.payload.recall_skeptic.findings_added > 0)] | length)} end'
```

**ロールバック条件**: 昇格後のサンプル（`fired=true` かつ `attribution_schema >= 2`）が **15 件以上貯まった時点で価値率が 25% を下回っていたら**、high を「スキップ」に戻す。昇格判断が n=8 の 50% だったので、**n を倍にしても半分を切る**なら昇格根拠が崩れたとみなす。

- **昇格直後の数件で判断しない**（`findings_added=0` が 2〜3 件続くのは 50% の分布内）
- **`findings_overlap` を価値率の分子に混ぜない**（reviewer と重複した指摘は「盲点でなかった事例」なので、混ぜると価値率が 100% に張り付いて縮小分岐が原理的に発火しなくなる）
- 戻すのは effort 適応行の 1 行だけ。ユーザー側は `enable_recall_skeptic: false` で個別に止められる

**⚠️ `attribution_schema` が無い（＝ schema 1 相当）サンプルの `findings_added` は判断に使えない**: code-review 2.35.1 より前は由来タグ `[recall-skeptic]` がレポート書式に規定されておらず、dedup 時のタグ生存も未規定だったため、publish 時点で由来を再構成できず `findings_added` が記憶依存で系統的に 0 へ潰れていた。**日付では切らないこと** — マーケットプレイス配布のため、未更新マシンは修正日以降も schema 1 の payload を publish し続ける。publish 側が自己申告する版マーカーだけが配布ラグに耐える。壊れた計測を根拠に不可逆な撤去をしない。

### model / 作法（反証レイヤーと対称）

| 項目 | 冷や読み skeptic | 反証レイヤー（既存） |
|---|---|---|
| 係 | false-negative を足す | false-positive を潰す |
| findings 注入 | **非注入（独立）** | 主張のみ |
| focus 分割 | 無し（generalist 一頭） | 指摘単位 |
| 契約注入 | 薄め（冷や読み） | 通常 |
| model | **opus**（独立検証は強モデル: ルーティング表） | opus |
| 起動ゲート | high-risk surface（事前所見・severe 非依存） | 非対称ゾーン |

skeptic テンプレートは `prompts/recall-skeptic.md`。findings / reviewer 推論は渡さず、diff と最小 focus のみ渡す。#1（層跨ぎ値フロー）を独立でも捕捉できるよう、敵対的入力逆算の核（受理入力の端点を末端の永続層制約まで前進させる）をテンプレートに内挿し、独立性に「破り方」を持たせる。

### userConfig / 失敗時

- **userConfig**: `enable_recall_skeptic: false` で強制スキップ（既定 true）。計測前の暴走はこの config と effort での明示スキップで即時停止できる
- **失敗時**: skeptic が失敗 / タイムアウトした場合は `missing_coverage` に `recall-skeptic: <failure reason>` を追記して best-effort 続行する。**起動条件（high-risk surface）を満たしたのに未実行だった事実はレポートに必ず出す**（silent 失敗で「守ったつもり」の偽の安心を防ぐ）

## 9. 反証レイヤー（Phase 5.9 / 4.9 / 動的）

reviewer の指摘を独立エージェントが反証し、過大な指摘の prominence を下げるフェーズ。**冷や読み skeptic の後・scoring の前**に挿入する（review=Phase 5.9 / self-review=Phase 4.9）。meta-reviewer / skeptic が「見落とし（false negative）」を足す係なのに対し、本レイヤーは「独立読み直しで**severity を較正し、偽陽性を摘出する**」鏡像の係。skeptic が足した指摘も本レイヤーの反証対象に含める。

> **実際の主機能は severity の較正であって偽陽性の除去ではない**（GitHub issue #114 / n=19・67 verdict）: `severity_inflated` **60%** / `confirmed` 34% / `refuted` **6%** / `uncertain` 0%。層の価値を否定するデータではない（実測 1 件では 9 件中 6 件を降格して報告を 1 件に絞れている）が、**「偽陽性を潰す層」と読むと期待と実挙動がずれる**。過大 severity の上流対策は `prompts/reviewer-common.md`「severity を付ける前に: base 状態の確認」に置いた。

### 対象指摘の選定（非対称ゾーン優先 + specialist 除外）

「詰めると取り下がる」のは **不確実だが報告される非対称ゾーン**。そこを狙い撃ちして既定パスのコストを抑える。

| effort | 反証対象（報告マトリクス通過見込みの指摘のうち） | 反証体数 |
|---|---|---|
| low / medium | スキップ | 0 |
| high（既定） | 非対称ゾーンのみ: BLOCKER 60-94 / CRITICAL 80-94 | `ceil(対象件数 / 5)` 体・上限 3 体 |
| xhigh / max | 上記 + BLOCKER/CRITICAL 95+ + MAJOR | 同上 |

**バッチ化（v2.41.0）**: 反証は **1 体あたり最大 5 件**をまとめて渡す（旧: 指摘ごと 1 体）。反証に必要な独立性は「指摘を出した reviewer と別コンテキスト」であって「指摘同士が別コンテキスト」ではないため、同一 diff の読み直しを N 体で重複させる意味がない。反証は**かつて指摘数に比例する唯一の変動費**（triage-guide.md `## 7` の体数表で reviewer / specialist は上限が効くのに対し、旧構成の反証だけは指摘が増えるほど体数が増えた）であり、既定パスのコストの主要項だった。**本節のバッチ化で上限 3 体・15 件に頭打ちになり、他層と同じく上限で止まる**。バッチ内の相互汚染（1 件の verdict を別件の根拠にする）は `prompts/adversarial-verify.md` の鉄則で禁止する。

**対象が 15 件（3 体 × 5 件）を超えた場合**: severity → confidence の順で優先度を付け、上位 15 件のみ反証する。溢れた指摘は verdict なし（＝反証スキップ）として元の confidence / severity のまま続行し、**レポートの反証行に予算超過件数を明記する**（silent に落とさない）。レポート行の書式の正本は orchestration-dynamic-rounds.md `## 10` 手順 4。

**縮小のロールバック条件（v2.41.0 のバッチ化 + effort 引き下げ）— 判定済み・維持（v2.57.0 / GitHub issue #119）**

サンプルが貯まったため判定した。**`effort: high` とバッチサイズ 5 を維持する**（n=19 / 計 67 verdict）:

| 監視項目 | 実測 | 判定 |
|---|---|---|
| **`uncertain` 比率**（= 根拠を出せず判定できなかった割合） | **0 件 / 0%** | effort を `max` に戻す根拠なし |
| **`refuted` 比率** | 4 件 / **6%** | バッチサイズを 5 → 3 に下げる根拠なし |

`uncertain` が 0 なのは「反証エージェントが判定を避けている」のではなく**判定できている**と読んでよい（`prompts/adversarial-verify.md` は根拠を出せない場合に `uncertain` を選ぶよう指示しており、実測 1 件では 9 件すべてに `file:line` 付きの根拠が返っていた）。→ 実測の詳細と `severity_inflated` 60% の扱い: `design-notes/scoring-rationale.md`

- **再監視の条件**: 反証プロンプト・ゲート・バッチサイズを変更したときは、`uncertain` が 0 のままかを再確認する（この判定は現行の 3 つの組み合わせに対するもの）
- **`orchestration-guide.md ## 5` の注記（不変条件を緩めるときは反証 effort を `max` に戻すか同時に判断する）は本判定で閉じない。** あちらは verdict 分布とは独立の条件で、scoring-guide の「高 severity 非削除」不変条件に依存している

**除外（全 effort 共通）**:

- **specialist 由来（specialist-injection / -secret-handling / -destructive-op / -input-validation / -guardrail-bypass）の指摘は反証対象外**。これらは「断定できなくても BLOCKER + 低 confidence で人間判断を促す」前提（`prompts/specialist/<key>.md`）であり、誤反証で人間の警戒度を下げる代償が非対称に大きい
- 95+ の高確証指摘は high では対象外（取り下がりにくい層）

**high-risk surface 例外ゲート（surface-aware 閾値との吸収整合 / F4）**:

surface-aware 報告閾値（scoring-guide.md `## 報告マトリクス`）が high-risk surface に限り CRITICAL 80→70 / MAJOR 95→85 に緩めることで**新規に報告化する CRITICAL 70-79 / MAJOR 85-94 帯**は、上表の high ゲート（BLOCKER 60-94 / CRITICAL 80-94）の対象外に落ちる。これを放置すると「recall で緩めた指摘が反証の二段構えを素通りする」ため、**high-risk surface の指摘に限り high でもこの帯を反証対象に含める**（CRITICAL 70-79 / MAJOR 85-94 を high の非対称ゾーンに追加）。surface 非該当の変更では従来ゲートのまま（noise を増やさない）。緩めた recall を反証レイヤーが independently 吸収する二段構えを high でも成立させる。

### 動作

1. 上表のゲートで対象指摘を選ぶ
2. 対象指摘を 5 件ずつのバッチに分け、バッチごとに反証エージェント（`prompts/adversarial-verify.md`）を `model: opus`, `effort: high` で起動。指摘の主張のみ渡し reviewer 推論は渡さない
   - **effort は v2.41.0 で `max` → `high`**。effort 方針の正本は orchestration-guide.md `## 5`（「下げるのは『全レビューで走る』または『指摘数に比例する』レイヤー、据え置くのは 1 体固定の検証レイヤー」）。反証は誤判定コストの非対称性を **verdict の扱い側**（高 severity は `refuted` でも `severity-inflated` でも消さず係争注記 = scoring-guide の不変条件）で吸収しているため、effort での二重の保険は要らない
3. `pre-existing` / `intended` の鮮度は LLM 前に `git show <base>:<file>` / `git blame` で機械判定
4. verdict を scoring（scoring-guide.md `## 反証レイヤーの verdict 反映`）に渡す。**高 severity は消さず注記**、MAJOR/MINOR のみ取り下げ可（理由は付録に記録）
5. 1 体が複数 verdict を返す（バッチ）。**全 finding_id 分の verdict が揃っているか突合し、欠落は verdict なし扱い**にする（欠落を confirmed とも refuted とも解釈しない）

### effort 適応（5.5/5.6 とは別ゲート）

| effort | 反証レイヤー |
|---|---|
| low / medium | スキップ |
| high (default) | 非対称ゾーンのみ起動 |
| xhigh / max | 報告ゾーン全体 + MAJOR まで起動 |

> adaptive(5.5) は high で起動・meta-reviewer(5.6) は xhigh+ のみ。反証レイヤーは「非対称ゾーンを high から狙う」独自ゲートで、5.6 とは起動条件が異なる。

**xhigh / max ゲートと非対称ゾーン論の緊張（据え置きの明示 / GitHub issue #100 補足）**: 本節冒頭は反証対象の設計思想を「詰めると取り下がるのは**不確実だが報告される非対称ゾーン**」と述べているが、xhigh / max のゲートは「報告ゾーン全体 + MAJOR」なので **confidence 95+ の MAJOR / BLOCKER / CRITICAL が全件対象**になる。これは**最も取り下がりにくい層に、直列 wave 1 本（triage-guide.md `## 5.1` の目安で 6〜16 min）を使う**ことを意味し、非対称ゾーン論からはみ出す。実測例: 52 分のレビューで最終的に残った反証対象が MAJOR 3 件（conf 95 / 99 / 100）だけという構成になった。

それでも据え置くのは、xhigh / max が**明示 escalation**（「小さな diff を深く読む」の意思表示）であり、この帯で偽陽性を 1 件通すコストが wave 1 本より大きいと判断しているため。ただし**この緊張とコストは記録しておく** — 壁時計を縮める必要が出たとき、xhigh の反証ゲートを「非対称ゾーン + BLOCKER/CRITICAL 95+」に狭める（MAJOR 95+ を外す）のが最初の候補になる。判断は `adversarial_verify` の `refuted` 内訳（95+ MAJOR の取り下げ実績）が貯まってから行う。

### userConfig による無効化

- `enable_adversarial_verify: false` → 反証レイヤーを強制スキップ（デフォルト true）。誤却下が多い・コストを抑えたい場合に false
