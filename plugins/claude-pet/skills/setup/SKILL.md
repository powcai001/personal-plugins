---
description: 一键配置 claude-pet 状态栏（修改 ~/.claude/settings.json 的 statusLine）。用户说"配置状态栏""setup""状态栏不显示"时使用。
---

# claude-pet 状态栏配置

按顺序执行：

1. 找到插件根目录：`PET_ROOT=$(dirname "$(dirname "$(readlink -f "$(command -v claude-pet)")")")`，确认 `$PET_ROOT/bin/claude-pet` 存在；若 `command -v claude-pet` 失败，请用户重启会话后重试。
2. 生成启动器：先把 `$HOME` 解析为绝对路径（Write 工具需要绝对路径，不接受 `~`），再用 Write 工具写 `<绝对HOME>/.claude/claude-pet/statusline-launcher.sh`（内容如下，其中 PET_ROOT 换成第 1 步的绝对路径）：

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
     const fs=require("fs"),os=require("os"),path=require("path");
     const p=path.join(os.homedir(),".claude","settings.json");
     let s={},raw;
     try{raw=fs.readFileSync(p,"utf8")}catch(e){
       if(e.code!=="ENOENT"){console.error("读取 settings.json 失败："+e.message+"；本次未做任何写入");process.exit(1)}
     }
     if(raw!==undefined){
       try{s=JSON.parse(raw)}catch(e){console.error("settings.json 已损坏（不是合法 JSON），请先手工修复后再运行本配置；本次未做任何写入。");process.exit(1)}
     }
     s.statusLine={type:"command",command:path.join(os.homedir(),".claude","claude-pet","statusline-launcher.sh")};
     const tmp=p+".tmp-"+process.pid;
     fs.writeFileSync(tmp,JSON.stringify(s,null,2)+"\n");
     fs.renameSync(tmp,p);
     console.log("statusLine 已写入（原子写入，其他配置键已保留）");'
     ```

     若脚本输出"已损坏"，如实转告用户并停止配置（不覆盖文件）。

5. 验证：运行 `~/.claude/claude-pet/statusline-launcher.sh`，应输出一行含 Lv. 的合法状态栏（新档案为 🥚 Lv.1，已有档案为当前形态）。
6. 告知用户：重启 Claude Code（或新开终端）后状态栏生效；插件升级后若路径变化，重跑本命令即可。
