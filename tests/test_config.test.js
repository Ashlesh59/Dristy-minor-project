const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

function runConfigWithWindow(windowObj) {
  const code = fs.readFileSync(path.join(__dirname, '../js/config.js'), 'utf8');
  const context = { window: windowObj };
  vm.createContext(context);
  vm.runInContext(code, context);
  return context.INVESTIQ_API_BASE;
}

try {
  // Test 1: Localhost appends :5000
  let base1 = runConfigWithWindow({ location: { hostname: 'localhost', protocol: 'http:' }});
  assert.strictEqual(base1, 'http://localhost:5000', 'localhost should append :5000');

  // Test 2: 127.0.0.1 appends :5000
  let base2 = runConfigWithWindow({ location: { hostname: '127.0.0.1', protocol: 'http:' }});
  assert.strictEqual(base2, 'http://127.0.0.1:5000', '127.0.0.1 should append :5000');

  // Test 3: Production Vercel domain does NOT append port
  let base3 = runConfigWithWindow({ location: { hostname: 'investiq-preview.vercel.app', protocol: 'https:' }});
  assert.strictEqual(base3, 'https://investiq-preview.vercel.app', 'Production should not append port');

  // Test 4: Explicit override is respected
  let base4 = runConfigWithWindow({ location: { hostname: 'localhost', protocol: 'http:' }, INVESTIQ_API_BASE: 'https://custom.api' });
  assert.strictEqual(base4, 'https://custom.api', 'Explicit override should be respected');

  console.log('✔ config.js resolves API base URL correctly for local and production');
} catch (e) {
  console.error('config.js tests failed:', e);
  process.exit(1);
}
