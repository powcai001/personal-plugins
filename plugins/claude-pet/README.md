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

## 开发与测试

运行全部测试：`node --test "test/*.test.js"`（注意：本机 Node v22 下 `node --test test/` 目录形式不可用，需用 glob 形式）。

## 数据与卸载

状态在 `~/.claude/claude-pet/`（明文 JSON，可备份可手改）。卸载：移除插件 + 删除该目录 + 删 `~/.claude/settings.json` 的 `statusLine`。
