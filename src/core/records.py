"""
记录管理模块
===========

用于记录、存储和管理上传成功/失败的文件信息，支持：
- 记录失败文件及其详细错误信息
- 记录成功上传的文件（避免重复上传）
- 持久化存储到JSON文件
- 查询和统计记录
"""

import json
import os
from datetime import datetime
from threading import Lock
from typing import Optional
import logging

from ..config import FAILED_RECORDS_DIR, SUCCESS_RECORDS_DIR

log = logging.getLogger("Records")


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
    使用JSON文件持久化存储，按日期分文件。
    """
    
    def __init__(self, records_dir: str = None):
        """
        初始化管理器
        
        Args:
            records_dir (str): 记录存储目录，默认使用配置中的路径
        """
        self.records_dir = records_dir or FAILED_RECORDS_DIR
        self.records: dict[str, FailedRecord] = {}
        self._lock = Lock()
        
        os.makedirs(self.records_dir, exist_ok=True)
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
        """
        with self._lock:
            if file_path in self.records:
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
            
            self._save_records()
            return record
    
    def remove_record(self, file_path: str) -> bool:
        """移除失败记录（成功后调用）"""
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
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {"total": len(self.records), "by_stage": {}, "retryable": 0}
        for record in self.records.values():
            stage = record.error_stage
            stats["by_stage"][stage] = stats["by_stage"].get(stage, 0) + 1
            if stage != FailedRecord.STAGE_FOLDER_NOT_FOUND:
                stats["retryable"] += 1
        return stats
    
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


class SuccessRecord:
    """
    单条成功记录
    
    Attributes:
        file_path (str): 文件完整路径
        file_name (str): 文件名
        dataset_id (str): 知识库ID
        document_id (str): 文档ID
        uploaded_at (str): 上传时间
    """
    
    def __init__(
        self,
        file_path: str,
        file_name: str = "",
        dataset_id: str = "",
        document_id: str = "",
        uploaded_at: str = None,
    ):
        self.file_path = file_path
        self.file_name = file_name or os.path.basename(file_path)
        self.dataset_id = dataset_id
        self.document_id = document_id
        self.uploaded_at = uploaded_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "dataset_id": self.dataset_id,
            "document_id": self.document_id,
            "uploaded_at": self.uploaded_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SuccessRecord":
        """从字典创建实例"""
        return cls(
            file_path=data.get("file_path", ""),
            file_name=data.get("file_name", ""),
            dataset_id=data.get("dataset_id", ""),
            document_id=data.get("document_id", ""),
            uploaded_at=data.get("uploaded_at"),
        )


class SuccessRecordsManager:
    """
    成功记录管理器
    
    用于记录已成功上传的文件，避免重复上传。
    使用单个JSON文件持久化存储（不按日期分割，因为需要跨天查询）。
    """
    
    def __init__(self, records_dir: str = None):
        """
        初始化管理器
        
        Args:
            records_dir (str): 记录存储目录，默认使用配置中的路径
        """
        self.records_dir = records_dir or SUCCESS_RECORDS_DIR
        self.records: set[str] = set()
        self.records_detail: dict[str, SuccessRecord] = {}
        self._lock = Lock()
        self._save_counter = 0
        self._save_batch_size = 10
        
        os.makedirs(self.records_dir, exist_ok=True)
        self._load_records()
    
    def _get_records_file(self) -> str:
        """获取记录文件路径"""
        return os.path.join(self.records_dir, "success_records.json")
    
    def _load_records(self):
        """加载成功记录"""
        file_path = self._get_records_file()
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for record_data in data.get("records", []):
                        record = SuccessRecord.from_dict(record_data)
                        self.records.add(record.file_path)
                        self.records_detail[record.file_path] = record
                log.info(f"加载成功记录：{len(self.records)} 条")
            except Exception as e:
                log.error(f"加载成功记录出错：{e}")
    
    def _save_records(self, force: bool = False):
        """保存记录到文件"""
        if not force:
            self._save_counter += 1
            if self._save_counter < self._save_batch_size:
                return
            self._save_counter = 0
        
        file_path = self._get_records_file()
        try:
            data = {
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_count": len(self.records),
                "records": [r.to_dict() for r in self.records_detail.values()],
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"保存成功记录出错：{e}")
    
    def is_uploaded(self, file_path: str) -> bool:
        """检查文件是否已上传"""
        return file_path in self.records
    
    def add_record(
        self,
        file_path: str,
        file_name: str = "",
        dataset_id: str = "",
        document_id: str = "",
    ) -> SuccessRecord:
        """添加成功记录"""
        with self._lock:
            record = SuccessRecord(
                file_path=file_path,
                file_name=file_name,
                dataset_id=dataset_id,
                document_id=document_id,
            )
            self.records.add(file_path)
            self.records_detail[file_path] = record
            self._save_records()
            return record
    
    def remove_record(self, file_path: str) -> bool:
        """移除成功记录（如需重新上传时调用）"""
        with self._lock:
            if file_path in self.records:
                self.records.discard(file_path)
                del self.records_detail[file_path]
                self._save_records(force=True)
                return True
            return False
    
    def get_record(self, file_path: str) -> Optional[SuccessRecord]:
        """获取指定文件的成功记录"""
        return self.records_detail.get(file_path)
    
    def get_count(self) -> int:
        """获取成功记录总数"""
        return len(self.records)
    
    def flush(self):
        """强制保存所有记录到文件"""
        with self._lock:
            self._save_records(force=True)
