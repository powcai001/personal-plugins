// test/cli.test.js
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
  return execFileSync('node', [BIN, ...args], { encoding: 'utf8', input: input || '' });
}

function seedState(d, over) {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  Object.assign(s, over || {});
  fs.writeFileSync(path.join(d, 'state.json'), JSON.stringify(s));
  return s;
}

test('status：建档后面板含 Lv 与形态', () => {
  freshDir();
  run(['session']);
  const out = run(['status']);
  assert.ok(out.includes('Lv.1'));
  assert.ok(out.includes('🥚'));
});

test('statusline：无档时渲染蛋且不落盘', () => {
  const d = freshDir();
  const out = run(['statusline']);
  assert.ok(out.includes('🥚'));
  assert.ok(out.includes('Lv.1'));
  assert.equal(fs.existsSync(path.join(d, 'state.json')), false);
});

test('feed：无零食提示', () => {
  freshDir();
  run(['session']);
  const out = run(['feed']);
  assert.ok(out.includes('没有零食'));
});

test('feed：有零食扣 1 加经验', () => {
  freshDir();
  run(['session']);
  seedState(process.env.PET_STATE_DIR, { snacks: 2, level: 2, xp: 0 });
  const out = run(['feed']);
  assert.ok(out.includes('+7'));
  const st = stateIo.loadState();
  assert.equal(st.snacks, 1);
});

test('pet：摸头有反应文案', () => {
  freshDir();
  run(['session']);
  const out = run(['pet']);
  assert.ok(out.trim().length > 0);
});

test('rebirth：未满级拒绝', () => {
  freshDir();
  run(['session']);
  const out = run(['rebirth']);
  assert.ok(out.includes('还未满级'));
});

test('未知子命令 exit 0 且有 usage', () => {
  freshDir();
  const out = run([]);
  assert.ok(out.includes('用法'));
});
