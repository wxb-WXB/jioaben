# -*- coding: utf-8 -*-
"""
解析 aa.md 中的目录结构，按三级目录区分
根据 Windows tree 命令的输出格式解析
"""

def count_level(line):
    """
    计算目录层级
    每个层级前面有 "│  " 或 "   " (3个字符)
    """
    level = 0
    pos = 0
    
    while pos < len(line):
        chunk = line[pos:pos+3]
        if chunk in ['│  ', '   ']:
            level += 1
            pos += 3
        elif line[pos:pos+2] in ['├─', '└─']:
            break
        else:
            break
    
    return level


def extract_name(line):
    """
    提取目录名称
    """
    for marker in ['├─', '└─']:
        if marker in line:
            return line.split(marker)[-1].strip()
    return None


def parse_directory_tree(file_path):
    """
    解析目录树结构，只提取前三级目录
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 存储结果 - 结构: {一级: {二级: [三级列表]}}
    result = {}
    
    # 当前一级、二级目录
    current_level1 = None
    current_level2 = None
    
    for line in lines:
        line = line.rstrip('\n')
        if not line.strip():
            continue
        
        # 跳过头部信息
        if line.startswith('卷') or line.startswith('E:.'):
            continue
        
        # 提取目录名
        dir_name = extract_name(line)
        if not dir_name:
            continue
        
        # 计算层级 (0-based)
        level = count_level(line)
        
        # 根据层级处理
        if level == 0:
            # 一级目录
            current_level1 = dir_name
            current_level2 = None
            if current_level1 not in result:
                result[current_level1] = {}
        
        elif level == 1 and current_level1:
            # 二级目录
            current_level2 = dir_name
            if current_level2 not in result[current_level1]:
                result[current_level1][current_level2] = []
        
        elif level == 2 and current_level1 and current_level2:
            # 三级目录
            result[current_level1][current_level2].append(dir_name)
        
        # 更深层级的目录不处理
    
    return result


def export_to_markdown(result, output_file):
    """
    导出为 Markdown 格式
    """
    output_lines = []
    output_lines.append("# 目录结构（三级目录）\n")
    output_lines.append(f"**统计信息**")
    
    total_level1 = len(result)
    total_level2 = sum(len(v) for v in result.values())
    total_level3 = sum(len(v3) for v2 in result.values() for v3 in v2.values())
    
    output_lines.append(f"- 一级目录数量: {total_level1}")
    output_lines.append(f"- 二级目录数量: {total_level2}")
    output_lines.append(f"- 三级目录数量: {total_level3}")
    output_lines.append("")
    output_lines.append("---\n")
    
    for level1, level2_dict in result.items():
        output_lines.append(f"## {level1}\n")
        
        for level2, level3_list in level2_dict.items():
            output_lines.append(f"### {level2}\n")
            
            if level3_list:
                for level3 in level3_list:
                    output_lines.append(f"- {level3}")
                output_lines.append("")
            else:
                output_lines.append("（无三级目录）\n")
    
    output_text = "\n".join(output_lines)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(output_text)
    
    print(f"Markdown 格式已保存到: {output_file}")
    return total_level1, total_level2, total_level3


def export_to_text(result, output_file):
    """
    导出为纯文本格式
    """
    output_lines = []
    output_lines.append("=" * 80)
    output_lines.append("目录结构（三级目录）")
    output_lines.append("=" * 80)
    output_lines.append("")
    
    for level1, level2_dict in result.items():
        output_lines.append(f"【一级目录】{level1}")
        output_lines.append("-" * 60)
        
        for level2, level3_list in level2_dict.items():
            output_lines.append(f"    【二级目录】{level2}")
            
            if level3_list:
                for level3 in level3_list:
                    output_lines.append(f"        【三级目录】{level3}")
            
            output_lines.append("")
        
        output_lines.append("")
    
    output_text = "\n".join(output_lines)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(output_text)
    
    print(f"文本格式已保存到: {output_file}")


if __name__ == "__main__":
    input_file = "aa.md"
    
    print("正在解析目录结构...")
    result = parse_directory_tree(input_file)
    
    # 保存为 Markdown 格式
    l1, l2, l3 = export_to_markdown(result, "目录结构_三级.md")
    
    # 保存为文本格式
    export_to_text(result, "目录结构_三级.txt")
    
    # 打印统计信息
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)
    print(f"一级目录数量: {l1}")
    print(f"二级目录数量: {l2}")
    print(f"三级目录数量: {l3}")
    
    # 打印一级目录列表
    print("\n" + "=" * 60)
    print("一级目录列表")
    print("=" * 60)
    for i, name in enumerate(result.keys(), 1):
        print(f"{i}. {name}")
