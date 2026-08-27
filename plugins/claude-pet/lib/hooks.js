'use strict';
const fs = require('fs');
const stateIo = require('./state');
const store = require('./store');

function readStdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch (_) {
    return '';
  }
}

function hooksMain(argv) {
  readStdin(); // 消费并忽略内容
  const sub = argv[0];
  const now = new Date().toISOString();
  switch (sub) {
    case 'prompt':
      store.runHookEvent({ type: 'prompt', ts: now });
      break;
    case 'tool':
      store.runHookEvent({ type: 'tool', ts: now });
      break;
    case 'stop': {
      const r = store.runHookEvent({ type: 'stop', roll: Math.random(), ts: now });
      if (r.ok && r.result && r.result.banner) {
        process.stdout.write(JSON.stringify({ systemMessage: r.result.banner }));
      }
      break;
    }
    case 'session': {
      const state = stateIo.loadState();
      if (!state) {
        store.runUserCommand(() => {});
        break;
      }
      const gapMs = Date.now() - Date.parse(state.lastActive);
      if (Number.isFinite(gapMs) && gapMs > 48 * 3600 * 1000) {
        const st = store.STAGES[state.stage] || store.STAGES[0];
        const hours = Math.floor(gapMs / 3600000);
        process.stdout.write(`${st.form} 宠物想你了——已经 ${hours} 小时没一起干活啦`);
      }
      break;
    }
    default:
      break;
  }
}

module.exports = { hooksMain };
