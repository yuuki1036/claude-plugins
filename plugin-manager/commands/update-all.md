---
description: 自作プラグインを最新版に一括アップデートする（--all で全プラグイン対象）
user_invocable: true
argument-hint: "[--all]"
allowed-tools:
  - Bash
---

インストール済みプラグインを一括更新してください。

引数 `$ARGUMENTS`:
- 引数なし（デフォルト）: **自作プラグインのみ**更新
- `--all`: インストール済みの全プラグインを更新

## 手順

### Phase 0: 更新対象スコープの判定

`claude plugin list` を実行する（この出力は Phase 1 / Phase 2 でも再利用する）。

1. 出力から plugin-manager 自身の識別子 `plugin-manager@<marketplace>` を探し、`@` 以降を **「自作マーケットプレイス名」** として記録する（このコマンドが属するマーケットプレイス = 自作の出所とみなす。特定の名前をハードコードしない）。
2. 引数 `$ARGUMENTS` を確認する:
   - `--all` を含む → インストール済みの全プラグインを対象（従来挙動）
   - 含まない（デフォルト）→ 自作マーケットプレイスに属するプラグインのみを対象
3. 以降の全 Phase は、ここで絞り込んだ **対象プラグイン** に対してのみ実行する。
4. 対象スコープを冒頭で一言報告する（例: `自作プラグイン（@yuuki1036-claude-plugins）7件を対象に更新します。全件対象にする場合は /update-all --all`）。

### Phase 1: マーケットプレイスキャッシュの最新化

Phase 0 で記録した対象プラグインの `name@marketplace` から、マーケットプレイス名（`@` 以降の部分）を抽出する。
重複を除いた各マーケットプレイスに対して以下を順番に実行する:

1. ローカルキャッシュを削除する（古いバージョンが残っていると install 時に反映されない）:

```bash
rm -rf ~/.claude/plugins/cache/<marketplace-name>
```

2. マーケットプレイスキャッシュをリモートから再取得する:

```bash
claude plugin marketplace update <marketplace-name>
```

### Phase 2: 対象プラグイン一覧とバージョンの記録

Phase 0 で実行した `claude plugin list` の出力を再利用し、Phase 0 で絞り込んだ **対象プラグイン** の以下の情報を記録する:

- `name@marketplace` 形式の識別子
- 現在のバージョン（Before バージョンとして保持する）

> `claude plugin list` の出力例:
> ```
> name@marketplace (v1.2.0)
>   Description: ...
>   Scope: user
> ```

### Phase 2.5: deprecated プラグインの自動移行（auto-migrate）

marketplace が後継プラグインを宣言している deprecated プラグインを検出し、更新の代わりに移行する。

1. **opt-out 確認**: `~/.claude/plugin-manager/config.json` の `auto_migrate` が `false` なら本 Phase をスキップし、検出結果だけ Phase 5 で「移行候補（auto_migrate=false のためスキップ）」として報告する（既定は有効）。
2. **検出**: Phase 1 で最新化した各マーケットプレイスの `~/.claude/plugins/marketplaces/<mp-name>/.claude-plugin/marketplace.json` を読み、Phase 2 の対象プラグインのうち **エントリに `_superseded_by` を持つもの**を抽出する:

```bash
jq -r '.plugins[] | select(._superseded_by) | "\(.name)	\(._superseded_by)"' "$MP_JSON"
```

3. **後継ごとにグループ化して移行を原子的に実行する**（同一後継を持つ deprecated 群は、後継の hook・トリガーと衝突するため「全部 uninstall → 後継を 1 回 install」の順序を厳守。片方だけ uninstall した中間状態で止めない）:
   1. グループ内の deprecated プラグインを全て uninstall する（Phase 3-1 と同じフォールバック chain を使う）
   2. 後継 `<successor>@<marketplace>` が未インストールなら install する（既にインストール済みなら uninstall のみで完了 = 併存状態の解消）
   3. **ロールバック**: 後継の install に失敗した場合、直前に uninstall した deprecated 群を元のバージョンで再 install し、エラーとして報告する（プラグインが 1 つも無い状態で放置しない）
4. 移行したプラグインは Phase 3 の更新対象から除外する。
5. 移行結果（deprecated 群 → 後継、uninstall/install の成否）を Phase 5 の報告に渡す。

> 例: linear-workflow / indie-workflow は `_superseded_by: "issue-workflow"` を宣言しており、どちらか（または両方）がインストール済みのマシンでは update-all 実行時に自動で issue-workflow へ移行される。

### Phase 3: 各プラグインの再インストール

CLI の競合を避けるため順次実行（並列不可）。
各プラグインに対して以下を実行する:

#### 3-1. アンインストール（フォールバック付き）

以下の順で試行し、いずれかが成功したら 3-2 に進む:

1. `claude plugin uninstall <name@marketplace>`
2. 失敗した場合: `claude plugin uninstall <name@marketplace> --scope user`
3. 失敗した場合: `claude plugin uninstall <name@marketplace> --scope project`
4. すべて失敗した場合: `~/.claude/plugins/installed_plugins.json` を読み込み、該当プラグインのエントリを JSON から削除して書き戻す（手動削除フォールバック）

#### 3-2. インストール

```bash
claude plugin install <name@marketplace>
```

- install が失敗した場合はエラーとして記録し、次のプラグインに進む

### Phase 4: 更新後バージョンの取得

`claude plugin list` を実行し、各プラグインの更新後バージョン（After）を取得する。

### Phase 4.5: 更新内容の取得

Phase 4 で「更新済み」と判定されたプラグイン（Before ≠ After）に対して、CHANGELOG.md から更新内容を抽出する。

1. キャッシュ内の CHANGELOG.md を読み込む:

