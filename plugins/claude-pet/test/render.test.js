'use strict';
const test = require('node:test');
const assert = require('node:assert');
const engine = require('../lib/engine');
const render = require('../lib/render');
const { FALLBACK_STAGES } = require('../lib/species');

const NOW = '2026-08-27T00:00:00.000Z';

function matureState() {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 42; s.stage = 5; s.xp = 400; s.snacks = 3; s.turnXp = 64; s.rebirths = 1;
  s.petsCount = 12;
  return s;
}

test('progressBar 钳制与填充', () => {
  assert.equal(render.progressBar(0, 6), '░░░░░░');
  assert.equal(render.progressBar(1, 6), '▓▓▓▓▓▓');
  assert.equal(render.progressBar(1.5, 6), '▓▓▓▓▓▓');
  assert.equal(render.progressBar(0.5, 6), '▓▓▓░░░');
});

test('statusline 常规格式', () => {
  const line = render.renderStatusline(matureState(), FALLBACK_STAGES);
  assert.ok(line.includes('🐲 云中蛟 Lv.42'));
  assert.ok(line.includes('本轮+64xp'));
  assert.ok(line.includes('🍪3'));
  assert.ok(/▓+░*/.test(line));
  assert.ok(line.includes('%'));
});

test('statusline PET_ASCII 模式', () => {
  process.env.PET_ASCII = '1';
  try {
    const line = render.renderStatusline(matureState(), FALLBACK_STAGES);
    assert.ok(!line.includes('▓'));
    assert.ok(!line.includes('🍪'));
    assert.ok(line.includes('云中蛟 Lv.42'));
    assert.ok(line.includes('零食3'));
  } finally {
    delete process.env.PET_ASCII;
  }
});

test('panel 包含关键信息与图鉴', () => {
  const p = render.renderPanel(matureState(), FALLBACK_STAGES);
  assert.ok(p.includes('🐲'));
  assert.ok(p.includes('云中蛟'));
  assert.ok(p.includes('Lv.42'));
  assert.ok(p.includes('🍪 3'));
  assert.ok(p.includes('🔁 1'));
  assert.ok(p.includes('摸头 12'));
  assert.ok(p.includes('(1/7)')); // 新档只有蛋入图鉴
  assert.ok(p.includes('陪伴'));
});

test('panel 满级提示转生', () => {
  const s = matureState();
  s.level = 45; s.stage = 6; s.xp = engine.xpForLevel(45);
  const p = render.renderPanel(s, FALLBACK_STAGES);
  assert.ok(p.includes('转生'));
});
