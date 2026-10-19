import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import partial from '../../contracts/examples/transient-event-partial.test.json'
import listing from '../../contracts/examples/transient-event-listing.test.json'
import unavailable from '../../contracts/examples/transient-event-unavailable.test.json'
import unknown from '../../contracts/examples/transient-event-unknown.test.json'
import type { TransientEventSearchResponse } from './lib/types'
import { formatMinutes, formatMoney } from './lib/format'

beforeEach(async () => {
  vi.stubEnv('VITE_API_BASE_URL', '/api')
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
  await act(() => i18n.changeLanguage('en'))
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

async function showEvent(value: unknown) {
  const posts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options) => {
      if (url === '/api/health')
        return new Response('{"status":"ok"}', {
          headers: { 'content-type': 'application/json' },
        })
      expect(url).toBe('/api/events/search')
      const body = JSON.parse(String(options?.body))
      posts.push(body)
      const response = {
        ...structuredClone(value as object),
        request_id: body.request_id,
      } as TransientEventSearchResponse
      return new Response(JSON.stringify(response), {
        status: response.status === 'unavailable' ? 503 : 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
  const user = userEvent.setup()
  render(<App />)
  await user.click(screen.getByRole('button', { name: 'Events' }))
  await user.type(
    screen.getByRole('textbox', { name: i18n.t('search.query') }),
    'TEST ONLY event search',
  )
  await user.click(screen.getByRole('button', { name: 'Find events' }))
  return { user, posts }
}

describe('current S04 event contract in the complete App', () => {
  it.each([partial, listing, unavailable, unknown])(
    'renders the shared $status fixture through HTTP without generic failure',
    async (fixture) => {
      const { posts } = await showEvent(fixture)
      expect(
        await screen.findByText(
          i18n.t(`codes.response_status.${fixture.status}`),
          { selector: 'strong' },
        ),
      ).toBeVisible()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(
        screen.getByText(
          `${i18n.t('events.searchStatus')}: ${i18n.t(`events.searchStates.${fixture.live_web_search}`)}`,
        ),
      ).toBeVisible()
      expect(
        screen.queryByText(i18n.t('events.citations')),
      ).not.toBeInTheDocument()
      expect(posts).toHaveLength(1)
      await userEvent.click(
        screen.getAllByText(i18n.t('source.title'), { selector: 'summary' })[0],
      )
      expect(
        screen.getByRole('link', { name: fixture.sources[0].url }),
      ).toHaveAttribute('href', fixture.sources[0].url)
      if (fixture.items.length || fixture.listings.length)
        expect(screen.getAllByRole('article')).toHaveLength(1)
      else expect(screen.queryByRole('article')).not.toBeInTheDocument()
    },
  )

  it('preserves card reasons, route snapshot, session action, missing facts and locale without duplicating the same event listing', async () => {
    const value = structuredClone(partial) as TransientEventSearchResponse
    const card = value.items[0]
    card.route_status = 'estimated'
    card.travel_minutes_estimate = 12
    card.visit_minutes_estimate = 45
    card.reason_codes = ['query_match', 'visit_duration_estimate']
    card.missing_fields = card.missing_fields.filter(
      (field) => field !== 'travel_minutes_estimate',
    )
    card.session.source_url = 'https://example.invalid/synthetic-session'
    card.action.url = card.session.source_url
    value.sources.push({
      ...value.sources[0],
      source_id: 'synthetic:session-source',
      url: card.session.source_url,
    })
    card.source_ids.push('synthetic:session-source')
    value.listings = [
      {
        ...structuredClone(
          (listing as TransientEventSearchResponse).listings[0],
        ),
        status: 'discovered',
        sessions: [card.session],
      },
    ]
    const { user, posts } = await showEvent(value)
    const article = await screen.findByRole('article', {
      name: card.event.title,
    })
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(within(article).getByText(card.explanation)).toBeVisible()
    expect(
      within(article).getByText(i18n.t('codes.route_status.estimated')),
    ).toBeVisible()
    expect(within(article).getByText(formatMinutes(12, 'en'))).toBeVisible()
    expect(
      within(article).getByText(
        i18n.t('codes.reason_codes.visit_duration_estimate'),
        { selector: 'li' },
      ),
    ).toBeVisible()
    expect(
      within(article).getByRole('link', {
        name: i18n.t('events.checkTickets'),
      }),
    ).toHaveAttribute('href', card.session.source_url)
    expect(
      within(article).getByText(i18n.t('events.fields.source_verification'), {
        selector: 'li',
      }),
    ).toBeVisible()
    for (const [locale, language] of [
      ['ru', 'Русский'],
      ['kk', 'Қазақша'],
    ] as const) {
      await user.click(screen.getByRole('button', { name: language }))
      expect(
        within(article).queryByText(card.explanation),
      ).not.toBeInTheDocument()
      expect(
        within(article).getByText(i18n.t('card.localizedSummary')),
      ).toBeVisible()
      expect(
        within(article).getByText(
          (_, element) =>
            element?.tagName === 'DD' &&
            element.textContent ===
              i18n.t('events.from', { amount: formatMoney(1000, locale) }),
        ),
      ).toBeVisible()
      expect(
        within(article).getByText(i18n.t('codes.route_status.estimated')),
      ).toBeVisible()
      expect(
        within(article).getByText(i18n.t('events.fitUnknown')),
      ).toBeVisible()
    }
    expect(posts).toHaveLength(1)
  })

  it('keeps a session and an unrelated listing separately named and selected when their IDs match', async () => {
    const value = structuredClone(partial) as TransientEventSearchResponse
    const event = structuredClone(
      (listing as TransientEventSearchResponse).listings[0],
    )
    event.event_id = value.items[0].session.session_id
    event.title = 'SYNTHETIC TEST ONLY - A different listing'
    value.listings = [event]
    const { user, posts } = await showEvent(value)
    const articles = await screen.findAllByRole('article')
    expect(articles).toHaveLength(2)
    expect(articles[0]).toHaveAccessibleName(value.items[0].event.title)
    expect(articles[1]).toHaveAccessibleName(event.title)
    await user.click(
      within(articles[1]).getByRole('button', { name: i18n.t('card.select') }),
    )
    expect(
      within(articles[1]).getByRole('button', {
        name: i18n.t('card.selected'),
      }),
    ).toHaveAttribute('aria-pressed', 'true')
    expect(
      within(articles[0]).getByRole('button', { name: i18n.t('card.select') }),
    ).toHaveAttribute('aria-pressed', 'false')
    const details = screen.getByRole('region', { name: i18n.t('map.title') })
    expect(
      within(details).getByRole('heading', { name: event.title }),
    ).toBeVisible()
    expect(posts).toHaveLength(1)
  })

  it('labels transient source timestamps as observations without claiming a page fetch', async () => {
    const { user } = await showEvent(partial)
    const article = await screen.findByRole('article')
    const summaries = screen.getAllByText(i18n.t('source.title'), {
      selector: 'summary',
    })
    for (const summary of summaries) await user.click(summary)
    expect(
      within(article).getByText(i18n.t('events.observationNotice')),
    ).toBeVisible()
    const envelope = summaries[0].parentElement!
    expect(
      within(envelope).getByText(i18n.t('events.observationNotice')),
    ).toBeVisible()
    expect(
      screen.queryByText(`${i18n.t('source.retrieved')}:`, {
        exact: false,
      }),
    ).not.toBeInTheDocument()
    expect(
      screen.getAllByText(`${i18n.t('events.observed')}:`, {
        exact: false,
      }),
    ).toHaveLength(2)
  })

  it('keeps same-event schedule notes and withheld sessions inspectable without offering another alternative', async () => {
    const value = structuredClone(partial) as TransientEventSearchResponse
    const card = value.items[0]
    const sourceListing = structuredClone(
      (listing as TransientEventSearchResponse).listings[0],
    )
    const withheld = structuredClone(card.session)
    withheld.session_id = 'synthetic:withheld-session'
    withheld.venue_name = 'SYNTHETIC TEST ONLY - Withheld venue'
    withheld.starts_at = null
    withheld.status = 'unknown'
    withheld.recommendation_candidate = false
    withheld.exclusion_reasons = ['unknown_start']
    withheld.missing_fields.push('starts_at')
    sourceListing.schedule_hints = [
      'SYNTHETIC TEST ONLY - Source schedule note',
    ]
    sourceListing.sessions = [card.session, withheld]
    value.listings = [sourceListing]
    const { user, posts } = await showEvent(value)
    const article = await screen.findByRole('article')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(
      screen.getAllByRole('button', { name: i18n.t('card.select') }),
    ).toHaveLength(1)
    const disclosure = within(article).getByText(
      i18n.t('events.supplementalDetails'),
      { selector: 'summary' },
    )
    await user.click(disclosure)
    const details = disclosure.parentElement!
    expect(
      within(details).getByText(i18n.t('events.notRecommendedSession')),
    ).toBeVisible()
    expect(
      within(details).getByText(sourceListing.schedule_hints[0]),
    ).toHaveAttribute('lang', '')
    expect(within(details).getByText(withheld.venue_name!)).toBeVisible()
    expect(
      within(details).getByText(i18n.t('codes.session_status.unknown')),
    ).toBeVisible()
    expect(within(details).getAllByRole('region')).toHaveLength(1)
    expect(within(details).queryByRole('button')).not.toBeInTheDocument()
    expect(within(details).queryByText('unknown_start')).not.toBeInTheDocument()
    expect(posts).toHaveLength(1)
  })
})
