# personal-plugins

> 给 Claude Code 的三个轻量插件：**状态栏**、**健康提醒**、**电子宠物**。纯本地运行、零模型调用、无第三方依赖。

[![Claude Code Plugins](https://img.shields.io/badge/Claude%20Code-Plugins-blue)](https://claude.com/claude-code)
[![python3](https://img.shields.io/badge/python3-零依赖-brightgreen)](https://www.python.org/)
[![node](https://img.shields.io/badge/node-%E2%89%A518%20%E4%BB%85claude--pet-orange)](https://nodejs.org/)

三个插件可以单独装，也可以组合成一套"会照顾你的终端"：

- **statusline** —— 纯 python3 状态栏渲染器，~36ms 刷新，替换 npx 类重量级方案
- **health-reminder** —— 定时提醒站起来、喝水、伸懒腰；倒计时进状态栏，到点弹横幅
- **claude-pet** —— 放置挂机电子宠物：Claude 干活 = 宠物成长，升级进化，满级转生

## 效果预览

三个插件全装后，终端底部状态栏长这样（三行分层：**工作 · 节律 · 陪伴**）：

```
 ✱ opus-5 │ personal-plugins │ ▓▓▓▓▓▓░░░░ 62% │ ⎇ main✱
 💧 32m │ ⏱ 45m │ 🕐 14:32
 🦎 小蜥蜴 │ Lv.13 ▰▰▰▰▰▰▰▰▱▱ 75% │ 🍪3 │ 📜 1969·ARPANET 四节点首次联机
```

- 第 1 行 **工作**：模型 · 上下文占比（1M 窗口自适应）· git 分支/脏标记/领先落后
- 第 2 行 **节律**：💧 距下次提醒倒计时 · ⏱ 连续工作时长 · 🕐 时钟（深夜变红）
- 第 3 行 **陪伴**：宠物实时状态 · 🍪 零食数 · 📜 科技史小知识（内置 150 条，按小时轮换）

到点未休息时，第 2 行变红：`🚨 站起来·喝水·伸懒腰`，同时 Claude 答完话会弹横幅。

## 系统要求

| | 要求 | 说明 |
|---|---|---|
| Claude Code | 任意近期版本 | 需要 plugin / marketplace 支持 |
| health-reminder、statusline | python3 ≥ 3.8 | macOS / Linux 系统自带即可，无 pip 依赖 |
| claude-pet | node ≥ 18 | 仅这一个插件需要；不装宠物则完全不需要 node |
| 平台 | macOS / Linux 为主 | Windows 未验证；状态栏 ⚡ 负载段仅 Linux 显示 |

## 快速开始

### 1. 添加本仓库为插件市场

```text
/plugin marketplace add powcai001/personal-plugins
```

（也可以用本地路径：`/plugin marketplace add /path/to/personal-plugins`）

### 2. 安装插件

```text
/plugin install statusline@personal-plugins
/plugin install health-reminder@personal-plugins
/plugin install claude-pet@personal-plugins    # 可选，游戏向
```

### 3. 一次性初始化

```text
/statusline setup        # 把渲染器写入 settings.json（自动备份原状态栏）
/health start 45m        # 开启健康提醒（间隔随意，如 30m / 1h）
```

> 装了 claude-pet 的话**不需要**再跑它自带的 setup——statusline 渲染器会直接读宠物存档渲染第 3 行。宠物 setup 只在你想要"纯宠物单行"状态栏时才用（它会询问是否覆盖现有状态栏）。

### 4. 重启 Claude Code

状态栏出现在终端底部，完成。🎉

## 插件详解

### [statusline](plugins/statusline/) —— 状态栏渲染器

纯 python3 单行渲染器，无 npx/node 进程，实测 ~36ms/次。各段独立降级：任一段数据缺失只隐藏该段，绝不报错、绝不丢整行；空行自动收起。

| 段 | 数据源 | 隐藏条件 |
|---|---|---|
| ✱ 模型 | stdin `model.display_name` | 缺失 |
| 目录名 | `workspace.current_dir` 叶子目录 | 缺失 |
| ▓░ 上下文占比 | transcript 最后一条 usage / 模型窗口 | transcript 不可读 |
| ⎇ git 分支 | `git branch --show-current` + dirty/↑↓ | 非 git 目录 |
| 💧 倒计时（行 2） | health-reminder 状态 | 未开启提醒 |
| ⏱ 🕐 ⚡ 节律（行 2） | 工作时长 / 时钟 / `/proc/loadavg` | 各段独立（⚡ 仅 Linux） |
| 🦎 宠物（行 3） | claude-pet 存档（直读 JSON，不走 node） | 未装宠物 |
| 📜 小知识（行 3） | 内置 `tech_facts.json` 150 条 | 库损坏 |

上下文窗口自动识别：模型 id 含 `1m` / `[1m]` / `2000k` / `longcontext` 映射 1M，否则 200k。模型 id 不含特征串时（如部分 1M 代理模型），用环境变量强制指定：

```json
{ "env": { "HEALTH_CTX_WINDOW": "1000000" } }
```

| 命令 | 作用 |
|---|---|
| `/statusline setup` | 安装渲染器到 `~/.claude/settings.json`（原子写入，自动备份原状态栏） |
| `/statusline setup --remove` | 恢复安装前的原状态栏 |

### [health-reminder](plugins/health-reminder/) —— 健康提醒

定时提醒**站起来、喝水、伸懒腰**。"墙上时钟"设计：状态文件只记 `started_at / interval_s / last_ack / paused`，是否到期由当前时间计算——无后台进程、无轮询、无模型调用。

- **状态栏倒计时**：`💧 32m`，到点变红 `🚨 站起来·喝水·伸懒腰`，暂停显示 `⏸`
- **Stop 横幅**：到期后 Claude 每次答完话弹 `⏰ 站起来喝水伸懒腰！`，**保持提醒直到你手动 `/health done`**，长时间未回应会提示错过了几次

| 命令 | 作用 |
|---|---|
| `/health start 45m` | 开始（间隔支持 `30m` / `1h` / `10s`；缺省沿用上次或 45m） |
| `/health pause` / `resume` | 暂停 / 恢复（暂停不吃掉剩余时间） |
| `/health status` | 查看当前状态 |
| `/health ack` | 手动确认，重新计时（人还在，只是不休息） |
| `/health done` | 确认已休息：连续工作时长清零并重新计时 |
| `/health stop` | 停止并清除 |

状态文件在 `~/.local/state/health-reminder/state.json`（明文，可用 `HEALTH_STATE_DIR` 覆盖）。

### [claude-pet](plugins/claude-pet/) —— 电子宠物 🥚→🐉

放置挂机玩法：**Claude 干活 = 你的宠物成长**。等长任务跑完时瞄一眼状态栏，看它吃饭升级。

| 事件 | 效果 |
|---|---|
| 你发一条 prompt | +5 XP |
| Claude 每次工具调用 | +2 XP |
| 一轮完成 | +10 XP，25% 掉零食；每轮第 15 次工具必掉 |
| 喂零食 | +当前升级需求 40% 的 XP |
| 摸头 | 每 10 次叼出 1 零食 |

进化链：🥚Lv1 → 🐣Lv3 → 🦎Lv8 → 🦖Lv16 → 🦕Lv26 → 🐲Lv38 → 🐉Lv45。满级可**转生**：回到蛋，经验永久 +15%/世，图鉴保留。**零惩罚**——不喂不会死，离线不衰减。

- 交互面板：对 Claude 说「看看宠物」「喂点零食」「摸摸头」「转生」即可（插件 CLI 支持 `status / feed / pet / rebirth`）
- 无 emoji 终端：`export PET_ASCII=1`
- 存档在 `~/.claude/claude-pet/`（明文 JSON，可备份可手改）

## 常见问题

**Q：装完插件状态栏没显示？**
状态栏由 `~/.claude/settings.json` 的 `statusLine` 字段驱动，插件安装不会自动改你的全局设置。跑一次 `/statusline setup` 再重启 Claude Code。用 `/statusline setup --remove` 可随时恢复原状（你最早的状态栏配置一直保留在备份里）。

**Q：状态栏只有一行，第二行（💧⏱🕐）没出现？**
健康段只在**提醒会话进行中**才渲染。先 `/health start 45m`，第二行立即出现。第三行同理：装了 claude-pet 并产生存档后出现。

**Q：上下文占比显示不对 / 一直是 200k？**
模型 id 不含 `1m` 等特征串时识别不到 1M 窗口，在 settings 的 `env` 里设 `HEALTH_CTX_WINDOW=1000000` 强制覆盖。

**Q：会不会很卡 / 很费 token？**
不会。状态栏是纯 python3 脚本（~36ms/次），健康提醒和宠物全部通过本地 hooks 读写状态文件，**零模型调用、零网络请求**。所有数据都留在本机。

**Q：⚡ 负载段在哪？**
读的是 `/proc/loadavg`，仅 Linux 显示；macOS 自动隐藏该段。

**Q：和 npx 类状态栏（如 ccusage 等）比有什么优势？**
无 node 启动开销（npx 冷启动数百 ms，本渲染器 ~36ms），无第三方依赖、无网络，各段独立降级——git 失败、transcript 不可读都只影响自己那一段。

## 仓库结构

```
├── .claude-plugin/marketplace.json   # marketplace 清单（三插件注册）
├── plugins/
│   ├── health-reminder/              # 健康提醒（CLI + Stop hook + 倒计时）
│   ├── statusline/                   # 状态栏渲染器（三行分层，逐段降级）
│   └── claude-pet/                   # 电子宠物（XP/进化/转生）
└── docs/superpowers/                 # 设计文档(specs) + 实现计划(plans)
```

各插件目录内还有独立的 README，含更详细的设计说明。

## 开发

```bash
# health-reminder / statusline 测试（纯 python，无框架依赖）
python3 plugins/health-reminder/tests/test_health_lib.py
python3 plugins/statusline/tests/test_statusline.py
python3 plugins/statusline/tests/test_setup_cli.py

# claude-pet 测试（node 内置 test runner，注意要用 glob 形式）
cd plugins/claude-pet && node --test "test/*.test.js"
```

新增插件：在 `plugins/` 下建目录（含 `.claude-plugin/plugin.json`），并在根目录 `.claude-plugin/marketplace.json` 注册即可。

## 卸载

```text
/statusline setup --remove        # 先恢复原状态栏（装过的话）
/plugin uninstall claude-pet@personal-plugins
/plugin uninstall statusline@personal-plugins
/plugin uninstall health-reminder@personal-plugins
/plugin marketplace remove personal-plugins
```

宠物想彻底清除再删掉存档目录：`rm -rf ~/.claude/claude-pet/`。
