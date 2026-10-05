// review-progress: review / self-review の進み具合を、プロンプトの上の帯に出す mod
//
// レビューは 10〜57 分かかり、その間に見えるのは agent の起動と途中の出力だけだった。SKILL 本文は
// 変えず、レビューが既に打っている計測の打点（scripts/review-timing.sh）と subagent の起動・完了を
// 見るだけで組む。wave の打点は落ちることが多い（GitHub issue #161）ので、段階は start / t2 / publish
// と agent の数だけから決める。`run_in_background` で起動した agent はその場で知らせる
// （結果を取りこぼす / orchestration-guide.md `## 0`。transcript からは事後にしか分からなかった）
import { atom, read, update } from 'claude-code'
import type { AgentSpawnInput, AgentSpawnResult, EngineInterface, On } from 'claude-code'

import type { ReviewProgress } from '../types'

/** 経過時間の表示を進める間隔 */
export const TICK_MS = 60_000
/** これだけ何も起きなければ、レビューは止まった（publish せずに終わった）とみなして帯を消す */
export const STALE_MS = 2 * 60 * 60_000

const progress = atom({ plugin: 'code-review', key: 'progress' } as const, null)
const isHidden = atom({ plugin: 'code-review', key: 'progressHidden' } as const, false)

const TIMING_RE = /review-timing\.sh["']?\s+(start|mark\s+t2|discard)\b/
const PUBLISH_RE = /publish-review-event\.sh/

/** このレビューで main が起動した agent（完了の突き合わせに使う） */
const running = new Set<string>()
let tick: { cancel: () => void } | null = null

function stopTick() {
  tick?.cancel()
  tick = null
}

async function end($: EngineInterface) {
  stopTick()
  running.clear()
  await update($, progress, () => null)
}

/** 帯の 1 行目。段階は打点の取りこぼしに強いものだけから決める */
export function progressLine(p: ReviewProgress): string {
  const label = p.kind === 'review' ? 'review' : 'self-review'
  const minutes = Math.max(0, Math.floor((p.now - p.startedAt) / 60_000))
  let phase: string
  if (p.spawned > p.done) phase = `agent 実行中（完了 ${p.done} / 起動 ${p.spawned}）`
  else if (p.isReported) phase = 'レポート出力済み・publish 待ち'
  else if (p.spawned > 0) phase = `統合中（agent ${p.done} 体 完了）`
  else phase = 'トリアージ中'
  return `${label} · ${phase} · ${minutes} 分`
}

/** 起動した subagent を他の mod にも知らせる口（$ を持たない関数だけ） */
export type SpawnListener = (t: number, e: AgentSpawnInput, r: AgentSpawnResult) => void

export function registerProgress(on: On, onSpawn: SpawnListener) {
  on('agent.spawn', async ($, e, next) => {
    const r = await next(e)
    const t = await $.clock.now()
    onSpawn(t, e, r)
    // 孫 agent は数えない（reviewer の数と合わせる）
    if (r.deny !== undefined || r.agentId === undefined || e.parentAgentId !== undefined) return r
    if ((await read($, progress)) === null) return r
    running.add(r.agentId)
    await update($, progress, v =>
      v === null ? v : { ...v, now: t, lastEventAt: t, spawned: v.spawned + 1, background: v.background + (e.background ? 1 : 0) },
    )
    if (e.background) $.ui.toast('agent を run_in_background で起動した（結果を取りこぼす）')
    return r
  })


  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    // subagent の Bash は打点を打たない
    const m = e.agentId === undefined ? TIMING_RE.exec(e.command) : null
    const isPublish = e.agentId === undefined && PUBLISH_RE.test(e.command)
    const r = await next(e)
    if (r.deny !== undefined || r.isError === true) return r
    if (m?.[1] === 'start') {
      const t = await $.clock.now()
      running.clear()
      await update($, isHidden, () => false)
      await update($, progress, () => ({
        kind: /--pr\b/.test(e.command) ? 'review' : 'self-review',
        startedAt: t,
        now: t,
        lastEventAt: t,
        spawned: 0,
        done: 0,
        background: 0,
        isReported: false,
      }))
      stopTick()
      tick = $.clock.every(TICK_MS, () => {
        void (async () => {
          const now = await $.clock.now()
          const v = await read($, progress)
          if (v !== null && now - v.lastEventAt > STALE_MS) await end($)
          else await update($, progress, x => (x === null ? x : { ...x, now }))
        })()
      })
    } else if (m?.[1] === 'discard' || isPublish) {
      await end($)
    } else if (m !== null && m[1] !== undefined) {
      const t = await $.clock.now()
      await update($, progress, v => (v === null ? v : { ...v, now: t, lastEventAt: t, isReported: true }))
    }
    return r
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined && running.delete(e.agentId)) {
      const t = await $.clock.now()
      await update($, progress, v => (v === null ? v : { ...v, now: t, lastEventAt: t, done: v.done + 1 }))
    }
    return next(e)
  })

  // 他のプラグインの帯の上に重ねる（next を呼ばずに返すと、下の帯が消える）
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const below = await next(e)
    const p = await read($, progress)
    if (p === null || e.props.hasSurvey || (await read($, isHidden))) return below
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        <Box gap={1}>
          <Text dimColor>{progressLine(p)}</Text>
          <Button key="hide-progress" label="隠す" onPress={() => update($, isHidden, () => true)} />
        </Box>
        {p.background > 0 && (
          <Text color="warning">
            ⚠️ run_in_background で起動した agent が {p.background} 体（結果を取りこぼす。run_in_background: false を明示する）
          </Text>
        )}
        {below}
      </Box>
    )
  })
}
