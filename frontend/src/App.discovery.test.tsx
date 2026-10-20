import { StrictMode } from 'react'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import type { SearchRequest } from './lib/types'
import { syntheticDiscoveryResponse } from './test/eventDiscovery'

beforeEach(async () => {
  vi.stubEnv('VITE_API_BASE_URL', '/api')
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
  await act(() => i18n.changeLanguage('en'))
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('live event envelope through the real frontend transport', () => {
  it('keeps citations inspectable when web search ran but no grounded event was accepted', async () => {
    const response = syntheticDiscoveryResponse()
    response.status = 'unknown'
    response.discovery!.provider_status = 'unknown'
    response.discovery!.provider_code = 'no_grounded_events'
    response.discovery!.events = []
    response.warnings = [
      {
        code: 'data_unknown',
        message: 'TEST ONLY no grounded event.',
        fields: [],
        clarifications: [],
      },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof globalThis.fetch>(async (url, options) => {
        let data: unknown = { status: 'ok' }
        if (url === '/api/events/search' && typeof options?.body === 'string') {
          const body = JSON.parse(options.body) as SearchRequest
          data = { ...response, request_id: body.request_id }
        } else if (url !== '/api/health') {
          throw new Error('Unexpected synthetic request')
        }
        return new Response(JSON.stringify(data), {
          headers: { 'content-type': 'application/json' },
        })
      }),
    )
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Events' }))
    await user.type(
      screen.getByRole('textbox', { name: 'What would you like to do?' }),
      'TEST ONLY concert search',
    )
    await user.click(screen.getByRole('button', { name: 'Find events' }))
    expect(
      await screen.findByText('Not enough information', { selector: 'strong' }),
    ).toBeVisible()
    expect(screen.getByText('Source search: Web search was used')).toBeVisible()
    await user.click(
      screen.getByText('Search citations', { selector: 'summary' }),
    )
    const source = screen.getByRole('link', { name: i18n.t('source.open') })
    expect(source).toBeVisible()
    expect(source).toHaveAttribute(
      'href',
      response.discovery!.evidence!.citations[0].url,
    )
    expect(source).toHaveAttribute('rel', 'noopener noreferrer')
    expect(
      screen.queryByText(response.discovery!.evidence!.citations[0].context),
    ).not.toBeInTheDocument()
    expect(screen.getByText(i18n.t('events.citationNotice'))).toBeVisible()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(
      screen.queryByText('No match', { selector: 'strong' }),
    ).not.toBeInTheDocument()
  })

  it('renders D03 listings from the event API without using legacy cards or synthetic fallback', async () => {
    const posts: SearchRequest[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof globalThis.fetch>(async (url, options) => {
        let data: unknown = { status: 'ok' }
        if (url === '/api/events/search' && typeof options?.body === 'string') {
          const body = JSON.parse(options.body) as SearchRequest
          posts.push(body)
          data = {
            ...syntheticDiscoveryResponse(),
            request_id: body.request_id,
          }
        } else if (url !== '/api/health') {
          throw new Error('Unexpected synthetic request')
        }
        return new Response(JSON.stringify(data), {
          headers: { 'content-type': 'application/json' },
        })
      }),
    )
    const user = userEvent.setup()
    const { container } = render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
    expect(await screen.findByText('Server online')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Events' }))
    await user.type(
      screen.getByRole('textbox', { name: 'What would you like to do?' }),
      'TEST ONLY concert search',
    )
    await user.click(screen.getByRole('button', { name: 'Find events' }))
    expect(
      await screen.findByRole('heading', {
        name: 'TEST ONLY fictional event listing',
      }),
    ).toBeVisible()
    expect(screen.getByText('Listing · session unconfirmed')).toBeVisible()
    expect(screen.getByText('Live API')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      container.querySelector('.fixture-notice, .synthetic-badge'),
    ).not.toBeInTheDocument()
    expect(posts).toHaveLength(1)
    expect(posts[0]).toMatchObject({
      query: 'TEST ONLY concert search',
      locale: 'en',
      origin: null,
    })
  })
})
