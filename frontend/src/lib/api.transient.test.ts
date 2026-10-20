import { afterEach, describe, expect, it, vi } from 'vitest'
import partial from '../../../contracts/examples/transient-event-partial.test.json'
import listing from '../../../contracts/examples/transient-event-listing.test.json'
import unavailable from '../../../contracts/examples/transient-event-unavailable.test.json'
import unknown from '../../../contracts/examples/transient-event-unknown.test.json'
import { ApiError, parseSearchResponse, searchEvents } from './api'
import type { TransientEventSearchResponse } from './types'
import { withWarningDefaults } from '../test/warnings'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('published S04 transient event boundary', () => {
  it.each([partial, listing, unavailable, unknown])(
    'accepts the shared $status fixture without fabricating citations or persistence rights',
    (fixture) => {
      const before = structuredClone(fixture)
      const result = parseSearchResponse(fixture, 'events', 'en')
      expect(result.status).toBe(fixture.status)
      expect(result.transient).toEqual(withWarningDefaults(fixture))
      expect(result.discovery).toBeUndefined()
      expect(result.sources).toEqual([])
      expect(fixture).toEqual(before)
      expect(
        result.transient!.sources.every(
          (source) => !source.storage_allowed && !source.indexing_allowed,
        ),
      ).toBe(true)
    },
  )

  it('handles a valid current 503 as unavailable rather than an invalid-response error', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '/api')
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify(unavailable), {
            status: 503,
            headers: { 'content-type': 'application/json' },
          }),
      ),
    )
    const result = await searchEvents({
      query: 'TEST ONLY unavailable event search',
      locale: 'en',
      request_id: unavailable.request_id,
    })
    expect(result.status).toBe('unavailable')
    expect(result.transient!.provider_status).toBe('unavailable')
  })

  it.each([
    'Astana qalasy',
    'Астана қаласы',
    'Астана қ.',
    'г. Астана',
    'Astana city',
    'Астане',
    'в Астане',
    'Астанада',
    'Астана қаласында',
  ])('accepts the backend Astana alias %s', (city) => {
    const value = structuredClone(partial)
    value.items[0].session.city = city
    value.items[0].event.city = city
    expect(
      parseSearchResponse(value, 'events', 'en').transient?.items,
    ).toHaveLength(1)
  })

  it('keeps an invalid-time withheld session in its listing without promoting it to a card', () => {
    const value = withWarningDefaults(
      structuredClone(listing),
    ) as TransientEventSearchResponse
    const session = structuredClone(
      partial.items[0].session,
    ) as TransientEventSearchResponse['items'][number]['session']
    session.ends_at = '2030-01-15T18:00:00+05:00'
    session.recommendation_candidate = false
    session.exclusion_reasons = ['invalid_time_order']
    value.listings[0].sessions = [session]
    const result = parseSearchResponse(value, 'events', 'en')
    expect(result.transient!.items).toEqual([])
    expect(result.transient!.listings[0].sessions[0].exclusion_reasons).toEqual(
      ['invalid_time_order'],
    )
  })

  it('rejects source checks predating observation by less than one millisecond', () => {
    const value = withWarningDefaults(
      structuredClone(partial),
    ) as TransientEventSearchResponse
    const session = value.items[0].session
    session.source_fetched_at = '2030-01-15T10:00:00.000999+05:00'
    session.verification_status = 'verified'
    session.verified_fields = [
      {
        session_id: session.session_id,
        field: 'city',
        value: session.city!,
        source_url: session.source_url,
        checked_at: '2030-01-15T10:00:00.000001+05:00',
        method: 'manual_source',
      },
    ]
    expect(() => parseSearchResponse(value, 'events', 'en')).toThrow(ApiError)
  })

  it('preserves ordered submillisecond session and verification instants', () => {
    const value = withWarningDefaults(
      structuredClone(partial),
    ) as TransientEventSearchResponse
    const session = value.items[0].session
    session.starts_at = '2030-01-15T19:00:00.000001+05:00'
    session.ends_at = '2030-01-15T19:00:00.000999+05:00'
    session.source_fetched_at = '2030-01-15T10:00:00.000001+05:00'
    session.verification_status = 'verified'
    session.verified_fields = [
      {
        session_id: session.session_id,
        field: 'starts_at',
        value: session.starts_at,
        source_url: session.source_url,
        checked_at: '2030-01-15T10:00:00.000999+05:00',
        method: 'manual_source',
      },
    ]
    expect(
      parseSearchResponse(value, 'events', 'en').transient!.items,
    ).toHaveLength(1)
  })

  const corruptions: [string, (value: TransientEventSearchResponse) => void][] =
    [
      [
        'source rights',
        (v) => Object.assign(v.sources[0], { storage_allowed: true }),
      ],
      [
        'dangling card source',
        (v) => {
          v.items[0].source_ids = ['missing']
        },
      ],
      [
        'different session event',
        (v) => {
          v.items[0].session.event_id = 'different'
        },
      ],
      [
        'uncited action',
        (v) => {
          v.items[0].action.url = 'https://example.invalid/uncited'
        },
      ],
      [
        'uncited session source',
        (v) => {
          v.items[0].session.source_url = 'https://example.invalid/uncited'
        },
      ],
      [
        'wrong locale',
        (v) => {
          v.items[0].generated_locale = 'ru'
        },
      ],
      [
        'false confirmed fit',
        (v) => {
          v.items[0].fit_status = 'fits'
        },
      ],
      [
        'false budget proof',
        (v) => {
          v.items[0].reason_codes.push('within_budget')
        },
      ],
      [
        'hidden missing ticket status',
        (v) => {
          v.items[0].missing_fields = v.items[0].missing_fields.filter(
            (f) => f !== 'ticket_availability',
          )
        },
      ],
      [
        'unknown route with numeric duration',
        (v) => {
          v.items[0].travel_minutes_estimate = 0
        },
      ],
      [
        'invalid card chronology',
        (v) => {
          v.items[0].session.ends_at = '2030-01-15T18:00:00+05:00'
        },
      ],
      [
        'fabricated verification',
        (v) => {
          v.items[0].session.verification_status = 'verified'
        },
      ],
      [
        'unfinished source search',
        (v) => {
          v.live_web_search = 'not_run'
        },
      ],
      [
        'bounded discovery no-match',
        (v) => {
          v.status = 'no_match'
        },
      ],
      [
        'provider failure hidden as partial',
        (v) => {
          v.provider_status = 'unavailable'
        },
      ],
      [
        'unsafe source credentials',
        (v) => {
          v.sources[0].url = 'https://username:password@example.invalid/event'
        },
      ],
      [
        'invalid provider code',
        (v) => {
          v.provider_code = 'unsafe arbitrary prose'
        },
      ],
    ]
  it.each(corruptions)('rejects %s', (_, corrupt) => {
    const value = withWarningDefaults(
      structuredClone(partial),
    ) as TransientEventSearchResponse
    corrupt(value)
    expect(() => parseSearchResponse(value, 'events', 'en')).toThrow(ApiError)
  })
})
