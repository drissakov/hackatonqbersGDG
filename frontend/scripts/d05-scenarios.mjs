// Public QA points only. No user GPS, provider payloads or event content is saved.
import { mkdir, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { fileURLToPath } from 'node:url'

export const scenarios = [
  {
    id: '01-walk',
    point: ['Baiterek', 51.1282882, 71.4304546, 'way/230401645'],
    minutes: 30,
    queries: {
      kk: '30 минутқа серуендейтін орын ұсын.',
      ru: 'Предложи место для прогулки на 30 минут.',
      en: 'Suggest a place for a 30-minute walk.',
    },
  },
  {
    id: '02-outlet',
    point: ['Khan Shatyr', 51.1325089, 71.4038726, 'way/460703779'],
    minutes: 90,
    queries: {
      kk: 'Розеткасы бар кофехана керек, ноутбукты қуаттағым келеді.',
      ru: 'Нужна кофейня с розеткой, хочу зарядить ноутбук.',
      en: 'I need a coffee shop with a power outlet to charge my laptop.',
    },
  },
  {
    id: '03-child',
    point: ['Chaplin Cinema EXPO', 51.0883192, 71.40973, 'node/5880883097'],
    minutes: 90,
    queries: {
      kk: 'Алты жастағы баламен баруға болатын мұражай ұсын. Жас шектеуі белгісіз болса, айт.',
      ru: 'Предложи музей для посещения с шестилетним ребенком. Скажи, если возрастные ограничения неизвестны.',
      en: 'Suggest a museum to visit with a six-year-old child. Say if age restrictions are unknown.',
    },
  },
  {
    id: '04-return',
    point: ['National Museum', 51.1182297, 71.4693823, 'node/4894937300'],
    minutes: 120,
    returnToStart: true,
    queries: {
      kk: 'Мен туристпін. Бір көрікті жерге барып, 120 минут ішінде бастапқы нүктеге қайтқым келеді.',
      ru: 'Я турист. Хочу посетить одну достопримечательность и вернуться в исходную точку за 120 минут.',
      en: 'I am a tourist. I want to visit one landmark and return to the starting point within 120 minutes.',
    },
  },
  {
    id: '05-indoor',
    point: ['Saken Seifullin Museum', 51.1714825, 71.4235922, 'way/240376692'],
    minutes: 90,
    indoor: true,
    queries: {
      kk: 'Тек ғимарат ішінде болатын көрме немесе мұражай керек.',
      ru: 'Нужна выставка или музей только внутри помещения.',
      en: 'I need an exhibition or museum strictly indoors.',
    },
  },
  {
    id: '06-budget',
    point: ['Koktal 2', 51.1942364, 71.3361409, 'node/4933998230'],
    minutes: 90,
    budget: 3000,
    queries: {
      kk: 'Түскі асқа бір адамға 3000 теңгеден аспайтын орын керек.',
      ru: 'Нужно место для обеда с бюджетом не более 3000 тенге на человека.',
      en: 'I need a lunch place costing no more than 3000 tenge per person.',
    },
  },
  {
    id: '07-late',
    point: ['Baqytbek Arena', 51.1289349, 71.2564542, 'way/1102228687'],
    minutes: 90,
    date: '2026-10-24T23:30:00+05:00',
    queries: {
      kk: '2026 жылғы 24 қазанда сағат 23:30-да кофе ішетін орын керек. Ашық екенін тексер.',
      ru: 'Нужно место выпить кофе 24 октября 2026 года в 23:30. Проверь часы работы.',
      en: 'I need a place for coffee at 23:30 on 24 October 2026. Check opening hours.',
    },
  },
  {
    id: '08-event',
    point: [
      'Railway History Museum',
      51.1122858,
      71.5316883,
      'node/13948916190',
    ],
    minutes: 360,
    mode: 'events',
    date: '2026-10-24T18:00:00+05:00',
    queries: {
      kk: '2026 жылғы 24 қазанда сағат 18:00-ден кейін Астана Операдағы концертті тап.',
      ru: 'Найди концерт в Астана Опера 24 октября 2026 года после 18:00.',
      en: 'Find a concert at Astana Opera after 18:00 on 24 October 2026.',
    },
  },
  {
    id: '09-conflict',
    point: [
      'Airport-area Starbucks',
      51.0268214,
      71.4613139,
      'node/10976892637',
    ],
    minutes: 30,
    budget: 0,
    queries: {
      kk: 'Мұражайда кемінде екі сағат болғым келеді, бірақ жалпы уақытым 30 минут, бюджетім 0 теңге.',
      ru: 'Хочу провести в музее не менее двух часов, но всего есть 30 минут и бюджет 0 тенге.',
      en: 'I want to spend at least two hours in a museum, but I have only 30 minutes total and a budget of 0 tenge.',
    },
  },
  {
    id: '10-missing',
    point: [
      'Shanghai public POI reference (not supplied)',
      51.205116,
      71.4785643,
      'node/10581496518',
    ],
    missing: true,
    queries: {
      kk: 'Мұражай ұсын. Бастапқы нүкте, уақыт және бюджет әзірге белгісіз. Белгісіз деректерді ойдан шығарма.',
      ru: 'Предложи музей. Исходная точка, время и бюджет пока неизвестны. Не выдумывай отсутствующие данные.',
      en: 'Suggest a museum. Starting point, time and budget are unknown for now. Do not invent missing data.',
    },
  },
]

export function inputFor(scenario, locale) {
  return {
    request_id: randomUUID(),
    query: scenario.queries[locale],
    locale,
    origin: scenario.missing
      ? null
      : { latitude: scenario.point[1], longitude: scenario.point[2] },
    available_minutes: scenario.minutes ?? null,
    budget_kzt_per_person: scenario.budget ?? null,
    date_time:
      scenario.date ?? (scenario.missing ? null : '2026-10-24T14:00:00+05:00'),
    return_to_start: scenario.returnToStart ?? false,
    indoor_only: scenario.indoor ?? false,
    explicit_fields: [
      'origin',
      'available_minutes',
      'budget_kzt_per_person',
      'date_time',
      'return_to_start',
      'indoor_only',
    ],
  }
}

export const aliases = [
  {
    id: 'A1-mixed',
    base: '02-outlet',
    locale: 'kk',
    query: 'Кофе керек, нужна розетка, power outlet for laptop.',
  },
  {
    id: 'A2-nursultan',
    base: '10-missing',
    locale: 'en',
    query:
      'Suggest a museum in Nur-Sultan (Astana); time, origin and budget are unknown.',
  },
  {
    id: 'A3-baiterek',
    base: '04-return',
    locale: 'ru',
    query:
      'Я турист, хочу увидеть Бәйтерек / Baiterek / Байтерек и вернуться за 120 минут.',
  },
  {
    id: 'A4-mixed-event',
    base: '08-event',
    locale: 'ru',
    query: 'Astana Opera / Астана Опера, концерт 24 October 2026 после 18:00.',
  },
]

function summarize(body, event) {
  return {
    status: body.status ?? null,
    contract_version: body.contract_version ?? null,
    warnings: (body.warnings ?? []).map(({ code, fields }) => ({
      code,
      fields: fields ?? [],
    })),
    provider_status: body.provider_status ?? null,
    provider_code: body.provider_code ?? null,
    live_web_search: body.live_web_search ?? null,
    item_count: body.items?.length ?? null,
    listing_count: body.listings?.length ?? null,
    source_count: body.sources?.length ?? null,
    // Retain stable codes/counts only for transient event output, never its content.
    cards: (body.items ?? []).map((card) => ({
      ...(event
        ? {}
        : {
            id: card.poi?.id,
            name: card.poi?.name,
            activity: card.activity_code,
            indoor: card.poi?.indoor,
            price: card.poi?.price_kzt_per_person,
            opening_hours: card.poi?.opening_hours,
            source_urls: card.poi?.sources?.map((source) => source.url),
          }),
      fit: card.fit_status,
      route: card.route_status,
      travel: card.travel_minutes_estimate,
      visit: card.visit_minutes_estimate,
      missing: card.missing_fields,
      reasons: card.reason_codes,
      generated_locale: card.generated_locale,
    })),
    error_code: body.error?.code ?? null,
  }
}

export function assess(receipt) {
  const actual = receipt.actual
  if (receipt.protocol_error)
    return { status: 'failed', reason: receipt.protocol_error }
  if (receipt.transport) return { status: 'not_run', reason: receipt.transport }
  if (!receipt.correlated || receipt.cache_control !== 'no-store')
    return { status: 'failed', reason: 'correlation_or_cache_policy' }
  if (
    !actual ||
    ![200, 503].includes(receipt.http) ||
    (receipt.http === 503) !== (actual.status === 'unavailable') ||
    !Number.isInteger(actual.item_count) ||
    actual.item_count < 0 ||
    actual.item_count > 3
  )
    return { status: 'failed', reason: 'invalid_envelope' }
  if (actual.status === 'unavailable')
    return {
      status: 'not_run',
      reason: 'provider_unavailable; failure handling observed separately',
    }
  if (receipt.id.startsWith('02-outlet-') || receipt.id === 'A1-mixed')
    return actual.status === 'unknown' &&
      actual.item_count === 0 &&
      actual.source_count === 0 &&
      actual.warnings.some(({ code }) => code === 'missing_input')
      ? {
          status: 'passed',
          reason:
            'unsupported outlet requirement remains unknown, no invented source',
        }
      : {
          status: 'failed',
          reason: 'outlet requirement silently accepted or missing uncertainty',
        }
  // A non-empty HTTP 200 still requires a human semantic/source/hard-filter review.
  return { status: 'not_run', reason: 'manual_semantic_review_required' }
}

export async function runScenarios() {
  const base = process.env.D05_API_BASE ?? 'http://127.0.0.1:8000'
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))
    throw new Error('Local QA endpoint required')
  const cases = scenarios.flatMap((scenario) =>
    ['kk', 'ru', 'en'].map((locale) => ({
      id: `${scenario.id}-${locale}`,
      path:
        scenario.mode === 'events'
          ? '/api/events/search'
          : '/api/recommendations',
      input: inputFor(scenario, locale),
    })),
  )
  for (const alias of aliases) {
    const scenario = scenarios.find(({ id }) => id === alias.base)
    cases.push({
      id: alias.id,
      path:
        scenario.mode === 'events'
          ? '/api/events/search'
          : '/api/recommendations',
      input: { ...inputFor(scenario, alias.locale), query: alias.query },
    })
  }
  const output = fileURLToPath(
    new URL('../artifacts/d05/api-results.json', import.meta.url),
  )
  await mkdir(fileURLToPath(new URL('../artifacts/d05', import.meta.url)), {
    recursive: true,
  })
  const results = []
  async function run(item) {
    const started = Date.now()
    const receipt = { ...item, checked_at: new Date().toISOString() }
    try {
      const response = await fetch(`${base}${item.path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item.input),
        signal: AbortSignal.timeout(190_000),
      })
      receipt.http = response.status
      receipt.cache_control = response.headers.get('cache-control')
      const body = await response.json()
      Object.assign(receipt, {
        correlated: body.request_id === item.input.request_id,
        actual: summarize(body, item.path.includes('events')),
      })
    } catch (error) {
      if (receipt.http !== undefined)
        receipt.protocol_error = 'invalid_json_or_shape'
      else
        receipt.transport =
          error.name === 'TimeoutError' ? 'timeout' : 'network'
    }
    receipt.elapsed_seconds = Math.round((Date.now() - started) / 10) / 100
    receipt.evaluation = assess(receipt)
    results.push(receipt)
    console.log(
      JSON.stringify({
        id: item.id,
        http: receipt.http,
        status: receipt.actual?.status,
        items: receipt.actual?.item_count,
        sources: receipt.actual?.source_count,
        seconds: receipt.elapsed_seconds,
        transport: receipt.transport,
      }),
    )
  }
  // Two requests maximum; each pair finishes before starting another pair.
  for (let index = 0; index < cases.length; index += 2) {
    await Promise.all(cases.slice(index, index + 2).map(run))
    // One writer owns each complete snapshot; requests never race on this file.
    await writeFile(
      output,
      JSON.stringify({ base, base_commit: '181e012', results }, null, 2) + '\n',
    )
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1])
  await runScenarios()
