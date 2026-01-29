"""
核心模块
=======

包含API客户端、数据库模型、记录管理和工具函数。
"""
from .api import LingyanDataset, LingyanFile
from .models import FolderMap, db
from .records import FailedRecord, FailedRecordsManager, SuccessRecord, SuccessRecordsManager
from .utils import (
    collect_files,
    get_file_relative_dir,
    list_files,
    is_pdf_file,
    pdf_has_images,
    pdf_get_image_count,
    file_type_from_extension,
)

__all__ = [
    # API客户端
    "LingyanDataset",
    "LingyanFile",
    # 数据库模型
    "FolderMap",
    "db",
    # 记录管理
    "FailedRecord",
    "FailedRecordsManager",
    "SuccessRecord",
    "SuccessRecordsManager",
    # 工具函数
    "collect_files",
    "get_file_relative_dir",
    "list_files",
    "is_pdf_file",
    "pdf_has_images",
    "pdf_get_image_count",
    "file_type_from_extension",
]
