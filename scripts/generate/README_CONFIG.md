# 配置文件统一管理说明

## 更新说明

优先文件夹配置已统一移至 `src/config.py`，不再需要在每个脚本中单独修改。

## 配置位置

所有优先文件夹配置都在 `src/config.py` 文件中：

```python
# =============================================================================
# 优先处理文件夹配置
# =============================================================================
# 优先处理的文件夹ID列表（用于retry_failed_tasks.py、segment_index.py、doc_summary.py）
# 如果设置了此值，会优先处理这些文件夹下的知识库，然后再处理其他文件夹
PRIORITY_FOLDER_IDS = [
    "10aab4f5-3191-4e12-a11c-2f3c4efb8204",  # 09正式稿设计图纸汇总至20260114
    "dd63fd77-cf46-46c2-9233-b55104c056b6",  # 安全管理
]

# 是否只处理优先文件夹（如果为True，只处理PRIORITY_FOLDER_IDS指定的文件夹）
ONLY_PRIORITY_FOLDER = True
```

## 使用的脚本

以下脚本会自动读取 `config.py` 中的配置：

1. **retry_failed_tasks.py** - 失败文档重试脚本
2. **segment_index.py** - 分段索引生成脚本
3. **doc_summary.py** - 文档摘要生成脚本

## 如何修改配置

### 1. 添加新的优先文件夹

只需在 `src/config.py` 中的 `PRIORITY_FOLDER_IDS` 列表添加新的文件夹ID：

```python
PRIORITY_FOLDER_IDS = [
    "10aab4f5-3191-4e12-a11c-2f3c4efb8204",  # 09正式稿设计图纸汇总至20260114
    "dd63fd77-cf46-46c2-9233-b55104c056b6",  # 安全管理
    "新的文件夹ID",  # 文件夹名称备注
]
```

### 2. 修改处理模式

如果想处理所有文件夹（不限制优先文件夹），修改：

```python
ONLY_PRIORITY_FOLDER = False
```

### 3. 禁用优先处理

如果不想使用优先处理功能，可以设置为空列表：

```python
PRIORITY_FOLDER_IDS = []
```

## 优点

✅ **统一管理**：所有配置在一个地方，不需要修改多个文件  
✅ **避免错误**：不会出现不同脚本配置不一致的情况  
✅ **易于维护**：添加或删除文件夹ID只需修改一次  
✅ **版本控制**：配置变更可以通过git清晰追踪  

## 注意事项

1. 修改 `config.py` 后，无需重启脚本，直接运行即可生效
2. 如果需要临时测试不同配置，建议复制一份 `config.py` 为 `config_local.py`
3. 确保文件夹ID格式正确（UUID格式）
4. 添加注释便于识别每个文件夹的用途

## 示例场景

### 场景1：只处理两个特定文件夹

```python
PRIORITY_FOLDER_IDS = [
    "10aab4f5-3191-4e12-a11c-2f3c4efb8204",
    "dd63fd77-cf46-46c2-9233-b55104c056b6",
]
ONLY_PRIORITY_FOLDER = True
```

### 场景2：优先处理特定文件夹，然后处理其他

```python
PRIORITY_FOLDER_IDS = [
    "10aab4f5-3191-4e12-a11c-2f3c4efb8204",
]
ONLY_PRIORITY_FOLDER = False
```

### 场景3：处理所有文件夹，无优先级

```python
PRIORITY_FOLDER_IDS = []
ONLY_PRIORITY_FOLDER = False
```

## 相关文件

- 配置文件：`src/config.py`
- 使用配置的脚本：
  - `scripts/generate/retry_failed_tasks.py`
  - `scripts/generate/segment_index.py`
  - `scripts/generate/doc_summary.py`
