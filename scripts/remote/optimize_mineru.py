"""
MinerU GPU 深度诊断脚本（只读，不修改任何配置）
持续采样 60 秒，分析 GPU 利用率波形、容器竞争、进程占用、docker配置

使用方式：
  python scripts/remote/optimize_mineru.py                  # 诊断所有服务器
  python scripts/remote/optimize_mineru.py --server 1       # 只诊断第1台(212)
  python scripts/remote/optimize_mineru.py --duration 120   # 采样120秒（默认60）
  python scripts/remote/optimize_mineru.py --export         # 导出报告
"""
import paramiko
import sys
import time
from datetime import datetime

SERVERS = [
    {
        "name": "解析-212",
        "host": "10.11.76.212",
        "port": 22,
        "username": "root",
        "password": "1s3LwmnznxQ=",
        "gpu_count": 2,
    },
    {
        "name": "切片-214",
        "host": "10.11.76.214",
        "port": 22,
        "username": "root",
        "password": "QttnkiO!Z=BFoeSa",
        "gpu_count": 1,
    },
    {
        "name": "解析-210",
        "host": "10.11.76.210",
        "port": 22,
        "username": "root",
        "password": "anc48yji3",
        "gpu_count": 1,
    },
]

DOCKER_DIR = "/data/mineru-api"

B  = "\033[1m"
R  = "\033[91m"
Y  = "\033[93m"
G  = "\033[92m"
C  = "\033[96m"
GR = "\033[90m"
E  = "\033[0m"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def make_client(server: dict):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=server["host"], port=server["port"],
            username=server["username"], password=server["password"],
            timeout=10,
        )
        return client
    except Exception as e:
        print(f"  {R}连接失败: {e}{E}")
        return None


def run(client, cmd: str, timeout: int = 30):
    try:
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        ec = stdout.channel.recv_exit_status()
        return ec, stdout.read().decode("utf-8", errors="replace").strip(), stderr.read().decode("utf-8", errors="replace").strip()
    except Exception as e:
        return -1, "", str(e)


