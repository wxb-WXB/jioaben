#!/Users/wenxuebin/Documents/project/jioaben/.venv/bin/python
"""
LLM Chat 调用脚本
================
调用 flydiysz 提供的 OpenAI 兼容 API 进行对话

用法：
    ./chat.py                        # 发送默认文本
    ./chat.py "你想问的问题"          # 自定义问题
"""
import json
import sys
import time

import requests

from config import API_BASE_URL, API_KEY, DEFAULT_MODEL

# 默认发送的文本（知识库清洗整合结果）
DEFAULT_INPUT = """\
以下是一份知识库清洗整合后的文本，其中存在大量重复内容、格式混乱、表格拼接错误等问题，请帮我：
1. 去除重复段落，保留一份即可
2. 整理格式，使内容清晰易读
3. 保留所有有效信息，不要删减实质内容

原始文本如下：

---

来源：（附件3）湛江市高层次人才认定申请表(刘芃呈).doc

【基本信息】
姓名：刘芃呈 | 性别：男 | 出生年月：1981.11 | 民族：汉族
籍贯：山东胶州 | 户口所在地：辽宁沈阳 | 政治面貌：群众
学历：本科 | 学位：学士 | 职称：高级工程师
身份证号：370281198111130510
现家庭住址：辽宁省沈阳市和平区 | 手机：13929501092
现工作单位：广东粤海粤西供水有限公司 | 职务：工程部副总经理
在本单位工作年限：1年 | 合同聘用期限：3年

【主要工作简历】
2004年7月-2014年12月：大连理工大学水利水电工程专业毕业后，进入辽宁省水利厅大伙房水库输水工程建设局工作；
2015年1月-2020年2月：事转企，辽宁省水资源管理集团下属辽宁润中供水有限公司、投资公司筹备组，任工程部副部长、筹备组副组长；
2020年3月-2021年2月：岭南水务集团广佛区域工程总监，谭江河流治理工程大项目总；
2021年3月至今：广东粤海粤西供水有限公司工程部副总经理。

【个人业绩简介和遵纪守法情况】
从业以来，一直从事大型引调水工程建设管理，业务范围涉及TBM隧洞施工、钻爆法隧洞施工、PCCP管制造与安装、钢管制造与安装、配水厂站建安、市政顶管工程、水务与水环境治理等工程项目，国家级期刊发表论文5篇，获得厅级技术奖项2次，实用新型专利1项。
一直严守国家法律法规及所在单位规章制度，克己奉公，恪守职业道德，从事工程管理以来，一直对自己高标准、严要求，切实践行服务型业主，立足协调和服务，不对各参建单位吃拿卡要，受到各界单位、领导与同事的好评。
2020年进入民企后，也能自觉遵守中央八项规定，坚持清清白白做人，明明白白做事，不对各层官员行贿，减少非公务接触，坚持契约精神。
进入粤海粤西公司后，汲取粤海廉洁文化，打铁还须自身硬，不拿参建单位一针一线，不食施工单位一粥一饭。

【申请人承诺】
本人保证所填写内容和报送的相关资料真实有效。如有虚假或隐瞒事实，同意按有关规定处理。

---

来源：第6篇 电气附件.pdf
问题：廉江泵站计划何时投产？
内容：廉江泵站计划于2026年至2028年间投产。

---

来源：92.环北部湾广东水资源配置工程自建混凝土搅拌站管理工作指引（第二次修订）.pdf
内容：附录3-6为搅拌站投入使用验收申请表、验收通知、验收记录表、整改情况确认表等标准表格。

---

来源：98.环北部湾广东水资源配置工程质量责任制.pdf
内容：
4.5 各参建单位质量职责：工程参建单位包括建设单位、监理单位、勘察设计单位、施工单位、监测单位、质量检测单位、原材料/中间产品/设备供应商等，各单位质量职责见《环北部湾广东水资源配置工程质量管理规定》。
5. 考核要求：各参建单位考核标准按《环北部湾广东水资源配置工程参建单位考核管理规定》执行。
6. 附则：本制度由广东粤海粤西供水有限公司安全质量部负责解释，自发布之日起实施，原《环北部湾广东水资源配置工程质量责任制》同时废止。
"""


def chat(messages: list, model: str = DEFAULT_MODEL, **kwargs) -> dict:
    """
    调用 Chat Completions API

    Args:
        messages: 消息列表，格式 [{"role": "user", "content": "你好"}]
        model:    模型名称
        **kwargs: 其他参数，如 temperature、max_tokens 等

    Returns:
        包含 content、usage、elapsed 的字典
    """
    url = f"{API_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        **kwargs,
    }
    t0 = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    elapsed = time.time() - t0

    resp.raise_for_status()
    data = resp.json()

    return {
        "content": data["choices"][0]["message"]["content"],
        "usage": data.get("usage", {}),
        "elapsed": elapsed,
    }


def main():
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = DEFAULT_INPUT

    messages = [{"role": "user", "content": user_input}]

    print(f"模型: {DEFAULT_MODEL}")
    print("-" * 40)

    try:
        result = chat(messages)
        usage = result["usage"]
        reply = result["content"]
        print(f"回复:\n{reply}")
        print("-" * 40)
        print(f"耗时:         {result['elapsed']:.2f} 秒")
        print(f"输入字符数:   {len(user_input)}")
        print(f"输出字符数:   {len(reply)}")
        print(f"输入 tokens:  {usage.get('prompt_tokens', 'N/A')}")
        print(f"输出 tokens:  {usage.get('completion_tokens', 'N/A')}")
        print(f"总计 tokens:  {usage.get('total_tokens', 'N/A')}")
    except requests.exceptions.HTTPError as e:
        print(f"请求失败: {e}")
        if e.response is not None:
            try:
                err = e.response.json()
                print("错误详情:", json.dumps(err, ensure_ascii=False, indent=2))
            except Exception:
                print("响应内容:", e.response.text[:500])
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"网络错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
