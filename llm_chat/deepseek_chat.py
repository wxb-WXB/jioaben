#!/Users/wenxuebin/Documents/project/jioaben/.venv/bin/python
"""
DeepSeek Chat 调用脚本
======================
调用内网 deepseekv3-0324 模型（OpenAI 兼容 API）进行对话

用法：
    ./deepseek_chat.py                  # 发送默认问题
    ./deepseek_chat.py "你想问的问题"    # 自定义问题
"""
import json
import sys
import time

import requests

# API 配置
API_BASE_URL = "http://10.4.0.2:9080/v1"
API_KEY = "6774be4b-40a0-49bb-8747-468872d1f771"
DEFAULT_MODEL = "deepseekv3-0324"

DEFAULT_INPUT = "你好，请自我介绍"


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
    print(f"地址: {API_BASE_URL}")
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
