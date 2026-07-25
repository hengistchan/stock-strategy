# Security Policy

## 支持范围

当前维护分支为默认分支。安全修复不承诺回移到旧版本。

## 报告漏洞

请使用 GitHub Security Advisory 的私密报告功能，不要先创建公开 Issue。报告应包含影响、复现步骤、受影响文件与建议修复方向。

## 部署边界

Strategy Lab 默认只绑定 `127.0.0.1`。非本机绑定必须显式传入 `--allow-remote`，并通过 `STRATEGY_LAB_API_TOKEN` 配置至少 32 字符的访问令牌；这仍不提供租户隔离或公网级防护，不要把服务直接暴露到互联网。

远程浏览器可首次访问 `http://host:8000/backtests#access_token=<token>`。前端会立即清除 fragment，并只在当前浏览器会话与 SameSite cookie 中保留令牌。生产环境仍应使用 HTTPS、主机防火墙或带认证的反向代理。

策略是本地 Python 代码，正式回测等同于允许该脚本在本机子进程中执行；只运行你信任的策略文件。`trusted-local-v2` 会清除宿主敏感环境变量、替换 `PYTHONPATH`、启用 Python safe-path，限制 CPU、文件、进程数、打开文件数与输出量，并在超时或越界时终止整个进程组；Linux 还限制地址空间。它不会禁止策略读取本机文件或访问网络。

Futu 策略迁移的确定性 fixture 使用 `restricted-import-v1`，禁用网络、子进程和 native library 加载，并限制写入目录。这个受限运行时是迁移筛查层，不是可抵御恶意 Python 的完整容器沙箱；未知来源代码仍应先在一次性虚拟机或容器中审查。多用户部署不在支持范围内。
