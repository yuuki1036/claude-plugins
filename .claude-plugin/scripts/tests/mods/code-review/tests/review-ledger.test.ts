// code-review の review-ledger mod（hooks/review-ledger.ts）のテスト。`claude plugin test` で走る
//
// 記録の形は publish 側（scripts/lib/live_ledger.py）が読む契約なので、書き出した JSON そのものを見る。
// live_ledger.py の集計は python 側のテスト（test_code_review_live_ledger.py）が同じ形の記録で見る
import type { Engine } from 'claude-code/testing'
import { expect, mock, test } from 'claude-code/testing'

import { limitFrom, MAX_STEPS } from '../hooks/review-ledger'
import type { Ledger, Step } from '../hooks/review-ledger'
import type { On } from 'claude-code'

const SID = 'sess-1234_ab'
const CFG = '/home/u/.config/claude-review'
const PATH = `${CFG}/live/${SID}.json`
const PUBLISH = 'bash /p/code-review/scripts/publish-review-event.sh --plugin code-review:self-review --payload /tmp/x.json'

type World = { writes: { path: string; text: string }[]; runs: string[][]; sid: string; writeFails?: boolean; published: number }

function stub(on: On, w: World, env: Record<string, string> = { HOME: '/home/u' }) {
  mock.env(on, env)
  on('session.id', () => ({ value: w.sid }))
  on('process.run', (_$, e) => {
    w.runs.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('fs.write', (_$, e) => {
    if (w.writeFails) return { deny: 'EACCES' }
    w.writes.push({ path: e.path, text: e.text })
    return { value: undefined }
  })
  on('turn.step', async function* (_$, e) {
    const out = e.model === 'none' ? null : { model: e.model, input_tokens: 10, output_tokens: 200, cache_creation_input_tokens: 3000, cache_read_input_tokens: 40000 }
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: out ? ('end_turn' as const) : null, usage: out }
  })
  on('agent.spawn', (_$, e) => ({ value: undefined, model: 'claude-sonnet-x', agentId: `agent-${e.description}` }))
  on('tool.call', () => {
    w.published++
    return { result: { stdout: 'ok', stderr: '', interrupted: false }, text: 'ok' }
  })
}

async function step($: Engine, model: string, agentId?: string) {
  const s = $.turn.step({ turnId: 't', index: 0, model, messageCount: 1, ...(agentId ? { agentId } : {}) })
  // chunk は使わない。結果は generator の戻り値（for await は捨てる）
  for (;;) {
    const r = await s.next()
    if (r.done) return r.value
  }
}

async function spawn($: Engine, description: string, background: boolean, parentAgentId?: string) {
  return $.agent.spawn({
    tool_use_id: `tu-${description}`,
    prompt: '業務の ISSUE-123 を見て src/secret.ts をレビュー',
    description,
    subagentType: 'general-purpose',
    provider: { plugin: 'engine', tier: 'core' },
    parentModel: 'claude-opus-x',
    background,
    fork: false,
    ...(parentAgentId ? { parentAgentId } : {}),
  })
}

function newWorld(): World {
  return { writes: [], runs: [], sid: SID, published: 0 }
}

test('publish の直前に、step と起動を記録へ書き出す', async ($, on) => {
  const clock = mock.clock(on, { now: 1_000_000 })
  const w = newWorld()
  stub(on, w)
  await step($, 'claude-opus-x')
  await clock.advance(5)
  await spawn($, 'r1', false)
  await spawn($, 'r2', true, 'agent-r1')
  await step($, 'claude-sonnet-x', 'agent-r1')
  await step($, 'claude-sonnet-x', 'agent-r1')
  // usage の無い応答（失敗・中断）は数えず、step の結果はそのまま呼び出し側へ返す
  expect((await step($, 'none', 'agent-r2')).stopReason).toBeNull()
  expect(w.writes).toEqual([])

  await $.tool.call({ tool: 'Bash', command: PUBLISH })
  expect(w.writes.map(x => x.path)).toEqual([PATH])
  expect(w.runs).toContainEqual(['mkdir', '-p', '-m', '700', `${CFG}/live`])
  const led = JSON.parse(w.writes[0]?.text ?? '{}')
  expect(led).toMatchObject({ schema: 1, session: SID, started: 1_000_000, truncated: false })
  expect(led.models).toEqual(['claude-opus-x', 'claude-sonnet-x'])
  expect(led.steps).toEqual([
    [1_000_000, '', 0, 10, 200, 3000, 40000],
    [1_000_005, 'agent-r1', 1, 10, 200, 3000, 40000],
    [1_000_005, 'agent-r1', 1, 10, 200, 3000, 40000],
  ])
  expect(led.agents).toEqual({
    'agent-r1': { t: 1_000_005, type: 'general-purpose', background: false, fork: false, parent: null },
    'agent-r2': { t: 1_000_005, type: 'general-purpose', background: true, fork: false, parent: 'agent-r1' },
  })
})

test('記録に prompt・description を残さない（自由記述で業務の ID やパスが入る）', async ($, on) => {
  mock.clock(on, { now: 1 })
  const w = newWorld()
  stub(on, w)
  await step($, 'claude-opus-x')
  await spawn($, 'r1', false)
  await $.tool.call({ tool: 'Bash', command: PUBLISH })
  const text = w.writes[0]?.text ?? ''
  expect(text).not.toContain('ISSUE-123')
  expect(text).not.toContain('secret.ts')
  expect(text).not.toContain('"r1"')
})

test('publish 以外の Bash では書かない / 数え始める前は書かない', async ($, on) => {
  mock.clock(on, { now: 1 })
  const w = newWorld()
  stub(on, w)
  await $.tool.call({ tool: 'Bash', command: PUBLISH })
  expect(w.writes).toEqual([])
  await step($, 'claude-opus-x')
  for (const command of ['git status', 'bash /p/scripts/review-timing.sh start', 'echo publish-review-event']) {
    await $.tool.call({ tool: 'Bash', command })
  }
  expect(w.writes).toEqual([])
})

test('設定 dir は CLAUDE_REVIEW_CONFIG_DIR を優先する', async ($, on) => {
  mock.clock(on, { now: 1 })
  const w = newWorld()
  stub(on, w, { HOME: '/home/u', CLAUDE_REVIEW_CONFIG_DIR: '/cfg' })
  await step($, 'claude-opus-x')
  await $.tool.call({ tool: 'Bash', command: PUBLISH })
  expect(w.writes.map(x => x.path)).toEqual([`/cfg/live/${SID}.json`])
})

test('置き場を決められないとき（HOME も設定 dir も無い）は書かない', async ($, on) => {
  mock.clock(on, { now: 1 })
  const w = newWorld()
  stub(on, w, {})
  await step($, 'claude-opus-x')
  await $.tool.call({ tool: 'Bash', command: PUBLISH })
  expect(w.writes).toEqual([])
  expect(w.published).toBe(1)
})

test('session id がファイル名に使えないときは書かない', async ($, on) => {
  mock.clock(on, { now: 1 })
  const w = newWorld()
  w.sid = '../other'
  stub(on, w)
  await step($, 'claude-opus-x')
  await $.tool.call({ tool: 'Bash', command: PUBLISH })
  expect(w.writes).toEqual([])
  expect(w.published).toBe(1)
})

test('書き出しに失敗しても publish は走る', async ($, on) => {
  mock.clock(on, { now: 1 })
  const w = newWorld()
  w.writeFails = true
  stub(on, w)
  await step($, 'claude-opus-x')
  const r = await $.tool.call({ tool: 'Bash', command: PUBLISH })
  expect(w.published).toBe(1)
  expect(r.text).toBe('ok')
})

// 上限は環境変数で小さくして確かめる（MAX_STEPS 件を engine に流すと高負荷時に 60 秒を超えた / GitHub issue #409）
async function ledgerAfter($: Engine, on: On, n: number, limit?: string) {
  mock.clock(on, { now: 1 })
  const w = newWorld()
  stub(on, w, { HOME: '/home/u', ...(limit === undefined ? {} : { CLAUDE_REVIEW_LEDGER_MAX_STEPS: limit }) })
  for (let i = 0; i < n; i++) await step($, 'claude-opus-x')
  await $.tool.call({ tool: 'Bash', command: PUBLISH })
  return JSON.parse(w.writes[0]?.text ?? '{}')
}

test('step が上限を超えたら、それ以上は数えずに truncated を立てる', async ($, on) => {
  const led = await ledgerAfter($, on, 6, '5')
  expect(led.steps).toHaveLength(5)
  expect(led.truncated).toBe(true)
})

test('上限ちょうどでは truncated を立てない', async ($, on) => {
  const led = await ledgerAfter($, on, 5, '5')
  expect(led.steps).toHaveLength(5)
  expect(led.truncated).toBe(false)
})

// 'abc' だけは検証を外しても NaN との比較が常に偽で 6 件残る。検証を外す変異は '0' / '-3' / '2.5' / ' 5' が捕まえる
for (const bad of ['abc', '0', '-3', '2.5', ' 5']) {
  test(`上限の環境変数が ${JSON.stringify(bad)} なら MAX_STEPS のまま（正の整数でなければ無視する）`, async ($, on) => {
    const led = await ledgerAfter($, on, 6, bad)
    expect(led.steps).toHaveLength(6)
    expect(led.truncated).toBe(false)
  })
}

// 上げる向きを engine で確かめると MAX_STEPS 件を流すことになるので、値から上限を決める関数を直接見る
test('上限の環境変数は下げる向きにしか効かない', () => {
  expect(limitFrom('5')).toBe(5)
  expect(limitFrom(String(MAX_STEPS - 1))).toBe(MAX_STEPS - 1)
  expect(limitFrom(String(MAX_STEPS))).toBe(MAX_STEPS)
  expect(limitFrom(String(MAX_STEPS + 1))).toBe(MAX_STEPS)
  expect(limitFrom('30000')).toBe(MAX_STEPS)
  expect(limitFrom(undefined)).toBe(MAX_STEPS)
})

test('MAX_STEPS 件の step を書き出しても fs.write の上限（4 MiB）に収まる', () => {
  // 各欄を実際に出うる桁の大きめの値で埋める（ms の時刻・agentId の長さ・百万単位の token）
  const s: Step = [1_800_000_000_000, 'a'.repeat(24), 9, 9_999_999, 9_999_999, 9_999_999, 9_999_999]
  const ledger: Ledger = {
    schema: 1, session: SID, started: s[0], written: s[0], models: ['claude-opus-x'],
    steps: Array.from({ length: MAX_STEPS }, () => s), agents: {}, truncated: true,
  }
  expect(new TextEncoder().encode(JSON.stringify(ledger)).length).toBeLessThan(4 * 1024 * 1024)
})
