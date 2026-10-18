import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadFixture } from './fixtures'
import type { ResponseStatus } from '../lib/types'

describe('explicit synthetic preview', () => {
  afterEach(() => vi.unstubAllEnvs())

  it.each<ResponseStatus>([
    'ok',
    'partial',
    'unknown',
    'unavailable',
    'no_match',
  ])(
    'loads the original contract %s fixture only in development',
    async (status) => {
      vi.stubEnv('DEV', true)
      const response = await loadFixture('recommendations', status)
      expect(response.status).toBe(status)
      expect(
        response.warnings.some((warning) => warning.code === 'test_data'),
      ).toBe(true)
      expect(
        response.items.every(
          (item) => item.poi.is_test && item.generated_locale === 'en',
        ),
      ).toBe(true)
    },
  )

  it('preserves event partial/unknown end semantics', async () => {
    vi.stubEnv('DEV', true)
    const response = await loadFixture('events')
    expect(response.status).toBe('partial')
    expect(response.items[0].session.ends_at).toBeNull()
    expect(response.items[0].fit_status).toBe('unknown')
  })

  it('rejects fixture loading in production without falling back', async () => {
    vi.stubEnv('DEV', false)
    await expect(loadFixture('recommendations', 'ok')).rejects.toMatchObject({
      code: 'not_ready',
    })
    await expect(loadFixture('events')).rejects.toMatchObject({
      code: 'not_ready',
    })
  })
})
