# 剪定ヒューリスティクス: モデル世代ごとの制約棚卸し

CC Catch-Up の **Phase P（剪定モード）** が使用する判定基準。

> **コンセプト**: Anthropic のハーネス設計論では「ハーネス = モデルへの仮定のエンコーディング」。
> モデル世代が進むと、かつて必要だった制約が不要化しノイズ（context 浪費・誤発火）になる。
> 定期的に「今でも必要か？」を棚卸しし、不要になった制約は削る。

---

## トリガー条件

以下のいずれかで Phase P を起動する:

1. **モデル世代アップデート検知**: state file の `lastCatchUpModel` と現在のモデルファミリが異なる
   - 例: `claude-opus-4-8` → `claude-opus-5`、`claude-sonnet-4-6` → `claude-sonnet-5`
2. **ユーザー明示**: Phase 0 の AskUserQuestion で「剪定モード」を選択
3. **定期実行**: 前回剪定から 90 日以上経過（state file の `lastPruningDate`）

---

## 剪定候補カテゴリ

各プラグインの hooks / skills / CLAUDE.md / rules を走査し、以下カテゴリに分類する。

### C-1: Model-Behavior Guards（モデル挙動ガード）

**定義**: 旧モデルが苦手だった挙動を補正するための制約。新モデルで自然解決される可能性が高い。

| サブカテゴリ | 旧モデル課題 | 新世代で改善されうる理由 |
|-------------|-------------|------------------------|
| ツール選択ガード | `grep/find/cat` を Bash で呼ぶ傾向 | 最新モデルは dedicated tool を優先 |
| 並列化リマインダ | 独立呼び出しを直列化する傾向 | Opus 4.7 以降は並列 tool call を積極採用 |
| コメント抑制 | 過剰コメント生成 | 4.7 世代以降は「コメント書きすぎない」が default |
| TaskCreate 促進 | タスク分割を怠る傾向 | 新モデルは自発的に TodoWrite/TaskCreate |
| effort=max 一律設定 | 4.6 以前は max で頭打ち | 4.7 以降は xhigh が推奨、max は overthinking |
| 自己検証の促進（Opus 5〜） | 「最後にダブルチェックせよ」で検証漏れを補正 | Opus 5 は自己検証が既定挙動。指示を残すと over-verification でコスト増 |
| subagent 委譲の促進（Opus 5〜） | 「積極的に委譲せよ」で委譲不足（4.8 世代）を補正 | Opus 5 は委譲過剰側に反転。促進文は削り、体数上限の明示に置き換える |

**方向が反転した制約に注意（Opus 5〜）**: 「冗長出力抑制」（簡潔指示）は 4.7 世代では剪定候補だったが、**Opus 5 は既定の応答・成果物が長め**のため簡潔指示はむしろ有効に戻った。剪定は一方通行ではなく世代ごとに方向を再判定する。実行経路は下記「復活判定（prunedConstraints の再走査）」（Phase P.1 の走査対象に含まれ、レポート・対話フローに復活候補として流れる）。

**判定シグナル**:
- hook/skill/CLAUDE.md 本文に「〜するな」「必ず〜」系の短い行動規則がある
- 制約の根拠が「モデルが間違えるから」である（モデル独立のドメインルールではない）

### C-2: Redundant-with-Harness（ハーネスと重複）

**定義**: Claude Code 本体が後から提供した機能によって、プラグイン側の実装が重複している。

| 例 | 旧実装 | ハーネス側の現行機能 |
|----|-------|--------------------|
| ツール名マッチ | スクリプト内で `$CLAUDE_TOOL_USE_TOOL_NAME` チェック | hooks の `if: "Bash(...)"` 条件 |
| 依存チェック重複実行 | 毎ターン実行 | `once: true` |
| Stop フックの同期実行 | ブロッキング | `async: true` |
| ファイル変更ポーリング | SessionStart 毎回差分確認 | `FileChanged` event |
| 永続化の DIY | `~/.claude/projects/.../memory` 直接書き込み | `${CLAUDE_PLUGIN_DATA}` |

**判定シグナル**:
- スクリプトの冒頭で条件分岐の多くを占めている処理が `if` / `once` / `async` で済む
- 機能そのものが v2.1.x 以降の組み込みに重複

### C-3: Obsolete-by-Builtin（組み込みスキル/コマンドに置換可能）

**定義**: 以前はカスタムで書いていたが、組み込みスキル/コマンドで代替可能になったもの。

| 例 | 置換先 |
|----|-------|
| 自前の review スキル | 組み込み `/review` or ultrareview |
| 自前の permission 管理 | `less-permission-prompts-builtin` |
| 自前の catch-up scrape | 組み込み changelog 取得（将来） |

**判定シグナル**: 組み込みコマンド/スキルがプラグインの core 機能と重複

### C-4: Dead-Legacy（世代交代で意味を失ったもの）

**定義**: 過去の非推奨 API・旧 effort レベル・削除されたフックを参照している。

| 例 | 対応 |
|----|-----|
| `effort: max` を全スキルに一律設定 | `xhigh` / `high` へ降格（P-11 参照） |
| 旧 hook event 名 | 新 event 名へ差し替え |
| retired model ID のハードコード | 最新モデル ID へ置換 |

### C-5: Over-Specified-Workflow（過剰に細かいワークフロー記述）

**定義**: SKILL.md や rules で「ステップ 1, 2, 3, ...」と手順を過剰に規定しており、新モデルなら文脈判断できる粒度。

