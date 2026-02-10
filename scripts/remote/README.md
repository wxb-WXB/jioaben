# 远程服务器管理脚本

本目录包含通过SSH连接到远程服务器执行命令的脚本。

## 环境要求

安装所需依赖：

```bash
pip install paramiko
```

或者安装项目所有依赖：

```bash
pip install -r requirements.txt
```

## 脚本说明

### restart_mineru_docker.py

重启环北服务器上的 MinerU Docker 服务。

**功能：**
- 通过SSH连接到环北服务器（10.11.76.212）
- 进入 `/data/mineru-api` 目录
- 执行 `docker-compose down` 停止服务
- 执行 `docker-compose up -d` 后台启动服务

**使用方法：**

```bash
# 从项目根目录执行
python scripts/remote/restart_mineru_docker.py

# 或者直接执行脚本
cd scripts/remote
python restart_mineru_docker.py
```

**输出示例：**

```
============================================================
MinerU Docker 服务重启脚本
============================================================
服务器: 10.11.76.212
用户: root
操作: 重启 /data/mineru-api 下的 Docker 服务
============================================================
[2026-02-10 14:30:00] 正在连接到服务器 10.11.76.212:22...
[2026-02-10 14:30:01] ✓ 连接成功!

[2026-02-10 14:30:01] 执行命令: cd /data/mineru-api && docker-compose down && docker-compose up -d
------------------------------------------------------------
Stopping mineru-api ... done
Removing mineru-api ... done
Creating mineru-api ... done
------------------------------------------------------------
[2026-02-10 14:30:15] ✓ 命令执行成功 (退出码: 0)

============================================================
✅ MinerU Docker 服务重启成功!
============================================================
[2026-02-10 14:30:15] 连接已关闭
```

## 服务器配置

当前配置的服务器信息：

- **环北服务器**
  - IP: 10.11.76.212
  - 用户: root
  - 密码: 1s3LwmnznxQ=
  - 端口: 22

## 安全注意事项

⚠️ **重要提示：**

1. 密码明文存储在脚本中，请确保脚本文件权限设置正确
2. 建议在生产环境中使用SSH密钥认证替代密码认证
3. 不要将包含密码的脚本提交到公共代码仓库

## 扩展使用

### SSHExecutor 类

脚本中的 `SSHExecutor` 类可以复用于执行其他远程命令：

```python
from scripts.remote.restart_mineru_docker import SSHExecutor

# 创建连接
executor = SSHExecutor(
    host='10.11.76.212',
    port=22,
    username='root',
    password='1s3LwmnznxQ='
)

# 连接服务器
if executor.connect():
    # 执行单条命令
    exit_code, stdout, stderr = executor.execute_command('ls -la /data')
    
    # 或执行多条命令
    commands = [
        'cd /data',
        'ls -la',
        'pwd'
    ]
    executor.execute_commands(commands)
    
    # 关闭连接
    executor.close()
```

## 常见问题

### 1. 连接超时

如果出现连接超时错误，请检查：
- 服务器IP是否正确
- 网络是否可达（尝试 ping 服务器）
- SSH端口（默认22）是否开放

### 2. 认证失败

如果出现认证失败：
- 检查用户名和密码是否正确
- 确认服务器允许密码登录（检查 `/etc/ssh/sshd_config` 中的 `PasswordAuthentication` 设置）

### 3. 命令执行失败

如果命令执行失败：
- 检查目标目录是否存在
- 确认当前用户是否有执行权限
- 查看错误输出获取详细信息
