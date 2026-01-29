# 灵眼AI知识库自动化工具

> 环北工程知识库自动化管理脚本集合

本项目提供了一套完整的工具，用于自动化管理灵眼AI知识库平台的文档上传、向量化处理、内容生成和统计查询等操作。

## 📁 项目结构

```
jioaben/
├── src/                          # 核心源代码
│   ├── config.py                 # 全局配置文件 ⭐
│   └── core/                     # 核心模块
│       ├── api.py                # API客户端（LingyanFile, LingyanDataset）
│       ├── models.py             # 数据库模型（FolderMap）
│       ├── records.py            # 记录管理（成功/失败记录）
│       └── utils.py              # 工具函数
│
├── scripts/                      # 可执行脚本
│   ├── upload/                   # 📤 文件上传
│   │   └── upload_to_folder.py   # 指定目录上传
│   │
│   ├── generate/                 # ✨ 内容生成
│   │   ├── doc_summary.py        # 文档摘要生成
│   │   ├── segment_index.py      # 段落索引生成
│   │   └── generate_faq.py       # FAQ问答生成
│   │
│   ├── query/                    # 🔍 查询统计
│   │   ├── vector_status.py      # 向量化状态查询
│   │   └── stop_task.py          # 停止任务
│   │
│   ├── delete/                   # 🗑️ 删除操作
│   │   └── delete_files.py       # 删除文件
│   │
│   └── local/                    # 📊 本地统计
│       └── scan_files.py         # 本地目录扫描
│
├── data/                         # 数据目录（自动创建）
│   ├── folder.db                 # 目录映射数据库
│   ├── failed_records/           # 失败记录
│   └── success_records/          # 成功记录
│
├── logs/                         # 日志目录（自动创建）
│
├── requirements.txt              # Python依赖
└── README.md                     # 本文档
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置参数

编辑 `src/config.py` 文件，修改以下关键配置：

```python
# API配置
API_HOST = "http://10.4.49.66:18080"
API_KEY = "your-api-key"

# 工作空间配置
WORKSPACES = [
    {"id": "xxx-xxx-xxx", "name": "你的知识库"},
]
```

### 3. 运行脚本

```bash
# 上传文件到指定目录
python scripts/upload/upload_to_folder.py

# 查询向量化状态
python scripts/query/vector_status.py

# 生成文档摘要
python scripts/generate/doc_summary.py
```

## 📖 脚本使用说明

### 📤 文件上传 (`scripts/upload/`)

#### `upload_to_folder.py` - 指定目录上传

将本地文件夹中的文件批量上传到指定的远程知识库目录。

**配置方式：**
编辑脚本中的 `UPLOAD_TASKS` 列表：

```python
UPLOAD_TASKS = [
    {
        "local_folder": r'E:\项目档案\施工文件',    # 本地文件夹路径
        "folder_id": "xxx-xxx-xxx",                # 远程目录ID
        "dataset_name": "施工文件知识库",           # 知识库名称
    },
]
```

**运行：**
```bash
python scripts/upload/upload_to_folder.py
```

**功能特点：**
- ✅ 支持多文件夹批量上传
- ✅ 自动跳过已上传的文件
- ✅ 实时显示上传进度和预计完成时间
- ✅ 失败自动重试（支持503等服务器错误）
- ✅ 支持断点续传

---

### ✨ 内容生成 (`scripts/generate/`)

#### `doc_summary.py` - 文档摘要生成

为向量化成功的文档调用LLM生成摘要。

**运行：**
```bash
python scripts/generate/doc_summary.py
```

**功能特点：**
- ✅ 自动跳过超过模型上下文窗口的文档
- ✅ 显示文件夹路径方便验证

#### `segment_index.py` - 段落索引生成

为文档段落生成标题、摘要、问题索引。

**运行：**
```bash
python scripts/generate/segment_index.py
```

#### `generate_faq.py` - FAQ问答生成

为向量化成功的文档生成FAQ问答任务。

**配置方式：**
编辑脚本顶部的配置区域：

```python
CONCURRENT_TASKS = 5      # 同时运行的任务数量
CHECK_INTERVAL = 5        # 检查任务状态的间隔（秒）
MAX_WAIT_TIME = 2400      # 单个任务最大等待时间（秒）
```

**运行：**
```bash
python scripts/generate/generate_faq.py
```

---

### 🔍 查询统计 (`scripts/query/`)

#### `vector_status.py` - 向量化状态查询

查询所有知识库中文档的向量化状态统计。

**运行：**
```bash
python scripts/query/vector_status.py
```

**输出示例：**
```
======================================================================
向量化状态统计
======================================================================
[环北知识库] 获取到 15 个知识库

【施工文件知识库】
  文件总数: 2781
  向量成功: 2500 (89.9%)
  正在向量: 100
  向量失败: 50
  未开始:   131
======================================================================
```

**功能特点：**
- ✅ 统计结果自动保存到日志文件
- ✅ 显示开始/结束时间和总耗时

#### `stop_task.py` - 停止任务

停止正在进行的向量化任务。

**运行：**
```bash
python scripts/query/stop_task.py
```

---

### 🗑️ 删除操作 (`scripts/delete/`)

#### `delete_files.py` - 删除文件

删除指定类型或条件的文件。

**配置方式：**
编辑脚本中的删除条件：

```python
# 删除file_size=0的文件
DELETE_ZERO_SIZE = True

