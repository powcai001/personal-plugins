# claude-pet 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 claude-pet v1 —— Claude Code 放置挂机电子宠物插件（XP/进化/零食/转生/状态栏/面板互动）。

**Architecture:** 纯 Node 标准库 CJS 模块：`lib/engine.js`（纯函数游戏数值）、`lib/species.js`（进化链数据+兜底）、`lib/state.js`（原子读写/锁/容错）、`lib/store.js`（读改写驱动+overflow 折叠）、`lib/render.js`（状态栏/面板）、`lib/hooks.js`（hook 子命令）、`bin/claude-pet`（CLI 入口，吞一切错误永远 exit 0）。hook 通过 `hooks/hooks.json` 以 `node ${CLAUDE_PLUGIN_ROOT}/bin/claude-pet <sub>` 接入四个生命周期事件。

**Tech Stack:** Node ≥18（本机 v22），仅标准库；测试用内置 `node:test`；无 package.json、无第三方依赖。

**Spec:** `docs/superpowers/specs/2026-08-27-claude-pet-design.md`（数值与行为以 spec 为准，冲突时以 spec 为准）

## Global Constraints

- 插件名 `claude-pet`；manifest 在 `.claude-plugin/plugin.json`，其余目录（`hooks/`、`bin/`、`lib/`、`data/`、`skills/`、`test/`）都在插件根目录
- 仅 Node 标准库；CJS（`require`）；**不创建 package.json**
- 运行时状态目录：`$PET_STATE_DIR`（测试用），默认 `~/.claude/claude-pet/`；权威状态是其中 `state.json`
- hook 进程**任何情况 exit 0**：所有错误吞掉并追加写入 `<状态目录>/error.log`
- XP 规则（spec §3，逐字）：发 prompt +5；工具调用 +2；轮次完成 +10；升级需求 `ceil(15 × 1.10^(Lv-1))`；转生后 XP 获取 ×(1 + 0.15 × 转生数)
- 满级 Lv45；零食上限 9；Stop 25% 掉零食（roll < 0.25）；单轮每第 15 次工具必掉；喂食得当前等级需求 40% XP；每第 10 次摸头得 1 零食
- 进化链（species.json 与代码内置兜底一致）：🥚Lv1 神秘的蛋 → 🐣Lv3 破壳 → 🦎Lv8 小蜥蜴 → 🦖Lv16 暴龙少年 → 🦕Lv26 长颈龙 → 🐲Lv38 云中蛟 → 🐉Lv45 神龙
- 横幅仅两处：进化（Stop 时 stage 相比轮初提升）、满级（进化到最终形态时用满级文案）；普通升级/掉零食不弹
- 锁：`mkdir lock`，自旋 10ms、总超时 300ms；超时降级 append `overflow.jsonl`（仅 hook 事件），下次拿锁成功时折叠合并
- 测试一律通过 `PET_STATE_DIR` 指向临时目录，绝不动真实 `~/.claude/`
- 提交信息用中文，格式 `feat:/test:/docs: <内容>`

## File Structure

```
claude-pet/
├── .claude-plugin/plugin.json     # Task 1
├── lib/engine.js                  # Task 1-4：纯函数游戏引擎
├── lib/species.js                 # Task 2：进化链加载+内置兜底
├── data/species.json              # Task 2
├── lib/state.js                   # Task 5：路径/原子读写/锁/容错日志
├── lib/store.js                   # Task 6：runHookEvent / runUserCommand / applyEvent
├── lib/render.js                  # Task 7：状态栏 / 面板
├── bin/claude-pet                 # Task 8：CLI 入口（需 chmod +x）
├── lib/hooks.js                   # Task 9：prompt/tool/stop/session
├── hooks/hooks.json               # Task 9
├── skills/pet/SKILL.md            # Task 10
├── skills/setup/SKILL.md          # Task 10
├── README.md                      # Task 11
└── test/                          # 各任务同名 test 文件
```

**共享类型（所有任务通用）：**

```js
// Stage（lib/species.js 与 data/species.json）
{ level: number, form: string, name: string }
// State（state.json，engine.newState 产出）
{
  version: 1, level: number, xp: number,
  stage: number,               // 当前进化链下标（0-6）
  stageAtTurnStart: number,    // prompt 时快照，stop 用于横幅判定
  rebirths: number,
  dex: [{ form: string, name: string, ts: string }],
  snacks: number, toolsThisTurn: number, turnXp: number, petsCount: number,
  born: string, lastActive: string   // ISO 时间
}
```

---

### Task 1: 脚手架 + XP 曲线引擎

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `lib/engine.js`
- Test: `test/curve.test.js`

**Interfaces:**
- Produces: `xpForLevel(level:number):number`；`xpMultiplier(state):number`；`newState(now:string, stages:Stage[]):State`；`applyXp(state, baseAmount:number, stages:Stage[], now:string):number`（返回实际获得 XP）；常量 `MAX_LEVEL=45`、`SNACK_CAP=9`。参数 `stages/now` 在本任务暂未使用（Task 2 的 syncStage 会用到），**签名从现在起固定不变**。

- [ ] **Step 1: 写失败测试**

```js
// test/curve.test.js
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/curve.test.js`
Expected: FAIL（`Cannot find module '../lib/engine'`）

- [ ] **Step 3: 建脚手架与最小实现**

`.claude-plugin/plugin.json`：

```json
{
  "name": "claude-pet",
  "description": "放置挂机电子宠物：Claude 干活 = 宠物成长，升级进化，满级转生",
  "version": "0.1.0",
  "author": { "name": "plugin-dev" }
}
```

`lib/engine.js`：

