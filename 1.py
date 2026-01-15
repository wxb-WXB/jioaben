import requests

url = "http://10.4.49.66:18080/api/v1/service/files/ce3b255d-acfe-4d2c-8cc1-2f1ff6a70d3d/download"

payload = ""
headers = {
    "accept": "application/json",
    "X-API-Key": "sk-mZaD8UalsAxMa9E87rn2zmptaeu0XW2wH7LkcKxS",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent": "PostmanRuntime-ApipostRuntime/1.1.0",
    "Connection": "keep-alive"
}

response = requests.request("GET", url, data=payload, headers=headers)


print(response)