'use strict';
const test = require('node:test');
const assert = require('node:assert');
const engine = require('../lib/engine');

const STAGES = [
  { level: 1, form: '🥚', name: '神秘的蛋' },
  { level: 3, form: '🐣', name: '破壳' },
  { level: 8, form: '🦎', name: '小蜥蜴' },
  { level: 16, form: '🦖', name: '暴龙少年' },
  { level: 26, form: '🦕', name: '长颈龙' },
  { level: 38, form: '🐲', name: '云中蛟' },
  { level: 45, form: '🐉', name: '神龙' },
];
const NOW = '2026-08-27T00:00:00.000Z';

test('xpForLevel 基础值与曲线', () => {
  assert.equal(engine.xpForLevel(1), 15);
  assert.equal(engine.xpForLevel(2), 17);
  assert.equal(engine.xpForLevel(44), Math.ceil(15 * Math.pow(1.1, 43)));
});

test('newState 初始状态', () => {
  const s = engine.newState(NOW, STAGES);
  assert.equal(s.level, 1);
  assert.equal(s.xp, 0);
  assert.equal(s.stage, 0);
  assert.equal(s.rebirths, 0);
  assert.equal(s.snacks, 0);
  assert.equal(s.dex.length, 1); // 蛋出生即入图鉴
  assert.equal(s.dex[0].form, '🥚');
});

test('XP 够即升级，余数保留', () => {
  const s = engine.newState(NOW, STAGES);
  const gain = engine.applyXp(s, 15, STAGES, NOW);
  assert.equal(gain, 15);
  assert.equal(s.level, 2);
  assert.equal(s.xp, 0);
});

test('一次大额 XP 可连升多级', () => {
  const s = engine.newState(NOW, STAGES);
  engine.applyXp(s, 32, STAGES, NOW); // 15+17
  assert.equal(s.level, 3);
  assert.equal(s.xp, 0);
});

test('升级差 1 点不升', () => {
  const s = engine.newState(NOW, STAGES);
  engine.applyXp(s, 14, STAGES, NOW);
  assert.equal(s.level, 1);
  assert.equal(s.xp, 14);
});

test('转生倍率作用于 XP 获取', () => {
  const s = engine.newState(NOW, STAGES);
  s.rebirths = 1; // ×1.15
  const gain = engine.applyXp(s, 20, STAGES, NOW);
  assert.equal(gain, 23); // round(20×1.15)
});

test('满级后 XP 封顶在需求值，多余丢弃', () => {
  const s = engine.newState(NOW, STAGES);
  s.level = 45;
  s.xp = 0;
  engine.applyXp(s, 999999, STAGES, NOW);
  assert.equal(s.level, 45);
  assert.equal(s.xp, engine.xpForLevel(45));
});
