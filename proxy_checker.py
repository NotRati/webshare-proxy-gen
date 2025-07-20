import asyncio
import json
import aiohttp
import aiofiles
import logging
from datetime import datetime, timedelta, timezone

async def check_proxies_from_file(
    logger: logging.Logger,
    input_file: str,
    output_file: str = None,
    test_url: str = "https://api.ipify.org",
    timeout_seconds: int = 10,
    max_proxies: int | None = None
) -> list:
    now = datetime.now(timezone.utc)
    FIVE_MINUTES_AGO = now - timedelta(minutes=5)

    async def check_proxy(session: aiohttp.ClientSession, proxy_info: dict) -> dict | None:
        proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['proxy_address']}:{proxy_info['port']}"
        try:
            async with session.get(test_url, proxy=proxy_url, timeout=timeout_seconds) as response:
                if response.status == 200:
                    proxy_info['last_checked'] = datetime.now(timezone.utc).isoformat()
                    logger.info(f"Success: {proxy_info['proxy_address']}")
                    return proxy_info
                else:
                    logger.warning(f"Bad status {response.status} on {proxy_info['proxy_address']}")
        except Exception as e:
            logger.warning(f"Error on {proxy_info.get('proxy_address')} - {type(e).__name__}")
        return None

    async with aiofiles.open(input_file, 'r') as f:
        content = await f.read()
        if content.strip() == "":
            return []
        proxies_data = json.loads(content)

    def should_check(proxy):
        last_checked = proxy.get("last_checked")
        if not last_checked:
            return True
        try:
            return datetime.fromisoformat(last_checked) < FIVE_MINUTES_AGO
        except Exception:
            return True

    proxies_to_check = [p for p in proxies_data if should_check(p)]
    skipped_proxies = [p for p in proxies_data if not should_check(p)]

    if max_proxies is not None:
        proxies_to_check = proxies_to_check[:max_proxies]

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [check_proxy(session, proxy) for proxy in proxies_to_check]
        logger.info(f"Checking {len(tasks)} proxies (Skipped: {len(skipped_proxies)})...")

        working_proxies = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                working_proxies.append(result)

    final_proxies = skipped_proxies + working_proxies

    logger.info(f"Found {len(working_proxies)} working proxies (Total retained: {len(final_proxies)})")

    if output_file:
        async with aiofiles.open(output_file, 'w') as f:
            await f.write(json.dumps(final_proxies, indent=4))
        logger.info(f"Saved {len(final_proxies)} working proxies to {output_file}")

    return final_proxies

# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("proxy_checker")
    asyncio.run(check_proxies_from_file(
        logger,
        input_file="proxies.json",
        output_file="proxies.json",
        timeout_seconds=5
    ))
