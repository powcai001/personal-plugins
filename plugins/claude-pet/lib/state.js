'use strict';
const fs = require('fs');
const path = require('path');

const LOCK_TIMEOUT_MS = 300;
const LOCK_SPIN_MS = 10;
const STALE_LOCK_MS = 5000; // 临界区仅毫秒级，5s 只可能是残留锁

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function stateDir() {
  return process.env.PET_STATE_DIR || path.join(process.env.HOME || '.', '.claude', 'claude-pet');
}
function statePath() { return path.join(stateDir(), 'state.json'); }
function overflowPath() { return path.join(stateDir(), 'overflow.jsonl'); }
function lockPath() { return path.join(stateDir(), 'lock'); }

function ensureDir() {
  fs.mkdirSync(stateDir(), { recursive: true });
}

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(statePath(), 'utf8'));
  } catch (e) {
    if (e.code === 'ENOENT') return null;
    try {
      fs.copyFileSync(statePath(), path.join(stateDir(), `state.corrupt-${Date.now()}.json`));
    } catch (_) { /* 尽力备份 */ }
    return null;
  }
}

function saveState(state) {
  ensureDir();
  const tmp = path.join(stateDir(), `.state.tmp-${process.pid}`);
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2) + '\n');
  fs.renameSync(tmp, statePath());
}

function appendOverflow(event) {
  ensureDir();
  fs.appendFileSync(overflowPath(), JSON.stringify(event) + '\n');
}

function readOverflow() {
  try {
    return fs
      .readFileSync(overflowPath(), 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((l) => { try { return JSON.parse(l); } catch (_) { return null; } })
      .filter(Boolean);
  } catch (_) {
    return [];
  }
}

function clearOverflow() {
  try { fs.unlinkSync(overflowPath()); } catch (_) { /* 无文件即无积压 */ }
}

function claimOverflow() {
  try {
    const claimed = overflowPath() + `.claim-${process.pid}`;
    fs.renameSync(overflowPath(), claimed);
    return claimed;
  } catch (_) { return null; }
}

function readClaimed(file) {
  try {
    return fs.readFileSync(file, 'utf8')
      .split('\n').filter(Boolean)
      .map((l) => { try { return JSON.parse(l); } catch (_) { return null; } })
      .filter(Boolean);
  } catch (_) { return []; }
}

function unlinkClaimed(file) {
  try { fs.unlinkSync(file); } catch (_) { /* 尽力清理 */ }
}

function logError(err) {
  try {
    ensureDir();
    const msg = err && err.stack ? err.stack : String(err);
    fs.appendFileSync(path.join(stateDir(), 'error.log'), `[${new Date().toISOString()}] ${msg}\n`);
  } catch (_) { /* 吞掉 */ }
}

function isStaleLock() {
  try {
    const st = fs.statSync(lockPath());
    return Date.now() - st.mtimeMs > STALE_LOCK_MS;
  } catch (_) {
    return false; // 锁刚好被释放：下一轮 mkdir 自然成功
  }
}

function tryWithLock(fn) {
  ensureDir();
  const deadline = Date.now() + LOCK_TIMEOUT_MS;
  for (;;) {
    try {
      fs.mkdirSync(lockPath());
      break;
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      if (isStaleLock()) {
        try { fs.rmdirSync(lockPath()); } catch (_) { /* 他者已清理或已抢先重建 */ }
        continue; // 立即重试 mkdir（抢锁）
      }
      if (Date.now() >= deadline) return false;
      sleep(LOCK_SPIN_MS);
    }
  }
  try {
    fn();
    return true;
  } finally {
    try { fs.rmdirSync(lockPath()); } catch (_) { /* 尽力释放 */ }
  }
}

module.exports = {
  stateDir, statePath, overflowPath, lockPath,
  loadState, saveState, appendOverflow, readOverflow, clearOverflow,
  claimOverflow, readClaimed, unlinkClaimed,
  logError, tryWithLock,
};