```js
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
  return gain;
}

module.exports = { MAX_LEVEL, SNACK_CAP, xpForLevel, xpMultiplier, newState, applyXp };
```

- [ ] **Step 4: 跑测试确认通过**

Run: `node --test test/curve.test.js`
Expected: PASS（全部 # pass）

- [ ] **Step 5: 提交**

```bash
git add .claude-plugin lib/engine.js test/curve.test.js
git commit -m "feat: 插件脚手架与 XP 曲线引擎"
```

---

### Task 2: 进化系统与图鉴（含 species 数据）

**Files:**
- Create: `lib/species.js`
- Create: `data/species.json`
- Modify: `lib/engine.js`（新增 `stageIndexFor`/`syncStage`，`applyXp` 内调用）
- Test: `test/evolve.test.js`

**Interfaces:**
- Consumes: Task 1 的 `applyXp`、`newState`
- Produces: `stageIndexFor(stages:Stage[], level:number):number`；`applyXp` 内部行为扩展（升级后同步 `state.stage`、新形态入 `dex` 不重复）；`lib/species.js` 导出 `FALLBACK_STAGES:Stage[]` 与 `loadStages(filepath?:string):Stage[]`（默认路径 `path.resolve(__dirname, '..', 'data', 'species.json')`，读取失败返回 FALLBACK_STAGES）

- [ ] **Step 1: 写失败测试**

```js
// test/evolve.test.js
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/evolve.test.js`
Expected: FAIL（`Cannot find module '../lib/species'`）

- [ ] **Step 3: 实现**

`data/species.json`：

```json
{
  "defaultSpecies": "dragon",
  "species": [
    {
      "id": "dragon",
      "name": "龙系",
      "stages": [
        { "level": 1, "form": "🥚", "name": "神秘的蛋" },
        { "level": 3, "form": "🐣", "name": "破壳" },
        { "level": 8, "form": "🦎", "name": "小蜥蜴" },
        { "level": 16, "form": "🦖", "name": "暴龙少年" },
        { "level": 26, "form": "🦕", "name": "长颈龙" },
        { "level": 38, "form": "🐲", "name": "云中蛟" },
        { "level": 45, "form": "🐉", "name": "神龙" }
      ]
    }
  ]
}
```

`lib/species.js`：

```js
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
```

`lib/engine.js` 追加（并导出 `stageIndexFor`，`applyXp` 末尾、封顶判断之后插入 `syncStage(state, stages, now);`，放在 `return gain;` 之前）：

```js
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
    state.stage = idx;
    const st = stages[idx];
    if (!state.dex.some((e) => e.form === st.form)) {
      state.dex.push({ form: st.form, name: st.name, ts: now });
    }
  }
}
```

module.exports 增加 `stageIndexFor`。

- [ ] **Step 4: 跑全部测试确认通过**

Run: `node --test test/`
Expected: PASS（curve + evolve 全绿）

- [ ] **Step 5: 提交**

```bash
git add data lib test/evolve.test.js
git commit -m "feat: 进化链、图鉴与 species 数据加载"
```

---

### Task 3: 零食与互动（applyTool / applyStop / applyFeed / applyPet）

**Files:**
- Modify: `lib/engine.js`
- Test: `test/snacks.test.js`

**Interfaces:**
- Consumes: Task 1/2 的 `applyXp`、`newState`
- Produces:
  - `applyPrompt(state, stages, now):void` —— +5 XP；重置 `toolsThisTurn=0`、`turnXp=0`、`stageAtTurnStart=state.stage`；更新 `lastActive`
  - `applyTool(state, stages, now):{snackDrop:boolean}` —— +2 XP；`toolsThisTurn++`；每第 15 次（`% 15 === 0`）且未达上限掉 1 零食
  - `applyStop(state, stages, now, roll:number):{snackDrop:boolean, evolved:boolean, banner:string|null}` —— +10 XP；`roll < 0.25` 且未达上限掉 1 零食；`state.stage > state.stageAtTurnStart` 时进化横幅，满级（level≥45）用满级文案
  - `applyFeed(state, stages, now):{ok:boolean, msg:string}` —— 满级或无零食时拒绝；否则零食 -1、+`ceil(xpForLevel(level)×0.4)` XP
  - `applyPet(state, stages, now, rng:()=>number):{msg:string}` —— `petsCount++`；每第 10 次且未达上限掉 1 零食；rng 只选反应文案

- [ ] **Step 1: 写失败测试**

```js
// test/snacks.test.js
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/snacks.test.js`
Expected: FAIL（`engine.applyPrompt is not a function`）

- [ ] **Step 3: 实现（lib/engine.js 追加，并加入 module.exports）**

```js
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
```

- [ ] **Step 4: 跑全部测试确认通过**

Run: `node --test test/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lib/engine.js test/snacks.test.js
git commit -m "feat: 零食掉落、喂食、摸头与轮次事件"
```

---

### Task 4: 转生

**Files:**
- Modify: `lib/engine.js`
- Test: `test/rebirth.test.js`

**Interfaces:**
- Consumes: Task 1-3 的引擎函数
- Produces: `applyRebirth(state, stages, now):{ok:boolean, msg:string}` —— 未满级拒绝；满级则 level=1、xp=0、stage=0、stageAtTurnStart=0、turnXp=0、rebirths+1、更新 lastActive；**保留 dex/snacks/petsCount/born**

- [ ] **Step 1: 写失败测试**

```js
// test/rebirth.test.js
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/rebirth.test.js`
Expected: FAIL（`engine.applyRebirth is not a function`）

- [ ] **Step 3: 实现（lib/engine.js 追加并导出）**

```js
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
```

