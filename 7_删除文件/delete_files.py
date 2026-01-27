"""
全局删除知识库中的 PNG、ZIP 等格式文件
"""
import sys
import os
import logging
from datetime import datetime

# 添加项目根目录和核心模块目录到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "1_核心模块"))

from LingyanAi import LingyanDataset

# 确保logs文件夹存在（使用项目根目录）
logs_dir = os.path.join(project_root, "logs")
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# 配置日志文件名（按日期）
log_filename = os.path.join(logs_dir, f"delete_files_{datetime.now().strftime('%Y-%m-%d')}.log")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s \t %(levelname)s \t %(name)s: \t %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("delete_files")

# ===================== 配置区域 =====================
workspace_id = "9c6857a6-f87b-4db8-8978-2f2e117f05a0"       # 工作区ID
api_key = "sk-7gIAz0lh7JdOIvcCUH9nm1UjfchNpAO6iNihHT8i"    # 灵燕平台 API Key

# 要删除的文件类型列表（注意：不带点，如 "png" 而不是 ".png"）
# 这里的类型对应文档的 type 字段，如 pdf, docx, png, jpg, zip 等
file_types_to_delete = ["png", "zip", "jpg", "jpeg","mp4","dwg","htm","ico","css","pdg","dat","xml","ico"]
# ====================================================

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("开始全局删除指定类型的文件")
    log.info(f"工作区ID: {workspace_id}")
    log.info(f"要删除的文件类型: {file_types_to_delete}")
    log.info("=" * 60)

    dataset = LingyanDataset(api_key)

    # 全局删除
    total_deleted, total_failed, dataset_results = dataset.delete_documents_global(
        workspace_id=workspace_id,
        file_types=file_types_to_delete,
        folder_id=None  # 不限制文件夹，全局搜索
    )

    # 输出结果
    log.info("=" * 60)
    log.info("删除完成！统计信息：")
    log.info(f"总共删除: {total_deleted} 个文档")
    log.info(f"删除失败: {len(total_failed)} 个文档")
    
    if dataset_results:
        log.info("-" * 40)
        log.info("各知识库删除详情：")
        for result in dataset_results:
            log.info(f"  知识库: {result['dataset_name']}")
            log.info(f"    - 删除成功: {result['deleted_count']} 个")
            log.info(f"    - 删除失败: {result['failed_count']} 个")
    
    if total_failed:
        log.info("-" * 40)
        log.info("删除失败的文档列表：")
        for failed in total_failed:
            log.error(f"  文档: {failed['name']} (知识库: {failed['dataset_name']})")
            log.error(f"    错误: {failed['error']}")
    
    log.info("=" * 60)
