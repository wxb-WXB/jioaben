"""
MinerU 服务诊断监控脚本
每秒刷新，实时显示三台服务器的：
  - 内存使用
  - CPU 使用率
  - Docker 容器状态 & 资源占用
  - MinerU 进程详情（CPU/内存/线程数）
  - GPU 使用率（如有 nvidia-smi）
  - 磁盘 IO 等待（iowait）
  - 任务队列积压（容器日志最新几行）
按 Ctrl+C 退出；按 'd' 进入诊断模式（一次性深度报告）
"""
import paramiko
import sys
import time
import threading
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor


# ─────────────────────────────────────────────
# 服务器配置
# ─────────────────────────────────────────────
SERVERS = [
    {
        "name": "解析-212",
        "host": "10.11.76.212",
        "port": 22,
        "username": "root",
        "password": "1s3LwmnznxQ=",
    },
    {
        "name": "切片-214",
        "host": "10.11.76.214",
        "port": 22,
        "username": "root",
        "password": "QttnkiO!Z=BFoeSa",
    },
    {
        "name": "解析-210",
        "host": "10.11.76.210",
        "port": 22,
        "username": "root",
        "password": "anc48yji3",
    },
]

REFRESH_INTERVAL = 3   # 秒，每次全量刷新间隔
DOCKER_DIR = "/data/mineru-api"

# ─────────────────────────────────────────────
# 采集命令（全部拼成一条，减少 SSH 往返）
# ─────────────────────────────────────────────
# 输出格式：各段用 @@SEP@@ 分隔，方便解析
COLLECT_CMD = r"""
echo "@@MEM@@" && free -m | awk 'NR==2{printf "%d %d %.1f", $3,$2,$3*100/$2}' && \
echo "" && echo "@@CPU@@" && cat /proc/stat | awk 'NR==1{idle=$5; total=0; for(i=2;i<=NF;i++) total+=$i; printf "%.1f", (1-idle/total)*100}' && \
echo "" && echo "@@IOWAIT@@" && (iostat -c 1 1 2>/dev/null | awk 'NR==4{printf "%.1f", $4}' || echo "N/A") && \
echo "" && echo "@@DOCKER@@" && docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}|{{.BlockIO}}" 2>/dev/null && \
echo "" && echo "@@CONTAINERS@@" && docker ps --format "{{.Names}}|{{.Status}}|{{.Ports}}" 2>/dev/null && \
echo "" && echo "@@GPU@@" && (nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null || echo "NO_GPU") && \
echo "" && echo "@@PROC@@" && ps aux --sort=-%cpu | awk 'NR==1 || /python|mineru|uvicorn|gunicorn|celery|worker/' | head -20
"""

LOGS_CMD = f"docker logs --tail=8 $(docker ps -q --filter 'name=mineru' 2>/dev/null | head -1) 2>&1 || echo 'NO_CONTAINER'"


# ─────────────────────────────────────────────
# SSH 工具
# ─────────────────────────────────────────────
def ts():
    return datetime.now().strftime("%H:%M:%S")


def make_client(server: dict):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=server["host"],
            port=server["port"],
            username=server["username"],
            password=server["password"],
            timeout=8,
        )
        return client
    except Exception:
        return None


def run_cmd(client, cmd: str, timeout: int = 10):
    try:
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")
    except Exception as e:
        return -1, "", str(e)