- [ ] **Step 4: 跑全部测试确认通过**

Run: `node --test test/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lib/engine.js test/rebirth.test.js
git commit -m "feat: 满级转生与永久倍率"
```

---

### Task 5: 状态存储与容错（lib/state.js）

**Files:**
- Create: `lib/state.js`
- Test: `test/state.test.js`

**Interfaces:**
- Consumes: 无（纯 IO 模块）
- Produces:
  - `stateDir():string`（`PET_STATE_DIR` 优先，否则 `~/.claude/claude-pet`）
  - `statePath():string`、`overflowPath():string`、`lockPath():string`
  - `loadState():State|null` —— 不存在返回 null；JSON 损坏则备份为 `state.corrupt-<ms>.json` 后返回 null
  - `saveState(state):void` —— temp+rename 原子写，自动建目录
  - `appendOverflow(event:object):void` / `readOverflow():object[]` / `clearOverflow():void`
  - `logError(err):void` —— 追加 `error.log`，自身吞错
  - `tryWithLock(fn):boolean` —— mkdir 锁，自旋 10ms、总超时 300ms；跑完 rmdir 释放；超时返回 false（fn 未执行）；同步 sleep 用 `Atomics.wait`

- [ ] **Step 1: 写失败测试**

```js
// test/state.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const stateIo = require('../lib/state');

function freshDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-pet-test-'));
  process.env.PET_STATE_DIR = d;
  return d;
}

test('saveState/loadState 往返', () => {
  freshDir();
  stateIo.saveState({ version: 1, level: 3, xp: 2 });
  assert.deepEqual(stateIo.loadState(), { version: 1, level: 3, xp: 2 });
});

test('state 不存在返回 null', () => {
  freshDir();
  assert.equal(stateIo.loadState(), null);
});

test('state 损坏：备份后返回 null', () => {
  const d = freshDir();
  fs.writeFileSync(path.join(d, 'state.json'), '{broken json');
  assert.equal(stateIo.loadState(), null);
  const backups = fs.readdirSync(d).filter((f) => f.startsWith('state.corrupt-'));
  assert.equal(backups.length, 1);
});

test('overflow 追加/读取/清空', () => {
  freshDir();
  stateIo.appendOverflow({ type: 'tool', ts: 'x' });
  stateIo.appendOverflow({ type: 'stop', roll: 0.5, ts: 'y' });
  assert.deepEqual(stateIo.readOverflow(), [
    { type: 'tool', ts: 'x' },
    { type: 'stop', roll: 0.5, ts: 'y' },
  ]);
  stateIo.clearOverflow();
  assert.deepEqual(stateIo.readOverflow(), []);
});

test('tryWithLock 执行并释放', () => {
  const d = freshDir();
  let ran = false;
  assert.equal(stateIo.tryWithLock(() => { ran = true; }), true);
  assert.ok(ran);
  assert.equal(fs.existsSync(path.join(d, 'lock')), false);
});

test('锁被占：等满约 300ms 后返回 false 且不执行 fn', () => {
  const d = freshDir();
  fs.mkdirSync(path.join(d, 'lock'));
  let ran = false;
  const t0 = Date.now();
  assert.equal(stateIo.tryWithLock(() => { ran = true; }), false);
  assert.ok(!ran);
  assert.ok(Date.now() - t0 >= 250);
});

test('logError 写入 error.log 且不抛', () => {
  freshDir();
  stateIo.logError(new Error('boom'));
  const log = fs.readFileSync(path.join(process.env.PET_STATE_DIR, 'error.log'), 'utf8');
  assert.ok(log.includes('boom'));
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/state.test.js`
Expected: FAIL（`Cannot find module '../lib/state'`）

- [ ] **Step 3: 实现 lib/state.js**

```js
'use strict';
const fs = require('fs');
const path = require('path');

const LOCK_TIMEOUT_MS = 300;
const LOCK_SPIN_MS = 10;

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function stateDir() {
  return process.env.PET_STATE_DIR || path.join(process.env.HOME || '.', '.claude', 'claude-pet');
}
function statePath() { return path.join(stateDir(), 'state.json'); }
function overflowPath() { return path.join(stateDir(), 'overflow.jsonl'); }
function lockPath() { return path.join(stateDir(), 'lock'); }

function ensureDir() {
  fs.mkdirSync(stateDir(), { recursive: true });
}

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(statePath(), 'utf8'));
  } catch (e) {
    if (e.code === 'ENOENT') return null;
    try {
      fs.copyFileSync(statePath(), path.join(stateDir(), `state.corrupt-${Date.now()}.json`));
    } catch (_) { /* 尽力备份 */ }
    return null;
  }
}

function saveState(state) {
  ensureDir();
  const tmp = path.join(stateDir(), `.state.tmp-${process.pid}`);
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2) + '\n');
  fs.renameSync(tmp, statePath());
}

function appendOverflow(event) {
  ensureDir();
  fs.appendFileSync(overflowPath(), JSON.stringify(event) + '\n');
}

function readOverflow() {
  try {
    return fs
      .readFileSync(overflowPath(), 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((l) => JSON.parse(l));
  } catch (_) {
    return [];
  }
}

function clearOverflow() {
  try { fs.unlinkSync(overflowPath()); } catch (_) { /* 无文件即无积压 */ }
}

function logError(err) {
  try {
    ensureDir();
    const msg = err && err.stack ? err.stack : String(err);
    fs.appendFileSync(path.join(stateDir(), 'error.log'), `[${new Date().toISOString()}] ${msg}\n`);
  } catch (_) { /* 吞掉 */ }
}

function tryWithLock(fn) {
  ensureDir();
  const deadline = Date.now() + LOCK_TIMEOUT_MS;
  for (;;) {
    try {
      fs.mkdirSync(lockPath());
      break;
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      if (Date.now() >= deadline) return false;
      sleep(LOCK_SPIN_MS);
    }
  }
  try {
    fn();
    return true;
  } finally {
    try { fs.rmdirSync(lockPath()); } catch (_) { /* 尽力释放 */ }
  }
}

module.exports = {
  stateDir, statePath, overflowPath, lockPath,
  loadState, saveState, appendOverflow, readOverflow, clearOverflow,
  logError, tryWithLock,
};
```

