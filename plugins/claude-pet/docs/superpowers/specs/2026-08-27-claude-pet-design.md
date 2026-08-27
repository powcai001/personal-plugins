# claude-pet 设计文档（v1）

- 日期：2026-08-27
- 状态：方案已与需求方确认
- 项目目录：`/home/plugin/claude-pet`

## 1. 背景与目标

Claude Code 执行长任务时用户只能盯着 spinner。市场调研结论：

- **claudemon**（宝可梦遭遇）证明"游戏进度与 Claude 工作绑定"比单纯打发时间更有黏性
- **fragwait**（等待时玩的终端 FPS）验证需求真实存在
- 大量"完成后通知"类插件说明等待无聊是普遍痛点，但专门做"等待小游戏"的插件仅 2~3 个，未饱和

核心约束：Claude Code 运行时独占终端 TTY，无法在同一窗口玩实时游戏，因此 v1 选择放置挂机路线。

**目标**：Claude 干活 = 宠物涨经验，升级进化，满级转生。零依赖、零惩罚、绝不拖慢 Claude。

**成功标准**：

1. 发一条 prompt 后数秒内，状态栏 XP 可见变化
2. 新用户前 5 分钟拿到首次升级，同一 session 内可见首次进化（Lv3）
3. 工具循环无可感知变慢（单次 hook < 100ms）
4. 状态跨 session / 跨项目 / 多终端共享，并发不丢经验
5. 游戏内部任何错误都不影响 Claude 正常工作（hooks 永远 exit 0）

## 2. 范围

### v1 做

- 进化链养成：🥚→🐣→🦎→🦖→🦕→🐲→🐉
- 状态栏实时展示 XP / 等级 / 形态 / 零食
- `/claude-pet:pet` 面板与互动（喂食 / 摸头 / 转生）
- `/claude-pet:setup` 状态栏一键配置
- 图鉴与转生永久倍率
- 多终端并发安全

### v1 不做（明确排除）

- tmux 分屏实时游戏（二期）
- 多物种初始选择（`species.json` 结构预留扩展）
- 菜园经济系统
- 饥饿 / 心情 / 离线衰减等惩罚机制（产品原则：零负罪感）
- Windows 适配（v1 仅 POSIX：Linux / macOS）
- community marketplace 发布（本地验证后再定）

## 3. 玩法数值

### XP 来源

| 事件 | XP | 触发点 |
|---|---|---|
| 用户发 prompt | +5 | UserPromptSubmit hook |
| Claude 工具调用 | +2 | PostToolUse hook |
| 一轮完成 | +10 | Stop hook |

参考速率：轻度 ≈ 275 XP/天（50 工具 + 15 prompt + 10 轮），重度 ≈ 1050 XP/天。

### 升级曲线

- N → N+1 所需 XP：`ceil(15 × 1.10^(N-1))`
- Lv1→2 = 15 XP（约 3 次工具调用，即开即爽）
- Lv2→3 = 17 XP，首次进化（Lv3）在开档几分钟内达成
- Lv44→45 ≈ 900 XP；满级累计 ≈ 9.8k XP
- 节奏：轻度约 5 周、重度约 10 天满级；零食与转生倍率可再加速

### 进化链（data/species.json）

| 达到等级 | 形态 | 名字 |
|---|---|---|
| 1 | 🥚 | 神秘的蛋 |
| 3 | 🐣 | 破壳 |
| 8 | 🦎 | 小蜥蜴 |
| 16 | 🦖 | 暴龙少年 |
| 26 | 🦕 | 长颈龙 |
| 38 | 🐲 | 云中蛟 |
| 45 | 🐉 | 神龙（满级） |

### 零食

- 获取：Stop 时 25% 概率掉落；单轮工具调用每满 15 次必掉 1 颗（计数每轮 prompt 时重置）；摸头每累计 10 次宠物叼出 1 颗
- 上限 9 颗，已满则不再掉落
- 喂食：立得当前等级升级所需 XP 的 40%（向上取整）

### 转生

- 条件：Lv45（满级）
- 效果：等级与 XP 重置为 Lv1 🥚；图鉴记录满级形态与时间；此后所有 XP 获取 ×(1 + 0.15 × 转生数)；零食库存保留（满级时喂食无效，提示"已达满级，零食留着转生后用"）
- 图鉴：记录历史解锁的所有形态，跨转生保留

### 通知横幅（Stop hook 的 systemMessage）

仅三类事件弹横幅：**进化、首次满级、转生**。普通升级与零食掉落不弹（进状态栏即可）。

### 离线

无任何衰减。距上次活跃 > 48 小时，SessionStart hook 的 stdout 输出一行想念语（该 hook 的 stdout 会进入会话上下文），否则静默 exit 0；不弹横幅。

## 4. 架构

### 4.1 目录结构

```
claude-pet/
├── .claude-plugin/plugin.json    # name: claude-pet, version: 0.1.0
├── hooks/hooks.json              # 四个 hook → node ${CLAUDE_PLUGIN_ROOT}/bin/pet.js <sub>
├── bin/pet.js                    # 全部游戏逻辑；Node ≥18 标准库；单文件；无第三方依赖
├── data/species.json             # 进化链数据（结构支持多物种扩展）
├── skills/pet/SKILL.md           # 面板查看与互动
├── skills/setup/SKILL.md         # 状态栏配置
└── docs/                         # 设计文档
```

> 勘误（2026-08-27）：实施时将单文件 bin/pet.js 拆为 bin/claude-pet（入口）+ lib/ 模块（engine/species/state/store/render/hooks），仍是 Node 标准库零依赖；见实施计划 Task 1。

