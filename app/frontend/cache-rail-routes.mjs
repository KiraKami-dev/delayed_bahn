import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { createServer } from 'vite'

const server = await createServer({ root: fileURLToPath(new URL('.', import.meta.url)), server: { middlewareMode: true }, appType: 'custom' })
try {
  const { mappedRouteForLeg, joinRouteWays, expandOsmRelation } = await server.ssrLoadModule('/src/lib/osm-route.ts')
  const { buildTrack } = await server.ssrLoadModule('/src/lib/track-path.ts')
  const journey = JSON.parse(await readFile(new URL('./public/seed/journey.json', import.meta.url), 'utf8'))
  const routes = []
  for (const [index, relationId] of [12144600, 1843976].entries()) {
    const leg = journey.legs[index]
    const input = process.argv[index + 2]
    const response = input ? await readFile(input, 'utf8') : execFileSync('curl', [
      '--fail', '--silent', '--show-error', '--max-time', '45',
      '--user-agent', 'error404-rail-map/0.1 (+https://github.com/KiraKami-dev/temporal_ai_error404.ai)',
      `https://www.openstreetmap.org/api/0.6/relation/${relationId}/full.json`,
    ], { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 })
    const data = JSON.parse(response.slice(0, response.lastIndexOf('}') + 1))
    assert.ok(!data.remark && Array.isArray(data.elements), 'The route response must be complete')
    const relation = expandOsmRelation(data.elements, relationId)
    assert.ok(relation, 'The requested service relation must be present')
    const candidates = [mappedRouteForLeg(relation, leg, data.osm3s?.timestamp_osm_base ?? '')].filter(Boolean)
    if (!candidates.length) console.log('Continuity diagnostics', { id: relation.id, ref: relation.tags?.ref, connected: Boolean(joinRouteWays(relation.members)) })
    assert.equal(candidates.length, 1, `Exactly one continuous mapped service route must match ${leg.trainId}`)
    const route = candidates[0]
    console.log(`${leg.trainId}: relation ${route.relationId}, ${route.coordinates.length} track points, ${(buildTrack(route.coordinates).length / 1000).toFixed(1)} km`)
    routes.push(route)
  }
  const output = { source: 'OpenStreetMap', attribution: '© OpenStreetMap contributors', license: 'ODbL-1.0', generatedAt: new Date().toISOString(), routes }
  await writeFile(new URL('./public/seed/mapped-routes.json', import.meta.url), JSON.stringify(output) + '\n')
  console.log('Saved mapped example routes. These are service paths, not live train diversions.')
} finally {
  await server.close()
}
