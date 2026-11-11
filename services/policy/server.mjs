import http from 'node:http'
import { operation } from './domain.mjs'

const port = Number(process.env.PORT)
const path = process.env.OPERATION_PATH
const host = process.env.HOST ?? '127.0.0.1'
const limit = 64 * 1024

function reply(response, status, body) {
  response.writeHead(status, { 'Content-Type': 'application/json' })
  response.end(JSON.stringify(body))
}

async function upstream(data) {
  const response = await fetch(process.env.UPSTREAM_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal: AbortSignal.timeout(2500),
  }).catch(() => null)
  if (!response) throw Object.assign(new Error('Dependency unavailable'), { status: 502 })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    const status = [400, 409, 422].includes(response.status) ? response.status : 502
    throw Object.assign(new Error(status === 502 ? 'Dependency failed' : error.error), { status })
  }
  return response.json()
}

http.createServer(async (request, response) => {
  if (request.method === 'GET' && request.url === '/health') {
    return reply(response, 200, { status: 'up' })
  }
  if (request.method !== 'POST' || request.url !== path) {
    return reply(response, 404, { error: 'Unknown route' })
  }
  try {
    const chunks = []
    let size = 0
    for await (const chunk of request) {
      size += chunk.length
      if (size <= limit) chunks.push(chunk)
    }
    if (size > limit) return reply(response, 413, { error: 'Payload too large' })
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
      return reply(response, 400, { error: 'Expected a JSON object' })
    }
    reply(response, 200, await operation(body, upstream))
  } catch (error) {
    const status = error.status ?? (error instanceof SyntaxError || error instanceof TypeError ? 400 : 500)
    if (status === 500) console.error(error)
    reply(response, status, { error: status === 500 ? 'Service failed' : error.message })
  }
}).listen(port, host)
