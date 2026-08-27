# health-reminder

定时提醒**站起来、喝水、伸懒腰**，并自带一个轻量状态栏渲染器。提醒只在 Claude Code 会话内可见：

- 状态栏渲染器单行：` ✱ 模型 │ ▓░ 占比 │ ⎇ 分支 │ 💧 32m`（无花费段；到点变红 `🚨 站起来·喝水·伸懒腰`，暂停显示 `⏸`）
- 对话横幅：到期后 Claude 答完话时弹 `⏰ 站起来喝水伸懒腰！`（自动确认，长时间未回应会提示错过了几次）

## 安装

```
/plugin marketplace add /home/plugin
/plugin install health-reminder@personal-plugins
```

## 用法

| 命令 | 作用 |
|---|---|
| `/health start 45m` | 开始（间隔支持 30m / 1h / 10s；缺省沿用上次或 45m） |
| `/health pause` / `resume` | 暂停 / 恢复（暂停不吃掉剩余时间） |
| `/health stop` | 停止并清除 |
| `/health status` | 查看状态 |
| `/health ack` | 手动确认，重新计时 |
| `/health done` | 确认已休息：连续工作时长清零并重新计时 |
| `/health setup` | 安装状态栏渲染器（备份原状态栏；已装旧包装器会自动升级） |
| `/health setup --remove` | 恢复原状态栏 |

## 工作原理

"墙上时钟"：`~/.local/state/health-reminder/state.json` 只记 `started_at / interval_s / last_ack / paused`，是否到期由当前时间计算得出。无后台进程、无模型调用——`/health` 直接执行本地 python3 脚本，Stop hook 只读写状态文件。

状态栏渲染器为独立 python3 脚本，上下文占比取自会话 transcript 的最后一条 usage 记录，模型窗口按 id 含 "1m" 映射 1M、否则 200k。

## 性能

状态栏渲染器实测开销：约 36 ms/次（无 npx/node 进程）。

## 边界与 v2

提醒仅在 Claude Code 会话内可见（不改本地终端配置的前提下实测的最优解）。切到其他窗口且长时间不回来时够不着你。v2 候选：本地终端标签闪烁指引、企业 IM 推送、分动作间隔、历史统计。

状态目录可用 `HEALTH_STATE_DIR` 环境变量覆盖。
