import time
from concurrent.futures import ThreadPoolExecutor

def square(n):
    time.sleep(1)
    return n * n

data = [1, 2, 3, 4, 5]

with ThreadPoolExecutor(max_workers=3) as executor:
    # 这里的 results 是一个生成器
    results = executor.map(square, data)

    # 遍历结果（会按照输入顺序 1, 2, 3... 打印）
    for result in results:
        print(f"结果: {result}")

print("所有任务完成")