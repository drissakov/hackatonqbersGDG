import { act, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import recommendation from '../../../contracts/examples/recommendation-ok.test.json'
import event from '../../../contracts/examples/event-search-response.test.json'
import i18n from '../i18n'
import { parseSearchResponse } from '../lib/api'
import { ResultCard } from './ResultCard'
import { EventCard } from './EventCard'
import { SourceDetails } from './SourceDetails'
import { safeExternalUrl } from '../lib/links'
import type { Locale } from '../lib/types'

beforeEach(async () => {
  await i18n.changeLanguage('en')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('sourced cards', () => {
  it('reuses source names and facts while switching local codes, actions and explanation without requests', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const response = parseSearchResponse(
      recommendation,
      'recommendations',
      'en',
    )
    const { rerender } = render(
      <ResultCard
        card={response.items[0]}
        sources={response.sources}
        locale="en"
      />,
    )
    for (const locale of ['ru', 'kk', 'en'] as const) {
      await act(async () => {
        await i18n.changeLanguage(locale)
      })
      rerender(
        <ResultCard
          card={response.items[0]}
          sources={response.sources}
          locale={locale}
        />,
      )
      expect(
        screen.getByRole('heading', { name: response.items[0].poi.name }),
      ).toHaveAttribute('lang', '')
      expect(
        screen.getByText(i18n.t('codes.activity_code.museum')),
      ).toBeInTheDocument()
      expect(
        screen.getByText(i18n.t('codes.reason_codes.within_budget'), {
          selector: 'li',
        }),
      ).toBeInTheDocument()
      expect(
        screen.getByText(i18n.t('activityAction.museum')),
      ).toBeInTheDocument()
      expect(screen.getByText(i18n.t('card.sourceFacts'))).toBeInTheDocument()
      expect(screen.getByText(i18n.t('card.idea'))).toBeInTheDocument()
      if (locale === 'en') {
        expect(screen.getByText(response.items[0].explanation)).toHaveAttribute(
          'lang',
          'en',
        )
      } else {
        expect(
          screen.queryByText(response.items[0].explanation),
        ).not.toBeInTheDocument()
        expect(
          screen.getByText(i18n.t('card.localizedSummary')),
        ).toBeInTheDocument()
      }
    }
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps unknown event end, price and fit visible instead of implying free admission', () => {
    const response = parseSearchResponse(event, 'events', 'en')
    const { container } = render(
      <EventCard
        card={response.items[0]}
        sources={response.sources}
        locale="en"
      />,
    )
    expect(screen.getByText('Fit unconfirmed')).toBeInTheDocument()
    expect(screen.getAllByText('Unknown').length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText('Schedule incomplete')).toBeInTheDocument()
    expect(
      screen.getByText('Times shown in Astana (Asia/Almaty)'),
    ).toBeInTheDocument()
    expect(container.textContent).not.toContain('undefined')
    expect(screen.getByRole('link', { name: /Check tickets/ })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    )
  })

  it.each(['kk', 'ru', 'en'] as Locale[])(
    'makes unknown facts and unavailable walking route visible in %s',
    async (locale) => {
      await i18n.changeLanguage(locale)
      const response = parseSearchResponse(
        recommendation,
        'recommendations',
        'en',
      )
      const card = {
        ...response.items[0],
        travel_minutes_estimate: null,
        route_status: 'unavailable' as const,
        poi: {
          ...response.items[0].poi,
          price_kzt_per_person: null,
          opening_hours_text: null,
        },
      }
      const { container } = render(<ResultCard card={card} locale={locale} />)
      const price = screen.getByText(i18n.t('card.price')).parentElement!
      expect(within(price).getByText(i18n.t('card.unknown'))).toBeVisible()
      const hours = screen.getByText(`${i18n.t('card.hours')}:`).parentElement!
      expect(within(hours).getByText(i18n.t('card.unknown'))).toBeVisible()
      const walking = screen.getByText(i18n.t('card.travel')).parentElement!
      expect(within(walking).getByText(i18n.t('card.unknown'))).toBeVisible()
      expect(
        screen.getByText(i18n.t('codes.route_status.unavailable')),
      ).toBeVisible()
      expect(
        screen.getByText(`${i18n.t('card.availability')}:`).parentElement,
      ).toHaveTextContent(i18n.t('card.unknown'))
      expect(container).not.toHaveTextContent('undefined')
      expect(container).not.toHaveTextContent('NaN')
    },
  )

  it('uses a sourced ticket URL and otherwise falls back to an event source instead of an arbitrary action', () => {
    const response = parseSearchResponse(event, 'events', 'en')
    const card = response.items[0]
    card.action.url = 'https://example.invalid/unconfirmed-action'
    card.session.booking_url = 'https://example.invalid/test-only/tickets'
    const { rerender } = render(<EventCard card={card} locale="en" />)
    expect(screen.getByRole('link', { name: /Check tickets/ })).toHaveAttribute(
      'href',
      card.event.sources[0].url,
    )
    card.session.provenance = [
      { ...card.session.provenance[0], fields: ['booking_url'] },
    ]
    rerender(<EventCard card={card} locale="en" />)
    expect(screen.getByRole('link', { name: /Check tickets/ })).toHaveAttribute(
      'href',
      card.session.booking_url,
    )
  })

  it('prefers the source of this occurrence over the general event page for ticket checks', () => {
    const response = parseSearchResponse(event, 'events', 'en')
    const card = response.items[0]
    card.event.sources = [
      {
        ...card.event.sources[0],
        source_id: 'event-source',
        url: 'https://example.invalid/test-only/event',
      },
    ]
    card.event.provenance = [
      { ...card.event.provenance[0], source_id: 'event-source' },
    ]
    render(<EventCard card={card} locale="en" />)
    expect(screen.getByRole('link', { name: /Check tickets/ })).toHaveAttribute(
      'href',
      card.session.sources[0].url,
    )
  })

  it('retains observation provenance for displayed nested record facts when card provenance cites fewer facts', () => {
    const response = parseSearchResponse(
      recommendation,
      'recommendations',
      'en',
    )
    const card = response.items[0]
    card.provenance = [{ ...card.provenance[0], fields: ['name'] }]
    card.poi.provenance = [
      {
        ...card.poi.provenance[0],
        fields: ['price_kzt_per_person'],
        observed_at: null,
      },
    ]
    render(<ResultCard card={card} locale="en" />)
    expect(
      screen.getByText('Source supports: Price per person'),
    ).toBeInTheDocument()
    expect(screen.getByText('Fact observed: Unknown')).toBeInTheDocument()
  })

  it('labels descriptions as source text only when record provenance supports the description', () => {
    const response = parseSearchResponse(
      recommendation,
      'recommendations',
      'en',
    )
    const card = response.items[0]
    card.poi.description = 'TEST ONLY description without source evidence'
    const { rerender } = render(<ResultCard card={card} locale="en" />)
    expect(screen.queryByText(card.poi.description)).not.toBeInTheDocument()
    card.poi.provenance = [
      { ...card.poi.provenance[0], fields: ['description'] },
    ]
    rerender(<ResultCard card={card} locale="en" />)
    expect(screen.getByText(card.poi.description)).toHaveAttribute('lang', '')
  })

  it('does not use retrieval time as an unknown fact observation time', () => {
    const response = parseSearchResponse(
      recommendation,
      'recommendations',
      'en',
    )
    render(
      <SourceDetails
        sources={response.sources}
        provenance={[{ ...response.items[0].provenance[0], observed_at: null }]}
        locale="en"
      />,
    )
    expect(screen.getByText('Fact observed: Unknown')).toBeInTheDocument()
    expect(screen.getByText('Retrieved')).toBeInTheDocument()
    expect(screen.getByText(/Source supports:/)).toBeInTheDocument()
  })

  it('blocks executable action and source URLs even when passed directly to a component', () => {
    const response = parseSearchResponse(
      recommendation,
      'recommendations',
      'en',
    )
    const card = {
      ...response.items[0],
      action: { ...response.items[0].action, url: 'javascript:alert(1)' },
      poi: {
        ...response.items[0].poi,
        sources: response.sources.map((source) => ({
          ...source,
          url: 'data:text/html,unsafe',
          rights_basis_url: 'javascript:alert(1)',
        })),
      },
    }
    render(<ResultCard card={card} locale="en" />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('Source link is unavailable')).toBeInTheDocument()
    expect(safeExternalUrl('/relative')).toBeNull()
    expect(safeExternalUrl('https://example.com/path')).toBe(
      'https://example.com/path',
    )
  })
})
