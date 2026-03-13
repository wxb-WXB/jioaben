"""
远程重启 MinerU Docker 服务脚本
- 支持三台解析服务器并发重启
- 每2个小时自动执行一次
- 实时监控三台服务器内存（每秒刷新）
"""
import paramiko
import sys
import time
import threading
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


# ─────────────────────────────────────────────
# 服务器配置
# ─────────────────────────────────────────────
SERVERS = [
    {
        "name": "环北-解析服务器-212",
        "host": "10.11.76.212",
        "port": 22,
        "username": "root",
        "password": "1s3LwmnznxQ=",
    },
    {
        "name": "切片服务器-214",
        "host": "10.11.76.214",
        "port": 22,
        "username": "root",
        "password": "QttnkiO!Z=BFoeSa",
    },
    {
        "name": "解析服务器-210",
        "host": "10.11.76.210",
        "port": 22,
        "username": "root",
        "password": "anc48yji3",
    },
]

# Docker 重启命令（组合为单条，确保顺序执行）
RESTART_CMD = "cd /data/mineru-api && docker-compose down && docker-compose up -d"

# 重启间隔（秒）
RESTART_INTERVAL = 60 * 60

# 内存监控刷新间隔（秒）
MEM_REFRESH_INTERVAL = 1

# 内存查询命令：返回 "已用MB/总MB/使用率%"
MEM_CMD = "free -m | awk 'NR==2{printf \"%d/%d/%.1f\", $3, $2, $3*100/$2}'"


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────
def ts():
    """当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_client(server: dict) -> paramiko.SSHClient | None:
    """创建并返回已连接的 SSH 客户端，失败返回 None"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=server["host"],
            port=server["port"],
            username=server["username"],
            password=server["password"],
            timeout=10,
        )
        return client
    except Exception as e:
        print(f"[{ts()}] [{server['name']}] 连接失败: {e}")
        return None


def run_cmd(client: paramiko.SSHClient, cmd: str, timeout: int = 120):
    """
    在已连接的 SSH 客户端上执行命令。
    返回 (exit_code, stdout, stderr)。
    """
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    return exit_code, stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")


# ─────────────────────────────────────────────
# 单台服务器重启逻辑
# ─────────────────────────────────────────────
def restart_server(server: dict) -> bool:
    """对单台服务器执行 Docker 重启，返回是否成功"""
    name = server["name"]
    print(f"\n[{ts()}] [{name}] 开始重启 Docker 服务...")

    client = make_client(server)
    if client is None:
        print(f"[{ts()}] [{name}] 跳过（无法连接）")
        return False

    try:
        exit_code, stdout, stderr = run_cmd(client, RESTART_CMD, timeout=180)
        if stdout.strip():
            for line in stdout.strip().splitlines():
                print(f"[{ts()}] [{name}] {line}")
        if stderr.strip():
            for line in stderr.strip().splitlines():
                print(f"[{ts()}] [{name}] [stderr] {line}")

        if exit_code == 0:
            print(f"[{ts()}] [{name}] 重启成功 (exit={exit_code})")
            return True
        else:
            print(f"[{ts()}] [{name}] 重启失败 (exit={exit_code})")
            return False
    except Exception as e:
        print(f"[{ts()}] [{name}] 执行异常: {e}")
        return False
    finally:
        client.close()


# ─────────────────────────────────────────────
# 并发重启三台服务器
# ─────────────────────────────────────────────
def restart_all():
    """并发重启所有服务器，打印汇总结果"""
    print("\n" + "=" * 70)
    print(f"[{ts()}] 开始并发重启 {len(SERVERS)} 台服务器...")
    print("=" * 70)

    results = {}
    with ThreadPoolExecutor(max_workers=len(SERVERS)) as pool:
        future_map = {pool.submit(restart_server, s): s["name"] for s in SERVERS}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                results[name] = future.result()
            except Exception as e:
                print(f"[{ts()}] [{name}] 线程异常: {e}")
                results[name] = False

    print("\n" + "=" * 70)
    print(f"[{ts()}] 重启汇总:")
    for name, ok in results.items():
        status = "成功" if ok else "失败"
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}: {status}")
    all_ok = all(results.values())
    print(f"\n  整体结果: {'全部成功' if all_ok else '部分或全部失败'}")
    print("=" * 70)
    return all_ok