- [ ] **Step 4: 跑全部测试确认通过**

Run: `node --test test/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lib/state.js test/state.test.js
git commit -m "feat: 原子状态存储、锁与容错"
```

---

### Task 6: 并发驱动（lib/store.js：锁内读改写 + overflow 折叠）

**Files:**
- Create: `lib/store.js`
- Test: `test/concurrency.test.js`

**Interfaces:**
- Consumes: `engine.applyPrompt/applyTool/applyStop`、`stateIo.*`
- Produces:
  - `runHookEvent(ev:object):{ok:boolean, busy?:boolean, result?:any}` —— 锁内：load（无则 newState）→ 折叠 overflow → `applyEvent` → save；锁超时：`appendOverflow(ev)` 后返回 `{ok:false, busy:true}`。`ev.type` ∈ `prompt|tool|stop`（stop 必带 `roll:number` 与 `ts:string`）；返回的 `result` 是 `applyEvent` 的引擎返回值（stop 时为 `{snackDrop, evolved, banner}`）
  - `runUserCommand(fn:(state:State)=>any):any` —— 锁内同上折叠，执行 `fn(state)` 并 save，返回 fn 结果；锁超时返回 `{ok:false, busy:true, msg:'状态文件忙（可能有其他终端在写），请重试'}`
  - `applyEvent(state, ev):any` —— 事件→引擎调用映射（模块内函数，导出便于测试）
  - `STAGES` —— `loadStages()` 结果（模块加载时求值一次）

- [ ] **Step 1: 写失败测试**

```js
// test/concurrency.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, execFileSync } = require('child_process');
const stateIo = require('../lib/state');
const store = require('../lib/store');
const engine = require('../lib/engine');

const NOW = '2026-08-27T00:00:00.000Z';
const BIN = path.join(__dirname, '..', 'bin', 'claude-pet');

function freshDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-pet-test-'));
  process.env.PET_STATE_DIR = d;
  return d;
}

test('runHookEvent 首次写入自动建档', () => {
  freshDir();
  const r = store.runHookEvent({ type: 'prompt', ts: NOW });
  assert.equal(r.ok, true);
  const st = stateIo.loadState();
  assert.equal(st.level, 1);
  assert.equal(st.xp, 5);
});

test('applyEvent: stop 事件用事件内 roll 折叠', () => {
  const s = engine.newState(NOW, store.STAGES);
  store.applyEvent(s, { type: 'stop', roll: 0.1, ts: NOW });
  assert.equal(s.xp, 10);
  assert.equal(s.snacks, 1); // roll 0.1 < 0.25
});

test('锁被占：hook 事件进 overflow，下次写入时折叠合并', () => {
  const d = freshDir();
  fs.mkdirSync(path.join(d, 'lock'));
  const r = store.runHookEvent({ type: 'prompt', ts: NOW });
  assert.equal(r.busy, true);
  assert.equal(fs.existsSync(path.join(d, 'overflow.jsonl')), true);
  fs.rmdirSync(path.join(d, 'lock'));
  store.runUserCommand((s) => { engine.applyPet(s, store.STAGES, NOW, () => 0); });
  const st = stateIo.loadState();
  assert.equal(st.xp, 5); // overflow 的 prompt +5 已折进来
  assert.equal(st.petsCount, 1);
  assert.equal(fs.existsSync(path.join(d, 'overflow.jsonl')), false);
});

test('锁被占：用户命令直接提示重试，不写 overflow', () => {
  const d = freshDir();
  fs.mkdirSync(path.join(d, 'lock'));
  const r = store.runUserCommand(() => { throw new Error('不应执行'); });
  assert.equal(r.busy, true);
  assert.ok(r.msg.includes('重试'));
  assert.equal(fs.existsSync(path.join(d, 'overflow.jsonl')), false);
});

test('双进程并发 + 后续一次写入：XP 一条不丢（确定性）', async () => {
  freshDir();
  execFileSync('node', [BIN, 'session'], { input: '' }); // 建档
  const ps = [spawn('node', [BIN, 'tool']), spawn('node', [BIN, 'tool'])];
  ps.forEach((p) => p.stdin.end('{}'));
  const codes = await Promise.all(ps.map((p) => new Promise((res) => p.on('exit', (c) => res(c)))));
  assert.deepEqual(codes, [0, 0]);
  execFileSync('node', [BIN, 'tool'], { input: '{}' }); // 串行最后一次必折叠全部积压
  const st = stateIo.loadState();
  assert.equal(st.xp, 6); // 2 并发 +2 与 1 串行 +2，共 6
  assert.equal(st.toolsThisTurn, 3);
});
```

