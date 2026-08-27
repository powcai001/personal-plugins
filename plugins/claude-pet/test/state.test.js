'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const stateIo = require('../lib/state');

function freshDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-pet-test-'));
  process.env.PET_STATE_DIR = d;
  return d;
}

test('saveState/loadState 往返', () => {
  freshDir();
  stateIo.saveState({ version: 1, level: 3, xp: 2 });
  assert.deepEqual(stateIo.loadState(), { version: 1, level: 3, xp: 2 });
});

test('state 不存在返回 null', () => {
  freshDir();
  assert.equal(stateIo.loadState(), null);
});

test('state 损坏：备份后返回 null', () => {
  const d = freshDir();
  fs.writeFileSync(path.join(d, 'state.json'), '{broken json');
  assert.equal(stateIo.loadState(), null);
  const backups = fs.readdirSync(d).filter((f) => f.startsWith('state.corrupt-'));
  assert.equal(backups.length, 1);
});

test('overflow 追加/读取/清空', () => {
  freshDir();
  stateIo.appendOverflow({ type: 'tool', ts: 'x' });
  stateIo.appendOverflow({ type: 'stop', roll: 0.5, ts: 'y' });
  assert.deepEqual(stateIo.readOverflow(), [
    { type: 'tool', ts: 'x' },
    { type: 'stop', roll: 0.5, ts: 'y' },
  ]);
  stateIo.clearOverflow();
  assert.deepEqual(stateIo.readOverflow(), []);
});

test('tryWithLock 执行并释放', () => {
  const d = freshDir();
  let ran = false;
  assert.equal(stateIo.tryWithLock(() => { ran = true; }), true);
  assert.ok(ran);
  assert.equal(fs.existsSync(path.join(d, 'lock')), false);
});

test('锁被占：等满约 300ms 后返回 false 且不执行 fn', () => {
  const d = freshDir();
  fs.mkdirSync(path.join(d, 'lock'));
  let ran = false;
  const t0 = Date.now();
  assert.equal(stateIo.tryWithLock(() => { ran = true; }), false);
  assert.ok(!ran);
  assert.ok(Date.now() - t0 >= 250);
});

test('logError 写入 error.log 且不抛', () => {
  freshDir();
  stateIo.logError(new Error('boom'));
  const log = fs.readFileSync(path.join(process.env.PET_STATE_DIR, 'error.log'), 'utf8');
  assert.ok(log.includes('boom'));
});

test('claimOverflow 认领式契约：改名认领、迟到写入不丢、可再次认领', () => {
  const d = freshDir();
  stateIo.appendOverflow({ type: 'tool', ts: 'E1' });
  const claimed = stateIo.claimOverflow();
  assert.ok(claimed, '应返回认领文件路径');
  assert.ok(fs.existsSync(claimed), '认领文件应存在');
  assert.equal(fs.existsSync(path.join(d, 'overflow.jsonl')), false, '原 overflow.jsonl 应已改名消失');
  // 模拟迟到的竞争者：锁外直接 append 会重新创建新的 overflow.jsonl
  fs.appendFileSync(stateIo.overflowPath(), JSON.stringify({ type: 'tool', ts: 'E2' }) + '\n');
  assert.deepEqual(stateIo.readClaimed(claimed), [{ type: 'tool', ts: 'E1' }]);
  stateIo.unlinkClaimed(claimed);
  assert.equal(fs.existsSync(claimed), false, '认领文件应已删除');
  const claimed2 = stateIo.claimOverflow();
  assert.ok(claimed2, '第二次认领应成功');
  assert.deepEqual(stateIo.readClaimed(claimed2), [{ type: 'tool', ts: 'E2' }]);
  stateIo.unlinkClaimed(claimed2);
});

test('残留锁超过 5s：tryWithLock 破锁后正常执行并释放', () => {
  const d = freshDir();
  fs.mkdirSync(path.join(d, 'lock'));
  const oldTime = new Date(Date.now() - 10000);
  fs.utimesSync(path.join(d, 'lock'), oldTime, oldTime);
  let ran = false;
  assert.equal(stateIo.tryWithLock(() => { ran = true; }), true);
  assert.ok(ran);
  assert.equal(fs.existsSync(path.join(d, 'lock')), false);
});

test('readOverflow 逐行解析：单行坏 JSON 跳过、好行保留', () => {
  freshDir();
  fs.writeFileSync(stateIo.overflowPath(), '{"type":"tool","ts":"a"}\n{broken\n{"type":"tool","ts":"b"}\n');
  assert.deepEqual(stateIo.readOverflow(), [
    { type: 'tool', ts: 'a' },
    { type: 'tool', ts: 'b' },
  ]);
});
