// review-retro: `/review-retro [引数]` で振り返り集計（scripts/review-retro.sh）をモデルを呼ばずに出す mod
//
// 集計は決定的なスクリプトで（orchestration-measurement.md `## 18`）、手で回すとき（`--logs` で合算・
// `--min-plugin-version` で版を絞る）にモデルを挟む理由が無い。引数はシェルで展開する —
// `--logs ~/Projects/*/.claude/events.jsonl` の `~` と glob を端末と同じに効かせるため（打つのは利用者自身）
import type { On } from 'claude-code'

const COMMAND = 'review-retro'

export function registerRetro(on: On) {
  on('command.run', { command: COMMAND }, async ($, e) => {
    const script = `${$.plugin.root}/scripts/review-retro.sh`
    try {
      const r = await $.process.run(['bash', '-c', `bash "$0" ${e.args}`, script], {
        cwd: await $.session.cwd(),
        timeoutMs: 180_000,
      })
      const out = `${r.stdout}${r.stderr ? `\n${r.stderr}` : ''}`.trim()
      return { text: r.exitCode === 0 ? out : `review-retro: exit ${r.exitCode}\n${out}` }
    } catch (err) {
      return { text: `review-retro: 実行できなかった（${String(err)}）` }
    }
  })
}
