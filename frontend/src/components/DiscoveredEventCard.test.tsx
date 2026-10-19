import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '../i18n'
import {
  syntheticDiscoveryResponse,
  syntheticListing,
  syntheticSession,
} from '../test/eventDiscovery'
import { DiscoveredEventCard } from './DiscoveredEventCard'
import { EventSearchSources } from './EventSearchSources'
import type { Locale } from '../lib/types'

beforeEach(async () => {
  await i18n.changeLanguage('en')
})

describe('transient event discovery cards', () => {
  it('keeps an incomplete listing as a listing with no fabricated session or free price', () => {
    const response = syntheticDiscoveryResponse()
    const { container } = render(
      <DiscoveredEventCard
        event={response.discovery!.events[0]}
        citations={response.discovery!.evidence!.citations}
        locale="en"
      />,
    )
    expect(screen.getByText('Listing · session unconfirmed')).toBeVisible()
    expect(screen.getByText(/This remains a listing/)).toBeVisible()
    expect(screen.getByText('Fit unconfirmed')).toBeVisible()
    expect(screen.getByText(/Ticket availability is unknown/)).toBeVisible()
    expect(screen.queryByText('Starts')).not.toBeInTheDocument()
    expect(container).not.toHaveTextContent('KZT 0')
    expect(screen.getByRole('heading', { level: 3 })).toHaveAttribute(
      'lang',
      '',
    )
    expect(
      screen
        .getAllByRole('link')
        .every((link) => link.getAttribute('rel') === 'noopener noreferrer'),
    ).toBe(true)
    expect(
      screen.getByText(/cited by the generated search response/),
    ).toBeInTheDocument()
  })

  it('shows starting prices, unknown end time, and exact checked fields without claiming a verified session', () => {
    const event = syntheticListing()
    event.status = 'discovered'
    const session = syntheticSession()
    session.verification_status = 'verified'
    session.verified_fields = [
      {
        session_id: session.session_id,
        field: 'starts_at',
        value: session.starts_at!,
        source_url: session.source_url,
        checked_at: session.source_fetched_at,
        method: 'manual_source',
      },
    ]
    event.sessions = [session]
    render(<DiscoveredEventCard event={event} citations={[]} locale="en" />)
    const facts = screen.getByRole('region', {
      name: 'Discovered session details',
    })
    expect(within(facts).getByText(/^From /)).toBeVisible()
    const end = within(facts).getByText('Ends').parentElement!
    expect(end).toHaveTextContent('Unknown')
    expect(
      within(facts).getByText('Only these fields were checked: Start time'),
    ).toBeVisible()
    expect(screen.getByText(/An unknown end time cannot prove/)).toBeVisible()
  })

  it('does not present cancelled or otherwise excluded sessions as eligible options', () => {
    const event = syntheticListing()
    event.sessions = [
      {
        ...syntheticSession(),
        status: 'cancelled',
        recommendation_candidate: false,
        exclusion_reasons: ['cancelled'],
      },
    ]
    render(<DiscoveredEventCard event={event} citations={[]} locale="en" />)
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
    expect(screen.getByText(/This remains a listing/)).toBeVisible()
  })

  it('preserves promotion conditions and a missing currency instead of inventing a regular KZT price', () => {
    const event = syntheticListing()
    event.sessions = [
      {
        ...syntheticSession(),
        currency: null,
        price_kind: 'promotion',
        price_conditions: 'TEST ONLY student promotion',
      },
    ]
    render(<DiscoveredEventCard event={event} citations={[]} locale="en" />)
    expect(
      screen.getByText('From 5,000 (currency unknown) · Promotional price'),
    ).toBeVisible()
    expect(screen.getByText('TEST ONLY student promotion')).toHaveAttribute(
      'lang',
      '',
    )
    expect(screen.getByText(/^From /)).toBeVisible()
  })

  it('blocks executable links when the component is used directly', () => {
    const event = syntheticListing()
    event.source_url = 'javascript:alert(1)'
    render(<DiscoveredEventCard event={event} citations={[]} locale="en" />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(
      screen.getAllByText('Source link is unavailable').length,
    ).toBeGreaterThan(0)
  })

  it('formats an amount with unknown currency using the active locale without inventing KZT', async () => {
    await i18n.changeLanguage('ru')
    const event = syntheticListing()
    event.sessions = [
      {
        ...syntheticSession(),
        currency: null,
        price_kind: 'regular',
        price_from: 12500,
      },
    ]
    render(<DiscoveredEventCard event={event} citations={[]} locale="ru" />)
    const price = screen.getByText(i18n.t('events.price')).parentElement!
    expect(price.querySelector('dd')?.textContent).toBe(
      `${i18n.t('events.from')} ${new Intl.NumberFormat('ru-KZ', { maximumFractionDigits: 0 }).format(12500)} (${i18n.t('events.currencyUnknown')})`,
    )
    expect(price).not.toHaveTextContent('₸')
  })

  it('exposes independent venue coordinate sources separately from event discovery sources', () => {
    const event = syntheticListing()
    event.venue = {
      ...event.venue,
      poi_id: 'test-poi',
      location: { latitude: 51.13, longitude: 71.43 },
      basis: 'name_address_astana_permitted_poi',
      source_ids: ['test-osm'],
      source_urls: ['https://example.invalid/test-only/venue'],
      geography_basis: 'central_astana_bbox',
    }
    event.sessions = [
      {
        ...syntheticSession(),
        venue: {
          ...event.venue,
          source_urls: ['https://example.invalid/test-only/session-venue'],
        },
      },
    ]
    render(<DiscoveredEventCard event={event} citations={[]} locale="en" />)
    expect(
      screen.getByRole('link', {
        name: 'https://example.invalid/test-only/venue',
      }),
    ).toHaveAttribute('href', event.venue.source_urls[0])
    expect(
      screen.getByRole('link', {
        name: 'https://example.invalid/test-only/session-venue',
      }),
    ).toHaveAttribute('href', event.sessions[0].venue.source_urls[0])
    expect(screen.getAllByText(i18n.t('events.venueNotice'))).toHaveLength(2)
  })

  it.each(['kk', 'ru', 'en'] as Locale[])(
    'localizes discovery actions and preserves source facts without showing generated citation prose in %s',
    async (locale) => {
      await i18n.changeLanguage(locale)
      const response = syntheticDiscoveryResponse()
      const event = response.discovery!.events[0]
      const citations = response.discovery!.evidence!.citations
      render(
        <>
          <DiscoveredEventCard
            event={event}
            citations={citations}
            locale={locale}
          />
          <EventSearchSources citations={citations} />
        </>,
      )
      expect(
        screen.getByRole('heading', { name: event.title }),
      ).toBeInTheDocument()
      expect(screen.queryByText(citations[0].context)).not.toBeInTheDocument()
      expect(screen.queryByText(citations[0].title)).not.toBeInTheDocument()
      expect(
        screen.getByRole('link', { name: i18n.t('events.checkTickets') }),
      ).toHaveAttribute('href', event.source_url)
      expect(screen.getByText(i18n.t('events.activity'))).toBeVisible()
      expect(
        screen.getByText(i18n.t('codes.route_status.not_requested')),
      ).toBeVisible()
      expect(screen.getByText(i18n.t('events.ticketsUnknown'))).toBeVisible()
    },
  )
})