# ─────────────────────────────────────────────
# 内存监控（后台线程，每秒刷新）
# ─────────────────────────────────────────────
class MemoryMonitor:
    """持久 SSH 连接，后台每秒采集内存并打印到终端"""

    def __init__(self):
        self._clients: dict[str, paramiko.SSHClient | None] = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mem-monitor")
        self._lock = threading.Lock()

    def _connect_all(self):
        for s in SERVERS:
            name = s["name"]
            client = make_client(s)
            self._clients[name] = client
            if client:
                print(f"[{ts()}] [内存监控] {name} 连接成功")
            else:
                print(f"[{ts()}] [内存监控] {name} 连接失败，将持续重试")

    def _get_mem(self, name: str, server: dict) -> str:
        """获取单台服务器内存信息，连接断开时自动重连"""
        client = self._clients.get(name)
        # 检查连接是否存活
        if client is None or not client.get_transport() or not client.get_transport().is_active():
            client = make_client(server)
            self._clients[name] = client

        if client is None:
            return "连接失败"

        try:
            exit_code, stdout, _ = run_cmd(client, MEM_CMD, timeout=5)
            if exit_code == 0 and stdout.strip():
                used, total, pct = stdout.strip().split("/")
                return f"{used}MB/{total}MB ({pct}%)"
            return "查询失败"
        except Exception:
            # 标记连接失效，下次重连
            self._clients[name] = None
            return "超时/断开"

    def _loop(self):
        self._connect_all()
        # 记录上一次打印的行数，用于回退光标
        last_lines = 0
        while not self._stop_event.is_set():
            rows = []
            for s in SERVERS:
                mem_str = self._get_mem(s["name"], s)
                rows.append(f"  {s['name']:<22} | {mem_str}")

            now = datetime.now().strftime("%H:%M:%S")
            header = f"[内存监控] {now}"
            separator = "  " + "-" * 50

            # 回退到上次输出的起始行
            if last_lines > 0:
                sys.stdout.write(f"\033[{last_lines}A\033[J")

            output_lines = [header, separator] + rows + [separator]
            print("\n".join(output_lines), flush=True)
            last_lines = len(output_lines)

            self._stop_event.wait(MEM_REFRESH_INTERVAL)

        print()  # 退出时换行

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        # 关闭所有持久连接
        for client in self._clients.values():
            if client:
                try:
                    client.close()
                except Exception:
                    pass


# ─────────────────────────────────────────────
# 主循环：每30分钟重启一次
# ─────────────────────────────────────────────
def main():
    print("=" * 70)
    print("MinerU Docker 定时重启脚本")
    print(f"  服务器数量 : {len(SERVERS)} 台")
    print(f"  重启间隔   : 每 {RESTART_INTERVAL // 60} 分钟")
    print(f"  内存监控   : 每 {MEM_REFRESH_INTERVAL} 秒刷新")
    print("  按 Ctrl+C 退出")
    print("=" * 70)

    # 启动内存监控后台线程
    monitor = MemoryMonitor()
    monitor.start()

    try:
        round_num = 0
        while True:
            round_num += 1
            next_time = datetime.now() + timedelta(seconds=RESTART_INTERVAL)

            # 执行重启（内存监控行会被重启日志打断，属正常现象）
            print()  # 换行，避免覆盖内存行
            restart_all()

            print(f"\n[{ts()}] 第 {round_num} 轮完成，下次重启时间: {next_time.strftime('%H:%M:%S')}")
            print(f"[{ts()}] 等待 {RESTART_INTERVAL // 60} 分钟...")

            # 等待期间内存监控持续运行
            time.sleep(RESTART_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n\n[{ts()}] 用户中断，正在退出...")
    finally:
        monitor.stop()
        print(f"[{ts()}] 脚本已退出")


if __name__ == "__main__":
    main()
