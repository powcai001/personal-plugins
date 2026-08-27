// test/hooks.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const stateIo = require('../lib/state');
const engine = require('../lib/engine');
const { FALLBACK_STAGES } = require('../lib/species');

const BIN = path.join(__dirname, '..', 'bin', 'claude-pet');
const NOW = '2026-08-27T00:00:00.000Z';

function freshDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-pet-test-'));
  process.env.PET_STATE_DIR = d;
  return d;
}

function run(args, input) {
  return execFileSync('node', [BIN, ...args], { encoding: 'utf8', input: input === undefined ? '{}' : input });
}

test('session：建档且平时无输出', () => {
  const d = freshDir();
  const out = run(['session']);
  assert.equal(out.trim(), '');
  assert.ok(fs.existsSync(path.join(d, 'state.json')));
});

test('session：超 48 小时输出想念语', () => {
  const d = freshDir();
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.lastActive = '2026-08-20T00:00:00.000Z'; // 7 天前
  fs.writeFileSync(path.join(d, 'state.json'), JSON.stringify(s));
  const out = run(['session']);
  assert.ok(out.includes('想你了'));
});

test('stop：进化时输出 systemMessage JSON', () => {
  const d = freshDir();
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 2; s.xp = engine.xpForLevel(2) - 10; s.stage = 0; s.stageAtTurnStart = 0;
  fs.writeFileSync(path.join(d, 'state.json'), JSON.stringify(s));
  const out = run(['stop']);
  const parsed = JSON.parse(out);
  assert.ok(parsed.systemMessage.includes('进化'));
});

test('stop：未进化时无输出', () => {
  freshDir();
  run(['session']);
  const out = run(['stop']);
  assert.equal(out.trim(), '');
});

test('stdin 非法 JSON 仍 exit 0', () => {
  freshDir();
  run(['session']);
  const out = run(['tool'], 'not-json-at-all');
  assert.equal(out.trim(), '');
  const st = stateIo.loadState();
  assert.equal(st.xp, 2); // 事件仍生效
});
