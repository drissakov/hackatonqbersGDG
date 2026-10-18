import { StrictMode } from 'react'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import type { SearchRequest } from './lib/types'

const modes = [
  {
    name: 'recommendations',
    path: '/api/v1/recommendations',
    submitLabel: 'Find places',
    warning: 'Place search is temporarily unavailable. Please try again later.',
  },
  {
    name: 'events',
    path: '/api/v1/events/search',
    submitLabel: 'Find events',
    warning: 'Event search is temporarily unavailable. Please try again later.',
  },
] as const

const emptyMessage =
  'No matching places or events were found with these preferences.'
const unavailableMessage =
  'Search is temporarily unavailable. This does not mean there are no matching places.'
const diagnostic = 'TEST_ONLY_UPSTREAM_DIAGNOSTIC'

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  })
}

function unavailable(body: SearchRequest, message: string) {
  return {
    status: 'unavailable',
    items: [],
    warnings: [{ code: 'provider_unavailable', message, fields: [] }],
    sources: [],
    request_id: body.request_id,
  }
}

function mockTransport(path: string, reply: (body: SearchRequest) => Response) {
  const posts: SearchRequest[] = []
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, options) => {
    if (input === '/api/health' && options?.method === 'GET') {
      return json({ status: 'ok' })
    }
    if (
      input === path &&
      options?.method === 'POST' &&
      typeof options.body === 'string'
    ) {
      const body = JSON.parse(options.body) as SearchRequest
      posts.push(body)
      return reply(body)
    }
    throw new Error('Unexpected synthetic HTTP request')
  })
  vi.stubGlobal('fetch', fetch)
  return { fetch, posts }
}

async function search(mode: (typeof modes)[number]) {
  const user = userEvent.setup()
  const view = render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  expect(await screen.findByText('API online')).toBeVisible()
  if (mode.name === 'events') {
    await user.click(screen.getByRole('button', { name: 'Events' }))
  }
  await user.type(
    screen.getByRole('textbox', { name: 'What would you like to do?' }),
    'TEST ONLY: an outing',
  )
  await user.click(screen.getByRole('button', { name: mode.submitLabel }))
  return view
}

beforeEach(async () => {
  vi.stubEnv('VITE_API_BASE_URL', '/api')
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
  await act(() => i18n.changeLanguage('en'))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe.each(modes)('HTTP 503 screen through real $name transport', (mode) => {
  it('renders a valid unavailable envelope and its localized warning instead of an empty result or generic error', async () => {
    const { fetch, posts } = mockTransport(mode.path, (body) =>
      json(unavailable(body, mode.warning), 503),
    )
    const { container } = await search(mode)

    expect(
      await screen.findByText('Search unavailable', { selector: 'strong' }),
    ).toBeVisible()
    expect(screen.getByText(unavailableMessage)).toBeVisible()
    expect(screen.getByText(mode.warning)).toBeVisible()
    expect(screen.getByText(mode.warning)).toHaveAttribute('lang', 'en')
    expect(screen.queryByText(emptyMessage)).not.toBeInTheDocument()
    expect(
      screen.queryByText('No match', { selector: 'strong' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryAllByRole('article')).toHaveLength(0)
    expect(
      container.querySelector('.fixture-notice, .synthetic-badge'),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Live API')).toBeVisible()
    expect(posts).toHaveLength(1)
    expect(posts[0]).toEqual(
      expect.objectContaining({ locale: 'en', request_id: expect.any(String) }),
    )
    expect(fetch).toHaveBeenCalledWith(
      mode.path,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it.each([
    {
      name: 'HTML body',
      reply: () =>
        new Response(`<html><body>${diagnostic}</body></html>`, {
          status: 503,
          headers: { 'content-type': 'text/html' },
        }),
    },
    {
      name: 'malformed JSON body',
      reply: () =>
        new Response(`{"private_details":"${diagnostic}"`, {
          status: 503,
          headers: { 'content-type': 'application/json' },
        }),
    },
    {
      name: 'a valid envelope with the wrong status',
      reply: (body: SearchRequest) =>
        json({ ...unavailable(body, diagnostic), status: 'no_match' }, 503),
    },
  ])(
    'keeps $name as a safe generic error without showing the raw response',
    async ({ reply }) => {
      const { posts } = mockTransport(mode.path, reply)
      const { container } = await search(mode)

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'The request could not be completed. Try again.',
      )
      expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
      expect(
        screen.queryByText('Search unavailable', { selector: 'strong' }),
      ).not.toBeInTheDocument()
      expect(screen.queryByText(unavailableMessage)).not.toBeInTheDocument()
      expect(screen.queryByText(emptyMessage)).not.toBeInTheDocument()
      expect(
        screen.queryByText('No match', { selector: 'strong' }),
      ).not.toBeInTheDocument()
      expect(container).not.toHaveTextContent(diagnostic)
      expect(screen.queryAllByRole('article')).toHaveLength(0)
      expect(
        container.querySelector('.fixture-notice, .synthetic-badge'),
      ).not.toBeInTheDocument()
      expect(screen.getByText('Live API')).toBeVisible()
      expect(posts).toHaveLength(1)
    },
  )
})
