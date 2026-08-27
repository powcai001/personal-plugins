'use strict';
const test = require('node:test');
const assert = require('node:assert');
const engine = require('../lib/engine');
const { FALLBACK_STAGES } = require('../lib/species');

const NOW = '2026-08-27T00:00:00.000Z';

test('prompt: +5 XP 且重置轮内计数', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.toolsThisTurn = 9;
  s.turnXp = 40;
  engine.applyPrompt(s, FALLBACK_STAGES, NOW);
  assert.equal(s.xp, 5);
  assert.equal(s.toolsThisTurn, 0);
  assert.equal(s.turnXp, 5);
  assert.equal(s.stageAtTurnStart, s.stage);
});

test('tool: +2 XP，每第 15 次必掉零食', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  for (let i = 1; i <= 14; i++) engine.applyTool(s, FALLBACK_STAGES, NOW);
  assert.equal(s.snacks, 0);
  assert.equal(s.level, 2);
  assert.equal(s.xp, 13); // 28 XP 中 15 用于升 Lv2，余 13
  const r = engine.applyTool(s, FALLBACK_STAGES, NOW); // 第 15 次
  assert.equal(r.snackDrop, true);
  assert.equal(s.snacks, 1);
  assert.equal(s.toolsThisTurn, 15);
});

test('stop: roll<0.25 掉零食，roll=0.25 不掉', () => {
  const s1 = engine.newState(NOW, FALLBACK_STAGES);
  engine.applyStop(s1, FALLBACK_STAGES, NOW, 0.24);
  assert.equal(s1.snacks, 1);
  assert.equal(s1.xp, 10);
  const s2 = engine.newState(NOW, FALLBACK_STAGES);
  engine.applyStop(s2, FALLBACK_STAGES, NOW, 0.25);
  assert.equal(s2.snacks, 0);
});

test('零食上限 9：掉落与摸头都停', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.snacks = 9;
  engine.applyStop(s, FALLBACK_STAGES, NOW, 0.01);
  assert.equal(s.snacks, 9);
  s.petsCount = 9;
  engine.applyPet(s, FALLBACK_STAGES, NOW, () => 0);
  assert.equal(s.snacks, 9);
});

test('stop 进化横幅：普通进化文案', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 2; s.xp = engine.xpForLevel(2) - 10; s.stage = 0; s.stageAtTurnStart = 0;
  const r = engine.applyStop(s, FALLBACK_STAGES, NOW, 0.99);
  assert.equal(s.level, 3);
  assert.equal(s.stage, 1);
  assert.equal(r.evolved, true);
  assert.ok(r.banner.includes('进化'));
  assert.ok(r.banner.includes('🐣'));
});

test('stop 满级横幅：最终形态文案', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 44; s.xp = engine.xpForLevel(44) - 10; s.stage = 5; s.stageAtTurnStart = 5;
  const r = engine.applyStop(s, FALLBACK_STAGES, NOW, 0.99);
  assert.equal(s.level, 45);
  assert.equal(s.stage, 6);
  assert.ok(r.banner.includes('满级'));
  assert.ok(r.banner.includes('🐉'));
});

test('stop 未进化时无横幅', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  const r = engine.applyStop(s, FALLBACK_STAGES, NOW, 0.99);
  assert.equal(r.banner, null);
  assert.equal(r.evolved, false);
});

test('feed: 消耗零食得 40% 升级需求 XP', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 2; s.xp = 0; s.snacks = 1;
  const r = engine.applyFeed(s, FALLBACK_STAGES, NOW);
  assert.equal(r.ok, true);
  assert.equal(s.snacks, 0);
  assert.equal(s.xp, Math.ceil(engine.xpForLevel(2) * 0.4)); // ceil(17×0.4)=7
});

test('feed: 满级与无零食均拒绝且不扣零食', () => {
  const s1 = engine.newState(NOW, FALLBACK_STAGES);
  s1.level = 45; s1.snacks = 2;
  assert.equal(engine.applyFeed(s1, FALLBACK_STAGES, NOW).ok, false);
  assert.equal(s1.snacks, 2);
  const s2 = engine.newState(NOW, FALLBACK_STAGES);
  assert.equal(engine.applyFeed(s2, FALLBACK_STAGES, NOW).ok, false);
});

test('pet: 计数、每第 10 次掉零食、文案含反应', () => {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  for (let i = 1; i <= 9; i++) engine.applyPet(s, FALLBACK_STAGES, NOW, () => 0);
  assert.equal(s.snacks, 0);
  const r = engine.applyPet(s, FALLBACK_STAGES, NOW, () => 0);
  assert.equal(s.petsCount, 10);
  assert.equal(s.snacks, 1);
  assert.ok(r.msg.length > 0);
});