```bash
cat ~/.claude/plugins/cache/<marketplace-name>/<plugin-name>/<After-version>/CHANGELOG.md
```

2. CHANGELOG.md から Before バージョンより新しいエントリを抽出する:
   - `## [<After-version>]` から `## [<Before-version>]` の直前までを取得
   - Before と After の間に複数バージョンがある場合は全て含める
   - `### Added` / `### Fixed` / `### Changed` 等のサブセクションをそのまま保持

3. CHANGELOG.md が存在しない場合や読み取りに失敗した場合は「CHANGELOG なし」として記録する

### Phase 4.7: 未インストールの自作プラグイン検出

自作マーケットプレイスに登録済みだが未インストールのプラグインを検出する（後から追加された自作プラグインの取りこぼし防止）。デフォルトスコープ・`--all` のどちらでも、検出対象は **Phase 0 で記録した自作マーケットプレイス** に限定する（他マーケットプレイスは対象外）。

1. Phase 0 で記録した自作マーケットプレイス名に対応する `marketplace.json` を特定し、登録済み全プラグインの `name@marketplace` 一覧を取得する。
2. インストール済み一覧（`installed_plugins.json` の keys）と突き合わせ、差分（＝登録済みだが未インストール）を抽出する。
3. SessionStart hook と挙動を揃えるため、`~/.claude/plugin-manager/config.json` の `ignore_plugins` / `ignore_marketplaces` を尊重して除外する（cooldown / install_ratio 閾値は update-all では適用しない＝明示実行なので毎回検出する）。
4. **`_superseded_by` を持つ（= deprecated な）未インストールプラグインは提案から除外する**（deprecated の新規 install を勧めない）。

```bash
MP_NAME="<Phase 0 で記録した自作マーケットプレイス名>"

# 真実の marketplace.json は marketplaces/ 配下（cache/ ではない）
MP_JSON=""
for f in ~/.claude/plugins/marketplaces/*/.claude-plugin/marketplace.json; do
  [ "$(jq -r '.name // empty' "$f" 2>/dev/null)" = "$MP_NAME" ] && MP_JSON="$f" && break
done

INSTALLED_FILE=~/.claude/plugins/installed_plugins.json
CONFIG_FILE=~/.claude/plugin-manager/config.json

if [ -n "$MP_JSON" ] && [ -f "$INSTALLED_FILE" ]; then
  ignore_plugins_json='[]'; ignore_marketplaces_json='[]'
  if [ -f "$CONFIG_FILE" ]; then
    ignore_plugins_json=$(jq -c '.ignore_plugins // []' "$CONFIG_FILE" 2>/dev/null || echo '[]')
    ignore_marketplaces_json=$(jq -c '.ignore_marketplaces // []' "$CONFIG_FILE" 2>/dev/null || echo '[]')
  fi
  if [ "$(jq -nr --argjson ig "$ignore_marketplaces_json" --arg p "$MP_NAME" '$ig|map(.==$p)|any')" != "true" ]; then
    registered=$(jq -r --arg mp "$MP_NAME" '.plugins[]? | select(._superseded_by | not) | .name // empty | "\(.)@\($mp)"' "$MP_JSON" 2>/dev/null | sort -u)
    installed=$(jq -r '.plugins // {} | keys[]' "$INSTALLED_FILE" 2>/dev/null | sort -u)
    comm -23 <(printf '%s\n' "$registered") <(printf '%s\n' "$installed") | while IFS= read -r p; do
      [ -z "$p" ] && continue
      [ "$(jq -nr --argjson ig "$ignore_plugins_json" --arg p "$p" '$ig|map(.==$p)|any')" = "true" ] && continue
      echo "$p"
    done
  fi
fi
```

4. 抽出結果（未インストールの `name@marketplace` 一覧）を Phase 5 の報告に渡す。`marketplace.json` が見つからない場合は検出をスキップする（警告のみ・更新処理は止めない）。

### Phase 5: 結果の報告

以下のフォーマットで報告する:

```
## プラグイン更新結果

| プラグイン | Before | After | 結果 |
|-----------|--------|-------|------|
| name@marketplace | 1.0.0 | 1.1.0 | 更新済み |
| name@marketplace | 1.0.0 | 1.0.0 | 変更なし |
| name@marketplace | 1.0.0 | - | エラー |

### 移行（deprecated → 後継）

- linear-workflow, indie-workflow → issue-workflow へ移行しました（uninstall → install）
- 反映には Claude Code の再起動が必要です

### 更新内容

#### name (1.0.0 → 1.1.0)
- Added: 新機能の説明
- Fixed: バグ修正の説明

### 未インストールの自作プラグイン

自作マーケットプレイスに登録済みだが未インストールのプラグインがあります（`update-all` は更新専用のため自動導入はしません）:

- name@marketplace
- name@marketplace

導入する場合:

    claude plugin install <name>@<marketplace>

抑止: ~/.claude/plugin-manager/config.json の ignore_plugins / ignore_marketplaces

反映にはClaude Codeの再起動が必要です。
```

結果の判定ルール:
- Before と After のバージョンが異なる → **更新済み**
- Before と After のバージョンが同じ → **変更なし**
- install に失敗した → **エラー**（After は `-` と表示）

「移行」セクションは Phase 2.5 で移行（または移行候補の検出）が 1 件以上ある場合のみ表示する。
「更新内容」セクションは更新済みプラグインが1つ以上ある場合のみ表示する。
全プラグインが「変更なし」の場合はこのセクションを省略する。

「未インストールの自作プラグイン」セクションは Phase 4.7 で検出が1件以上ある場合のみ表示する。0件の場合は省略する（更新のみが成果物）。
