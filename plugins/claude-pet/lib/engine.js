'use strict';

const MAX_LEVEL = 45;
const SNACK_CAP = 9;

function xpForLevel(level) {
  return Math.ceil(15 * Math.pow(1.10, level - 1));
}

function xpMultiplier(state) {
  return 1 + 0.15 * (state.rebirths || 0);
}

function newState(now, stages) {
  return {
    version: 1,
    level: 1,
    xp: 0,
    stage: 0,
    stageAtTurnStart: 0,
    rebirths: 0,
    dex: [{ form: stages[0].form, name: stages[0].name, ts: now }],
    snacks: 0,
    toolsThisTurn: 0,
    turnXp: 0,
    petsCount: 0,
    born: now,
    lastActive: now,
  };
}

function applyXp(state, baseAmount, stages, now) {
  const gain = Math.round(baseAmount * xpMultiplier(state));
  state.xp += gain;
  state.turnXp = (state.turnXp || 0) + gain;
  while (state.level < MAX_LEVEL && state.xp >= xpForLevel(state.level)) {
    state.xp -= xpForLevel(state.level);
    state.level += 1;
  }
  if (state.level >= MAX_LEVEL && state.xp > xpForLevel(MAX_LEVEL)) {
    state.xp = xpForLevel(MAX_LEVEL);
  }
  syncStage(state, stages, now);
  return gain;
}

function stageIndexFor(stages, level) {
  let idx = 0;
  for (let i = 0; i < stages.length; i++) {
    if (level >= stages[i].level) idx = i;
  }
  return idx;
}

function syncStage(state, stages, now) {
  const idx = stageIndexFor(stages, state.level);
  if (idx !== state.stage) {
    for (let i = state.stage + 1; i <= idx; i++) {
      const st = stages[i];
      if (!state.dex.some((e) => e.form === st.form)) {
        state.dex.push({ form: st.form, name: st.name, ts: now });
      }
    }
    state.stage = idx;
  }
}

const PET_REACT = [
  '发出满足的咕噜声',
  '蹭了蹭你的手',
  '打了个滚',
  '尾巴摇成了螺旋桨',
  '眯起眼睛晒太阳',
];

function applyPrompt(state, stages, now) {
  state.toolsThisTurn = 0;
  state.turnXp = 0;
  state.stageAtTurnStart = state.stage;
  applyXp(state, 5, stages, now);
  state.lastActive = now;
}

function applyTool(state, stages, now) {
  applyXp(state, 2, stages, now);
  state.toolsThisTurn = (state.toolsThisTurn || 0) + 1;
  let snackDrop = false;
  if (state.toolsThisTurn % 15 === 0 && state.snacks < SNACK_CAP) {
    state.snacks += 1;
    snackDrop = true;
  }
  state.lastActive = now;
  return { snackDrop };
}

function applyStop(state, stages, now, roll) {
  applyXp(state, 10, stages, now);
  let snackDrop = false;
  if (roll < 0.25 && state.snacks < SNACK_CAP) {
    state.snacks += 1;
    snackDrop = true;
  }
  state.lastActive = now;
  const evolved = state.stage > state.stageAtTurnStart;
  let banner = null;
  if (evolved) {
    const st = stages[state.stage];
    banner =
      state.level >= MAX_LEVEL
        ? `👑 满级！${st.name} ${st.form} 降临！可用 /claude-pet:pet 转生`
        : `🎉 进化！${st.name} ${st.form}`;
  }
  return { snackDrop, evolved, banner };
}

function applyFeed(state, stages, now) {
  if (state.level >= MAX_LEVEL) {
    return { ok: false, msg: '已达满级，零食留着转生后用' };
  }
  if (state.snacks <= 0) {
    return { ok: false, msg: '没有零食了，让 Claude 多干点活吧' };
  }
  state.snacks -= 1;
  const gain = applyXp(state, Math.ceil(xpForLevel(state.level) * 0.4), stages, now);
  return { ok: true, msg: `🍪 零食 -1，经验 +${gain}` };
}

function applyPet(state, stages, now, rng) {
  state.petsCount = (state.petsCount || 0) + 1;
  let snack = false;
  if (state.petsCount % 10 === 0 && state.snacks < SNACK_CAP) {
    state.snacks += 1;
    snack = true;
  }
  state.lastActive = now;
  const st = stages[state.stage] || stages[0];
  const react = PET_REACT[Math.floor(rng() * PET_REACT.length)];
  const msg = snack
    ? `${st.form} ${react}，还从窝里叼出一颗零食 🍪`
    : `${st.form} ${react}`;
  return { msg };
}

function applyRebirth(state, stages, now) {
  if (state.level < MAX_LEVEL) {
    return { ok: false, msg: `还未满级（Lv.${state.level}/${MAX_LEVEL}），继续加油` };
  }
  state.level = 1;
  state.xp = 0;
  state.stage = 0;
  state.stageAtTurnStart = 0;
  state.turnXp = 0;
  state.rebirths = (state.rebirths || 0) + 1;
  state.lastActive = now;
  return {
    ok: true,
    msg: `🔁 转生成功！现在是第 ${state.rebirths} 世，经验获取 ×${xpMultiplier(state).toFixed(2)}`,
  };
}

module.exports = {
  MAX_LEVEL, SNACK_CAP, xpForLevel, xpMultiplier, newState, applyXp, stageIndexFor,
  applyPrompt, applyTool, applyStop, applyFeed, applyPet, applyRebirth,
};