def draw_bar(values: list, width: int = 60) -> list[str]:
    """用ASCII画一个简易的利用率波形图"""
    if not values:
        return ["  (无数据)"]
    lines = []
    max_v = max(max(values), 1)
    rows = 8
    for row in range(rows, 0, -1):
        threshold = max_v * row / rows
        label = f"{int(threshold):>3}%│"
        bar = ""
        for v in values:
            bar += "█" if v >= threshold else " "
        lines.append(f"  {label}{bar}│")
    # X 轴
    lines.append(f"     └{'─' * len(values)}┘")
    tick_line = "      "
    for i in range(0, len(values), max(len(values) // 6, 1)):
        tick_line += f"{i * 2}s"
        tick_line += " " * max(1, (max(len(values) // 6, 1)) - len(f"{i * 2}s"))
    lines.append(tick_line)
    return lines


# ─────────────────────────────────────────────
# 诊断单台服务器
# ─────────────────────────────────────────────
def diagnose_server(server: dict, duration: int = 60):
    name = server["name"]
    host = server["host"]
    print(f"\n{B}{'='*74}{E}")
    print(f"{B}{C} 诊断 {name} ({host}) — 采样 {duration} 秒{E}")
    print(f"{B}{'='*74}{E}")

    client = make_client(server)
    if client is None:
        return {"server": name, "host": host, "error": "连接失败"}

    report = {"server": name, "host": host, "sections": []}

    try:
        # ═══════════════════════════════════════════════
        # 1. 基础信息
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[1/8] 基础信息{E}")
        _, cores, _  = run(client, "nproc")
        _, mem, _    = run(client, "free -g | awk 'NR==2{printf \"%d/%d\", $3, $2}'")
        _, load, _   = run(client, "uptime | awk -F'load average:' '{print $2}'")
        _, gpus, _   = run(client, "nvidia-smi --query-gpu=index,name,driver_version --format=csv,noheader")
        print(f"    CPU: {cores} 核  内存: {mem}GB  负载: {load}")
        print(f"    GPU: {gpus.replace(chr(10), '  |  ')}")
        report["sections"].append(("基础信息", f"CPU={cores}核 内存={mem}GB 负载={load}\nGPU: {gpus}"))

        # ═══════════════════════════════════════════════
        # 2. docker-compose.yml 完整配置
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[2/8] docker-compose.yml 配置{E}")
        _, compose, _ = run(client, f"cat {DOCKER_DIR}/docker-compose.yml", timeout=10)
        if compose:
            print(f"    文件长度: {len(compose.splitlines())} 行")
            # 提取关键配置
            for keyword in ["runtime", "device_ids", "NVIDIA_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES",
                            "capabilities", "gpu", "deploy", "resources", "worker", "WORKERS",
                            "mem_limit", "cpus", "shm_size", "command"]:
                matched = [l.strip() for l in compose.splitlines() if keyword.lower() in l.lower()]
                if matched:
                    print(f"    {C}{keyword}{E}: {Y}{' | '.join(matched[:3])}{E}")
            # 显示完整文件
            print(f"\n    {GR}--- docker-compose.yml 完整内容 ---{E}")
            for i, line in enumerate(compose.splitlines(), 1):
                print(f"    {GR}{i:3d}{E}| {line}")
            print(f"    {GR}--- 结束 ---{E}")
            report["sections"].append(("docker-compose.yml", compose))
        else:
            print(f"    {R}未找到 docker-compose.yml{E}")

        # ═══════════════════════════════════════════════
        # 3. GPU 进程详情（nvidia-smi pmon / 计算进程）
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[3/8] GPU 上正在运行的进程{E}")
        _, pmon, _ = run(client, "nvidia-smi pmon -c 1 2>/dev/null || nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader 2>/dev/null || echo 'N/A'", timeout=10)
        if pmon and pmon != "N/A":
            for line in pmon.splitlines()[:20]:
                if line.startswith("#") or not line.strip():
                    continue
                print(f"    {line}")
        else:
            print(f"    {Y}未检测到 GPU 计算进程（可能进程间歇性启动）{E}")
        report["sections"].append(("GPU进程", pmon))

        # ═══════════════════════════════════════════════
        # 4. 每个容器的 GPU 可见性（容器内视角）
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[4/8] 每个容器看到的 GPU{E}")
        _, cnames, _ = run(client, "docker ps --filter 'name=mineru' --format '{{.Names}}'")
        containers = [c for c in cnames.splitlines() if c.strip()]
        for cname in containers:
            _, gpu_in, _ = run(client, f"docker exec {cname} nvidia-smi -L 2>/dev/null || echo 'NO_GPU'", timeout=8)
            _, env_cuda, _ = run(client, f"docker exec {cname} printenv CUDA_VISIBLE_DEVICES 2>/dev/null || echo 'unset'", timeout=5)
            _, env_nv, _ = run(client, f"docker exec {cname} printenv NVIDIA_VISIBLE_DEVICES 2>/dev/null || echo 'unset'", timeout=5)
            gpu_count = len([l for l in gpu_in.splitlines() if "GPU" in l and "UUID" in l])
            color = G if gpu_count > 0 else R
            print(f"    {B}{cname}{E}: 可见 {color}{gpu_count} 块GPU{E}  CUDA_VISIBLE={env_cuda}  NVIDIA_VISIBLE={env_nv}")
            if gpu_in and "NO_GPU" not in gpu_in:
                for gl in gpu_in.splitlines():
                    if gl.strip():
                        print(f"      {GR}{gl.strip()}{E}")
        report["sections"].append(("容器GPU可见性", f"{len(containers)} containers"))

        # ═══════════════════════════════════════════════
        # 5. 容器启动命令和关键环境变量
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[5/8] 容器启动命令 & 关键参数{E}")
        for cname in containers:
            _, cmd_out, _ = run(client, f"docker inspect {cname} --format='{{{{json .Config.Cmd}}}}'", timeout=5)
            _, entrypoint, _ = run(client, f"docker inspect {cname} --format='{{{{json .Config.Entrypoint}}}}'", timeout=5)
            _, all_env, _ = run(client, f"docker exec {cname} env 2>/dev/null | grep -iE 'worker|thread|batch|parallel|cuda|gpu|device|model|uvicorn|gunicorn|host|port' || echo 'none'", timeout=8)
            print(f"    {B}{cname}{E}:")
            print(f"      Entrypoint: {C}{entrypoint}{E}")
            print(f"      Cmd:        {C}{cmd_out}{E}")
            if all_env and all_env != "none":
                for ev in all_env.splitlines():
                    print(f"      ENV: {Y}{ev}{E}")
        report["sections"].append(("容器配置", "shown above"))

        # ═══════════════════════════════════════════════
        # 6. 长时间 GPU 采样（核心！）
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[6/8] GPU 利用率持续采样（{duration}秒，每2秒一次）{E}")
        print(f"  {GR}采样中", end="", flush=True)

        # 用服务器端 nvidia-smi 循环采样，一次 SSH 搞定，不反复连接
        sample_count = duration // 2
        sample_cmd = f"""
for i in $(seq 1 {sample_count}); do
  nvidia-smi --query-gpu=index,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null
  echo "@@TICK@@"
  sleep 2
done
"""
        _, sample_raw, _ = run(client, sample_cmd, timeout=duration + 30)
        print(f"{E}")

        # 解析采样数据
        ticks = sample_raw.split("@@TICK@@")
        gpu_timeline = {}  # gpu_id -> [util_values]
        mem_timeline = {}
        all_ticks_data = []

        for tick in ticks:
            tick_gpus = {}
            for line in tick.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 7:
                    idx, gpu_u, mem_u, mem_used, mem_total, temp, power = parts[:7]
                    try:
                        gpu_util = int(gpu_u) if gpu_u.isdigit() else int(float(gpu_u))
                    except (ValueError, TypeError):
                        gpu_util = 0
                    try:
                        mem_util = int(mem_u) if mem_u.isdigit() else int(float(mem_u))
                    except (ValueError, TypeError):
                        mem_util = 0

                    if idx not in gpu_timeline:
                        gpu_timeline[idx] = []
                        mem_timeline[idx] = []
                    gpu_timeline[idx].append(gpu_util)
                    mem_timeline[idx].append(mem_util)
                    tick_gpus[idx] = {"gpu_u": gpu_util, "mem_u": mem_util, "mem_used": mem_used,
                                     "mem_total": mem_total, "temp": temp, "power": power}
            if tick_gpus:
                all_ticks_data.append(tick_gpus)

        # 打印波形图
        for gpu_id, utils in sorted(gpu_timeline.items()):
            avg = sum(utils) / len(utils) if utils else 0
            peak = max(utils) if utils else 0
            zeros = utils.count(0)
            low = len([v for v in utils if v < 10])
            high = len([v for v in utils if v >= 50])

            color = R if avg < 20 else (Y if avg < 50 else G)
            print(f"\n    {B}GPU {gpu_id} 利用率波形{E}  (采样{len(utils)}次, 共{len(utils)*2}秒)")
            print(f"    平均: {color}{avg:.1f}%{E}  峰值: {peak}%  空闲(0%): {zeros}次  低(<10%): {low}次  高(≥50%): {high}次")

            for bline in draw_bar(utils):
                print(f"  {bline}")

        # 显存趋势
        for gpu_id, mems in sorted(mem_timeline.items()):
            avg_m = sum(mems) / len(mems) if mems else 0
            print(f"    GPU {gpu_id} 显存带宽利用率: 平均 {avg_m:.1f}%  峰值 {max(mems) if mems else 0}%")

        report["sections"].append(("GPU采样", {
            "duration": duration,
            "gpu_timeline": gpu_timeline,
            "sample_count": len(all_ticks_data),
        }))

        # ═══════════════════════════════════════════════
        # 7. 容器日志分析（100行）
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[7/8] 容器日志分析（最近100行）{E}")
        for cname in containers[:4]:
            _, logs, _ = run(client, f"docker logs --tail=100 {cname} 2>&1", timeout=15)
            if not logs:
                print(f"    {cname}: {GR}无日志{E}")
                continue

            log_lines = logs.splitlines()
            # 统计关键词
            error_lines = [l for l in log_lines if any(k in l.lower() for k in ("error", "exception", "traceback", "oom", "killed", "fail"))]
            process_lines = [l for l in log_lines if any(k in l.lower() for k in ("processing page", "process", "it/s", "200 ok", "post /"))]
            warn_lines = [l for l in log_lines if any(k in l.lower() for k in ("warning", "warn", "slow", "timeout", "retry"))]

            print(f"    {B}{cname}{E}: 总{len(log_lines)}行  请求/处理:{G}{len(process_lines)}{E}  警告:{Y}{len(warn_lines)}{E}  错误:{R}{len(error_lines)}{E}")

            # 提取处理速度
            speed_lines = [l for l in log_lines if "it/s" in l]
            if speed_lines:
                print(f"      处理速度:")
                for sl in speed_lines[-5:]:
                    print(f"        {GR}{sl.strip()[:120]}{E}")

            # 显示最近的请求日志
            recent_requests = [l for l in log_lines if "200 OK" in l or "POST /" in l]
            if recent_requests:
                print(f"      最近请求 ({len(recent_requests)} 条):")
                for rl in recent_requests[-5:]:
                    print(f"        {GR}{rl.strip()[:120]}{E}")

            if error_lines:
                print(f"      {R}错误日志:{E}")
                for el in error_lines[-3:]:
                    print(f"        {R}{el.strip()[:120]}{E}")

        # ═══════════════════════════════════════════════
        # 8. 综合分析 & 建议
        # ═══════════════════════════════════════════════
        print(f"\n  {B}[8/8] 综合分析{E}")
        print(f"  {'─'*70}")

        findings = []

        for gpu_id, utils in sorted(gpu_timeline.items()):
            if not utils:
                continue
            avg = sum(utils) / len(utils)
            peak = max(utils)
            zeros = utils.count(0)
            low_pct = len([v for v in utils if v < 10]) / len(utils) * 100

            if avg >= 80:
                print(f"    {G}✓ GPU{gpu_id}: 利用率良好 (平均{avg:.0f}%){E}")
            elif avg >= 40:
                print(f"    {Y}△ GPU{gpu_id}: 利用率中等 (平均{avg:.0f}%, 峰值{peak}%){E}")
                findings.append(f"GPU{gpu_id} 利用率平均{avg:.0f}%，还有提升空间")
            else:
                print(f"    {R}✗ GPU{gpu_id}: 利用率偏低 (平均{avg:.0f}%, {low_pct:.0f}%时间<10%){E}")
                findings.append(f"GPU{gpu_id} 利用率仅{avg:.0f}%，{low_pct:.0f}%时间低于10%")

                # 分析原因
                if zeros > len(utils) * 0.5:
                    print(f"      → {B}可能原因: GPU 超过一半时间完全空闲{E}")
                    print(f"        - 任务量不足，GPU 在等上游请求")
                    print(f"        - MinerU 的 CPU 预处理阶段耗时长，GPU 只在推理阶段短暂使用")
                    print(f"        - 容器间 GPU 没做隔离，排队等待")

        # 检查 GPU 隔离
        all_same_gpu = True
        for cname in containers:
            _, nv_devs, _ = run(client, f"docker exec {cname} nvidia-smi -L 2>/dev/null | wc -l", timeout=5)
            if nv_devs.strip().isdigit() and int(nv_devs.strip()) != server["gpu_count"]:
                all_same_gpu = False

        if all_same_gpu and server["gpu_count"] >= 2 and len(containers) >= 2:
            print(f"\n    {Y}△ 所有容器都能看到全部 {server['gpu_count']} 块GPU{E}")
            print(f"      这说明没有做 GPU 隔离，多容器可能争抢")
            findings.append("多容器共享GPU，未做device_ids隔离")

        # 给出操作建议
        print(f"\n  {B}{'═'*70}{E}")
        print(f"  {B}  操作建议（手动执行，脚本不会修改任何配置）{E}")
        print(f"  {B}{'═'*70}{E}")

        if findings:
            for i, f in enumerate(findings, 1):
                print(f"    {Y}{i}. {f}{E}")

        print(f"""
    {B}要让 GPU 跑到 100%，需要排查以下方面：{E}

    {C}1. MinerU 是否真正使用了 GPU 做推理？{E}
       检查方法: ssh root@{host}
         docker exec mineru-api01 python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
       如果返回 False，说明容器内 PyTorch 没检测到 GPU

    {C}2. MinerU 处理 PDF 的流程是什么？{E}
       典型流程: PDF→图像(CPU) → OCR/布局检测(GPU) → 结构化输出(CPU)
       GPU 只在 OCR 和布局检测阶段使用，前后的 CPU 阶段越长，GPU 空闲越多
       解决: 增加并发请求数，让多个任务的 GPU 阶段交替执行

    {C}3. 容器内 worker 数是否太少？{E}
       检查: docker exec mineru-api01 env | grep -iE 'worker|thread'
       如果 worker=1，那每个容器同时只处理1个请求，GPU自然空闲
       建议每容器 2-4 个 worker

    {C}4. 上游调用并发够不够？{E}
       如果上游每次只发1个请求等返回再发下一个，GPU 利用率永远上不去
       需要上游同时发多个请求

    {C}5. GPU 隔离（多GPU服务器）{E}
       如果有2块GPU但都看得见所有容器：
       在 docker-compose.yml 中用 device_ids 隔离
       api01/api02 → GPU0, api03/api04 → GPU1""")

        report["findings"] = findings
        return report

    except Exception as e:
        print(f"  {R}诊断异常: {e}{E}")
        import traceback
        traceback.print_exc()
        return {"server": name, "host": host, "error": str(e)}
    finally:
        client.close()


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="MinerU GPU 深度诊断（只读）")
    parser.add_argument("--server", type=int, help="只诊断第N台(1/2/3)")
    parser.add_argument("--duration", type=int, default=60, help="GPU采样时长(秒), 默认60")
    parser.add_argument("--export", "-e", action="store_true", help="导出报告")
    args = parser.parse_args()

    targets = SERVERS if args.server is None else [SERVERS[args.server - 1]]

    print(f"{B}{'='*74}{E}")
    print(f"{B}MinerU GPU 深度诊断（只读，不修改任何配置）{E}")
    print(f"  服务器: {len(targets)} 台")
    print(f"  采样时长: {args.duration} 秒")
    print(f"  预计耗时: {len(targets) * (args.duration + 30)} 秒")
    print(f"{B}{'='*74}{E}")

    all_results = []
    for server in targets:
        result = diagnose_server(server, duration=args.duration)
        all_results.append(result)

    print(f"\n{B}{'='*74}{E}")
    print(f"{B}全部诊断完成{E}")
    print(f"{B}{'='*74}{E}")

    if args.export:
        fname = f"mineru_gpu_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            for r in all_results:
                f.write(f"\n{'='*70}\n{r.get('server', '?')} ({r.get('host', '?')})\n{'='*70}\n")
                for title, content in r.get("sections", []):
                    f.write(f"\n--- {title} ---\n")
                    if isinstance(content, str):
                        f.write(content + "\n")
                    else:
                        f.write(str(content) + "\n")
                if r.get("findings"):
                    f.write("\n--- 发现 ---\n")
                    for finding in r["findings"]:
                        f.write(f"  - {finding}\n")
        print(f"\n{G}✓ 报告已导出: {fname}{E}")


if __name__ == "__main__":
    main()
