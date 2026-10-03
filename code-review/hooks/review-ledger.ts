// review-ledger: モデルへのリクエスト 1 回ごとの usage と subagent の起動を、その場で記録する mod
//
// publish（scripts/publish-review-event.sh）の tokens / dispatch は transcript から事後に読んでおり、
// transcript を引けない・取り違える回（GitHub issue #246 / #263）は丸ごと欠測か誤値になっていた。
// ここはイベントから直接数える別の経路で、publish が `tokens_live` として transcript の値と並べて載せる
// （どちらが正しいかは並走させて突き合わせてから決める）。
//
// 記録するのは数値と agent の種類だけ。prompt・description・本文は持たない（自由記述で業務の ID が入る /
// #265）。書き出しは publish の Bash を走らせる直前の 1 回だけで、mods が無い環境では何も起きない
import type { EngineInterface, On, TurnUsage } from 'claude-code'

/** 書き出す 1 ファイルの上限の目安。超えた step は数えず truncated を立てる（fs.write は 4 MiB まで） */
export const MAX_STEPS = 20000

/** [完了時刻 ms, agentId（main は ''）, model の番号, input, output, cache_write, cache_read] */
export type Step = [number, string, number, number, number, number, number]

export type Spawn = {
  t: number
  type: string
  background: boolean
  fork: boolean
  /** 起動した側の agentId（main からなら null） */
  parent: string | null
}

export type Ledger = {
  schema: 1
  session: string
  /** この mod が数え始めた時刻。これより前の step は無い（途中で読み込まれた・再読み込みされた回） */
  started: number
  written: number
  models: string[]
  steps: Step[]
  agents: Record<string, Spawn>
  truncated: boolean
}

const SESSION_RE = /^[A-Za-z0-9_-]+$/
const PUBLISH_RE = /publish-review-event\.sh/

let started: number | null = null
const models: string[] = []
const steps: Step[] = []
const agents: Record<string, Spawn> = {}
let truncated = false

async function now($: EngineInterface) {
  const t = await $.clock.now()
  if (started === null) started = t
  return t
}

function modelIndex(model: string) {
  const i = models.indexOf(model)
  if (i >= 0) return i
  models.push(model)
  return models.length - 1
}

function record(t: number, agentId: string | undefined, u: TurnUsage) {
  if (steps.length >= MAX_STEPS) {
    truncated = true
    return
  }
  steps.push([
    t,
    agentId ?? '',
    modelIndex(u.model),
    u.input_tokens,
    u.output_tokens,
    u.cache_creation_input_tokens,
    u.cache_read_input_tokens,
  ])
}

/** 記録の置き場。publish 側（scripts/lib/live_ledger.py）と同じ式: `<設定 dir>/live/<session id>.json` */
export async function ledgerPath($: EngineInterface): Promise<string | null> {
  const sid = await $.session.id()
  if (!SESSION_RE.test(sid)) return null
  const dir = (await $.env.get('CLAUDE_REVIEW_CONFIG_DIR')) || `${(await $.env.get('HOME')) ?? ''}/.config/claude-review`
  if (dir === '/.config/claude-review') return null
  return `${dir}/live/${sid}.json`
}

async function flush($: EngineInterface) {
  const path = await ledgerPath($)
  if (path === null || started === null) return
  const ledger: Ledger = {
    schema: 1,
    session: await $.session.id(),
    started,
    written: await $.clock.now(),
    models,
    steps,
    agents,
    truncated,
  }
  const dir = path.slice(0, path.lastIndexOf('/'))
  await $.process.run(['mkdir', '-p', '-m', '700', dir])
  await $.fs.write(path, JSON.stringify(ledger))
}

export function registerLedger(on: On) {
  on('turn.step', async function* ($, e, next) {
    const r = yield* next(e)
    if (r?.usage) record(await now($), e.agentId, r.usage)
    return r
  })

  on('agent.spawn', async ($, e, next) => {
    const r = await next(e)
    if (r.deny === undefined && r.agentId !== undefined) {
      agents[r.agentId] = {
        t: await now($),
        type: e.subagentType,
        background: e.background,
        fork: e.fork,
        parent: e.parentAgentId ?? null,
      }
    }
    return r
  })

  // publish が記録を読む直前に書き出す。失敗しても publish は止めない（記録は transcript の補助）
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (PUBLISH_RE.test(e.command)) {
      try {
        await flush($)
      } catch {
        // 書けなければ publish 側で記録が無い回になるだけ
      }
    }
    return next(e)
  })
}