# ─────────────────────────────────────────────
# 数据解析
# ─────────────────────────────────────────────
def parse_metrics(raw: str) -> dict:
    """解析采集命令输出，返回结构化字典"""
    result = {
        "mem": None, "cpu": None, "iowait": None,
        "docker_stats": [], "containers": [],
        "gpu": [], "procs": [],
    }
    if not raw:
        return result

    sections = {}
    current = None
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("@@") and line.endswith("@@"):
            current = line.strip("@")
            sections[current] = []
        elif current:
            sections[current].append(line)

    # 内存
    mem_lines = [l for l in sections.get("MEM", []) if l.strip()]
    if mem_lines:
        parts = mem_lines[0].split()
        if len(parts) == 3:
            result["mem"] = {"used": int(parts[0]), "total": int(parts[1]), "pct": float(parts[2])}

    # CPU
    cpu_lines = [l for l in sections.get("CPU", []) if l.strip()]
    if cpu_lines:
        try:
            result["cpu"] = float(cpu_lines[0])
        except ValueError:
            pass

    # IO Wait
    io_lines = [l for l in sections.get("IOWAIT", []) if l.strip()]
    if io_lines:
        result["iowait"] = io_lines[0]

    # Docker stats
    for line in sections.get("DOCKER", []):
        if "|" in line:
            parts = line.split("|")
            if len(parts) >= 6:
                result["docker_stats"].append({
                    "name": parts[0], "cpu": parts[1],
                    "mem_usage": parts[2], "mem_pct": parts[3],
                    "net_io": parts[4], "block_io": parts[5],
                })

    # Container 状态
    for line in sections.get("CONTAINERS", []):
        if "|" in line:
            parts = line.split("|")
            if len(parts) >= 2:
                result["containers"].append({
                    "name": parts[0],
                    "status": parts[1],
                    "ports": parts[2] if len(parts) > 2 else "",
                })

    # GPU
    for line in sections.get("GPU", []):
        if line.strip() in ("NO_GPU", ""):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 7:
            result["gpu"].append({
                "id": parts[0], "name": parts[1],
                "gpu_util": parts[2], "mem_util": parts[3],
                "mem_used": parts[4], "mem_total": parts[5],
                "temp": parts[6],
            })

    # 进程
    for line in sections.get("PROC", []):
        if line.strip():
            result["procs"].append(line)

    return result


# ─────────────────────────────────────────────
# 格式化输出
# ─────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
BLUE   = "\033[94m"


def color_pct(val: float, warn=70, crit=90) -> str:
    if val >= crit:
        return f"{RED}{val:.1f}%{RESET}"
    if val >= warn:
        return f"{YELLOW}{val:.1f}%{RESET}"
    return f"{GREEN}{val:.1f}%{RESET}"


def color_status(status: str) -> str:
    s = status.lower()
    if "up" in s:
        return f"{GREEN}{status}{RESET}"
    if "exit" in s or "dead" in s or "error" in s:
        return f"{RED}{status}{RESET}"
    return f"{YELLOW}{status}{RESET}"


def render_server_block(server: dict, metrics: dict, logs: str, width: int = 72) -> list[str]:
    """渲染单台服务器的监控块，返回行列表"""
    name = server["name"]
    host = server["host"]
    lines = []

    border = "─" * width
    lines.append(f"{BOLD}{CYAN}┌{border}┐{RESET}")
    lines.append(f"{BOLD}{CYAN}│ {name} ({host}){' ' * (width - len(name) - len(host) - 3)}│{RESET}")
    lines.append(f"{BOLD}{CYAN}└{border}┘{RESET}")

    if metrics is None:
        lines.append(f"  {RED}连接失败或数据采集超时{RESET}")
        return lines

    # ── 内存 & CPU & IO
    mem = metrics.get("mem")
    cpu = metrics.get("cpu")
    iowait = metrics.get("iowait", "N/A")

    mem_str = "N/A"
    if mem:
        bar_len = 20
        filled = int(bar_len * mem["pct"] / 100)
        bar_color = RED if mem["pct"] >= 90 else (YELLOW if mem["pct"] >= 70 else GREEN)
        bar = f"{bar_color}{'█' * filled}{'░' * (bar_len - filled)}{RESET}"
        mem_str = f"{bar} {color_pct(mem['pct'])}  {mem['used']}MB / {mem['total']}MB"

    cpu_str = color_pct(cpu) if cpu is not None else "N/A"
    io_str  = f"{YELLOW}{iowait}%{RESET}" if iowait not in ("N/A", None) else "N/A"

    lines.append(f"  {BOLD}内存:{RESET} {mem_str}")
    lines.append(f"  {BOLD}CPU :{RESET} {cpu_str}    {BOLD}IO等待:{RESET} {io_str}")

    # ── GPU
    gpus = metrics.get("gpu", [])
    if gpus:
        lines.append(f"  {BOLD}GPU :{RESET}")
        for g in gpus:
            g_util = float(g["gpu_util"]) if g["gpu_util"].replace(".","").isdigit() else 0
            lines.append(
                f"    [{g['id']}] {g['name'][:30]}  "
                f"GPU:{color_pct(g_util)}  "
                f"显存:{g['mem_used']}MB/{g['mem_total']}MB  "
                f"温度:{g['temp']}°C"
            )
    else:
        lines.append(f"  {GRAY}GPU : 无 GPU 或 nvidia-smi 未安装{RESET}")

    # ── Docker 容器状态
    containers = metrics.get("containers", [])
    docker_stats = {d["name"]: d for d in metrics.get("docker_stats", [])}
    if containers:
        lines.append(f"  {BOLD}Docker 容器:{RESET}")
        for c in containers:
            stat = docker_stats.get(c["name"], {})
            cpu_d  = stat.get("cpu", "-")
            mem_d  = stat.get("mem_usage", "-")
            memp_d = stat.get("mem_pct", "-")
            net_d  = stat.get("net_io", "-")
            blk_d  = stat.get("block_io", "-")
            lines.append(
                f"    {BOLD}{c['name'][:28]}{RESET}  {color_status(c['status'])}"
            )
            lines.append(
                f"      CPU:{YELLOW}{cpu_d}{RESET}  内存:{mem_d}({memp_d})  "
                f"网络:{net_d}  磁盘IO:{blk_d}"
            )
    else:
        lines.append(f"  {RED}Docker 容器: 无运行中的容器！{RESET}")

    # ── 进程（Python/MinerU 相关）
    procs = metrics.get("procs", [])
    mineru_procs = [p for p in procs if not p.startswith("USER")]
    if mineru_procs:
        lines.append(f"  {BOLD}相关进程 (Top CPU):{RESET}")
        for p in mineru_procs[:5]:
            cols = p.split()
            if len(cols) >= 11:
                user, pid, cpu_p, mem_p = cols[0], cols[1], cols[2], cols[3]
                cmd = " ".join(cols[10:])[:50]
                lines.append(
                    f"    PID:{pid}  CPU:{YELLOW}{cpu_p}%{RESET}  MEM:{mem_p}%  {GRAY}{cmd}{RESET}"
                )
    else:
        lines.append(f"  {GRAY}无 Python/MinerU 相关进程{RESET}")

    # ── 最新日志（慢的线索）
    if logs and logs.strip() not in ("NO_CONTAINER", ""):
        lines.append(f"  {BOLD}容器最新日志:{RESET}")
        for log_line in logs.strip().splitlines()[-6:]:
            # 高亮错误关键词
            if any(k in log_line.lower() for k in ("error", "exception", "traceback", "timeout", "failed", "oom")):
                lines.append(f"    {RED}{log_line[:100]}{RESET}")
            elif any(k in log_line.lower() for k in ("warn", "slow", "retry")):
                lines.append(f"    {YELLOW}{log_line[:100]}{RESET}")
            else:
                lines.append(f"    {GRAY}{log_line[:100]}{RESET}")

    return lines


