import { chromium } from '@playwright/test'
const S = process.env.S
const text = `München Hbf → Stuttgart Hbf
Sun 13.09.2026
ICE 690 (690)
To Stuttgart Hbf
From 09:55 München Hbf, Platform 23
To 12:07 Stuttgart Hbf, Platform 8`
const b = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
const ctx = await b.newContext({ viewport: { width: 414, height: 850 }, serviceWorkers: 'block' })
const p = await ctx.newPage()
const errors = []
p.on('pageerror', e => errors.push(e.message))
p.on('console', m => { if (m.type() === 'error' || /\[route\]|3D trains/.test(m.text())) errors.push(m.type() + ': ' + m.text().slice(0, 160)) })
await p.goto(`http://127.0.0.1:5173/share?text=${encodeURIComponent(text)}`)
await p.waitForFunction(() => !document.querySelector('.travel-status') && document.querySelectorAll('.station-marker').length >= 2, null, { timeout: 60000 })
const info = async () => p.evaluate(() => {
  const m = document.querySelector('.map-root')
  return { markers: [...document.querySelectorAll('.station-marker')].map(e => e.getAttribute('aria-label')), title: !!document.querySelector('.travel-map-title'), note: !!document.querySelector('.geometry-note'), follow: document.querySelector('.map-controls .follow')?.getAttribute('aria-pressed'), basemap: m?.dataset.basemap }
})
console.log('after load:', JSON.stringify(await info()))
await p.waitForTimeout(4000); await p.screenshot({ path: `${S}/trains-1.png` })
const geom = await p.evaluate(() => { const a = document.querySelector('.map-root'); return a ? 'ok' : 'no' })
await p.waitForTimeout(9000); await p.screenshot({ path: `${S}/trains-2.png` })
await p.waitForTimeout(12000); await p.screenshot({ path: `${S}/trains-3.png` })
await p.locator('.map-controls .follow').click(); await p.locator('.map-controls [aria-label="Fit whole journey"]').click()
await p.waitForTimeout(3500); await p.screenshot({ path: `${S}/trains-fit.png` })
console.log('errors:', errors.length ? errors : 'none')
await b.close()