说明：并发两个进程必有一个拿锁、另一个进 overflow；随后那次串行写入把 overflow 折叠合并，因此断言是确定性的 `xp=6`。

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/concurrency.test.js`
Expected: FAIL（`Cannot find module '../lib/store'`；最后一条因 bin 不存在 FAIL 属预期，前三条先失败即可）

- [ ] **Step 3: 实现 lib/store.js**

```js
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
  for (const ev of stateIo.readOverflow()) applyEvent(state, ev);
  stateIo.clearOverflow();
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
```

- [ ] **Step 4: 跑测试**

Run: `node --test test/concurrency.test.js`
Expected: 前四条 PASS；最后一条 FAIL（`Cannot find module .../bin/claude-pet`）——**这是预期**，bin 在 Task 8 创建；本条是给 Task 8 的预置回归测试。为保持本任务绿灯，先临时跳过：在该 test 前加 `{ skip: 'bin 于 Task 8 提供' }` 选项（`test('...', { skip: 'bin 于 Task 8 提供' }, async () => {...})`），Task 8 再移除 skip 并复跑。

- [ ] **Step 5: 提交**

```bash
git add lib/store.js test/concurrency.test.js
git commit -m "feat: 锁内读改写驱动与 overflow 折叠"
```

---

### Task 7: 渲染（状态栏 + 面板）

**Files:**
- Create: `lib/render.js`
- Test: `test/render.test.js`

**Interfaces:**
- Consumes: `engine.xpForLevel`、State/Stage 类型
- Produces:
  - `progressBar(pct:number, width:number):string` —— `'▓'×filled + '░'×(width-filled)`，pct 钳制 [0,1]
  - `renderStatusline(state:State, stages:Stage[]):string` —— 格式 `🐉 神龙 Lv.45 ▓▓▓▓▓▓ 100% · 本轮+64xp · 🍪3`；`PET_ASCII=1` 时纯文本 `[神龙 Lv.45 100% +64xp 零食3]`
  - `renderPanel(state:State, stages:Stage[]):string` —— 多行面板：形态大字、名字等级、XP 条、零食/转生/摸头、陪伴天数（`floor((now-born)/86400000)+1`）、图鉴串（如 `🥚 🐣 🦎 (3/7)`）

- [ ] **Step 1: 写失败测试**

```js
// test/render.test.js
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/render.test.js`
Expected: FAIL（`Cannot find module '../lib/render'`）

- [ ] **Step 3: 实现 lib/render.js**

```js
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
  return Math.floor((Date.now() - born) / 86400000) + 1;
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
    `│   🍪 零食 ${state.snacks}    🔁 转生 ${state.rebirths}`,
    `│   🤗 摸头 ${state.petsCount} 次`,
    `│   🎂 陪伴 ${daysTogether(state)} 天`,
    '╰──────────────────────────╯',
    `图鉴 ${state.dex.length}/${stages.length}：${dexForms}`,
  ];
  if (state.level >= engine.MAX_LEVEL) {
    lines.push('已满级，可转生：/claude-pet:pet 说"转生"');
  }
  return lines.join('\n');
}

module.exports = { progressBar, renderStatusline, renderPanel };
```

- [ ] **Step 4: 跑全部测试确认通过**

Run: `node --test test/`
Expected: PASS（concurrency 最后一条仍 skip）

- [ ] **Step 5: 提交**

```bash
git add lib/render.js test/render.test.js
git commit -m "feat: 状态栏与宠物面板渲染"
```

---

### Task 8: CLI 入口（bin/claude-pet）

**Files:**
- Create: `bin/claude-pet`（无扩展名，shebang，chmod +x）
- Modify: `test/concurrency.test.js`（移除最后一条的 skip）
- Test: `test/cli.test.js`

**Interfaces:**
- Consumes: 全部 lib 模块
- Produces: 子命令 `session|prompt|tool|stop`（转交 `lib/hooks.js` 的 `hooksMain(argv)`，Task 9 实现；本任务先建占位转发）、`status`（打印面板）、`statusline`（打印单行，无档时用 newState 渲染**不落盘**）、`feed`/`pet`/`rebirth`（runUserCommand 包裹引擎调用并打印 msg）、`version`。进程级 `uncaughtException` → `logError` + `exit 0`。

- [ ] **Step 1: 写失败测试**

```js
// test/cli.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const stateIo = require('../lib/state');
const engine = require('../lib/engine');
const { FALLBACK_STAGES } = require('../lib/species');

const BIN = path.join(__dirname, '..', 'bin', 'claude-pet');
const NOW = '2026-08-27T00:00:00.000Z';

function freshDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-pet-test-'));
  process.env.PET_STATE_DIR = d;
  return d;
}

function run(args, input) {
  return execFileSync('node', [BIN, ...args], { encoding: 'utf8', input: input || '' });
}

function seedState(d, over) {
  const s = engine.newState(NOW, FALLBACK_STAGES);
  Object.assign(s, over || {});
  fs.writeFileSync(path.join(d, 'state.json'), JSON.stringify(s));
  return s;
}

test('status：建档后面板含 Lv 与形态', () => {
  freshDir();
  run(['session']);
  const out = run(['status']);
  assert.ok(out.includes('Lv.1'));
  assert.ok(out.includes('🥚'));
});

test('statusline：无档时渲染蛋且不落盘', () => {
  const d = freshDir();
  const out = run(['statusline']);
  assert.ok(out.includes('🥚'));
  assert.ok(out.includes('Lv.1'));
  assert.equal(fs.existsSync(path.join(d, 'state.json')), false);
});

test('feed：无零食提示', () => {
  freshDir();
  run(['session']);
  const out = run(['feed']);
  assert.ok(out.includes('没有零食'));
});

test('feed：有零食扣 1 加经验', () => {
  freshDir();
  run(['session']);
  seedState(process.env.PET_STATE_DIR, { snacks: 2, level: 2, xp: 0 });
  const out = run(['feed']);
  assert.ok(out.includes('+7'));
  const st = stateIo.loadState();
  assert.equal(st.snacks, 1);
});

