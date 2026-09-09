/**
 * Fail the build if a server-only credential reached the browser bundle.
 *
 * Runs as `postbuild`, so it guards every `npm run build` — including the one
 * Vercel runs on deploy. A leak here is not a bug that shows up later as odd
 * behaviour: the Supabase secret key bypasses every row-level security policy
 * in the database, so publishing it once means anyone who views source can
 * read and rewrite every table. It is worth failing a deploy over.
 *
 * The check is deliberately narrow. `supabase-js` itself contains the literal
 * strings "sb_publishable_" and "sb_secret_" in a helper that tests what
 * prefix a key has, so matching the bare prefix flags the library on every
 * build and trains everyone to ignore the alarm. These patterns require the
 * key material that follows a prefix, which the library's own literals do not
 * have.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const DIST = new URL('../dist', import.meta.url).pathname

// A prefix on its own is the library's; a prefix plus key material is a key.
const SECRET_KEY = /sb_secret_[A-Za-z0-9_-]{8,}/

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

/**
 * Legacy service_role keys are JWTs, so the prefix check can't see them.
 * Decode any JWT-shaped run and look at what role it claims.
 */
function serviceRoleJwt(text) {
  for (const [match, payload] of text.matchAll(/eyJ[A-Za-z0-9_-]{8,}\.([A-Za-z0-9_-]{8,})\./g)) {
    try {
      const claims = JSON.parse(Buffer.from(payload, 'base64url').toString())
      if (claims.role === 'service_role') return match.slice(0, 24) + '…'
    } catch {
      // Not a JWT after all — a base64-ish run in minified code.
    }
  }
  return null
}

let failures = 0

for (const file of walk(DIST)) {
  if (!/\.(js|css|html|json|map)$/.test(file)) continue
  const text = readFileSync(file, 'utf8')
  const relative = file.slice(DIST.length + 1)

  const key = text.match(SECRET_KEY)
  if (key) {
    console.error(`\n  ${relative}: a Supabase secret key is in the bundle`)
    console.error(`    found: ${key[0].slice(0, 20)}…`)
    failures++
  }

  const jwt = serviceRoleJwt(text)
  if (jwt) {
    console.error(`\n  ${relative}: a service_role JWT is in the bundle`)
    console.error(`    found: ${jwt}`)
    failures++
  }
}

if (failures) {
  console.error(`
  A server-only credential was compiled into the browser bundle.

  Only VITE_-prefixed variables reach the client, so this means a secret was
  given a VITE_ name. Check Vercel's environment variables: the secret key
  belongs to SUPABASE_SERVICE_KEY and nothing else. Rotate the exposed key in
  the Supabase dashboard before redeploying — it has been built, and may have
  been served.
`)
  process.exit(1)
}

console.log('No server-only credentials in the bundle.')
