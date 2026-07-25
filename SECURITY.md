# Security Policy

## 支持范围

当前维护分支为默认分支。安全修复不承诺回移到旧版本。

## 报告漏洞

请使用 GitHub Security Advisory 的私密报告功能，不要先创建公开 Issue。报告应包含影响、复现步骤、受影响文件与建议修复方向。

## 部署边界

Strategy Lab 默认只绑定 `127.0.0.1`。非本机绑定必须显式传入 `--allow-remote`，并通过 `STRATEGY_LAB_API_TOKEN` 配置至少 32 字符的访问令牌；这仍不提供租户隔离或公网级防护，不要把服务直接暴露到互联网。

远程浏览器可首次访问 `http://host:8000/backtests#access_token=<token>`。前端会立即清除 fragment，并只在当前浏览器会话与 SameSite cookie 中保留令牌。生产环境仍应使用 HTTPS、主机防火墙或带认证的反向代理。

策略是本地 Python 代码，运行回测等同于允许该脚本在本机回测子进程中执行；只运行你信任的策略文件。`trusted-local-v1` 会清除宿主敏感环境变量、替换 `PYTHONPATH`、启用 Python safe-path，并在超时时终止进程组，但不会限制策略访问本机文件或网络。当前 restricted sandbox 尚未实现，多用户部署不在支持范围内。
