'use strict';
const test = require('node:test');
const assert = require('node:assert');
const engine = require('../lib/engine');
const { FALLBACK_STAGES, loadStages } = require('../lib/species');

const NOW = '2026-08-27T00:00:00.000Z';

test('loadStages 读到真实数据文件', () => {
  const stages = loadStages();
  assert.equal(stages.length, 7);
  assert.equal(stages[6].form, '🐉');
  assert.equal(stages[6].level, 45);
});

test('loadStages 文件损坏时返回内置兜底', () => {
  const stages = loadStages('/nonexistent/species.json');
  assert.deepEqual(stages, FALLBACK_STAGES);
});

test('stageIndexFor 阈值判定', () => {
  assert.equal(engine.stageIndexFor(FALLBACK_STAGES, 1), 0);
  assert.equal(engine.stageIndexFor(FALLBACK_STAGES, 2), 0);
  assert.equal(engine.stageIndexFor(FALLBACK_STAGES, 3), 1);
  assert.equal(engine.stageIndexFor(FALLBACK_STAGES, 7), 1);
  assert.equal(engine.stageIndexFor(FALLBACK_STAGES, 8), 2);
  assert.equal(engine.stageIndexFor(FALLBACK_STAGES, 44), 5);
  assert.equal(engine.stageIndexFor(FALLBACK_STAGES, 45), 6);
});

test('升级跨过进化阈值时切换形态并入图鉴', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  engine.applyXp(s, 32, FALLBACK_STAGES, NOW); // Lv3
  assert.equal(s.stage, 1);
  const forms = s.dex.map((e) => e.form);
  assert.deepEqual(forms, ['🥚', '🐣']);
});

test('图鉴不重复记录同一形态', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 2;
  s.xp = 0;
  engine.applyXp(s, 20, FALLBACK_STAGES, NOW); // →Lv3 stage1
  s.level = 2; // 手动回退模拟转生后
  s.stage = 0;
  s.xp = 0;
  engine.applyXp(s, 20, FALLBACK_STAGES, NOW); // 再次 →Lv3
  const forms = s.dex.map((e) => e.form);
  assert.equal(forms.filter((f) => f === '🐣').length, 1);
});

test('一次大额 XP 跨多段进化，图鉴按序补全', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  let total = 0;
  for (let lv = 1; lv <= 15; lv++) total += engine.xpForLevel(lv);
  engine.applyXp(s, total, FALLBACK_STAGES, NOW); // →Lv16
  assert.equal(s.stage, 3); // 🦖
  assert.deepEqual(s.dex.map((e) => e.form), ['🥚', '🐣', '🦎', '🦖']);
});
