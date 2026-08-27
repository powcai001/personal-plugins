'use strict';
const test = require('node:test');
const assert = require('node:assert');
const engine = require('../lib/engine');
const { FALLBACK_STAGES } = require('../lib/species');

const NOW = '2026-08-27T00:00:00.000Z';

test('未满级拒绝转生', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  const r = engine.applyRebirth(s, FALLBACK_STAGES, NOW);
  assert.equal(r.ok, false);
  assert.equal(s.level, 1);
});

test('满级转生：重置等级、保留图鉴零食、倍率生效', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 45;
  s.stage = 6;
  s.snacks = 3;
  s.petsCount = 5;
  s.turnXp = 100;
  s.dex = FALLBACK_STAGES.map((st) => ({ form: st.form, name: st.name, ts: NOW })); // 模拟正常游玩已集齐图鉴
  const r = engine.applyRebirth(s, FALLBACK_STAGES, NOW);
  assert.equal(r.ok, true);
  assert.equal(s.level, 1);
  assert.equal(s.xp, 0);
  assert.equal(s.stage, 0);
  assert.equal(s.stageAtTurnStart, 0);
  assert.equal(s.turnXp, 0);
  assert.equal(s.rebirths, 1);
  assert.equal(s.snacks, 3);
  assert.equal(s.petsCount, 5);
  assert.equal(s.dex.length, 7);
  assert.ok(r.msg.includes('×1.15'));
  const gain = engine.applyXp(s, 20, FALLBACK_STAGES, NOW);
  assert.equal(gain, 23);
});

test('多世倍率线性叠加', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 45;
  s.stage = 6;
  engine.applyRebirth(s, FALLBACK_STAGES, NOW);
  s.level = 45;
  s.stage = 6;
  const r = engine.applyRebirth(s, FALLBACK_STAGES, NOW);
  assert.equal(s.rebirths, 2);
  assert.ok(r.msg.includes('×1.30'));
});
