# 环北自动化脚本工程

灵燕AI知识库自动化管理脚本集合

---

## 📁 目录结构

```
jioaben/
├── 📂 核心模块
│   ├── LingyanAi.py          # 灵燕AI API封装（核心）
│   ├── LingyanEmptyAi.py     # 灵燕AI API模拟版（用于本地测试）
│   ├── models.py             # 数据库模型（FolderMap等）
│   └── utils.py              # 工具函数（文件操作、PDF检测等）
│
├── 📂 文件上传类
│   ├── autoUploads.py        # 批量上传文件到知识库（自动版）
│   ├── autoUploadsApp.py     # 批量上传文件到知识库（交互版，需手动输入）
│   └── getFolderIdMap.py     # 获取目录ID映射，写入数据库
│
├── 📂 任务管理类
│   ├── autoRestartTask.py    # 批量重启所有文档的向量化任务
│   ├── retry_failed_docs.py  # 重试向量化失败的文档
│   └── generate_faq_task.py  # 启动FAQ问答生成任务
│
├── 📂 内容生成类
│   ├── generate_doc_summary.py    # 生成文档摘要（整篇文章）
│   └── generate_segment_index.py  # 生成分段索引（标题、摘要、问题）
│
├── 📂 查询统计类
│   ├── query_vector_success.py    # 查询向量化成功/失败/进行中的文档
│   ├── list_all_datasets.py       # 列出所有知识库
│   └── 统计.py                    # 统计知识库文件数量
│
├── 📂 批量操作类
│   ├── delete_files.py            # 批量删除指定类型文件（PNG、ZIP等）
│   ├── 批量修改知识库配置为dpsk.py # 批量修改知识库配置（使用deepseek模型）
│   └── 批量下载.py                # 批量下载文件（未完成）
│
├── 📂 调试/测试类（可删除）
│   ├── 1.py                       # 测试文件下载
│   ├── 2.py                       # 测试文件上传流程
│   ├── demo.py                    # 线程池示例
│   ├── debug_docs.py              # 调试：查看文档数据结构
│   ├── debug_doc_summary.py       # 调试：查看文档摘要字段
│   ├── test_flyAi.py              # 测试灵燕AI接口
│   ├── test_single_summary.py     # 测试单个文档摘要生成
│   ├── test_segment_index.py      # 测试分段索引生成
│   └── test_generate_save.py      # 测试生成并保存摘要
│
├── 📂 数据文件
│   ├── folder.db                  # SQLite数据库（目录ID映射）
│   ├── all_datasets_list.txt      # 知识库列表缓存
│   └── 目录结构_三级_树形.txt      # 目录结构说明
│
└── 📂 其他
    ├── autoUploadsApp.spec        # PyInstaller打包配置
    └── logs/                      # 日志文件目录
```

---

## 🔧 核心模块说明

### `LingyanAi.py` - 灵燕AI API封装
提供与灵燕AI平台交互的所有API方法：
- `LingyanAi` - AI对话
- `LingyanFile` - 文件上传
- `LingyanDataset` - 知识库管理（创建、列表、文档管理、任务管理等）

### `models.py` - 数据库模型
- `FolderMap` - 目录ID与目录路径的映射关系

### `utils.py` - 工具函数
- `list_files()` - 列出目录下所有文件
- `is_pdf_file()` - 判断是否为PDF文件
- `pdf_has_images()` - 检测PDF是否包含图片

---

## 📋 常用脚本说明

### 1. 文件上传

#### `autoUploads.py` - 批量上传文件
```bash
python autoUploads.py
```
- 扫描指定目录下的所有文件
- 自动创建知识库（如不存在）
- 上传文件并创建向量化任务
- 支持多线程并发（12线程）

#### `getFolderIdMap.py` - 获取目录映射
```bash
python getFolderIdMap.py
```
- 从灵燕平台获取目录树
- 将目录ID和路径映射写入 `folder.db`
- **注意：上传前需要先运行此脚本**

---

### 2. 任务管理

#### `retry_failed_docs.py` - 重试失败文档
```bash
python retry_failed_docs.py
```
- 扫描所有知识库
- 找出向量化失败的文档
- 自动重新创建任务

#### `generate_faq_task.py` - 启动FAQ任务
```bash
python generate_faq_task.py
```
- 扫描向量化成功的文档
- 为每个文档启动FAQ问答生成任务
- 等待完成后再启动下一个

---

### 3. 内容生成

#### `generate_doc_summary.py` - 生成文档摘要
```bash
python generate_doc_summary.py
```
- 扫描向量化成功且无摘要的文档
- 调用AI生成文档摘要
- 保存摘要到文档

#### `generate_segment_index.py` - 生成分段索引
```bash
python generate_segment_index.py
```
- 扫描向量化成功的文档
- 为每个分段生成：标题、摘要、问题
- 失败的索引会重新生成

---

### 4. 查询统计

#### `query_vector_success.py` - 查询向量化状态
```bash
python query_vector_success.py
```
- 统计向量化成功/失败/进行中的文档数量
- 按知识库分类显示

#### `list_all_datasets.py` - 列出所有知识库
```bash
python list_all_datasets.py
```
- 列出工作空间下所有知识库

---

### 5. 批量操作

#### `delete_files.py` - 批量删除文件
```bash
python delete_files.py
```
- 删除知识库中指定类型的文件
- 默认删除：PNG、ZIP、JPG、MP4

#### `批量修改知识库配置为dpsk.py` - 修改知识库配置
```bash
python 批量修改知识库配置为dpsk.py
```
- 批量修改所有知识库的默认处理配置
- 使用 deepseek 模型

---

## ⚙️ 配置说明

大多数脚本头部都有配置区域，需要修改：

```python
# API 配置
API_KEY = "sk-xxx"           # 灵燕平台 API Key
AUTH_TOKEN = "eyJxxx"        # Bearer Token（用于Console API）

# 工作空间配置
WORKSPACE_ID = "xxx-xxx"     # 工作空间ID
WORKSPACE_NAME = "环北工程知识库"
```

---

## 🗑️ 可删除的文件

以下文件为调试/测试用途，可以安全删除：

```
1.py
2.py
demo.py
debug_docs.py
debug_doc_summary.py
test_flyAi.py
test_single_summary.py
test_segment_index.py
test_generate_save.py
LingyanEmptyAi.py
```

---

## 📝 日志

所有脚本的日志文件保存在 `logs/` 目录下，按日期命名：
- `autoUploads_2026-01-22.log`
- `retry_failed_docs_2026-01-22.log`
- 等等...

---

## 🚀 快速开始

1. **首次使用**：运行 `getFolderIdMap.py` 获取目录映射
2. **上传文件**：运行 `autoUploads.py`
3. **检查状态**：运行 `query_vector_success.py`
4. **重试失败**：运行 `retry_failed_docs.py`
5. **生成摘要**：运行 `generate_doc_summary.py`
6. **生成索引**：运行 `generate_segment_index.py`
7. **生成FAQ**：运行 `generate_faq_task.py`
