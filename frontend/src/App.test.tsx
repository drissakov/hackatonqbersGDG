import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import {
  ApiError,
  checkHealth,
  parseSearchResponse,
  searchRecommendations,
} from './lib/api'
import type { RecommendationResponse } from './lib/types'
import noMatchFixture from '../../contracts/examples/recommendation-no_match.test.json'
import unavailableFixture from '../../contracts/examples/recommendation-unavailable.test.json'
import unknownFixture from '../../contracts/examples/recommendation-unknown.test.json'

const fixtureLoader = vi.hoisted(() => vi.fn())
vi.mock('./dev/fixtures', () => ({ loadFixture: fixtureLoader }))
vi.mock('./lib/api', async () => {
  const actual = await vi.importActual<typeof import('./lib/api')>('./lib/api')
  return {
    ...actual,
    checkHealth: vi.fn(),
    searchRecommendations: vi.fn(),
    searchEvents: vi.fn(),
  }
})

const unknownResponse = parseSearchResponse(
  unknownFixture,
  'recommendations',
  'en',
)

beforeEach(async () => {
  vi.clearAllMocks()
  vi.mocked(checkHealth).mockResolvedValue({ status: 'ok' })
  await act(() => i18n.changeLanguage('en'))
})

async function enterQuery() {
  const user = userEvent.setup()
  await user.type(
    screen.getByRole('textbox', { name: 'What would you like to do?' }),
    'TEST ONLY: quiet outing',
  )
  return user
}

describe('live screen integration', () => {
  it.each([
    {
      status: 'no_match',
      fixture: noMatchFixture,
      heading: 'No match',
      message:
        'No matching places or events were found with these preferences.',
      absentMessage:
        'Search is temporarily unavailable. This does not mean there are no matching places.',
    },
    {
      status: 'unavailable',
      fixture: unavailableFixture,
      heading: 'Search unavailable',
      message:
        'Search is temporarily unavailable. This does not mean there are no matching places.',
      absentMessage:
        'No matching places or events were found with these preferences.',
    },
  ])(
    'renders a successful live $status response without conflating search outcomes',
    async ({ fixture, heading, message, absentMessage }) => {
      vi.mocked(searchRecommendations).mockResolvedValue(
        parseSearchResponse(fixture, 'recommendations', 'en'),
      )
      render(<App />)
      const user = await enterQuery()
      await user.click(screen.getByRole('button', { name: 'Find places' }))
      expect(
        await screen.findByText(heading, { selector: 'strong' }),
      ).toBeVisible()
      expect(screen.getByText(message)).toBeVisible()
      expect(screen.queryByText(absentMessage)).not.toBeInTheDocument()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.queryAllByRole('article')).toHaveLength(0)
      expect(screen.getByText('Live API')).toBeVisible()
      expect(searchRecommendations).toHaveBeenCalledOnce()
      expect(fixtureLoader).not.toHaveBeenCalled()
    },
  )

  it('checks health, sends the untouched defaults without explicit constraints, and renders unknown honestly', async () => {
    let finish!: (value: RecommendationResponse) => void
    vi.mocked(searchRecommendations).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    render(<App />)
    expect(await screen.findByText('API online')).toBeVisible()
    const user = await enterQuery()
    await user.click(screen.getByRole('button', { name: 'Find places' }))
    expect(screen.getByText('Looking for your next stop…')).toBeVisible()
    expect(searchRecommendations).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'TEST ONLY: quiet outing',
        locale: 'en',
        explicit_fields: [],
        origin: null,
        budget_kzt_per_person: null,
        indoor_only: false,
        return_to_start: false,
        request_id: expect.any(String),
      }),
      expect.any(AbortSignal),
    )
    await act(async () => {
      finish(unknownResponse)
    })
    expect(
      await screen.findByText('Not enough information', { selector: 'strong' }),
    ).toBeVisible()
    expect(
      screen.queryByText(
        'No matching places or events were found with these preferences.',
      ),
    ).not.toBeInTheDocument()
    expect(screen.getByText(unknownResponse.warnings[0].message)).toBeVisible()
  })

  it('shows an unavailable endpoint instead of silently replacing it with fixture cards', async () => {
    vi.mocked(searchRecommendations).mockRejectedValue(
      new ApiError('not_ready', 404),
    )
    render(<App />)
    const user = await enterQuery()
    await user.click(screen.getByRole('button', { name: 'Find places' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This search endpoint is not available yet',
    )
    expect(fixtureLoader).not.toHaveBeenCalled()
    expect(screen.getByText('Live API')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
  })

  it('abandons pending live results when the person changes language', async () => {
    let finish!: (value: RecommendationResponse) => void
    vi.mocked(searchRecommendations).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    render(<App />)
    const user = await enterQuery()
    await user.click(screen.getByRole('button', { name: 'Find places' }))
    const signal = vi.mocked(searchRecommendations).mock.calls[0][1]!
    await user.click(screen.getByRole('button', { name: 'Русский' }))
    expect(signal.aborted).toBe(true)
    expect(document.documentElement.lang).toBe('ru')
    await act(async () => {
      finish(unknownResponse)
    })
    expect(
      screen.queryByText('Not enough information', { selector: 'strong' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Найти места' })).toBeEnabled()
  })

  it('does not let a late dev fixture replace a newer live intent', async () => {
    let finish!: (value: RecommendationResponse) => void
    fixtureLoader.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    render(<App />)
    const user = userEvent.setup()
    await user.click(
      await screen.findByText('Synthetic preview · development only', {
        selector: 'summary',
      }),
    )
    await user.click(
      screen.getByRole('button', { name: 'Preview contract example' }),
    )
    await waitFor(() => expect(fixtureLoader).toHaveBeenCalledTimes(1))
    await user.click(screen.getByRole('button', { name: 'Return to live API' }))
    await act(async () => {
      finish(unknownResponse)
    })
    expect(screen.getByText('Live API')).toBeVisible()
    expect(
      screen.getByText('A good outing starts with what you feel like doing.'),
    ).toBeVisible()
    expect(
      screen.queryByText('Not enough information', { selector: 'strong' }),
    ).not.toBeInTheDocument()
  })
})
