import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import recommendation from '../../../contracts/examples/recommendation-ok.test.json'
import event from '../../../contracts/examples/event-search-response.test.json'
import i18n from '../i18n'
import { parseSearchResponse } from '../lib/api'
import { ResultCard } from './ResultCard'
import { EventCard } from './EventCard'
import { SourceDetails } from './SourceDetails'
import { safeExternalUrl } from '../lib/links'

beforeEach(async () => {
  await i18n.changeLanguage('en')
})

describe('sourced cards', () => {
  it('preserves source names while localizing activity and reason codes', async () => {
    await i18n.changeLanguage('ru')
    const response = parseSearchResponse(
      recommendation,
      'recommendations',
      'en',
    )
    render(
      <ResultCard
        card={response.items[0]}
        sources={response.sources}
        locale="ru"
      />,
    )
    expect(
      screen.getByRole('heading', {
        name: 'SYNTHETIC TEST ONLY - Fictional Astana Museum',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('Музей')).toBeInTheDocument()
    expect(screen.getByText('Укладывается в бюджет')).toBeInTheDocument()
    expect(screen.getByText('Приблизительный маршрут')).toBeInTheDocument()
    expect(
      screen.getByText('Синтетический тестовый пример', {
        selector: 'article > .synthetic-badge',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText(response.items[0].explanation)).toHaveAttribute(
      'lang',
      'en',
    )
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
    expect(screen.getByRole('link', { name: /View source/ })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    )
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