# ─────────────────────────────────────────────
# 单台服务器数据采集（含日志）
# ─────────────────────────────────────────────
def collect_server(server: dict) -> tuple[dict | None, str]:
    client = make_client(server)
    if client is None:
        return None, ""
    try:
        _, raw, _ = run_cmd(client, COLLECT_CMD, timeout=15)
        metrics = parse_metrics(raw)
        _, logs, _ = run_cmd(client, LOGS_CMD, timeout=8)
        return metrics, logs
    except Exception:
        return None, ""
    finally:
        client.close()


# ─────────────────────────────────────────────
# 主监控循环
# ─────────────────────────────────────────────
def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def print_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{BOLD}{'='*74}{RESET}")
    print(f"{BOLD}  MinerU 服务诊断监控    {CYAN}{now}{RESET}    {GRAY}刷新间隔: {REFRESH_INTERVAL}s  Ctrl+C 退出{RESET}")
    print(f"{BOLD}{'='*74}{RESET}")


def diagnose_slow(server: dict, client):
    """一次性深度诊断：分析慢的原因"""
    print(f"\n{BOLD}{CYAN}=== 深度诊断: {server['name']} ==={RESET}")

    checks = [
        ("系统负载",          "uptime"),
        ("内存详情",          "free -h && echo '---' && cat /proc/meminfo | grep -E 'MemTotal|MemFree|Cached|SwapTotal|SwapFree'"),
        ("CPU 核心数",        "nproc && lscpu | grep -E 'Model name|CPU\\(s\\)|Thread'"),
        ("磁盘使用",          "df -h /data 2>/dev/null || df -h /"),
        ("磁盘IO实时",        "iostat -x 1 2 2>/dev/null | tail -20 || echo 'iostat not available'"),
        ("Docker 容器日志(最新20行)", f"docker logs --tail=20 $(docker ps -q --filter 'name=mineru' | head -1) 2>&1 || echo 'no container'"),
        ("容器内进程",        "docker exec $(docker ps -q --filter 'name=mineru' | head -1) ps aux --sort=-%cpu 2>/dev/null | head -15 || echo 'N/A'"),
        ("网络连接数",        "ss -s 2>/dev/null || netstat -s 2>/dev/null | head -20"),
        ("OOM 记录",          "dmesg | grep -i 'oom\\|kill' | tail -5 || journalctl -k | grep -i oom | tail -5 || echo 'no oom'"),
        ("系统错误日志",      "journalctl -p err --since '1 hour ago' --no-pager 2>/dev/null | tail -10 || echo 'N/A'"),
    ]

    for title, cmd in checks:
        print(f"\n{BOLD}{YELLOW}▶ {title}{RESET}")
        print(f"{GRAY}  $ {cmd[:80]}{RESET}")
        _, out, err = run_cmd(client, cmd, timeout=15)
        output = (out or err or "（无输出）").strip()
        for line in output.splitlines()[:20]:
            print(f"  {line}")

    print(f"\n{BOLD}{GREEN}诊断完成{RESET}\n")


