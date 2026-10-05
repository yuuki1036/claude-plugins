// code-review の review-retro mod（hooks/review-retro.ts）のテスト。`claude plugin test` で走る
import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'

type World = { argv: string[][]; cwd: string[]; exitCode: number; throws: boolean }

function stub(on: On, w: World) {
  on('session.cwd', () => ({ value: '/w/repo' }))
  on('process.run', (_$, e) => {
    if (w.throws) return { deny: 'timeout' }
    w.argv.push([...e.argv])
    w.cwd.push(e.init?.cwd ?? '')
    return { value: { exitCode: w.exitCode, stdout: '## レビュー振り返り\n', stderr: w.exitCode ? 'FATAL: x' : '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
}

async function retro($: Engine, args: string) {
  return $.command.run({ command: 'review-retro', args, origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })
}

test('引数をシェルで展開して review-retro.sh に渡し、出力をそのまま返す', async ($, on) => {
  const w: World = { argv: [], cwd: [], exitCode: 0, throws: false }
  stub(on, w)
  const r = await retro($, '--logs ~/p/*/.claude/events.jsonl --last 5')
  expect(r.text).toBe('## レビュー振り返り')
  expect(w.argv[0]?.slice(0, 3)).toEqual(['bash', '-c', 'bash "$0" --logs ~/p/*/.claude/events.jsonl --last 5'])
  expect(w.argv[0]?.[3]).toMatch(/\/scripts\/review-retro\.sh$/)
  expect(w.cwd).toEqual(['/w/repo'])
})

test('失敗したら exit code と stderr を添える / 走らなければそう言う', async ($, on) => {
  const w: World = { argv: [], cwd: [], exitCode: 2, throws: false }
  stub(on, w)
  const r = await retro($, '--logs /nope')
  expect(r.text).toStartWith('review-retro: exit 2')
  expect(r.text).toContain('FATAL: x')
  w.throws = true
  expect((await retro($, '')).text).toStartWith('review-retro: 実行できなかった')
})
