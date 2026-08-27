// test/concurrency.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, execFileSync } = require('child_process');
const stateIo = require('../lib/state');
const store = require('../lib/store');
const engine = require('../lib/engine');

const NOW = '2026-08-27T00:00:00.000Z';
const BIN = path.join(__dirname, '..', 'bin', 'claude-pet');

function freshDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-pet-test-'));
  process.env.PET_STATE_DIR = d;
  return d;
}

test('runHookEvent 首次写入自动建档', () => {
  freshDir();
  const r = store.runHookEvent({ type: 'prompt', ts: NOW });
  assert.equal(r.ok, true);
  const st = stateIo.loadState();
  assert.equal(st.level, 1);
  assert.equal(st.xp, 5);
});

test('applyEvent: stop 事件用事件内 roll 折叠', () => {
  const s = engine.newState(NOW, store.STAGES);
  store.applyEvent(s, { type: 'stop', roll: 0.1, ts: NOW });
  assert.equal(s.xp, 10);
  assert.equal(s.snacks, 1); // roll 0.1 < 0.25
});

test('锁被占：hook 事件进 overflow，下次写入时折叠合并', () => {
  const d = freshDir();
  fs.mkdirSync(path.join(d, 'lock'));
  const r = store.runHookEvent({ type: 'prompt', ts: NOW });
  assert.equal(r.busy, true);
  assert.equal(fs.existsSync(path.join(d, 'overflow.jsonl')), true);
  fs.rmdirSync(path.join(d, 'lock'));
  store.runUserCommand((s) => { engine.applyPet(s, store.STAGES, NOW, () => 0); });
  const st = stateIo.loadState();
  assert.equal(st.xp, 5); // overflow 的 prompt +5 已折进来
  assert.equal(st.petsCount, 1);
  assert.equal(fs.existsSync(path.join(d, 'overflow.jsonl')), false);
});

test('锁被占：用户命令直接提示重试，不写 overflow', () => {
  const d = freshDir();
  fs.mkdirSync(path.join(d, 'lock'));
  const r = store.runUserCommand(() => { throw new Error('不应执行'); });
  assert.equal(r.busy, true);
  assert.ok(r.msg.includes('重试'));
  assert.equal(fs.existsSync(path.join(d, 'overflow.jsonl')), false);
});

test('双进程并发 + 后续一次写入：XP 一条不丢（确定性）', async () => {
  freshDir();
  execFileSync('node', [BIN, 'session'], { input: '' }); // 建档
  const ps = [spawn('node', [BIN, 'tool']), spawn('node', [BIN, 'tool'])];
  ps.forEach((p) => p.stdin.end('{}'));
  const codes = await Promise.all(ps.map((p) => new Promise((res) => p.on('exit', (c) => res(c)))));
  assert.deepEqual(codes, [0, 0]);
  execFileSync('node', [BIN, 'tool'], { input: '{}' }); // 串行最后一次必折叠全部积压
  const st = stateIo.loadState();
  assert.equal(st.xp, 6); // 2 并发 +2 与 1 串行 +2，共 6
  assert.equal(st.toolsThisTurn, 3);
});
