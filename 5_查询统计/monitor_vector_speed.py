"""
向量化速度实时监控脚本
======================

功能：
1. 首次遍历找出所有正在向量化的文档
2. 后续只查询这些文档的状态变化
3. 统计每分钟完成的文档数

使用方式：
    python monitor_vector_speed.py

按 Ctrl+C 停止监控
"""
import sys
import os
import time
from datetime import datetime
from collections import deque

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset

# ============================================================
# 配置参数
# ============================================================
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"

# 两个 workspace ID
workspace_ids = [
    ("9c6857a6-f87b-4db8-8978-2f2e117f05a0", "环北知识库"),
    ("2f6118d7-20c5-48fd-8c44-b34bfab1ac30", "第二个知识库"),
]

# 查询间隔（秒）
QUERY_INTERVAL = 60  # 每60秒查询一次

# 保留最近多少次查询的数据用于计算平均速度
HISTORY_COUNT = 30


def clear_screen():
    """清屏"""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_doc_status(doc):
    """从文档的 tasks 字段获取向量化任务状态"""
    tasks = doc.get("tasks", [])
    if not tasks:
        return "no_task"
    
    normal_tasks = [t for t in tasks if t.get("type") == "normal"]
    
    if normal_tasks:
        return normal_tasks[-1].get("status", "unknown")
    else:
        return tasks[-1].get("status", "unknown")


def get_all_datasets(dataset_service, workspace_ids_list):
    """获取所有工作空间的知识库列表"""
    all_datasets = []
    for ws_id, ws_name in workspace_ids_list:
        print(f"  正在获取 [{ws_name}] 的知识库列表...", end="", flush=True)
        status, datasets_list = dataset_service.list_datasets(ws_id)
        if status != 200:
            print(f" 失败")
            continue
        count = 0
        for ds in datasets_list:
            if isinstance(ds, dict):
                ds["_workspace_name"] = ws_name
                all_datasets.append(ds)
                count += 1
        print(f" 找到 {count} 个")
    return all_datasets


def find_indexing_docs(dataset_service, all_datasets):
    """
    遍历所有知识库，找出正在向量化的文档
    
    Returns:
        list: 正在向量化的文档列表，每个元素是 {
            'dataset_id': 知识库ID,
            'dataset_name': 知识库名称,
            'doc_id': 文档ID,
            'doc_name': 文档名称,
            'status': 当前状态
        }
    """
    indexing_docs = []
    total_datasets = len(all_datasets)
    
    for i, ds in enumerate(all_datasets):
        dataset_id = ds.get("id")
        dataset_name = ds.get("name", "未知")
        
        progress = (i + 1) / total_datasets * 100
        print(f"\r  扫描进度: [{i+1}/{total_datasets}] {progress:.0f}% - {dataset_name[:30]:<30}", end="", flush=True)
        
        try:
            status, documents = dataset_service.list_documents(dataset_id)
            if status != 200:
                continue
            
            for doc in documents:
                doc_status = get_doc_status(doc)
                
                if doc_status in ["indexing", "parsing", "waiting", "queuing"]:
                    indexing_docs.append({
                        'dataset_id': dataset_id,
                        'dataset_name': dataset_name,
                        'doc_id': doc.get("id"),
                        'doc_name': doc.get("name", "未知"),
                        'status': doc_status
                    })
        except Exception:
            pass
    
    print()  # 换行
    return indexing_docs


def check_docs_status(dataset_service, docs_list):
    """
    检查文档列表中每个文档的当前状态
    
    Args:
        dataset_service: LingyanDataset实例
        docs_list: 文档列表
    
    Returns:
        tuple: (仍在进行中的数量, 已完成的数量, 失败的数量, 更新后的文档列表)
    """
    indexing_count = 0
    completed_count = 0
    error_count = 0
    
    # 按 dataset_id 分组，减少API调用
    datasets_docs = {}
    for doc in docs_list:
        ds_id = doc['dataset_id']
        if ds_id not in datasets_docs:
            datasets_docs[ds_id] = []
        datasets_docs[ds_id].append(doc)
    
    updated_docs = []
    total_datasets = len(datasets_docs)
    
    for i, (dataset_id, docs) in enumerate(datasets_docs.items()):
        dataset_name = docs[0]['dataset_name'] if docs else "未知"
        
        print(f"\r  检查进度: [{i+1}/{total_datasets}] - {dataset_name[:30]:<30}", end="", flush=True)
        
        try:
            status, documents = dataset_service.list_documents(dataset_id)
            if status != 200:
                # 如果查询失败，保持原状态
                for doc in docs:
                    doc['status'] = 'unknown'
                    updated_docs.append(doc)
                    indexing_count += 1
                continue
            
            # 创建文档ID到状态的映射
            doc_status_map = {}
            for d in documents:
                doc_status_map[d.get("id")] = get_doc_status(d)
            
            # 更新每个文档的状态
            for doc in docs:
                new_status = doc_status_map.get(doc['doc_id'], 'unknown')
                doc['status'] = new_status
                
                if new_status in ["indexing", "parsing", "waiting", "queuing"]:
                    indexing_count += 1
                    updated_docs.append(doc)  # 仍在进行中，保留在列表
                elif new_status in ["completed", "success"]:
                    completed_count += 1
                    # 已完成，不再加入列表
                elif new_status in ["error", "failed"]:
                    error_count += 1
                    # 失败了，也不再跟踪
                else:
                    # 其他状态（如cancelled），也不再跟踪
                    pass
                    
        except Exception as e:
            # 出错时保持原状态
            for doc in docs:
                updated_docs.append(doc)
                indexing_count += 1
    
    print()  # 换行
    return indexing_count, completed_count, error_count, updated_docs


