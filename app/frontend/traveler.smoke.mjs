import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { chromium } from '@playwright/test'

const base = process.env.FRONTEND_URL || 'http://127.0.0.1:5174'
const seed = async (name) => JSON.parse(await readFile(new URL(`./public/seed/${name}.json`, import.meta.url), 'utf8'))
let browser
before(async () => { browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) }) })
after(async () => { await browser?.close() })

async function pageFor(t, width = 1440, height = 1000) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  t.after(() => context.close())
  const page = await context.newPage()
  await page.route(/https:\/\/(server\.arcgisonline\.com|tiles\.openfreemap\.org)/, route => route.abort())
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('requestfailed', request => { if (request.url().includes('maplibre-gl-worker')) errors.push('Map worker failed to load') })
  t.after(() => assert.deepEqual(errors, [], 'No browser runtime errors'))
  return page
}

test('a failed share request preserves the input instead of substituting a demo', async t => {
  const page = await pageFor(t)
  await page.route('**/api/**', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"Service unavailable"}' }))
  await page.goto(base)
  const input = page.locator('textarea')
  await input.fill('My Berlin to Hamburg journey')
  await page.getByRole('button', { name: /Check my (plan|trip)/ }).click()
  await page.getByRole('alert').waitFor()
  assert.equal(await input.inputValue(), 'My Berlin to Hamburg journey')
  assert.equal(await page.getByText('Nürnberg Hbf → München Flughafen Terminal', { exact: true }).count(), 0)
})

test('an explicit demo works offline and is visibly labelled', async t => {
  const page = await pageFor(t)
  await page.route('**/api/**', route => route.abort())
  await page.goto(base)
  await page.getByRole('button', { name: /Try an example trip/ }).click()
  await page.getByText('Example trip · not live travel advice', { exact: true }).waitFor()
  await page.getByRole('heading', { name: 'Your connection outlook' }).waitFor()
  assert.match(await page.locator('.outlook-number').innerText(), /^38%/)
})

test('real trip prediction failures never reuse the bundled forecast', async t => {
  const page = await pageFor(t)
  const journey = await seed('journey')
  journey.id = 'traveler-trip'
  journey.source = 'db-share'
  await page.route('**/api/journeys/parse', route => route.fulfill({ json: journey }))
  await page.route('**/api/predict', route => route.fulfill({ status: 503, json: { error: 'Unavailable' } }))
  await page.goto(base)
  await page.locator('textarea').fill('My own trip')
  await page.getByRole('button', { name: /Check my (plan|trip)/ }).click()
  await page.getByRole('alert').waitFor()
  assert.equal(await page.locator('.outlook-number').count(), 0)
  assert.equal(await page.getByText('Example trip · not live travel advice', { exact: true }).count(), 0)
})

for (const [width, height] of [[320, 844], [375, 844], [768, 1024], [1024, 900], [1440, 1000], [844, 390]]) {
  test(`traveler form stays accessible at ${width}x${height}`, async t => {
    const page = await pageFor(t, width, height)
    await page.goto(base)
    assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme), 'light')
    await page.getByRole('button', { name: 'From → To' }).click()
    await page.getByRole('combobox', { name: 'From station', exact: true }).waitFor()
    await page.getByRole('combobox', { name: 'From station', exact: true }).fill('Berlin')
    await page.getByRole('combobox', { name: 'From station', exact: true }).press('ArrowDown')
    await page.getByRole('combobox', { name: 'From station', exact: true }).press('Enter')
    assert.match(await page.getByRole('combobox', { name: 'From station', exact: true }).inputValue(), /Berlin/)
    await page.getByRole('button', { name: 'Find my route', exact: true }).scrollIntoViewIfNeeded()
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  })
}

test('help dialog supports Escape and restores keyboard focus', async t => {
  const page = await pageFor(t)
  await page.goto(base)
  const trigger = page.getByRole('button', { name: 'How it works', exact: true })
  await trigger.click()
  await page.getByRole('dialog').waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await page.getByRole('dialog').isVisible(), false)
  assert.equal(await trigger.evaluate(el => el === document.activeElement), true)
})

test('a shared journey URL retains its text if the parser is unavailable', async t => {
  const page = await pageFor(t)
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { error: 'Unavailable' } }))
  await page.goto(`${base}/share?text=${encodeURIComponent('Berlin Hbf to Hamburg Hbf, my saved journey')}`)
  await page.getByRole('alert').waitFor()
  assert.equal(await page.locator('textarea').inputValue(), 'Berlin Hbf to Hamburg Hbf, my saved journey')
  assert.equal(new URL(page.url()).searchParams.has('text'), false)
})

