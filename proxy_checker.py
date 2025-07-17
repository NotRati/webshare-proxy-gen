import asyncio
import json
import aiohttp
import aiofiles

async def check_proxies_from_file(
    input_file: str,
    output_file: str = None,
    test_url: str = "https://api.ipify.org",
    timeout_seconds: int = 10,
    max_proxies: int | None = None  # New parameter to limit proxies checked
) -> list:
    async def check_proxy(session: aiohttp.ClientSession, proxy_info: dict) -> dict | None:
        
        proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['proxy_address']}:{proxy_info['port']}"

        try:
            async with session.get(test_url, proxy=proxy_url, timeout=timeout_seconds) as response:
                if response.status == 200:
                    print(f"✅ Success: {proxy_info['proxy_address']}")
                    return proxy_info
                else:
                    print(f"❌ Bad status {response.status} on {proxy_info['proxy_address']}")
        except Exception as e:
            print(f"❌ Error on {proxy_info.get('proxy_address')} - {type(e).__name__}")
        return None

    async with aiofiles.open(input_file, 'r') as f:
        content = await f.read()
        if content == "":
            return []
        proxies_data = json.loads(content)

    # Flatten proxies list
    all_proxies = proxies_data

    if max_proxies is not None:
        all_proxies = all_proxies[:max_proxies]

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [check_proxy(session, proxy) for proxy in all_proxies]
        print(f"🔍 Checking {len(tasks)} proxies...")

        working_proxies = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                working_proxies.append(result)

    print(f"\n✅ Found {len(working_proxies)} working proxies.")

    if not output_file is None:
        async with aiofiles.open(output_file, 'w') as f:
            await f.write(json.dumps(working_proxies, indent=4))

        print(f"💾 Saved working proxies to {output_file}")
    return working_proxies

# Example usage
if __name__ == "__main__":
    print(asyncio.run(check_proxies_from_file("proxies.json", "1proxies.json", timeout_seconds=5, max_proxies=None)))