# 删除指定类型的文件
DELETE_TYPES = ["png", "jpg", "zip"]
```

**运行：**
```bash
python scripts/delete/delete_files.py
```

---

### 📊 本地统计 (`scripts/local/`)

#### `scan_files.py` - 本地目录扫描

递归扫描本地目录，统计文件数量和类型分布。

**配置方式：**
编辑脚本中的 `SCAN_DIRS` 列表：

```python
SCAN_DIRS = [
    r"E:\环北部湾广东水资源配置工程",
    r"F:\办公室档案知识库资料",
]
```

**运行：**
```bash
python scripts/local/scan_files.py
```

**输出示例：**
```
======================================================================
本地目录文件统计 - 2026-01-29 15:30:00
======================================================================
扫描目录: 2 个
  - E:\环北部湾广东水资源配置工程
  - F:\办公室档案知识库资料

总体统计
======================================================================
  文件总数:   214214
  总大小:     156.78 GB

按文件分类统计
======================================================================
  分类           数量            大小
----------------------------------------------------------------------
  PDF         186010      120.45 GB
  文本         28204       12.33 GB
  ...
```

---

## ⚙️ 配置说明

### 全局配置 (`src/config.py`)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `API_HOST` | API服务器地址 | `http://10.4.49.66:18080` |
| `API_KEY` | API密钥 | - |
| `WORKSPACE_ID` | 默认工作空间ID | - |
| `MAX_WORKERS` | 并发上传线程数 | `5` |
| `MAX_CONCURRENT_TASKS` | 同时处理的任务数 | `2` |
| `REQUEST_INTERVAL` | 请求间隔（秒） | `0.5` |
| `MAX_UPLOAD_RETRIES` | 上传失败重试次数 | `3` |
| `SKIP_EXTENSIONS` | 跳过的文件扩展名 | 见配置文件 |

### LLM模型配置

```python
LLM_CONFIG = {
    "provider": "langgenius/openai_api_compatible/openai_api_compatible",
    "name": "deepseekv3-0324",
    "mode": "chat",
    "size": 32768,
    "completion_params": {
        "temperature": 0.2,
        "top_p": 0.75,
        "max_tokens": 8000,
    },
}
```

---

## 📝 核心模块说明

### `src/core/api.py` - API客户端

提供两个主要类：

**`LingyanFile`** - 文件服务
```python
from src.core import LingyanFile

file_service = LingyanFile(api_key="xxx")
status, data = file_service.upload_file("test.pdf", "dataset")
```

**`LingyanDataset`** - 知识库服务
```python
from src.core import LingyanDataset

dataset = LingyanDataset(api_key="xxx")

# 获取知识库列表
status, datasets = dataset.list_datasets(workspace_id="xxx")

# 获取文档列表
status, documents = dataset.list_documents(dataset_id="xxx")

# 创建处理任务
status, task = dataset.create_task(dataset_id, document_id)
```

### `src/core/models.py` - 数据库模型

**`FolderMap`** - 目录映射
```python
from src.core import FolderMap

# 根据folder_id查询本地路径
folder = FolderMap.get_or_none(FolderMap.id == folder_id)
if folder:
    print(folder.folderPath)
```

### `src/core/records.py` - 记录管理

**`SuccessRecordsManager`** - 成功记录管理
```python
from src.core import SuccessRecordsManager

manager = SuccessRecordsManager()

# 检查文件是否已上传
if manager.is_uploaded(file_path):
    print("已上传，跳过")

# 添加成功记录
manager.add_record(file_path, file_name, dataset_id, document_id)
```

**`FailedRecordsManager`** - 失败记录管理
```python
from src.core import FailedRecordsManager, FailedRecord

manager = FailedRecordsManager()

# 添加失败记录
manager.add_record(
    file_path=file_path,
    file_name=file_name,
    file_classify="施工文件",
    error_stage=FailedRecord.STAGE_UPLOAD_FILE,
    error_message="上传超时",
)

# 获取可重试的记录
retryable = manager.get_retryable_records()
```

---

## ❓ 常见问题

### Q: 上传时出现"拒绝连接"错误怎么办？

A: 这通常是服务器压力过大导致的。脚本已内置重试机制，会自动等待后重试。如果频繁出现，可以：
1. 减少 `MAX_WORKERS` 的值（如改为3）
2. 增加 `REQUEST_INTERVAL` 的值（如改为1）

### Q: 上传时出现503错误怎么办？

A: 503表示服务器过载。脚本会自动重试最多3次。如果持续出现，建议：
1. 等待一段时间后再运行
2. 减少并发数

### Q: 如何查看上传进度？

A: 运行上传脚本后，会实时显示：
- 进度条
- 已上传/总数
- 成功/跳过/失败数量
- 预计剩余时间
- 预计完成时间

### Q: 如何断点续传？

A: 脚本会自动记录已成功上传的文件。再次运行时会自动跳过这些文件。记录保存在 `data/success_records/success_records.json`。

### Q: 如何清除上传记录重新上传？

A: 删除 `data/success_records/success_records.json` 文件即可。

---

## 📋 更新日志

### 2026-01-29
- 🎉 项目工程化重构
- ✨ 统一配置管理
- 📝 完善使用文档
- 🐛 修复上传超时和503错误处理

---

## 📄 License

MIT License
