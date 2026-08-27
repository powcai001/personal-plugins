# statusline

纯 python3 单行状态栏渲染器（36ms 刷新，无 npx/node 依赖），替换 npx 类重量级状态栏：

```
 ✱ opus-5 │ statusline │ ▓▓▓▓▓▓░░░░ 62% │ ⎇ feat/main✱
 💧 32m │ ⏱ 45m │ 🕐 14:32 │ ⚡0.8
 🦎 小蜥蜴 │ Lv.13 ▰▰▰▰▰▰▰▰▱▱ 75% │ 🍪3 │ 📜 1969·ARPANET 四节点首次联机
```

三行分层：**工作**（模型/占比/git）· **节律**（💧 倒计时 + ⏱ 连续工作 + 🕐 时钟 + ⚡ 负载，深夜/超时变色）· **陪伴**（宠物 + 📜 科技史小知识）。
宠物行按本渲染器风格重绘——紫粉主题、`│` 同构分隔；未装宠物/档案损坏时整行隐藏；
本轮 xp ≥30 才显示 `+Nxp`（降噪）。行尾 📜 从内置 150 条科技史库按小时轮换一条。
各行独立降级，空行自动收起。

| 段 | 数据源 | 隐藏条件 |
|---|---|---|
| ✱ 模型 | stdin `model.display_name` | 缺失 |
| 目录名 | stdin `workspace.current_dir` 的叶子目录 | 缺失/非目录 |
| ▓░ 上下文占比 | transcript 最后一条 usage / 模型窗口 | transcript 不可读 |
| ⎇ git 分支 | `git branch --show-current` + dirty 标记 | 非 git 目录/失败 |
| 💧 健康倒计时（第 2 行） | health-reminder 插件状态（跨插件联动，可独立运行） | 未启用提醒 |
| ⏱🕐⚡ 节律（第 2 行） | health-reminder 工作时长 + 系统时钟/负载 | 各段独立隐藏（🕐⚡ 恒显） |
| 🦎 宠物（第 3 行） | claude-pet 存档（直接读 state.json，不走 node） | 未装宠物/档案异常 |
| 📜 科技史小知识（第 3 行） | 内置 `data/tech_facts.json`（150 条，按小时轮换） | 库缺失/损坏 |

上下文窗口：模型 id 含 `1m`/`[1m]`/`2000k`/`longcontext` 自动映射 1M，否则 200k；
环境变量 `HEALTH_CTX_WINDOW` 可强制覆盖（如 glm 类 1M 模型 id 不含特征串）。

## 安装

```
/plugin marketplace add <本仓库路径>
/plugin install statusline@personal-plugins
```

## 用法

| 命令 | 作用 |
|---|---|
| `/statusline setup` | 安装为 statusLine（自动备份原状态栏；已装旧包装器自动升级） |
| `/statusline setup --remove` | 恢复原状态栏 |

## 设计要点

- 四段独立降级：任一段数据缺失/异常只隐藏该段，绝不报错、绝不丢整行
- 原子状态：setup 对 settings.json 的写入走临时文件 + rename
- 备份不覆盖：最早备份的原状态栏永远保留，`--remove` 恢复的就是它