### 4.2 运行时状态（`~/.claude/claude-pet/`，不在插件目录内）

- `state.json`：唯一权威状态（原子写：temp + rename）
- `overflow.jsonl`：锁竞争降级通道（正常为空，见 4.4）
- `lock/`：mkdir 型互斥锁目录
- `error.log`：吞掉的异常（调试用）
- `state.corrupt-<ts>.json`：损坏状态自动备份

不在插件目录的原因：插件升级 / 重装不丢档；多项目、多终端天然共享。

### 4.3 状态模型（state.json）

```json
{
  "version": 1,
  "level": 42,
  "xp": 834,
  "rebirths": 1,
  "dex": [{ "form": "🐉", "name": "神龙", "ts": "2026-08-20T..." }],
  "snacks": 3,
  "toolsThisTurn": 7,
  "turnXp": 64,
  "petsCount": 12,
  "born": "2026-08-01T...",
  "lastActive": "2026-08-27T..."
}
```

### 4.4 并发模型（多终端同时写）

1. 写路径（所有 hook 与互动命令共用）：`mkdir lock`（自旋 10ms、上限 300ms）→ 读 state.json → 应用事件 → temp+rename 原子写回 → `rmdir lock`
2. 锁超时降级：把本次事件追加到 `overflow.jsonl`（单行 ≤ 4KB，append 原子）后立即退出，绝不阻塞 Claude
3. 任何拿锁成功的写路径，先 fold `overflow.jsonl` 中的积压事件进状态并清空该文件
4. 读取（statusline / status）：只读 state.json，不 fold，O(1) 快
5. `version` 字段留作未来状态迁移

### 4.5 性能预算

- 单次 hook：Node 冷启 ~50-80ms + 同步 IO < 20ms，总 < 100ms，工具循环无感
- v1 不做常驻进程；若实测偏慢再优化

### 4.6 容错

- `pet.js` 全局 try/catch + `uncaughtException` 兜底 → 一律 exit 0，错误写 error.log
- state.json 损坏 / 不存在：损坏文件备份为 `state.corrupt-<ts>.json` 后重置新档
- species.json 缺失 / 损坏：使用代码内置的同一份进化链兜底
- hook stdin JSON 尽力读取，格式异常不报错

### 4.7 状态栏

- 输出格式：`🐉 神龙 Lv.42 ▓▓▓▓░░ 78% · 本轮+64xp · 🍪3`（6 格进度条）
- setup 生成 `~/.claude/claude-pet/statusline-launcher.sh`（解析当前插件绝对路径调用 `pet.js statusline`），`~/.claude/settings.json` 的 statusLine 指向该 launcher；插件路径变化后重跑 `/claude-pet:setup` 即可
- 用户已有自定义 statusLine：setup 询问「替换为宠物状态栏」或「跳过状态栏（仅用 /pet 面板）」，v1 不做自动合并
- 无 emoji 终端兜底：环境变量 `PET_ASCII=1` 切换纯文本 `[龙 Lv42 78% +64xp]`

### 4.8 hooks 映射

| Hook | 子命令 | 行为 |
|---|---|---|
| UserPromptSubmit | `prompt` | +5 XP；重置 toolsThisTurn、turnXp |
| PostToolUse | `tool` | +2 XP；toolsThisTurn++；满 15 掉零食 |
| Stop | `stop` | +10 XP；25% 掉零食；进化 / 满级判定，命中则 stdout 输出 `{"systemMessage": "..."}` |
| SessionStart | `session` | 初始化新档；>48h 附想念提示 |

## 5. Skills

- `pet/SKILL.md`：运行 `pet.js status` 渲染 ASCII 面板（形态、等级、XP 条、零食、转生数、陪伴天数）；按用户意图执行 `feed` / `pet` / `rebirth` 并展示结果文案（摸头有随机可爱反应文案）
- `setup/SKILL.md`：检测 `~/.claude/settings.json` 的 statusLine → 生成 launcher → 写配置；已有自定义状态栏时按 4.7 询问；完成后提示重启验证

## 6. 测试策略

### 单元测试（node:test，零依赖）

- XP 曲线：Lv1 需 15；升级边界（恰好够 / 差 1）；一次大额 XP 连升多级
- 进化：Lv3/8/16/26/38/45 形态切换；满级横幅只触发一次
- 转生：重置等级但保留 dex / rebirths / 倍率；倍率作用于后续 XP
- 零食：25% 概率路径（可注入随机源）、15 次工具必掉、上限 9 停掉、喂食 40% 计算
- 并发：锁超时 → overflow → 下次拿锁合并；双进程并发不崩溃
- 容错：损坏 state.json → 备份 + 重置；species.json 缺失 → 内置链兜底

### 手测清单（E2E）

`claude --plugin-dir ./claude-pet` 加载 → 发 prompt → 状态栏跳动 → 造 XP 直升 Lv3 验证进化横幅 → 重开 session 验证存档 → `/claude-pet:pet` 互动三连（摸头 / 喂食 / 转生）

## 7. 产品原则

1. **零负罪感**：绝不惩罚不玩的人
2. **绝不拖慢工作**：游戏是 Claude 的影子，不是同事
3. **惊喜留给里程碑**：横幅只在进化 / 满级 / 转生
4. **状态属于用户**：明文 JSON，可备份可手改

## 8. 发布路径（记录，不属 v1 任务）

git 仓库 → `claude plugin validate` → （可选）community marketplace 提交
