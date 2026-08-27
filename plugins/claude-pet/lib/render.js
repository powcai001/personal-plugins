'use strict';
const engine = require('./engine');

function progressBar(pct, width) {
  const p = Math.max(0, Math.min(1, pct));
  const filled = Math.round(p * width);
  return '▓'.repeat(filled) + '░'.repeat(width - filled);
}

function xpPct(state) {
  return Math.min(1, state.xp / engine.xpForLevel(state.level));
}

function renderStatusline(state, stages) {
  const st = stages[state.stage] || stages[0];
  const pct = Math.floor(xpPct(state) * 100);
  if (process.env.PET_ASCII === '1') {
    return `[${st.name} Lv.${state.level} ${pct}% +${state.turnXp || 0}xp 零食${state.snacks}]`;
  }
  return `${st.form} ${st.name} Lv.${state.level} ${progressBar(xpPct(state), 6)} ${pct}% · 本轮+${state.turnXp || 0}xp · 🍪${state.snacks}`;
}

function daysTogether(state) {
  const born = Date.parse(state.born);
  if (!Number.isFinite(born)) return 1;
  return Math.max(1, Math.floor((Date.now() - born) / 86400000) + 1);
}

function renderPanel(state, stages) {
  const st = stages[state.stage] || stages[0];
  const pct = Math.floor(xpPct(state) * 100);
  const dexForms = state.dex.map((e) => e.form).join(' ');
  const lines = [
    '╭──────────────────────────╮',
    `│         ${st.form}              │`,
    `│   ${st.name} · Lv.${state.level}${state.level >= engine.MAX_LEVEL ? '（满级）' : ''}`,
    `│   XP ${progressBar(xpPct(state), 8)} ${pct}%`,
    '│',
    `│   🍪 ${state.snacks}    🔁 ${state.rebirths}`,
    `│   摸头 ${state.petsCount}`,
    `│   🎂 陪伴 ${daysTogether(state)} 天`,
    '╰──────────────────────────╯',
    `图鉴 (${state.dex.length}/${stages.length})：${dexForms}`,
  ];
  if (state.level >= engine.MAX_LEVEL) {
    lines.push('已满级，可转生：/claude-pet:pet 说"转生"');
  }
  return lines.join('\n');
}

module.exports = { progressBar, renderStatusline, renderPanel };
