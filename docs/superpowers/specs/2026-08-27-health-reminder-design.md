# health-reminder 插件设计

- 日期：2026-08-27
- 状态：设计已评审通过（对话内确认），待实现
- 项目位置：`/home/plugin`（个人 Claude Code 插件仓库，本插件是第一个成员）

## 目标

定时（默认 45 分钟，可配置）提醒用户**站起来、喝水、伸懒腰**。提醒只出现在 Claude Code 会话内：状态栏 + 对话横幅。

## 决策记录

| 决策 | 结论 | 依据 |
|---|---|---|
| 提醒生命周期 | 状态跨会话持久；展示仅限 Claude Code 会话内 | 用户只需会话内提醒 |
| 本地终端配置 | 不依赖、不要求修改 | 实测 BEL / OSC-9 / OSC-777 到 Windows SSH 客户端全部无感知 |
| tmux 通道 | 不用 | 服务器未安装 tmux |
| IM 推送 | v1 不做 | 用户明确不要；通道设计预留扩展 |
| 计时模型 | **无后台进程**，"墙上时钟"纯计算 | 状态文件记起点+间隔+last_ack，到期与否由当前时间算出；无进程清理、重启免疫、多会话单一状态源 |
| 模型调用 | 零 | `/health` 命令经 `!` bash 模式直达 CLI；hook 只读写状态文件 |
| 实现语言 | python3 单文件，零第三方依赖 | 开发服务器必有 python3；flock/时间计算 stdlib 全覆盖 |
| 文案语言 | 中文 | 用户为中文用户 |

## 目录结构

```
/home/plugin/                              ← 个人插件仓库（marketplace）
├── .claude-plugin/marketplace.json
├── docs/superpowers/specs/                 ← 本文档
└── plugins/health-reminder/
    ├── .claude-plugin/plugin.json
    ├── commands/health.md                  # → !python3 …/scripts/health $ARGUMENTS
    ├── hooks/hooks.json                    # Stop 事件
    ├── scripts/health                      # CLI 主脚本
    ├── scripts/health_hook                 # Stop hook 入口（检查到期→横幅+ack）
    ├── scripts/health_statusline           # statusline 包装器
    └── README.md
```

## 状态文件

`~/.local/state/health-reminder/state.json`：

```json
{
  "started_at": 1789000000,      // unix epoch 秒
  "interval_s": 2700,            // 提醒间隔
  "last_ack": 1789002700,        // 上次确认时间；到期判断基准
  "paused": false,
  "paused_at": null
}
```

- 原子写：临时文件 + `os.replace`；并发用 `fcntl.flock`
- 损坏/缺失：视为未启用（各通道静默降级，status 提示重新 start）

### 到期计算

```
due     = not paused and now >= last_ack + interval_s
missed  = max(0, floor((now - last_ack) / interval_s))    // due 时 missed >= 1
剩余    = last_ack + interval_s - now                      // 正常时段的倒计时
```

- **pause**：记 `paused_at`；**resume**：`last_ack += now - paused_at`（暂停不吃掉剩余时间）
- **ack**（确认已提醒）：`last_ack = now`

## CLI（`scripts/health`）

| 命令 | 行为 |
|---|---|
| `health start [45m]` | 写入/覆盖状态；间隔接受 `Ns/Nm/Nh`（秒级供测试）；缺省用上次配置，无历史则 45m |
| `health pause` / `resume` | 见上 |
| `health stop` | 删除状态文件 |
| `health status` | 打印当前状态（运行/暂停/未启用、倒计时、错过计数） |
| `health ack` | 手动确认（hook 自动 ack 之外的手动兜底） |
| `health setup` | 把 settings.json 的 statusLine 替换为本包装器（先备份原值，可回滚） |

所有子命令输出一行中文结果。参数解析错误给帮助文本，退出码非 0。

## 命令文件

`commands/health.md` body 为 bash 直通：

```
!python3 "${CLAUDE_PLUGIN_ROOT}/scripts/health" $ARGUMENTS
```

（引号与 `$ARGUMENTS` 拆分细节在实现计划中确定；无参数时落到 `status`。）

## 通道 1：状态栏包装器

`scripts/health_statusline`：

1. 从 stdin 读 Claude Code 传入的 JSON
2. 执行原 statusline 命令（从 settings.json 读取，stdin JSON 喂给它），捕获输出
3. 追加健康段：
   - 未启用 → 无输出
   - 正常 → `💧 32m`（powerline 兼容配色）
   - 到期 → 红底 `🚨 站起来·喝水·伸懒腰`
   - 暂停 → `⏸ 45m`
4. 任何异常 → 只输出原命令结果（绝不弄丢用户已有状态栏）；无原 statusline → 独立渲染
5. 性能预算：整链 < 100ms（statusline 约每秒调用一次，python 启动 + 透传实现时实测）

## 通道 2：Stop hook 横幅

`hooks/hooks.json` 挂 Stop 事件 → `scripts/health_hook`：

- 读状态；若 `due`：stdout 输出 `{"systemMessage": "⏰ 站起来喝水伸懒腰！（错过了 N 个周期）"}` 并 ack
- 非 due 或未启用：无输出，exit 0
- hook 任何内部异常都 exit 0 静默，绝不阻塞会话

设计上只挂 Stop（Claude 答完话必达）；UserPromptSubmit 变体留作实现期可选增强，不进 v1 承诺。

## 错误处理汇总

- 状态文件损坏/缺失 → 一律视为未启用
- 并发写 → flock + 原子 rename
- 包装器异常 → 透传原状态栏
- hook 异常 → exit 0 静默

## 测试

1. **单元**（简单断言脚本，不引框架）：间隔解析、到期计算、missed 计算、pause/resume 时间平移
2. **集成（`start 10s` 手动）**：状态栏变红 → 横幅出现 → ack 后恢复倒计时
3. **statusline**：有/无原 statusline 两场景 + 包装器异常降级
4. **hook**：构造 due 状态验证 systemMessage 与 ack 幂等（连续两次 Stop 只横幅一次）

## v2 候选（本期不做）

本地客户端标签闪烁配置指引、企业 IM 推送、分动作间隔（喝水 30m / 站立 45m）、历史统计。

## 参考

- Claudoro（github.com/emson/claudoro）：CLI 单一状态源、statusline 包装、`!` 命令直通、原子状态写
- awesome-claude-code-plugins 入门教程：插件目录与 marketplace 结构
