// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdir, writeFile } from 'node:fs/promises'
import { runScenarios } from './d05-scenarios.mjs'

vi.mock('node:fs/promises', () => ({ mkdir: vi.fn(), writeFile: vi.fn() }))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('D05 evidence runner', () => {
  it('serializes receipt snapshots after each concurrent pair without losing cases', async () => {
    vi.stubEnv('D05_API_BASE', 'http://127.0.0.1:8000')
    vi.spyOn(console, 'log').mockImplementation(() => {})
    let activeWrites = 0
    let maximumWrites = 0
    const snapshots = []
    vi.mocked(mkdir).mockResolvedValue(undefined)
    vi.mocked(writeFile).mockImplementation(async (_path, content) => {
      activeWrites += 1
      maximumWrites = Math.max(maximumWrites, activeWrites)
      const snapshot = JSON.parse(content)
      await new Promise((resolve) => setTimeout(resolve, 1))
      snapshots.push(snapshot)
      activeWrites -= 1
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url, options) => {
        const input = JSON.parse(options.body)
        return new Response(
          JSON.stringify({
            request_id: input.request_id,
            status: 'unavailable',
            items: [],
            sources: [],
            warnings: [{ code: 'provider_unavailable', fields: [] }],
          }),
          { status: 503, headers: { 'Cache-Control': 'no-store' } },
        )
      }),
    )
    await runScenarios()
    expect(maximumWrites).toBe(1)
    expect(snapshots).toHaveLength(17)
    expect(snapshots.map(({ results }) => results.length)).toEqual(
      Array.from({ length: 17 }, (_unused, index) => (index + 1) * 2),
    )
    const final = snapshots.at(-1).results
    expect(new Set(final.map(({ id }) => id)).size).toBe(34)
    expect(
      final.every(({ evaluation }) => evaluation.status === 'not_run'),
    ).toBe(true)
  })

  it('distinguishes malformed HTTP replies from an unrun network dependency', async () => {
    vi.stubEnv('D05_API_BASE', 'http://127.0.0.1:8000')
    vi.spyOn(console, 'log').mockImplementation(() => {})
    let final
    vi.mocked(mkdir).mockResolvedValue(undefined)
    vi.mocked(writeFile).mockImplementation(async (_path, content) => {
      final = JSON.parse(content).results
    })
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockRejectedValueOnce(new TypeError('TEST ONLY network unavailable'))
        .mockImplementation(
          async () =>
            new Response('TEST ONLY invalid JSON', {
              status: 200,
              headers: { 'Cache-Control': 'no-store' },
            }),
        ),
    )
    await runScenarios()
    expect(final).toHaveLength(34)
    expect(
      final.filter(({ transport }) => transport === 'network'),
    ).toHaveLength(1)
    expect(
      final.filter(({ evaluation }) => evaluation.status === 'not_run'),
    ).toHaveLength(1)
    expect(
      final.filter(
        ({ evaluation }) =>
          evaluation.status === 'failed' &&
          evaluation.reason === 'invalid_json_or_shape',
      ),
    ).toHaveLength(33)
  })
})
