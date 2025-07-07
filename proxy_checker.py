import asyncio
import json
import aiohttp
import aiofiles

# The URL to test the proxies against.
TEST_URL = "https://api.ipify.org"
# How long to wait for a proxy to respond before giving up.
TIMEOUT_SECONDS = 10

async def check_proxy(session, proxy_info):
    """
    Asynchronously checks a single proxy.

    Args:
        session (aiohttp.ClientSession): The client session to use for the request.
        proxy_info (dict): A dictionary containing the proxy's details.

    Returns:
        dict or None: The proxy_info dictionary if the proxy is working, otherwise None.
    """
    # Skips proxies that have a "reason" field, indicating a previous failure.
    if proxy_info.get("reason"):
        return None

    proxy_url = (
        f"http://{proxy_info['username']}:{proxy_info['password']}"
        f"@{proxy_info['proxy_address']}:{proxy_info['port']}"
    )

    try:
        # The 'async with' statement is the async equivalent of 'with'.
        # We perform an HTTP GET request through the specified proxy.
        # The 'await' keyword pauses this function until the request is complete.
        async with session.get(TEST_URL, proxy=proxy_url) as response:
            # We only consider the proxy working if we get a 200 OK status.
            if response.status == 200:
                print(f"✅ Success on: {proxy_info['proxy_address']}")
                return proxy_info
            else:
                print(f"❌ Failed with status {response.status} on: {proxy_info['proxy_address']}")
                return None
    except Exception as e:
        # This will catch timeouts, connection errors, etc.
        print(f"❌ Error on: {proxy_info['proxy_address']} - {type(e).__name__}")
        return None

async def main():
    """
    The main asynchronous function to orchestrate the proxy checking.
    """
    # Use 'aiofiles' for async file reading.
    async with aiofiles.open("proxies.json", 'r') as f:
        content = await f.read()
        proxies_data = json.loads(content)

    tasks = []
    # Set a timeout for all requests within the session.
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)

    # Creating a single ClientSession is more efficient than creating one for each request.
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for proxy_list in proxies_data:
            for result in proxy_list.get('results', []):
                # Create a task for each proxy check. A task is a future-like object
                # that runs an async function in the event loop.
                task = asyncio.create_task(check_proxy(session, result))
                tasks.append(task)

        print(f"Checking {len(tasks)} proxies...")
        # asyncio.gather() runs all tasks concurrently and waits for them all to finish.
        # It returns a list of the results from each task.
        results = await asyncio.gather(*tasks)

    # Filter out the 'None' results to get only the working proxies.
    working = [res for res in results if res is not None]
    print(f"\nFound {len(working)} working proxies.")

    # Use 'aiofiles' for async file writing.
    async with aiofiles.open("valid_proxies.json", 'w') as f:
        # json.dumps is synchronous, but that's okay as it's a fast, CPU-bound operation.
        await f.write(json.dumps(working, indent=4))
    
    print("Saved working proxies to valid_proxies.json")

if __name__ == "__main__":
    # This is the standard way to run the top-level async function.
    asyncio.run(main())