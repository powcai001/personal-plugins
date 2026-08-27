# 第二行节律 + /health done + 提醒文案池 + 宠物小知识 设计

- 日期：2026-08-27
- 状态：对话内已确认方向，待实现
- 依赖：statusline 三行分层（f6a3ae2）、health-reminder v0.2.0

## 1. 休息判定：手动确认

- 提醒节奏钟（💧）不变：Stop hook 到点横幅后自动 ack 重新计时
- 连续工作钟（⏱）：`state.json` 新增 `last_break`（epoch 秒；start 时 = started_at），
  **只有 `/health done` 清零**（last_break=now，同时 last_ack=now）
- 横幅/状态栏文案不再保证"你已休息"——⏱ 是诚实的连续工作时长

## 2. CLI 变更（health-reminder）

- 新子命令 `health done`：`last_break = last_ack = now`，输出 `👌 已记录休息，计时重新开始`
- 兼容：旧 state.json 无 last_break → 读作 started_at
- status 输出增加连续工作时长

## 3. 提醒文案池

`health_lib.BANNERS = [...]` 十二条中文休息提示（不重复主题：转转/喝水/远眺/颈椎/腰/眼睛/伸懒腰…）。
- `banner_text(c)`：`BANNERS[c["missed"] % len(BANNERS)]`（按错过周期数轮换，确定性可测试），
  missed>1 时仍追加 `（期间错过了 N 次提醒）`
- 到期横幅尾缀 `（休息完 /health done）`
- 状态栏 🚨 段：取 `BANNERS[missed % 12]` 去掉首符号的正文，红底整段
- /health description 文案不变

## 4. 第二行段（statusline 渲染器）

顺序：`💧 │ ⏱ │ 🕐 │ ⚡`，段间 SEP，各自独立降级：

| 段 | 实现 | 规则 |
|---|---|---|
| 💧 | 已有 | 不变 |
| ⏱ 连续 | health_lib：now-last_break；格式 `⏱ 2.1h`/`⏱ 45m` | <1h 灰、≥1h 黄、≥2h 红 |
| 🕐 | `time.strftime("%H:%M")` | 23:00-06:00 暗红，其余灰 |
| ⚡ | 读 `/proc/loadavg` 首值 ÷ os.cpu_count() | <70% 灰、≥70% 黄、≥100% 红；非 Linux 隐藏 |

## 5. 宠物科技史小知识（第三行尾部）

- `plugins/statusline/data/tech_facts.json`：`{"facts": [{"y": 1969, "t": "ARPANET 首秀"}, ...]}`，
  首批 ~150 条（我写），按 `hour_of_day % len` 轮换，展示 `📜 1969·ARPANET 首秀`
- 宠物行已隐藏时知识点也不显示（绑定宠物行）
- 生成：`/claude-pet:pet` SKILL 追加"学新知识"动作——调模型生成 5 条去重追加进 facts.json，
  宠物 +30xp（走 feed 同路径）

## 6. 错误处理

- last_break 缺失/非法 → 回退 started_at；两者都坏 → 隐藏 ⏱ 段
- loadavg 读取失败/非 Linux → 隐藏 ⚡
- facts.json 缺失/空 → 不显示 📜
- 全部沿用"段级 try/except + 整行收起"

## 7. 测试

- health_lib：done 子命令（last_break/last_ack 同置）、旧档案兼容、banner 轮换确定性（missed 0..13 覆盖全池）、连续时长格式
- statusline：⏱ 三色阈值、🕐 深夜色、⚡ 阈值与非 Linux 隐藏、📜 轮换与缺失隐藏、e2e 第二行四段
- claude-pet："学新知识"追加去重（node 测试）
