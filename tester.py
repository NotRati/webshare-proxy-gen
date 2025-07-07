import json
import requests

json_file = "proxies.json"

with open("proxies.json", 'r') as f:
    json1 = json.loads(f.read())


proxy_data = json1[-1]['results'][-1]


proxy_url = f"http://{proxy_data['username']}:{proxy_data['password']}@{proxy_data['proxy_address']}:{proxy_data['port']}"

# Create the proxies dictionary for requests
proxies = {
    "http": proxy_url,
    "https": proxy_url,
}

# Example request using the proxy
try:
    response = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=10)
    print("Status:", response.status_code)
    print("Response:", response.json())
except requests.exceptions.RequestException as e:
    print("Proxy request failed:", e)