test('pet：摸头有反应文案', () => {
  freshDir();
  run(['session']);
  const out = run(['pet']);
  assert.ok(out.trim().length > 0);
});

test('rebirth：未满级拒绝', () => {
  freshDir();
  run(['session']);
  const out = run(['rebirth']);
  assert.ok(out.includes('还未满级'));
});

test('未知子命令 exit 0 且有 usage', () => {
  freshDir();
  const out = run([]);
  assert.ok(out.includes('用法'));
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/cli.test.js`
Expected: FAIL（spawn ENOENT：bin/claude-pet 不存在）

- [ ] **Step 3: 实现 bin/claude-pet**

```js
#!/usr/bin/env node
'use strict';

const stateIo = require('../lib/state');
process.on('uncaughtException', (err) => {
  stateIo.logError(err);
  process.exit(0);
});

function main() {
  const engine = require('../lib/engine');
  const species = require('../lib/species');
  const store = require('../lib/store');
  const render = require('../lib/render');
  const STAGES = store.STAGES;
  const argv = process.argv.slice(2);
  const sub = argv[0];

  if (['prompt', 'tool', 'stop', 'session'].includes(sub)) {
    require('../lib/hooks').hooksMain(argv);
    return;
  }

  switch (sub) {
    case 'status': {
      const state = stateIo.loadState();
      if (!state) {
        console.log('还没有宠物档案。开始一次对话（任意 prompt）即可孵蛋 🥚');
        return;
      }
      console.log(render.renderPanel(state, STAGES));
      return;
    }
    case 'statusline': {
      const state = stateIo.loadState() || engine.newState(new Date().toISOString(), STAGES);
      process.stdout.write(render.renderStatusline(state, STAGES) + '\n');
      return;
    }
    case 'feed': {
      const r = store.runUserCommand((s) => engine.applyFeed(s, STAGES, new Date().toISOString()));
      console.log(r.msg || '系统繁忙，请重试');
      return;
    }
    case 'pet': {
      const r = store.runUserCommand((s) => engine.applyPet(s, STAGES, new Date().toISOString(), Math.random));
      console.log(r.msg || '系统繁忙，请重试');
      return;
    }
    case 'rebirth': {
      const r = store.runUserCommand((s) => engine.applyRebirth(s, STAGES, new Date().toISOString()));
      console.log(r.msg || '系统繁忙，请重试');
      return;
    }
    case 'version':
      console.log('claude-pet 0.1.0');
      return;
    default:
      console.log('用法: claude-pet <status|statusline|feed|pet|rebirth|version>');
      console.log('（prompt/tool/stop/session 由 Claude Code hooks 调用）');
  }
}

try {
  main();
} catch (err) {
  stateIo.logError(err);
  process.exit(0);
}
```

`lib/hooks.js` 本任务先建最小占位（Task 9 完整实现），保证 CLI 可加载：

```js
'use strict';

function hooksMain() {
  // Task 9 完整实现
}

module.exports = { hooksMain };
```

然后：`chmod +x bin/claude-pet`

并移除 `test/concurrency.test.js` 最后一条的 `{ skip: ... }` 选项。

- [ ] **Step 4: 跑全部测试确认通过**

Run: `node --test test/`
Expected: PASS（含 concurrency 双进程条）

- [ ] **Step 5: 提交**

```bash
git add bin/claude-pet lib/hooks.js test/cli.test.js test/concurrency.test.js
git commit -m "feat: CLI 入口与用户命令"
```

---

### Task 9: Hook 处理器与 hooks.json 接线

**Files:**
- Modify: `lib/hooks.js`（完整实现，替换占位）
- Create: `hooks/hooks.json`
- Test: `test/hooks.test.js`

**Interfaces:**
- Consumes: `store.runHookEvent/runUserCommand`、`stateIo.loadState`
- Produces: `hooksMain(argv:string[]):void` —— 先同步读完 stdin（异常吞掉）；分派：
  - `prompt` → `runHookEvent({type:'prompt', ts})`
  - `tool` → `runHookEvent({type:'tool', ts})`
  - `stop` → `runHookEvent({type:'stop', roll:Math.random(), ts})`；若 `result.banner` 则 stdout 输出 `JSON.stringify({systemMessage: banner})`
  - `session` → 无档时 `runUserCommand(()=>{})` 建档；有档且 `Date.now()-Date.parse(lastActive) > 48h` 时 stdout 一行想念语
  - 未知子命令静默退出
- `hooks/hooks.json`：四事件 → `node "${CLAUDE_PLUGIN_ROOT}/bin/claude-pet" <sub>`，PostToolUse 不加 matcher（全工具）

- [ ] **Step 1: 写失败测试**

```js
// test/hooks.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const stateIo = require('../lib/state');
const engine = require('../lib/engine');
const { FALLBACK_STAGES } = require('../lib/species');

const BIN = path.join(__dirname, '..', 'bin', 'claude-pet');
const NOW = '2026-08-27T00:00:00.000Z';

function freshDir() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-pet-test-'));
  process.env.PET_STATE_DIR = d;
  return d;
}

function run(args, input) {
  return execFileSync('node', [BIN, ...args], { encoding: 'utf8', input: input === undefined ? '{}' : input });
}

test('session：建档且平时无输出', () => {
  const d = freshDir();
  const out = run(['session']);
  assert.equal(out.trim(), '');
  assert.ok(fs.existsSync(path.join(d, 'state.json')));
});

test('session：超 48 小时输出想念语', () => {
  const d = freshDir();
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.lastActive = '2026-08-20T00:00:00.000Z'; // 7 天前
  fs.writeFileSync(path.join(d, 'state.json'), JSON.stringify(s));
  const out = run(['session']);
  assert.ok(out.includes('想你了'));
});

test('stop：进化时输出 systemMessage JSON', () => {
  const d = freshDir();
  const s = engine.newState(NOW, FALLBACK_STAGES);
  s.level = 2; s.xp = engine.xpForLevel(2) - 10; s.stage = 0; s.stageAtTurnStart = 0;
  fs.writeFileSync(path.join(d, 'state.json'), JSON.stringify(s));
  const out = run(['stop']);
  const parsed = JSON.parse(out);
  assert.ok(parsed.systemMessage.includes('进化'));
});

test('stop：未进化时无输出', () => {
  freshDir();
  run(['session']);
  const out = run(['stop']);
  assert.equal(out.trim(), '');
});

test('stdin 非法 JSON 仍 exit 0', () => {
  freshDir();
  run(['session']);
  const out = run(['tool'], 'not-json-at-all');
  assert.equal(out.trim(), '');
  const st = stateIo.loadState();
  assert.equal(st.xp, 2); // 事件仍生效
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test test/hooks.test.js`
Expected: 前两条 PASS（占位 hooksMain 无操作但 session 子命令走占位→无建档，实际 FAIL）；至少「session：建档」「进化 systemMessage」两条 FAIL 即可进入实现

- [ ] **Step 3: 实现 lib/hooks.js（替换占位）与 hooks/hooks.json**

`lib/hooks.js`：

```js
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
```

`hooks/hooks.json`：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/bin/claude-pet\" prompt" } ] }
    ],
    "PostToolUse": [
      { "hooks": [ { "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/bin/claude-pet\" tool" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/bin/claude-pet\" stop" } ] }
    ],
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/bin/claude-pet\" session" } ] }
    ]
  }
}
```

- [ ] **Step 4: 跑全部测试确认通过**

Run: `node --test test/`
Expected: 全部 PASS

- [ ] **Step 5: 插件校验 + 提交**

Run: `claude plugin validate /home/plugin/claude-pet`
Expected: `✔ Validation passed`（如本机无 claude CLI 则记入 Task 11 清单补跑）

```bash
git add lib/hooks.js hooks/hooks.json test/hooks.test.js
git commit -m "feat: 生命周期 hook 处理器与接线"
```

---

### Task 10: Skills（/claude-pet:pet 面板互动 + /claude-pet:setup 状态栏配置）

**Files:**
- Create: `skills/pet/SKILL.md`
- Create: `skills/setup/SKILL.md`

**Interfaces:**
- Consumes: Task 8 的 CLI 子命令（插件 bin 目录已在会话 PATH 中，直接 `claude-pet <sub>`）
- Produces: 两个用户可调用 skill

- [ ] **Step 1: 写 skills/pet/SKILL.md**

```markdown
---
description: 查看 claude-pet 电子宠物状态，并进行摸头、喂食、转生等互动。用户提到"宠物""摸头""喂食""转生"时使用。
---

# claude-pet 宠物面板

运行 `claude-pet status`（在 Bash 中直接可用，无需路径），把输出原样放进代码块展示给用户，不要改写数字。

然后按用户意图操作（每个动作都是一次独立的 Bash 调用，运行后把输出原文展示给用户）：

- 摸头 → `claude-pet pet`
- 喂零食（+经验）→ `claude-pet feed`
- 转生（需 Lv.45）→ `claude-pet rebirth`
- 只看状态 → 无需额外命令

用户没说具体动作时，只展示面板，然后一句话列出可做的事（摸头/喂食/转生）。

若命令报"状态文件忙"或"还没有宠物档案"，如实转告：档案会在下一次对话开始时自动创建。
```

- [ ] **Step 2: 写 skills/setup/SKILL.md**

```markdown
---
description: 一键配置 claude-pet 状态栏（修改 ~/.claude/settings.json 的 statusLine）。用户说"配置状态栏""setup""状态栏不显示"时使用。
---

# claude-pet 状态栏配置

按顺序执行：

1. 找到插件根目录：`PET_ROOT=$(dirname "$(dirname "$(readlink -f "$(command -v claude-pet)")")")`，确认 `$PET_ROOT/bin/claude-pet` 存在；若 `command -v claude-pet` 失败，请用户重启会话后重试。
2. 生成启动器 `~/.claude/claude-pet/statusline-launcher.sh`（用 Write 工具，内容如下，其中 PET_ROOT 换成第 1 步的绝对路径）：

   ```sh
   #!/bin/sh
   exec node "PET_ROOT/bin/claude-pet" statusline
   ```

3. `chmod +x ~/.claude/claude-pet/statusline-launcher.sh`
4. 读取 `~/.claude/settings.json`（不存在则 `{}`）：
   - 已有 `statusLine` 字段 → 停下询问用户：「检测到已有状态栏配置。替换为宠物状态栏，还是保留原状（宠物只在 /claude-pet:pet 面板显示）？」得到明确答复再继续；选保留则到此结束。
   - 无 `statusLine` → 用 node 合并写入（保留其他键）：

     ```bash
     node -e '
     const fs=require("fs"),p=process.env.HOME+"/.claude/settings.json";
     let s={};try{s=JSON.parse(fs.readFileSync(p,"utf8"))}catch(e){}
     s.statusLine={type:"command",command:process.env.HOME+"/.claude/claude-pet/statusline-launcher.sh"};
     fs.mkdirSync(require("path").dirname(p),{recursive:true});
     fs.writeFileSync(p,JSON.stringify(s,null,2)+"\n");
     console.log("statusLine 已写入");'
     ```

5. 验证：运行 `~/.claude/claude-pet/statusline-launcher.sh`，应输出一行含 🥚 与 Lv.1 的状态栏。
6. 告知用户：重启 Claude Code（或新开终端）后状态栏生效；插件升级后若路径变化，重跑本命令即可。
```

- [ ] **Step 3: 验证**

Run: `claude plugin validate /home/plugin/claude-pet`
Expected: `✔ Validation passed`

Run: `ls skills/pet/SKILL.md skills/setup/SKILL.md && head -4 skills/pet/SKILL.md`
Expected: 两个文件存在且 frontmatter 完整

- [ ] **Step 4: 提交**

```bash
git add skills
git commit -m "feat: pet 面板与 setup 状态栏配置 skill"
```

---

### Task 11: README 与端到端验证

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: 全部已交付功能
- Produces: 文档 + 完整验证记录（E2E 模拟 + 插件校验）

- [ ] **Step 1: 写 README.md**

````markdown
# claude-pet 🥚→🐉

Claude Code 放置挂机电子宠物：**Claude 干活 = 你的宠物成长**。等待长任务时瞄一眼状态栏，看它吃饭升级。

## 玩法

| 事件 | 效果 |
|---|---|
| 你发一条 prompt | +5 XP |
| Claude 每次工具调用 | +2 XP |
| 一轮完成 | +10 XP，25% 掉零食；每轮第 15 次工具必掉 |
| 喂零食 `/claude-pet:pet` | +当前升级需求 40% 的 XP |
| 摸头 | 每 10 次叼出 1 零食 |

进化：🥚Lv1 → 🐣Lv3 → 🦎Lv8 → 🦖Lv16 → 🦕Lv26 → 🐲Lv38 → 🐉Lv45。满级可转生：回到蛋，经验永久 +15%/世，图鉴保留。**零惩罚**——不喂不会死，离线不衰减。

## 安装（本地开发）

```bash
claude --plugin-dir /path/to/claude-pet
```

安装后第一次对话自动建档。状态栏：会话内运行 `/claude-pet:setup` 一键配置。

## 日常使用

- 状态栏实时显示：`🐲 云中蛟 Lv.42 ▓▓▓░░ 62% · 本轮+64xp · 🍪3`
- `/claude-pet:pet`：看面板、摸头、喂食、转生
- 无 emoji 终端：`export PET_ASCII=1`

## 数据与卸载

状态在 `~/.claude/claude-pet/`（明文 JSON，可备份可手改）。卸载：移除插件 + 删除该目录 + 删 `~/.claude/settings.json` 的 `statusLine`。
````

- [ ] **Step 2: 模拟完整回合（E2E）**

Run（真实走一遍 hook 链路，验证游戏行为）：

```bash
cd /home/plugin/claude-pet
export PET_STATE_DIR=$(mktemp -d)
node bin/claude-pet session            # 建档（应无输出）
echo '{}' | node bin/claude-pet prompt # +5
echo '{}' | node bin/claude-pet tool   # +2
echo '{}' | node bin/claude-pet tool   # +2
echo '{}' | node bin/claude-pet stop   # +10（可能掉零食）
node bin/claude-pet status             # 面板：Lv.1，XP 19/15 → 已升 Lv.2
node bin/claude-pet statusline         # 单行状态栏
```

Expected: status 显示 Lv.2（19 XP = 15+4 升级后余 4），statusline 含 `▓` 进度条与 `🍪`；`$PET_STATE_DIR/error.log` 不存在

- [ ] **Step 3: 极速进化验证（横幅路径）**

```bash
export PET_STATE_DIR=$(mktemp -d)
node bin/claude-pet session
node -e '
const fs=require("fs"),p=process.env.PET_STATE_DIR+"/state.json";
const s=JSON.parse(fs.readFileSync(p,"utf8"));
s.level=2;s.xp=7;s.stage=0;s.stageAtTurnStart=0;
fs.writeFileSync(p,JSON.stringify(s));'
echo '{}' | node bin/claude-pet stop   # 7+10=17 → Lv3 进化
```

Expected: 输出 `{"systemMessage":"🎉 进化！破壳 🐣"}`

- [ ] **Step 4: 插件校验**

Run: `claude plugin validate /home/plugin/claude-pet`
Expected: `✔ Validation passed`（若本环境无 claude CLI，明确记录"待用户环境补跑"）

- [ ] **Step 5: 全量测试 + 提交**

Run: `node --test test/`
Expected: 全部 PASS

```bash
git add README.md
git commit -m "docs: README 与端到端验证"
```

- [ ] **Step 6: 真机冒烟（需要用户参与，单独确认）**

在真实 Claude Code 中：`claude --plugin-dir /home/plugin/claude-pet` → 随便发一句 → 观察状态栏/XP → `/claude-pet:setup` → 重启验证状态栏。此项完成后 v1 收工。

---

## Self-Review 记录

- **Spec 覆盖**：§3 数值（Task 1-4）、§4.1 结构（Task 1/8/9/10）、§4.2-4.4 状态与并发（Task 5/6）、§4.5 性能（Node 冷启 + 快 IO，无额外任务）、§4.6 容错（Task 5/8）、§4.7 状态栏（Task 7/8/10）、§4.8 hooks（Task 9）、§5 skills（Task 10）、§6 测试（各任务 + Task 11 E2E）——无缺项
- **占位符**：无 TBD/TODO；Task 8 的 hooks.js 占位在 Task 9 替换为完整实现，属计划内两步交付
- **类型一致**：`applyXp(state, baseAmount, stages, now)` 等签名跨任务一致；`runHookEvent` 返回 `{ok, busy?, result?}` 与 Task 9 用法一致；`STAGES` 由 store 导出供 hooks 使用
