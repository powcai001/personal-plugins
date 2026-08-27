'use strict';
const fs = require('fs');
const path = require('path');

const FALLBACK_STAGES = [
  { level: 1, form: '🥚', name: '神秘的蛋' },
  { level: 3, form: '🐣', name: '破壳' },
  { level: 8, form: '🦎', name: '小蜥蜴' },
  { level: 16, form: '🦖', name: '暴龙少年' },
  { level: 26, form: '🦕', name: '长颈龙' },
  { level: 38, form: '🐲', name: '云中蛟' },
  { level: 45, form: '🐉', name: '神龙' },
];

function loadStages(filepath) {
  const file = filepath || path.resolve(__dirname, '..', 'data', 'species.json');
  try {
    const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
    const sp = (raw.species || []).find((s) => s.id === raw.defaultSpecies) || raw.species[0];
    if (sp && Array.isArray(sp.stages) && sp.stages.length > 0) return sp.stages;
  } catch (_) { /* 兜底 */ }
  return FALLBACK_STAGES;
}

module.exports = { FALLBACK_STAGES, loadStages };
