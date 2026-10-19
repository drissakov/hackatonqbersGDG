import { afterEach, describe, expect, it, vi } from 'vitest'
import partial from '../../../contracts/examples/transient-event-partial.test.json'
import listing from '../../../contracts/examples/transient-event-listing.test.json'
import unknown from '../../../contracts/examples/transient-event-unknown.test.json'
import unavailable from '../../../contracts/examples/transient-event-unavailable.test.json'
import { parseSearchResponse, searchEvents } from './api'
import type { TransientEventSearchResponse } from './types'

const request = {
  query: 'TEST ONLY events',
  locale: 'en' as const,
  request_id: partial.request_id,
}
const copy = () => structuredClone(partial) as TransientEventSearchResponse
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  })
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('published transient event v1.3 contract', () => {
  it.each([partial, listing, unknown, unavailable])(
    'accepts the shared $status fixture without inventing persistent provenance',
    (fixture) => {
      const parsed = parseSearchResponse(fixture, 'events', 'en')
      expect(parsed.status).toBe(fixture.status)
      expect(parsed.transient).toEqual(fixture)
      expect(parsed.items).toEqual([])
      expect(parsed.sources).toEqual([])
      expect(parsed.discovery).toBeUndefined()
    },
  )

  it('applies optional Pydantic defaults without changing input', () => {
    const response = copy()
    delete (response as Partial<TransientEventSearchResponse>).contract_version
    delete (
      response.items[0].session as Partial<
        (typeof response.items)[0]['session']
      >
    ).verified_fields
    const parsed = parseSearchResponse(response, 'events', 'en')
    expect(parsed.transient?.contract_version).toBe('1.3.0')
    expect(parsed.transient?.items[0].session.verified_fields).toEqual([])
    expect(response).not.toHaveProperty('contract_version')
  })

  it.each([
    (value: TransientEventSearchResponse) => {
      value.status = 'ok'
    },
    (value: TransientEventSearchResponse) => {
      value.status = 'no_match'
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].fit_status = 'fits'
      value.status = 'ok'
    },
    (value: TransientEventSearchResponse) => {
      value.sources[0].storage_allowed = true as false
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].source_ids = ['missing-source']
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].event.source_id = 'missing-source'
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].session.source_url = 'https://example.invalid/uncited'
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].action.url = 'https://example.invalid/uncited'
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].missing_fields = []
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].session.city = 'Almaty'
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].session.status = 'cancelled'
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].session.verified_fields = [
        {
          session_id: 'wrong',
          field: 'city',
          value: 'Astana',
          source_url: value.sources[0].url,
          checked_at: value.sources[0].retrieved_at,
          method: 'manual_source',
        },
      ]
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].reason_codes.push('within_budget')
    },
    (value: TransientEventSearchResponse) => {
      value.items[0].route_status = 'known'
    },
    (value: TransientEventSearchResponse) => {
      value.provider_code = 'private provider details'
    },
    (value: TransientEventSearchResponse) => {
      value.provider_status = 'unavailable'
    },
    (value: TransientEventSearchResponse) => {
      value.live_web_search = 'failed'
    },
    (value: TransientEventSearchResponse) => {
      value.warnings = []
    },
    (value: TransientEventSearchResponse) => {
      value.items.push(structuredClone(value.items[0]))
    },
    (value: TransientEventSearchResponse) => {
      value.sources.push(structuredClone(value.sources[0]))
    },
  ])('rejects contradictory or uncited transient facts', (mutate) => {
    const value = copy()
    mutate(value)
    expect(() => parseSearchResponse(value, 'events', 'en')).toThrow(
      'invalid_response',
    )
  })

  it('rejects card explanations in a different generated locale', () => {
    expect(() => parseSearchResponse(partial, 'events', 'ru')).toThrow(
      'locale_mismatch',
    )
  })

  it.each([
    [200, partial],
    [200, listing],
    [200, unknown],
    [503, unavailable],
  ])(
    'accepts HTTP %s with its shared domain fixture',
    async (status, fixture) => {
      vi.stubEnv('VITE_API_BASE_URL', '/api')
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(json(fixture, status as number)),
      )
      const result = await searchEvents(request)
      expect(result.transient?.status).toBe((fixture as typeof partial).status)
    },
  )

  it.each([
    [503, partial],
    [200, unavailable],
    [201, partial],
  ])('rejects HTTP %s/domain envelope mismatch', async (status, fixture) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(json(fixture, status as number)),
    )
    await expect(searchEvents(request)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('rejects another request correlation ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(partial)))
    await expect(
      searchEvents({
        ...request,
        request_id: '00000000-0000-4000-8000-000000000099',
      }),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })
})
