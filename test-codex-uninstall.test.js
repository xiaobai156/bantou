'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const test = require('node:test');
const assert = require('node:assert');

const npmDir = path.join(process.env.APPDATA || '', 'npm');

test('codex npm global package fully removed', () => {
  const targets = [
    path.join(npmDir, 'codex'),
    path.join(npmDir, 'codex.cmd'),
    path.join(npmDir, 'node_modules', '@openai', 'codex'),
  ];
  for (const t of targets) {
    assert.strictEqual(fs.existsSync(t), false, `should be gone: ${t}`);
  }
  const entries = fs.readdirSync(npmDir);
  assert.ok(!entries.some((e) => e.toLowerCase().includes('codex')), 'no codex entries in npm dir');
  const r = spawnSync('npm', ['ls', '-g', '--depth=0'], { encoding: 'utf8', shell: true });
  assert.strictEqual(r.status, 0, 'npm ls -g should succeed');
  assert.ok(!r.stdout.includes('@openai/codex'), 'npm global list must not contain @openai/codex');
});
