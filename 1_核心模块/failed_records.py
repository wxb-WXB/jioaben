"""
失败记录管理模块
================

用于记录、存储和管理上传失败的文件信息，支持：
- 记录失败文件及其详细错误信息
- 持久化存储到 JSON 文件
- 查询和统计失败记录
- 支持重试功能

失败记录存储位置：项目根目录/failed_records/
"""

import json
import os
from datetime import datetime
from threading import Lock
from typing import Optional
import logging

log = logging.getLogger("FailedRecords")


class FailedRecord:
    """
    单条失败记录
    
    Attributes:
        file_path (str): 文件完整路径
        file_name (str): 文件名
        file_classify (str): 文件分类目录
        dataset_name (str): 目标知识库名称
        folder_id (str): 目录ID
        error_stage (str): 失败阶段
        error_message (str): 错误信息
        error_code (int): 错误状态码
        retry_count (int): 重试次数
        created_at (str): 创建时间
        updated_at (str): 更新时间
    """
    
    # 失败阶段常量
    STAGE_FOLDER_NOT_FOUND = "folder_not_found"      # 目录映射未找到
    STAGE_LIST_DATASETS = "list_datasets"            # 获取知识库列表失败
    STAGE_CREATE_DATASET = "create_dataset"          # 创建知识库失败
    STAGE_CHECK_FILE = "check_file"                  # 重名检测失败
    STAGE_UPLOAD_FILE = "upload_file"                # 文件上传失败
    STAGE_CREATE_DOCUMENT = "create_document"        # 创建文档失败
    STAGE_CREATE_TASK = "create_task"                # 创建任务失败
    STAGE_UNKNOWN = "unknown"                        # 未知错误
    
    def __init__(
        self,
        file_path: str,
        file_name: str,
        file_classify: str,
        dataset_name: str = "",
        folder_id: str = "",
        dataset_id: str = "",
        error_stage: str = "",
        error_message: str = "",
        error_code: int = 0,
        retry_count: int = 0,
        created_at: str = None,
        updated_at: str = None,
    ):
        self.file_path = file_path
        self.file_name = file_name
        self.file_classify = file_classify
        self.dataset_name = dataset_name
        self.folder_id = folder_id
        self.dataset_id = dataset_id
        self.error_stage = error_stage
        self.error_message = error_message
        self.error_code = error_code
        self.retry_count = retry_count
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = updated_at or self.created_at
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_classify": self.file_classify,
            "dataset_name": self.dataset_name,
            "folder_id": self.folder_id,
            "dataset_id": self.dataset_id,
            "error_stage": self.error_stage,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FailedRecord":
        """从字典创建实例"""
        return cls(
            file_path=data.get("file_path", ""),
            file_name=data.get("file_name", ""),
            file_classify=data.get("file_classify", ""),
            dataset_name=data.get("dataset_name", ""),
            folder_id=data.get("folder_id", ""),
            dataset_id=data.get("dataset_id", ""),
            error_stage=data.get("error_stage", ""),
            error_message=data.get("error_message", ""),
            error_code=data.get("error_code", 0),
            retry_count=data.get("retry_count", 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
    
    def get_stage_description(self) -> str:
        """获取失败阶段的中文描述"""
        stage_map = {
            self.STAGE_FOLDER_NOT_FOUND: "目录映射未找到",
            self.STAGE_LIST_DATASETS: "获取知识库列表失败",
            self.STAGE_CREATE_DATASET: "创建知识库失败",
            self.STAGE_CHECK_FILE: "重名检测失败",
            self.STAGE_UPLOAD_FILE: "文件上传失败",
            self.STAGE_CREATE_DOCUMENT: "创建文档失败",
            self.STAGE_CREATE_TASK: "创建任务失败",
            self.STAGE_UNKNOWN: "未知错误",
        }
        return stage_map.get(self.error_stage, self.error_stage)


class FailedRecordsManager:
    """
    失败记录管理器
    
    负责失败记录的存储、加载、查询和统计。
    使用 JSON 文件持久化存储，按日期分文件。
    
    Attributes:
        records_dir (str): 记录存储目录
        records (dict): 失败记录字典，key 为文件路径
    """
    
    def __init__(self, records_dir: str = None):
        """
        初始化管理器
        
        Args:
            records_dir (str): 记录存储目录，默认为项目根目录/failed_records/
        """
        if records_dir is None:
            # 默认存储在项目根目录的 failed_records 目录下
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            records_dir = os.path.join(project_root, "failed_records")
        
        self.records_dir = records_dir
        self.records: dict[str, FailedRecord] = {}
        self._lock = Lock()
        
        # 确保目录存在
        if not os.path.exists(self.records_dir):
            os.makedirs(self.records_dir)
        
        # 加载今天的记录
        self._load_today_records()
    
    def _get_today_file(self) -> str:
        """获取今天的记录文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.records_dir, f"failed_{today}.json")
    
    def _load_today_records(self):
        """加载今天的失败记录"""
        file_path = self._get_today_file()
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for record_data in data.get("records", []):
                        record = FailedRecord.from_dict(record_data)
                        self.records[record.file_path] = record
                log.info(f"加载失败记录：{len(self.records)} 条")
            except Exception as e:
                log.error(f"加载失败记录出错：{e}")
    
    def _save_records(self):
        """保存记录到文件"""
        file_path = self._get_today_file()
        try:
            data = {
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_count": len(self.records),
                "records": [r.to_dict() for r in self.records.values()],
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"保存失败记录出错：{e}")
    
    def add_record(
        self,
        file_path: str,
        file_name: str,
        file_classify: str,
        error_stage: str,
        error_message: str,
        error_code: int = 0,
        dataset_name: str = "",
        folder_id: str = "",
        dataset_id: str = "",
    ) -> FailedRecord:
        """
        添加失败记录
        
        如果该文件已存在记录，则更新现有记录的重试次数和错误信息。
        
        Args:
            file_path (str): 文件完整路径
            file_name (str): 文件名
            file_classify (str): 文件分类目录
            error_stage (str): 失败阶段（使用 FailedRecord.STAGE_* 常量）
            error_message (str): 错误信息
            error_code (int): 错误状态码
            dataset_name (str): 知识库名称
            folder_id (str): 目录ID
            dataset_id (str): 知识库ID
            
        Returns:
            FailedRecord: 创建或更新的失败记录
        """
        with self._lock:
            if file_path in self.records:
                # 更新现有记录
                record = self.records[file_path]
                record.error_stage = error_stage
                record.error_message = error_message
                record.error_code = error_code
                record.retry_count += 1
                record.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if dataset_name:
                    record.dataset_name = dataset_name
                if folder_id:
                    record.folder_id = folder_id
                if dataset_id:
                    record.dataset_id = dataset_id
            else:
                # 创建新记录
                record = FailedRecord(
                    file_path=file_path,
                    file_name=file_name,
                    file_classify=file_classify,
                    dataset_name=dataset_name,
                    folder_id=folder_id,
                    dataset_id=dataset_id,
                    error_stage=error_stage,
                    error_message=error_message,
                    error_code=error_code,
                )
                self.records[file_path] = record
            
            # 保存到文件
            self._save_records()
            
            return record
    
    def remove_record(self, file_path: str) -> bool:
        """
        移除失败记录（成功后调用）
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            if file_path in self.records:
                del self.records[file_path]
                self._save_records()
                return True
            return False
    
    def get_record(self, file_path: str) -> Optional[FailedRecord]:
        """获取指定文件的失败记录"""
        return self.records.get(file_path)
    
    def get_all_records(self) -> list[FailedRecord]:
        """获取所有失败记录"""
        return list(self.records.values())
    
    def get_records_by_stage(self, error_stage: str) -> list[FailedRecord]:
        """按失败阶段筛选记录"""
        return [r for r in self.records.values() if r.error_stage == error_stage]
    
    def get_retryable_records(self) -> list[FailedRecord]:
        """
        获取可重试的记录
        
        排除目录映射未找到的记录（需要先配置目录映射）
        """
        return [
            r for r in self.records.values() 
            if r.error_stage != FailedRecord.STAGE_FOLDER_NOT_FOUND
        ]
    
    def get_statistics(self) -> dict:
        """
        获取统计信息
        
        Returns:
            dict: 包含各阶段失败数量的统计
        """
        stats = {
            "total": len(self.records),
            "by_stage": {},
            "retryable": 0,
        }
        
        for record in self.records.values():
            stage = record.error_stage
            stats["by_stage"][stage] = stats["by_stage"].get(stage, 0) + 1
            if stage != FailedRecord.STAGE_FOLDER_NOT_FOUND:
                stats["retryable"] += 1
        
        return stats
    
    def clear_records(self):
        """清空所有记录"""
        with self._lock:
            self.records.clear()
            self._save_records()
    
    def load_all_records(self) -> list[FailedRecord]:
        """
        加载所有日期的失败记录
        
        Returns:
            list[FailedRecord]: 所有失败记录列表
        """
        all_records = []
        try:
            for filename in os.listdir(self.records_dir):
                if filename.startswith("failed_") and filename.endswith(".json"):
                    file_path = os.path.join(self.records_dir, filename)
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for record_data in data.get("records", []):
                            all_records.append(FailedRecord.from_dict(record_data))
        except Exception as e:
            log.error(f"加载所有失败记录出错：{e}")
        
        return all_records
    
    def print_summary(self):
        """打印失败记录摘要"""
        stats = self.get_statistics()
        print(f"\n{'='*60}")
        print(f"失败记录统计")
        print(f"{'='*60}")
        print(f"总失败数：{stats['total']}")
        print(f"可重试数：{stats['retryable']}")
        print(f"\n按阶段统计：")
        for stage, count in stats["by_stage"].items():
            # 获取阶段描述
            stage_desc = {
                FailedRecord.STAGE_FOLDER_NOT_FOUND: "目录映射未找到",
                FailedRecord.STAGE_LIST_DATASETS: "获取知识库列表失败",
                FailedRecord.STAGE_CREATE_DATASET: "创建知识库失败",
                FailedRecord.STAGE_CHECK_FILE: "重名检测失败",
                FailedRecord.STAGE_UPLOAD_FILE: "文件上传失败",
                FailedRecord.STAGE_CREATE_DOCUMENT: "创建文档失败",
                FailedRecord.STAGE_CREATE_TASK: "创建任务失败",
                FailedRecord.STAGE_UNKNOWN: "未知错误",
            }.get(stage, stage)
            print(f"  - {stage_desc}: {count}")
        print(f"{'='*60}\n")
