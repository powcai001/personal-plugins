'use strict';
const engine = require('./engine');
const species = require('./species');
const stateIo = require('./state');

const STAGES = species.loadStages();

function nowIso() {
  return new Date().toISOString();
}

function loadOrNew() {
  return stateIo.loadState() || engine.newState(nowIso(), STAGES);
}

function applyEvent(state, ev) {
  switch (ev.type) {
    case 'prompt':
      return engine.applyPrompt(state, STAGES, ev.ts || nowIso());
    case 'tool':
      return engine.applyTool(state, STAGES, ev.ts || nowIso());
    case 'stop':
      return engine.applyStop(state, STAGES, ev.ts || nowIso(), typeof ev.roll === 'number' ? ev.roll : 1);
    default:
      return null;
  }
}

function foldOverflow(state) {
  const claimed = stateIo.claimOverflow();
  if (!claimed) return;
  for (const ev of stateIo.readClaimed(claimed)) applyEvent(state, ev);
  stateIo.unlinkClaimed(claimed);
}

function runHookEvent(ev) {
  let out;
  const ran = stateIo.tryWithLock(() => {
    const state = loadOrNew();
    foldOverflow(state);
    out = applyEvent(state, ev);
    stateIo.saveState(state);
  });
  if (!ran) {
    stateIo.appendOverflow(ev);
    return { ok: false, busy: true };
  }
  return { ok: true, result: out };
}

function runUserCommand(fn) {
  let result;
  const ran = stateIo.tryWithLock(() => {
    const state = loadOrNew();
    foldOverflow(state);
    result = fn(state);
    stateIo.saveState(state);
  });
  if (!ran) {
    return { ok: false, busy: true, msg: '状态文件忙（可能有其他终端在写），请重试' };
  }
  return result;
}

module.exports = { STAGES, applyEvent, runHookEvent, runUserCommand };
