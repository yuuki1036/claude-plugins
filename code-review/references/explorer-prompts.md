# Explorer プロンプト索引

explorer のプロンプト本体は `references/prompts/` 配下に置く。**オーケストレーターは Read しない**（理由は reviewer-prompts.md 冒頭・orchestration-guide.md `## 3.5` と同じ）。

explorer は事実収集に特化し、問題の判定（バグかどうか等）は行わない。結果は reviewer に渡される。

## 索引

| 節 | ファイル | 用途 |
|---|---|---|
| 共通指示 | `${CLAUDE_PLUGIN_ROOT}/references/prompts/explorer-common.md` | 全 explorer 共通。**最初に Read する** |
| Focus | `${CLAUDE_PLUGIN_ROOT}/references/prompts/explorer/<focus>.md` | `function-flow` / `value-flow-trace` / `dependency-trace` / `branch-impact` / `history-context` / `shared-module-impact` / `re-explore` |

focus キーの語彙は triage-guide.md `## 3`「explorer の必要性判定」と reviewer の `unmet_information.focus` に一致する。

## プロンプトの組み立て方（オーケストレーター向け）

```
あなたは explorer-<focus> です。まず次の 2 ファイルを Read し、その指示に従って探索してください。
1. ${CLAUDE_PLUGIN_ROOT}/references/prompts/explorer-common.md
2. ${CLAUDE_PLUGIN_ROOT}/references/prompts/explorer/<focus>.md

<可変部: プラグインの実パス（{{PLUGIN_ROOT}} の読み替え先） / PR 番号 / 期待 HEAD SHA / メインルート（{{MAIN_ROOT}}）と依存 dir（review のみ） / diff ファイルのパスと担当ファイル / 探索対象（ファイル・関数・値）>
```

- 上の 2 パスは `${CLAUDE_PLUGIN_ROOT}` の部分だけをプラグインの実パスに置き換えて渡す（`/references/prompts/...` 以降は書き換えない。orchestration-guide.md `## 3.5`）
- **初回の explorer には、プラグインの実パスを可変部に必ず入れる**。初回の explorer は共通ブロック（`agent_ctx_file`）より前に走るので、explorer-common.md の `{{PLUGIN_ROOT}}`（`diff-slice.sh` の場所など）を読み替える手がかりはここにしか無い。review では `{{MAIN_ROOT}}` と依存 dir も同じ理由で可変部に入れる（orchestration-guide.md `## 1.1`）。Round 2 の追加 explorer は共通ブロックの後に走るので、そのパスを渡せばよい（orchestration-dynamic-rounds.md `## 6`）

explorer は判定せず事実収集に徹する役割なので、担当対象（どのファイル・どの関数・どの値）を可変部で具体的に与えること。
