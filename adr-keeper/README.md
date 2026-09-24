# adr-keeper

設計判断 (Architecture Decision Record, ADR) を **append-only** で蓄積するプラグイン。設計判断の **WHY** を残し、supersede 時の整合を機械的に担保する。

## 使い方

```
/adr                              # ADR 一覧（id 降順）
/adr list                         # 同上
/adr new <title>                  # 新規 ADR を作成（status は既定 accepted）
/adr supersede <old-id> <new-title>  # 新 ADR 作成 + 旧 ADR を superseded に更新
```

## 保存先・命名

- ディレクトリ: `.claude/adr/`（プロジェクトローカル・committed 前提）
- ファイル名: `YYYYMMDDhhmmss-kebab-case-title.md`（秒精度で衝突回避）
- タイムスタンプは Bash `date +%Y%m%d%H%M%S` で取得（擬似時刻を作らない）

## frontmatter 規約

```yaml
---
id: 20260529143012        # = ファイル名のタイムスタンプ
status: accepted          # proposed | accepted | superseded
phase: current            # current | target | superseded
last-validated: 2026-05-29
supersedes: []            # この ADR が置き換える ADR の id 配列
superseded-by: null       # この ADR を置き換えた ADR の id（superseded 時のみ）
append_only: true         # append-only 履歴文書として doc-freshness の stale 判定を免除
tags: []
---
```

`last-validated` / `phase` は doc-freshness と互換。`append_only: true` は ADR が append-only 履歴文書であることを示し、doc-freshness に stale 判定を免除させる（`phase: current` の閾値で作成直後から恒常 stale になるのを防ぐ）。

## 本文セクション（必須）

1. `# ADR-<id>: <title>`
2. `## ステータス`
3. `## コンテキスト / 背景`
4. `## 決定`
5. `## 影響 (Consequences)`（良い影響・悪い影響・トレードオフ）
6. `## 適用方法 (Enforcement)` ← **必須**。lint / test / hook で機械強制できないかを必ず検討して残す欄。死に文書化の予防が目的
7. `## 検討した代替案`
8. `## 関連`（関連 ADR / Issue / design doc / knowledge へのリンク・wikilink。design-doc から切り出された ADR は元 design doc へ相互リンクする）

## サブコマンド挙動

| サブコマンド | 挙動 |
|---|---|
| `list` | `.claude/adr/*.md` を Glob → frontmatter 解析 → id / title / status / phase / last-validated の表を id 降順で表示。0 件なら「ADR がまだありません」 |
| `new <title>` | kebab タイトル生成 → template の本文の節を会話文脈から埋める（埋められない節は完了報告に未記入として挙げる）→ Write の直前に timestamp 取得 → `.claude/adr/`（無ければ作成）に Write。status 既定 `accepted` |
| `supersede <old-id> <new-title>` | 新 ADR 作成（`supersedes: [<old-id>]`）+ 旧 ADR を Edit（`status` / `phase` / `superseded-by` / `last-validated`）+ 両方を Read で相互参照確認 |

## ADR の新規作成を検査する（adr-write-guard）

ADR をスキルを通さず直接 Write すると、id が `date` を通らず（手で丸めた時刻になる）、テンプレの節も落ちる。実測では既存 9 件中 4 件の id の秒が 00、3 件でテンプレの節（適用方法など）が落ちており、transcript で確認できた 3 件はどれもスキルを通さずに書かれていた。スキル本文はこの経路に届かないので、PreToolUse hook で次を検査し、外れていれば作成を止めて理由を返す:

- ファイル名が `<YYYYMMDDhhmmss>-<kebab-slug>.md` で、frontmatter の `id` と `# ADR-<id>` の id がその timestamp と一致する
- `id` が現在時刻の 5 分前から 1 分後までに入る（スキルは Write の直前に `date` を取る）
- テンプレの見出し（`# ADR-<id>: …` と 7 つの `##`）がすべてある

対象は `.claude/adr/` 直下への**新規作成**（Write と、old_string 空の Edit）だけ。次は見ない:

- 既存 ADR の上書き・Edit（supersede の旧 ADR 更新を含む）と、`README.md` / `index.md`
- Bash 経由の作成（heredoc・`cp`・`git checkout`）。過去の ADR を復元・移植するときはこちらを使う
- 丸めた時刻から 5 分以内に書かれた id（窓は丸めを全部は拾わない）
- jq が無い環境（検査せずに通し、SessionStart の check-deps が知らせる）

Bash ツールのシェルと hook のプロセスで TZ が違う（DST をまたぐ場合も）と、`date` を取り直しても時刻が合わない。止めるメッセージに hook 側の現在時刻を出すので、その値を id とファイル名に使えば通る。

## doc-freshness との住み分け

adr-keeper は ADR の **作成・命名・supersede 整合**のみ担当する。鮮度 lint（`last-validated` の stale 判定）は **doc-freshness** が `.claude/adr/` を走査して担う。両者は frontmatter（`last-validated` / `phase`）を共通化しているので連携できる。ADR は append-only 履歴文書なので、テンプレが付ける `append_only: true` により doc-freshness の stale 判定は免除される（frontmatter スキーマ・link 検証は通常どおり）。

| 担当 | adr-keeper | doc-freshness |
|---|---|---|
| ADR 作成 / 命名 | ✅ | - |
| supersede 整合 | ✅ | - |
| 鮮度 lint（stale 判定） | - | ✅ |

## install

```bash
# マーケットプレイスから
claude plugin install adr-keeper@yuuki1036-claude-plugins

# ローカルから
claude plugin install /path/to/claude-plugins/adr-keeper
```

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/adr` | ADR の list / new / supersede |
| スキル | `adr` | 作成・命名・supersede 整合のロジック |
| hook (PreToolUse) | `adr-write-guard.sh` | `.claude/adr/` への新規作成を検査し、スキルの手順から外れていれば止める |
| hook (SessionStart) | `check-deps.sh` | jq が無いとき（上の検査が素通しになる）だけ知らせる |