test('changing a selected station clears the old selection', async t => {
  const page = await pageFor(t)
  await page.goto(base)
  await page.getByRole('button', { name: 'From → To' }).click()
  assert.equal(await page.locator('input').count(), 2)
  for (const [label, query] of [['From station', 'Berlin'], ['To station', 'Hamburg']]) {
    const field = page.getByRole('combobox', { name: label, exact: true })
    await field.fill(query)
    await field.press('ArrowDown')
    await field.press('Enter')
  }
  assert.equal(await page.getByRole('button', { name: 'Find my route', exact: true }).isEnabled(), true)
  await page.getByRole('combobox', { name: 'From station', exact: true }).fill('Not a known station')
  assert.equal(await page.getByRole('button', { name: 'Find my route', exact: true }).isEnabled(), false)
})

test('German travel times handle summer, winter and nonexistent daylight-saving times', async t => {
  const page = await pageFor(t)
  await page.goto(base)
  const result = await page.evaluate(async () => {
    const { germanTime } = await import('/src/features/share-parser/components/JourneyBuilder.tsx')
    let rejected = false
    try { germanTime('2026-03-29', '02:30') } catch { rejected = true }
    return [germanTime('2026-01-13', '10:00'), germanTime('2026-09-13', '10:00'), rejected]
  })
  assert.deepEqual(result, ['2026-01-13T09:00:00.000Z', '2026-09-13T08:00:00.000Z', true])
})

test('reset prevents a delayed forecast from restoring the previous trip', async t => {
  const page = await pageFor(t)
  const journey = await seed('journey')
  journey.source = 'db-share'
  let release
  const gate = new Promise(resolve => { release = resolve })
  const prediction = await seed('prediction')
  await page.route('**/api/journeys/parse', route => route.fulfill({ json: journey }))
  await page.route('**/api/predict', async route => { await gate; await route.fulfill({ json: prediction }) })
  await page.goto(base)
  await page.locator('textarea').fill('My own trip')
  await page.getByRole('button', { name: 'Check my trip', exact: true }).click()
  await page.getByRole('button', { name: 'Check another trip' }).click()
  const response = page.waitForResponse('**/api/predict')
  release()
  await response
  await page.waitForTimeout(150)
  assert.equal(await page.locator('.outlook-number').count(), 0)
  assert.equal(await page.locator('textarea').isVisible(), true)
})