def format_time(seconds):
    """格式化时间显示"""
    if seconds < 0:
        return "计算中..."
    if seconds < 60:
        return f"{int(seconds)}秒"
    if seconds < 3600:
        return f"{int(seconds // 60)}分{int(seconds % 60)}秒"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{int(hours)}小时{int(minutes)}分"


def main():
    print("=" * 60)
    print("向量化速度实时监控")
    print("=" * 60)
    print(f"查询间隔: {QUERY_INTERVAL} 秒")
    print("按 Ctrl+C 停止监控")
    print("=" * 60)
    
    dataset_service = LingyanDataset(api_key)
    
    # 首次获取知识库列表
    print("\n正在获取知识库列表...")
    all_datasets = get_all_datasets(dataset_service, workspace_ids)
    print(f"共找到 {len(all_datasets)} 个知识库\n")
    
    # 首次扫描，找出所有正在向量化的文档
    print("正在扫描正在向量化的文档...")
    indexing_docs = find_indexing_docs(dataset_service, all_datasets)
    initial_count = len(indexing_docs)
    print(f"\n找到 {initial_count} 个正在向量化的文档\n")
    
    if initial_count == 0:
        print("没有正在向量化的文档，退出监控。")
        return
    
    # 按知识库统计
    dataset_counts = {}
    for doc in indexing_docs:
        ds_name = doc['dataset_name']
        dataset_counts[ds_name] = dataset_counts.get(ds_name, 0) + 1
    
    print("各知识库正在向量化的文档数:")
    for name, count in sorted(dataset_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {name}: {count} 个")
    if len(dataset_counts) > 10:
        print(f"  ... 还有 {len(dataset_counts) - 10} 个知识库")
    
    print(f"\n{QUERY_INTERVAL} 秒后开始监控...")
    time.sleep(QUERY_INTERVAL)
    
    # 历史记录: (时间戳, 剩余进行中数量, 本次完成数量)
    history = deque(maxlen=HISTORY_COUNT + 1)
    
    # 统计数据
    start_time = datetime.now()
    total_completed = 0
    total_error = 0
    query_count = 0
    
    try:
        while len(indexing_docs) > 0:
            query_start = time.time()
            query_count += 1
            
            print(f"第 {query_count} 次查询（跟踪 {len(indexing_docs)} 个文档）...")
            
            # 检查文档状态
            indexing_count, completed, error, indexing_docs = check_docs_status(
                dataset_service, indexing_docs
            )
            
            current_time = datetime.now()
            query_duration = time.time() - query_start
            
            # 累计统计
            total_completed += completed
            total_error += error
            
            # 记录历史
            history.append((current_time, indexing_count, completed))
            
            # 清屏并显示状态
            clear_screen()
            
            print("=" * 60)
            print(f"  向量化速度监控  |  {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            
            # 状态统计
            print(f"\n  初始进行中: {initial_count} 个")
            print(f"  当前进行中: {indexing_count} 个")
            print(f"  已完成:     {total_completed} 个")
            print(f"  失败:       {total_error} 个")
            
            # 计算速度
            session_time = (current_time - start_time).total_seconds()
            
            if len(history) >= 1:
                # 最近一次完成的数量
                last_completed = history[-1][2]
                
                # 计算平均速度
                if session_time > 0:
                    avg_speed_per_min = total_completed / session_time * 60
                else:
                    avg_speed_per_min = 0
                
                # 预估剩余时间
                if avg_speed_per_min > 0:
                    eta_seconds = indexing_count / avg_speed_per_min * 60
                else:
                    eta_seconds = -1
                
                print(f"\n{'─' * 50}")
                print(f"  本次完成:   +{last_completed} 个")
                print(f"  平均速度:   {avg_speed_per_min:.1f} 个/分钟")
                print(f"  运行时长:   {format_time(session_time)}")
                print(f"  预计剩余:   {format_time(eta_seconds)}")
                print(f"{'─' * 50}")
                
                # 历史记录
                if len(history) >= 2:
                    print(f"\n  历史（每次完成数）:")
                    records = list(history)
                    display_items = []
                    for i in range(len(records)):
                        time_str = records[i][0].strftime("%H:%M:%S")
                        diff = records[i][2]
                        display_items.append(f"{time_str}:+{diff}")
                    
                    # 每行显示5条
                    line = "  "
                    for i, item in enumerate(display_items):
                        line += f"{item:<14}"
                        if (i + 1) % 5 == 0:
                            print(line)
                            line = "  "
                    if line.strip():
                        print(line)
            
            print(f"\n  查询耗时: {query_duration:.1f}秒 | 下次: {QUERY_INTERVAL}秒后 | Ctrl+C 停止")
            
            # 检查是否全部完成
            if indexing_count == 0:
                print(f"\n  🎉 所有文档向量化完成！")
                break
            
            # 等待下一次查询
            sleep_time = max(0, QUERY_INTERVAL - query_duration)
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        pass
    
    # 最终统计
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    print("\n\n" + "=" * 60)
    print("监控结束")
    print("=" * 60)
    print(f"\n  监控时长:   {format_time(total_time)}")
    print(f"  初始数量:   {initial_count} 个")
    print(f"  完成数量:   {total_completed} 个")
    print(f"  失败数量:   {total_error} 个")
    print(f"  剩余数量:   {len(indexing_docs)} 个")
    if total_time > 0 and total_completed > 0:
        print(f"  平均速度:   {total_completed / total_time * 60:.1f} 个/分钟")
    print()


if __name__ == "__main__":
    main()