def run_diagnose_all():
    """对所有服务器执行深度诊断"""
    for server in SERVERS:
        print(f"\n{BOLD}正在连接 {server['name']} ({server['host']})...{RESET}")
        client = make_client(server)
        if client is None:
            print(f"{RED}连接失败，跳过{RESET}")
            continue
        try:
            diagnose_slow(server, client)
        finally:
            client.close()


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="MinerU 服务诊断监控")
    parser.add_argument("--diagnose", "-d", action="store_true", help="执行一次性深度诊断后退出")
    parser.add_argument("--server", "-s", type=int, default=None, help="只诊断第N台服务器(1/2/3)")
    args = parser.parse_args()

    if args.diagnose:
        targets = SERVERS if args.server is None else [SERVERS[args.server - 1]]
        for server in targets:
            print(f"\n{BOLD}正在连接 {server['name']} ({server['host']})...{RESET}")
            client = make_client(server)
            if client is None:
                print(f"{RED}连接失败，跳过{RESET}")
                continue
            try:
                diagnose_slow(server, client)
            finally:
                client.close()
        return

    # ── 实时监控模式
    print(f"{BOLD}启动 MinerU 实时监控...{RESET}")
    print(f"{GRAY}提示: 运行 python monitor_mineru.py --diagnose 可进行深度诊断{RESET}\n")

    try:
        while True:
            # 并发采集三台服务器数据
            results = {}
            with ThreadPoolExecutor(max_workers=len(SERVERS)) as pool:
                future_map = {pool.submit(collect_server, s): s for s in SERVERS}
                for future in future_map:
                    server = future_map[future]
                    try:
                        metrics, logs = future.result(timeout=20)
                        results[server["name"]] = (metrics, logs)
                    except Exception:
                        results[server["name"]] = (None, "")

            # 渲染输出
            clear_screen()
            print_header()

            all_lines = []
            for server in SERVERS:
                metrics, logs = results.get(server["name"], (None, ""))
                block = render_server_block(server, metrics, logs)
                all_lines.extend(block)
                all_lines.append("")  # 空行分隔

            print("\n".join(all_lines))

            # 慢速分析提示
            print(f"\n{BOLD}{'─'*74}{RESET}")
            print(f"{BOLD}慢速诊断提示:{RESET}")
            for server in SERVERS:
                metrics, _ = results.get(server["name"], (None, ""))
                if metrics is None:
                    print(f"  {RED}✗ {server['name']}: 无法连接{RESET}")
                    continue
                hints = []
                mem = metrics.get("mem")
                cpu = metrics.get("cpu")
                iowait = metrics.get("iowait")
                if mem and mem["pct"] >= 85:
                    hints.append(f"{RED}内存紧张({mem['pct']:.0f}%){RESET}")
                if cpu is not None and cpu >= 80:
                    hints.append(f"{RED}CPU高负载({cpu:.0f}%){RESET}")
                if iowait and iowait != "N/A":
                    try:
                        if float(iowait) >= 20:
                            hints.append(f"{YELLOW}磁盘IO等待高({iowait}%){RESET}")
                    except ValueError:
                        pass
                if not metrics.get("containers"):
                    hints.append(f"{RED}容器未运行！{RESET}")
                if hints:
                    print(f"  {YELLOW}⚠ {server['name']}:{RESET} " + "  ".join(hints))
                else:
                    print(f"  {GREEN}✓ {server['name']}: 指标正常{RESET}")

            print(f"\n{GRAY}下次刷新: {REFRESH_INTERVAL}s 后    深度诊断: python monitor_mineru.py --diagnose{RESET}")

            time.sleep(REFRESH_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n\n{BOLD}已退出监控{RESET}")


if __name__ == "__main__":
    main()