test('advice failure retains the matched forecast without inventing a replacement', async t => {
  const page = await pageFor(t)
  const journey = await seed('journey')
  journey.source = 'db-share'
  await page.route('**/api/journeys/parse', route => route.fulfill({ json: journey }))
  await page.route('**/api/predict', async route => route.fulfill({ json: await seed('prediction') }))
  await page.route('**/api/recommend', route => route.fulfill({ status: 503, json: { error: 'Unavailable' } }))
  await page.goto(base)
  await page.locator('textarea').fill('My trip')
  await page.getByRole('button', { name: 'Check my trip', exact: true }).click()
  await page.getByRole('alert').waitFor()
  assert.match(await page.locator('.outlook-number').innerText(), /^38%/)
  await page.getByRole('button', { name: 'Travel advice', exact: true }).click()
  await page.getByText('Travel advice isn’t available yet.', { exact: false }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Compare alternative' }).count(), 0)
})

test('map controls and trip tabs work when map tiles fail', async t => {
  const page = await pageFor(t)
  await page.goto(`${base}/?demo=1`)
  await page.getByRole('heading', { name: 'Your connection outlook' }).waitFor()
  await page.getByRole('button', { name: 'Switch to 3D map' }).click()
  await page.getByRole('button', { name: 'Switch to flat map' }).waitFor()
  await page.getByRole('button', { name: 'Fit whole journey' }).click()
  await page.getByRole('button', { name: 'Train details', exact: true }).click()
  await page.getByRole('slider', { name: 'Extra minutes at each change' }).fill('15')
  await page.getByRole('button', { name: 'Travel advice', exact: true }).click()
  await page.getByRole('button', { name: 'Compare alternative' }).click()
  await page.getByRole('heading', { name: 'Timing scenario · not a verified train' }).waitFor()
  await page.getByRole('button', { name: 'Hide 3D route' }).click()
  assert.equal(await page.locator('.maplibregl-canvas').count(), 0)
})

test('journey results fit every requested responsive viewport', async t => {
  const page = await pageFor(t, 375, 844)
  await page.goto(`${base}/?demo=1`)
  await page.getByRole('heading', { name: 'Your connection outlook' }).waitFor()
  for (const [width, height] of [[320, 844], [375, 844], [768, 1024], [1024, 900], [1440, 1000], [844, 390]]) {
    await page.setViewportSize({ width, height })
    for (const name of ['Your journey', 'Train details', 'Travel advice']) {
      await page.getByRole('button', { name, exact: true }).click()
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name} at ${width}x${height}`)
    }
  }
})

test('direct journeys show arrival delay, not a misleading zero connection risk', async t => {
  const page = await pageFor(t)
  const journey = await seed('journey')
  journey.legs = journey.legs.slice(0, 1)
  journey.source = 'db-share'
  const prediction = await seed('prediction')
  prediction.legs = prediction.legs.slice(0, 1)
  prediction.planFailProbability.value = 0
  await page.route('**/api/journeys/parse', route => route.fulfill({ json: journey }))
  await page.route('**/api/predict', route => route.fulfill({ json: prediction }))
  await page.route('**/api/recommend', route => route.fulfill({ status: 503, json: { error: 'Unavailable' } }))
  await page.goto(base)
  await page.locator('textarea').fill('Direct journey')
  await page.getByRole('button', { name: 'Check my trip', exact: true }).click()
  await page.getByRole('heading', { name: 'One train. No changes to make.' }).waitFor()
  assert.match(await page.locator('.outlook-number').innerText(), /^\+7/)
  await page.getByRole('button', { name: 'Train details', exact: true }).click()
  assert.equal(await page.getByText('Probability your plan fails', { exact: true }).count(), 0)
})

test('WebGL-unavailable browsers still get the full trip summary', async t => {
  const page = await pageFor(t)
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (kind, ...args) { return String(kind).includes('webgl') ? null : original.call(this, kind, ...args) }
  })
  await page.goto(`${base}/?demo=1`)
  await page.getByText('The interactive map isn’t supported by this browser.', { exact: false }).waitFor()
  await page.getByRole('heading', { name: 'Your trains, step by step.' }).waitFor()
  assert.match(await page.locator('.outlook-number').innerText(), /^38%/)
})

test('Higgsfield homepage reveals a globe and explains the example connections', async t => {
  const page = await pageFor(t)
  await page.route('**/api/**', route => route.abort())
  await page.goto(base)
  const art = page.locator('img[src="/rail-globe.png"]')
  await art.waitFor()
  assert.ok(await art.evaluate(el => el.complete && el.naturalWidth > 0), 'Generated artwork loads locally')
  await page.screenshot({ path: '/tmp/rail-homepage.png', fullPage: true })
  await page.getByRole('button', { name: 'Explore the interactive globe' }).click()
  await page.locator('.globe-preview .map-frame').waitFor()
  await page.getByRole('button', { name: /Try an example trip/ }).click()
  await page.getByRole('heading', { name: 'Follow your connection story.' }).waitFor()
  assert.ok(await page.locator('.story-train').count() > 0)
  await page.getByRole('button', { name: 'Replay', exact: true }).click()
  await page.getByRole('button', { name: 'Find a calmer plan' }).click()
  await page.screenshot({ path: '/tmp/rail-journey.png', fullPage: true })
})

for (const outage of [false, true]) test(`mobile two-station search ${outage ? 'preserves stations on outage' : 'returns a selectable connection'}`, async t => {
  const page = await pageFor(t, 375, 844)
  await page.route('https://v6.db.transport.rest/journeys?**', route => outage ? route.fulfill({ status: 503 }) : route.fulfill({ json: { journeys: [{ legs: [{ line: { name: 'ICE 100', mode: 'train' }, origin: { id: '8011160', name: 'Berlin Hbf' }, destination: { id: '8002549', name: 'Hamburg Hbf' }, plannedDeparture: '2026-09-13T10:00:00+02:00', plannedArrival: '2026-09-13T12:00:00+02:00' }] }] } }))
  await page.goto(base)
  assert.equal(await page.locator('input').count(), 2)
  for (const [label, query] of [['From station', 'Berlin'], ['To station', 'Hamburg']]) {
    const field = page.getByRole('combobox', { name: label, exact: true })
    await field.fill(query); await field.press('ArrowDown'); await field.press('Enter')
  }
  await page.screenshot({ path: '/tmp/rail-mobile-stations.png', fullPage: true })
  await page.getByRole('button', { name: 'Find my route' }).click()
  if (outage) {
    await page.getByRole('alert').waitFor()
    assert.match(await page.getByRole('combobox', { name: 'From station', exact: true }).inputValue(), /Berlin/)
    assert.equal(await page.locator('.route-options button').count(), 0)
  } else {
    await page.getByRole('heading', { name: 'Choose a connection' }).waitFor()
    await page.route('**/api/predict', route => route.fulfill({ status: 503 }))
    await page.getByRole('button', { name: /Check this connection/ }).click()
    await page.getByRole('heading', { name: /Berlin Hbf.*Hamburg Hbf/ }).waitFor()
  }
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
})