**判定シグナル**:
- 10 ステップ超の線形手順
- 「〜の前に必ず〜せよ」系の機械的連鎖（hook 化が望ましい決定的検証は除く）

---

## 復活判定（prunedConstraints の再走査）

剪定候補スキャン（現存ファイルの走査）とは**別に**、state file の `prunedConstraints` を読み、各項目を現世代の C-1 表で再判定する。剪定済み制約はファイルから消えているため現存ファイル走査ではヒットせず、この再走査が無いと剪定は一方通行になる。

- 判定: 剪定当時の `reason` が現世代でも成立するか？ **方向が反転していれば【復活候補】**（例: 「冗長出力抑制」は 4.7 世代で剪定 → Opus 5 で応答が長めに戻ったため復活候補）
- 復活候補はレポートの「復活候補（方向反転）」節に列挙し、対話フローで「復活する」を提示する
- 復活が承認されたら該当行を戻し、`prunedConstraints` から削除する（既存の「剪定された制約が復活する場合」の後始末規定に接続）

## 剪定判定フロー

各候補について以下を順に判定:

```
候補を特定
  │
  ▼
① 決定的検証として残す価値があるか？（ハーネス遵守率 100% vs CLAUDE.md ~80%）
  ├─ YES → 【保留】Hook 化 or そのまま残す
  └─ NO  ↓
  ▼
② 新モデルで自然に守られるか？（releases / model card / 実挙動から判断）
  ├─ YES → 【剪定候補】
  └─ NO  ↓
  ▼
③ モデル非依存のドメインルール？（プロジェクト固有命名・セキュリティ要件など）
  ├─ YES → 【保持】
  └─ NO  → 【剪定候補】
```

**重要**: 「剪定候補」になっても自動削除しない。必ずユーザーに AskUserQuestion で確認する。

---

## レポート形式（Phase P 出力）

```markdown
## 剪定レビュー レポート
**モデル世代**: {from-model} → {to-model}
**前回剪定**: {date}
**候補数**: {n} 件

### 剪定候補（優先度順）

#### 1. [High] {plugin-name}/{component}: {制約タイトル}
- **カテゴリ**: C-1 Model-Behavior Guards
- **現状**: （該当箇所の引用 3-5 行）
- **剪定理由**: {新モデルで自然解決される根拠・リリースノート引用}
- **リスク**: {削った場合に起きうる退行 / 低・中・高}
- **推奨アクション**: 削除 / hook 化 / 縮小
- **ファイル**: {path}:{line}

#### 2. [Medium] ...

### 復活候補（方向反転）
{prunedConstraints の再走査で方向反転を検出した場合のみ。0 件なら省略}
- {plugin}/{component}: {制約タイトル}
  - 剪定時の理由: {prunedConstraints の reason}
  - 復活理由: {現世代で方向が反転した根拠}

### 保持推奨（参考）
- {plugin}/{component}: {理由}
```

---

## 対話フロー（AskUserQuestion）

1. レポート提示後、候補ごとに以下を提示:
   ```
   Q: {plugin}/{component} の {制約} を剪定しますか？
   - 削除する（推奨）
   - hook 化する（決定的検証に格上げ）
   - 保留（今回は触らない）
   - 保持する（将来も剪定対象外としてマーク）
   ```
   復活候補（方向反転）には別の 3 択を提示する:
   ```
   Q: 剪定済みの {制約} は現世代で方向が反転しています。復活させますか？
   - 復活する（該当行を戻し prunedConstraints から削除）
   - 保留（今回は触らない。次回も候補化）
   - 破棄（復活不要として prunedConstraints に at を更新して残す）
   ```
2. multi-select ではなく **1 件ずつ** 確認（誤爆防止）
3. 候補が 10 件超の場合は優先度 High のみ個別確認、Medium/Low は「全件まとめて削除 / 全件保留」の 2 択
4. 「保持」を選んだものは state file の `preservedConstraints` に記録し、以降の剪定候補から除外

---

## state file 拡張

剪定モードは state file（`${CLAUDE_PROJECT_DIR:-$HOME}/.claude/claude-meta/cc-catch-up-state.json`）の以下のフィールドを使用/更新する:

```json
{
  "lastCatchUpVersion": "2.1.114",
  "lastCatchUpModel": "claude-opus-5",
  "lastCatchUpDate": "2026-04-22",
  "lastPruningDate": "2026-04-22",
  "appliedFeatures": [...],
  "skippedFeatures": [...],
  "prunedConstraints": [
    {
      "id": "dev-workflow/rules/no-grep-bash",
      "category": "C-1",
      "reason": "Opus 5 は dedicated tool を優先",
      "at": "2026-04-22"
    }
  ],
  "preservedConstraints": [
    {
      "id": "issue-workflow/SKILL.md/scope-size-warning",
      "reason": "プロジェクト固有のドメインルール",
      "at": "2026-04-22"
    }
  ]
}
```

---

## 注意事項

- **モデルがまだ学習途上のサーフェスは剪定しない**: 新機能/新 API は挙動が安定するまで保守的に保持
- **剪定後は必ず `/quality-check` と eval-runner を実行**: 退行検知
- **ロールバック容易性**: git 管理下なので commit 単位で巻き戻せる。剪定 commit は 1 件 1 ファイルに分けると安全
- **剪定された制約が復活する場合**: state file の `prunedConstraints` から削除し、再度提案対象に戻す
