// code-review の review-progress mod（hooks/review-progress.tsx）のテスト。`claude plugin test` で走る
import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { expect, mock, test } from 'claude-code/testing'

import { STALE_MS, TICK_MS } from '../hooks/review-progress'

const SURFACES = ['terminal', 'desktop'] as const
const T = 'bash "/p/code-review/scripts/review-timing.sh"'
const PUBLISH = 'bash /p/code-review/scripts/publish-review-event.sh --plugin code-review:self-review --payload x'

type World = { toasts: string[]; failing: Set<string> }

function stub(on: On, w: World) {
  mock.env(on, {})
  on('tool.call', (_$, e) => {
    const command = 'command' in e ? String(e.command) : ''
    return w.failing.has(command)
      ? { result: { stdout: '', stderr: 'boom', interrupted: false }, text: 'boom', isError: true as const }
      : { result: { stdout: '', stderr: '', interrupted: false }, text: '' }
  })
  on('agent.spawn', (_$, e) => ({ model: 'claude-sonnet-x', agentId: `id-${e.description}` }))
  on('turn.complete', () => ({ text: '' }))
  on('ui.toast', (_$, e) => {
    w.toasts.push(typeof e === 'string' ? e : JSON.stringify(e))
    return { value: undefined }
  })
  on('ui.render', { component: 'AbovePrompt' }, () => ({ type: 'Box', props: {}, children: [] }))
  // ledger の書き出し（publish の直前）に要る分
  on('session.id', () => ({ value: 's1' }))
}

function newWorld(): World {
  return { toasts: [], failing: new Set() }
}

async function bash($: Engine, command: string, agentId?: string) {
  return $.tool.call({ tool: 'Bash', command, ...(agentId ? { agentId } : {}) })
}

async function spawn($: Engine, name: string, opts: { background?: boolean; parent?: string } = {}) {
  return $.agent.spawn({
    tool_use_id: `tu-${name}`,
    prompt: 'p',
    description: name,
    subagentType: 'general-purpose',
    provider: { plugin: 'engine', tier: 'core' },
    parentModel: 'claude-opus-x',
    background: opts.background ?? false,
    fork: false,
    ...(opts.parent ? { parentAgentId: opts.parent } : {}),
  })
}

async function finish($: Engine, name: string) {
  return $.turn.complete({ turnId: 't', answer: '', durationMs: 1, isAborted: false, reason: 'answer', agentId: `id-${name}` })
}

async function band($: Engine, surface: (typeof SURFACES)[number]) {
  const ui = await $.ui.mount({
    plugin: 'code-review',
    surface,
    component: 'AbovePrompt',
    props: { hasSurvey: false, isWorking: true, maxRows: 10 } as never,
  })
  const line = (await ui.find({ type: 'Text', text: /分$/ }))?.text
  const warn = (await ui.find({ type: 'Text', text: /run_in_background/ }))?.text
  await ui.unmount()
  return { line, warn }
}

test('レビューが始まるまで帯は出ず、レビュー外の agent では知らせない', async ($, on) => {
  mock.clock(on, { now: 0 })
  const w = newWorld()
  stub(on, w)
  await spawn($, 'early')
  await spawn($, 'early-bg', { background: true })
  expect(w.toasts).toEqual([])
  await bash($, 'git status')
  for (const s of SURFACES) expect((await band($, s)).line).toBeUndefined()
})

test('段階: トリアージ → agent 実行中 → 統合中 → publish 待ち → 消える', async ($, on) => {
  const clock = mock.clock(on, { now: 1_000 })
  stub(on, newWorld())
  await bash($, `${T} start`)
  for (const s of SURFACES) expect((await band($, s)).line).toBe('self-review · トリアージ中 · 0 分')

  await spawn($, 'r1')
  await spawn($, 'r2')
  await spawn($, 'grandchild', { parent: 'id-r1' })
  expect((await band($, 'terminal')).line).toBe('self-review · agent 実行中（完了 0 / 起動 2） · 0 分')
  await finish($, 'r1')
  await finish($, 'grandchild')
  expect((await band($, 'terminal')).line).toBe('self-review · agent 実行中（完了 1 / 起動 2） · 0 分')
  await finish($, 'r2')
  await finish($, 'r2')
  await clock.advance(TICK_MS * 3)
  expect((await band($, 'desktop')).line).toBe('self-review · 統合中（agent 2 体 完了） · 3 分')

  await bash($, `${T} mark t2`)
  expect((await band($, 'terminal')).line).toBe('self-review · レポート出力済み・publish 待ち · 3 分')
  await bash($, PUBLISH)
  for (const s of SURFACES) expect((await band($, s)).line).toBeUndefined()
})

test('--pr 付きの start は review として出す / 次の start で数え直す', async ($, on) => {
  mock.clock(on, { now: 0 })
  stub(on, newWorld())
  await bash($, `${T} start`)
  await spawn($, 'a')
  await bash($, `${T} start --pr 12`)
  expect((await band($, 'terminal')).line).toBe('review · トリアージ中 · 0 分')
})

test('run_in_background で起動した agent はその場で知らせる', async ($, on) => {
  mock.clock(on, { now: 0 })
  const w = newWorld()
  stub(on, w)
  await bash($, `${T} start`)
  await spawn($, 'fg')
  expect(w.toasts).toEqual([])
  await spawn($, 'bg', { background: true })
  expect(w.toasts).toHaveLength(1)
  for (const s of SURFACES) expect((await band($, s)).warn).toContain('1 体')
})

test('discard で消える / 失敗した打点・subagent の Bash は数えない', async ($, on) => {
  mock.clock(on, { now: 0 })
  const w = newWorld()
  w.failing.add(`${T} start`)
  stub(on, w)
  await bash($, `${T} start`)
  expect((await band($, 'terminal')).line).toBeUndefined()
  await bash($, `bash /x/review-timing.sh start`, 'agent-1')
  expect((await band($, 'terminal')).line).toBeUndefined()

  await bash($, `bash /x/review-timing.sh start --pr 3`)
  await bash($, `bash /x/review-timing.sh mark t2`, 'agent-1')
  await bash($, `bash /x/publish-review-event.sh`, 'agent-1')
  expect((await band($, 'terminal')).line).toBe('review · トリアージ中 · 0 分')
  await bash($, `bash /x/review-timing.sh discard --pr 3`)
  expect((await band($, 'terminal')).line).toBeUndefined()
})

test('長く何も起きなければ消える', { timeoutMs: 20000 }, async ($, on) => {
  const clock = mock.clock(on, { now: 0 })
  stub(on, newWorld())
  await bash($, `${T} start`)
  await clock.advance(STALE_MS - TICK_MS)
  expect((await band($, 'terminal')).line).toBeDefined()
  await clock.advance(TICK_MS * 2)
  expect((await band($, 'terminal')).line).toBeUndefined()
})

test('隠すと消え、次のレビューでまた出る', async ($, on) => {
  mock.clock(on, { now: 0 })
  stub(on, newWorld())
  await bash($, `${T} start`)
  const ui = await $.ui.mount({
    plugin: 'code-review',
    surface: 'terminal',
    component: 'AbovePrompt',
    props: { hasSurvey: false, isWorking: true, maxRows: 10 } as never,
  })
  await ui.press({ key: 'hide-progress' })
  await ui.unmount()
  expect((await band($, 'terminal')).line).toBeUndefined()
  await bash($, `${T} start`)
  expect((await band($, 'terminal')).line).toBe('self-review · トリアージ中 · 0 分')
})
