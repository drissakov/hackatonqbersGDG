import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchForm } from './SearchForm'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: 'en' },
  }),
}))

beforeEach(() => {
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
})

afterEach(() => {
  vi.unstubAllEnvs()
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: undefined,
  })
})

async function withQuery() {
  const onSubmit = vi.fn()
  const user = userEvent.setup()
  render(
    <SearchForm onSubmit={onSubmit} loading={false} mode="recommendations" />,
  )
  await user.type(screen.getByLabelText('search.query'), 'A quiet walk')
  return { onSubmit, user }
}

describe('SearchForm contract constraints', () => {
  it('keeps untouched defaults nonexplicit and does not invent coordinates', async () => {
    const { onSubmit, user } = await withQuery()
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit).toHaveBeenCalledWith({
      query: 'A quiet walk',
      locale: 'en',
      origin: null,
      available_minutes: null,
      return_to_start: false,
      budget_kzt_per_person: null,
      indoor_only: false,
      date_time: null,
      explicit_fields: [],
    })
    expect(
      screen.queryByRole('region', { name: 'location.mapLabel' }),
    ).not.toBeInTheDocument()
  })

  it('retains deliberate false, zero and cleared null values in explicit_fields', async () => {
    const { onSubmit, user } = await withQuery()
    await user.click(screen.getByLabelText('search.returnToStart'))
    await user.click(screen.getByLabelText('search.returnToStart'))
    await user.click(screen.getByLabelText('search.indoor'))
    await user.click(screen.getByLabelText('search.indoor'))
    await user.type(screen.getByLabelText('search.budget'), '0')
    await user.type(screen.getByLabelText('search.minutes'), '45')
    await user.clear(screen.getByLabelText('search.minutes'))
    await user.type(screen.getByLabelText('location.latitude'), '51.13')
    await user.type(screen.getByLabelText('location.longitude'), '71.43')
    await user.click(screen.getByRole('button', { name: 'location.clear' }))
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        origin: null,
        available_minutes: null,
        budget_kzt_per_person: 0,
        return_to_start: false,
        indoor_only: false,
        explicit_fields: [
          'return_to_start',
          'indoor_only',
          'budget_kzt_per_person',
          'available_minutes',
          'origin',
        ],
      }),
    )
  })

  it('blocks a missing query and paired/out-of-range coordinate mistakes', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <SearchForm onSubmit={onSubmit} loading={false} mode="recommendations" />,
    )
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(screen.getByText('search.queryRequired')).toBeInTheDocument()
    await user.type(screen.getByLabelText('search.query'), 'Museum')
    await user.type(screen.getByLabelText('location.latitude'), '91')
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(screen.getByText('location.coordinatesInvalid')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
    await user.clear(screen.getByLabelText('location.latitude'))
    await user.type(screen.getByLabelText('location.latitude'), '51.13')
    await user.type(screen.getByLabelText('location.longitude'), '71.43')
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        origin: { latitude: 51.13, longitude: 71.43 },
        explicit_fields: ['origin'],
      }),
    )
    expect(screen.getByText('location.manual')).toBeInTheDocument()
  })

  it('validates minute and integer KZT limits before sending a request', async () => {
    const { onSubmit, user } = await withQuery()
    fireEvent.change(screen.getByLabelText('search.minutes'), {
      target: { value: '1441' },
    })
    fireEvent.change(screen.getByLabelText('search.budget'), {
      target: { value: '-1' },
    })
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(screen.getByText('search.minutesInvalid')).toBeInTheDocument()
    expect(screen.getByText('search.budgetInvalid')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('search.minutes'), {
      target: { value: '45.5' },
    })
    fireEvent.change(screen.getByLabelText('search.budget'), {
      target: { value: '10.5' },
    })
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sends Astana wall time as an aware instant for event searches', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<SearchForm onSubmit={onSubmit} loading={false} mode="events" />)
    await user.type(screen.getByLabelText('search.query'), 'Concert')
    fireEvent.change(screen.getByLabelText('search.dateTime'), {
      target: { value: '2026-10-19T18:30' },
    })
    await user.click(
      screen.getByRole('button', { name: 'search.submitEvents' }),
    )
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        date_time: '2026-10-19T13:30:00.000Z',
        explicit_fields: ['date_time'],
      }),
    )
  })

  it('disables duplicate submissions while the API is loading', () => {
    const onSubmit = vi.fn()
    const { container } = render(
      <SearchForm onSubmit={onSubmit} loading mode="recommendations" />,
    )
    expect(
      screen.getByRole('button', { name: 'search.searching' }),
    ).toBeDisabled()
    fireEvent.submit(container.querySelector('form')!)
    expect(onSubmit).not.toHaveBeenCalled()
  })
})

describe('one-shot browser geolocation', () => {
  it('does not ask on mount, handles denial once and keeps manual selection available', async () => {
    const getCurrentPosition = vi.fn(
      (_success, failure: PositionErrorCallback) => {
        failure({ code: 1 } as GeolocationPositionError)
      },
    )
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    })
    const { onSubmit, user } = await withQuery()
    expect(getCurrentPosition).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /location.gps$/ }))
    expect(screen.getByText('location.gpsDenied')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /location.gpsUsed/ }),
    ).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /location.gpsUsed/ }))
    expect(getCurrentPosition).toHaveBeenCalledOnce()
    await user.type(screen.getByLabelText('location.latitude'), '51')
    await user.type(screen.getByLabelText('location.longitude'), '71')
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        origin: { latitude: 51, longitude: 71 },
        explicit_fields: ['origin'],
      }),
    )
  })

  it('shows loading, uses successful coordinates, and labels the point source', async () => {
    let complete: PositionCallback = () => undefined
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      complete = success
    })
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    })
    const { onSubmit, user } = await withQuery()
    await user.click(screen.getByRole('button', { name: /location.gps$/ }))
    expect(
      screen.getByRole('button', { name: /location.gpsLoading/ }),
    ).toBeDisabled()
    act(() => {
      complete({
        coords: { latitude: 51.14, longitude: 71.44 },
      } as GeolocationPosition)
    })
    expect(screen.getByText('location.gpsSource')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        origin: { latitude: 51.14, longitude: 71.44 },
        explicit_fields: ['origin'],
      }),
    )
    expect(getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 },
    )
  })

  it('does not overwrite manual edits with a late GPS callback', async () => {
    let complete: PositionCallback = () => undefined
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition: vi.fn((success: PositionCallback) => {
          complete = success
        }),
      },
    })
    const { onSubmit, user } = await withQuery()
    await user.click(screen.getByRole('button', { name: /location.gps$/ }))
    await user.type(screen.getByLabelText('location.latitude'), '52')
    await user.type(screen.getByLabelText('location.longitude'), '72')
    act(() => {
      complete({
        coords: { latitude: 51, longitude: 71 },
      } as GeolocationPosition)
    })
    await user.click(screen.getByRole('button', { name: 'search.submit' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ origin: { latitude: 52, longitude: 72 } }),
    )
    expect(screen.getByText('location.manual')).toBeInTheDocument()
  })
})
