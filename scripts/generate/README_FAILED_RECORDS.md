# 失败记录管理说明

## 概述

`retry_failed_tasks.py` 脚本具有完整的失败记录功能，可以自动记录失败的文档，并在下次运行时跳过这些文档，避免重复处理已知的失败任务。

## 失败记录配置

在脚本中有三个主要的配置参数（第 104-109 行）：

```python
ENABLE_FAILED_RECORD = True          # 是否启用失败记录功能
SKIP_RECORDED_FAILED = True          # 是否跳过已记录的失败文档
PROCESS_ONLY_FAILED_RECORD = False   # 是否只处理失败记录
```

### 配置说明

1. **ENABLE_FAILED_RECORD**
   - `True`: 启用失败记录功能（推荐）
   - `False`: 禁用失败记录功能

2. **SKIP_RECORDED_FAILED**
   - `True`: 跳过已记录的失败文档（正常模式，推荐）
   - `False`: 不跳过失败记录，会重新尝试所有失败的文档

3. **PROCESS_ONLY_FAILED_RECORD**
   - `True`: 只处理失败记录中的文档（专门重试模式）
   - `False`: 正常处理所有需要重试的文档（推荐）

## 使用场景

### 场景1：正常运行（推荐配置）

```python
ENABLE_FAILED_RECORD = True
SKIP_RECORDED_FAILED = True
PROCESS_ONLY_FAILED_RECORD = False
```

**行为**：
- 自动记录失败的文档
- 跳过已经失败过的文档
- 处理所有新发现的失败/无任务文档

**适用于**：日常批量处理，避免浪费时间在总是失败的文档上

### 场景2：重新尝试失败记录

```python
ENABLE_FAILED_RECORD = True
SKIP_RECORDED_FAILED = False
PROCESS_ONLY_FAILED_RECORD = False
```

**行为**：
- 记录新的失败文档
- 不跳过已记录的失败文档，会重新尝试

**适用于**：修复了某些问题后，想重新尝试之前失败的文档

### 场景3：专门处理失败记录

```python
ENABLE_FAILED_RECORD = True
SKIP_RECORDED_FAILED = False
PROCESS_ONLY_FAILED_RECORD = True
```

**行为**：
- 只处理失败记录中的文档
- 忽略其他所有文档

**适用于**：专门针对失败记录进行批量重试

### 场景4：清空失败记录后重新开始

**步骤**：
1. 删除或重命名失败记录文件：`data/failed_records/retry_failed_tasks.json`
2. 使用场景1的配置运行脚本

**适用于**：已经解决了大部分失败原因，想重新开始记录

## 失败记录文件

### 文件位置

```
data/failed_records/retry_failed_tasks.json
```

### 文件格式

```json
{
  "updated_at": "2026-02-19 10:30:00",
  "total_failed": 150,
  "failed_docs": {
    "28725475657302016": {
      "name": "文档名称.pdf",
      "path": "完整路径/文档名称.pdf",
      "type": "pdf",
      "error": "具体错误信息",
      "failed_at": "2026-02-19 10:25:30"
    }
  }
}
```

## 控制台输出说明

### 启动时

```
============================================================
已加载 150 条失败记录
最后更新: 2026-02-19 10:00:00
失败记录文件: data/failed_records/retry_failed_tasks.json
⚠️  这些文档将被跳过，不会重新处理
============================================================
```

### 扫描时

```
[知识库 1/50] 扫描: 某个知识库
  发现 10 个待处理文档（跳过已失败 5 个）
```

### 失败时（新增的详细输出）

```
✗ 失败: 文档名称.pdf - 文件解析错误：不支持的PDF版本
```

### 结束时

```
⚠️  本次运行新增 8 条失败记录

============================================================
✓ 已保存 158 条失败记录
文件位置: data/failed_records/retry_failed_tasks.json
下次启动时将自动跳过这些失败的文档
============================================================
```

## 失败原因统计

在配置信息中会显示失败原因的分布统计：

```
  失败记录: 启用
    - 跳过已失败: 是
    - 只处理失败记录: 否
    - 已记录失败数: 150
    - 失败原因分布:
      · 文件解析错误：不支持的PDF版本: 45 个
      · 超时(3600秒): 30 个
      · 任务执行失败: 25 个
      · 网络错误: 20 个
      · 内存不足: 15 个
      · ... 还有 10 种其他错误
```

## 手动管理失败记录

### 查看失败记录

直接打开 JSON 文件查看：
```bash
cat data/failed_records/retry_failed_tasks.json
```

### 移除特定失败记录

1. 打开 `data/failed_records/retry_failed_tasks.json`
2. 在 `failed_docs` 中找到要移除的文档ID
3. 删除对应的条目
4. 更新 `total_failed` 数量
5. 保存文件

### 清空所有失败记录

```bash
# 方法1: 删除文件
rm data/failed_records/retry_failed_tasks.json

# 方法2: 重命名备份
mv data/failed_records/retry_failed_tasks.json \
   data/failed_records/retry_failed_tasks.json.backup
```

## 最佳实践

1. **日常运行**
   - 使用推荐配置（场景1）
   - 定期检查失败记录文件
   - 分析失败原因，解决根本问题

2. **问题修复后**
   - 清空或备份旧的失败记录
   - 使用场景2配置重新尝试
   - 或使用场景3只重试失败记录

3. **失败记录过多时**
   - 导出失败记录进行分析
   - 按失败原因分类处理
   - 解决常见问题后清空记录重新开始

4. **监控建议**
   - 关注新增失败记录的数量
   - 如果持续增加，需要排查原因
   - 定期清理已解决的失败记录

## 常见问题

### Q: 失败记录会一直累积吗？

A: 是的，除非手动清理。建议定期检查和清理已解决的失败记录。

### Q: 如何知道哪些文档被跳过了？

A: 查看控制台输出，会显示"跳过已失败 X 个"的提示。

### Q: 失败记录文件丢失了怎么办？

A: 脚本会自动创建新的失败记录文件，不会影响正常运行。

### Q: 可以导出失败记录列表吗？

A: 可以，失败记录文件是标准的 JSON 格式，可以用任何文本编辑器或 JSON 工具查看和处理。

### Q: 如何批量重试某些特定的失败文档？

A: 
1. 编辑失败记录文件，只保留想重试的文档
2. 使用场景3配置（PROCESS_ONLY_FAILED_RECORD = True）
3. 运行脚本

## 示例：失败分析脚本

如果需要分析失败记录，可以使用以下 Python 脚本：

```python
import json
from collections import Counter

with open('data/failed_records/retry_failed_tasks.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

failed_docs = data.get('failed_docs', {})

# 统计失败原因
errors = [doc['error'] for doc in failed_docs.values()]
error_counts = Counter(errors)

print(f"总失败数: {len(failed_docs)}")
print("\n失败原因统计:")
for error, count in error_counts.most_common(10):
    print(f"  {error}: {count} 个")

# 统计文件类型
types = [doc['type'] for doc in failed_docs.values()]
type_counts = Counter(types)

print("\n文件类型统计:")
for ftype, count in type_counts.most_common():
    print(f"  {ftype}: {count} 个")
```
