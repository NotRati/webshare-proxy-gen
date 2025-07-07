# webshare_registerer.py

import asyncio
import logging
import random
import os
import math
import json
import win32gui, win32con, win32process
from time import time
from typing import Dict, Any, Optional
import re
import psutil

from bs4 import BeautifulSoup
import httpx
import numpy as np
from playwright.async_api import async_playwright, Page, FrameLocator, Locator, BrowserContext
from scipy.interpolate import PchipInterpolator

# Import the separated solver class
from recaptcha_solver import RecaptchaAudioSolver

# --- FOR EMAIL GEN ---
# These are external API constants for Addy.io
ADDY_API_URL = "https://app.addy.io/api/v1/aliases"
ADDY_COOKIES = {
    'XSRF-TOKEN': 'eyJpdiI6InhCTXNtN3VrYkI4S0VGNldqdFpJRkE9PSIsInZhbHVlIjoibGUxbStJaktXdGRZbGduTWl2K0xoQ2VVbmhEYnNVMnQwN244M0I3N1N1Ykw4MW1KNlk2THVqWDgxQmhEcXc1RTFmZnVSWUYzOFA5YW9SbnJ0UzllZUlEMkM3S2ZUbDRCRUdyQnd1T1ArakFkTXdFNGwyZFdIQXArZHRBN0NlYk8iLCJtYWMiOiIxYzRlZjhkZmUzNzYzMDNiYWFmODQ4MmRiZDQ5NThmOWQxMzRkYzFmZmM1Y2JhMGVjZjNjNDc1YjhjMDZjOTI5IiwidGFnIjoiIn0%3D',
    'AnonAddy': 'eyJpdiI6ImZ0NFpnZUV0M0wrNjlTQjJGbENNd2c9PSIsInZhbHVlIjoiN1RrZHRLU3VnWU5DU1B0VjBUNFcrblFFY3dFTk5Pb3ZaOW5YWkZNZGRsQjJtUzdrdEtuNzRKcnl2TDFuN0R6OXlncWNMV3FZcE5xb0hJSlNjUzc0NWJyRUpDVlh4Q0V0VW1SRDZvdXRrbkl0ZVowNWZqZGNaQnVzUEQ3azBRekEiLCJtYWMiOiJiMzljNzk2MDlkM2MyZWNhOTgxNGUxMzE3NzE5MWE0ZmEyNDhlOWMzYjNlNDdhOWQ0ZjEzZmZkNzIzMGU4ODlhIiwidGFnIjoiIn0%3D',
}

ADDY_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://app.addy.io',
    'priority': 'u=1, i',
    'referer': 'https://app.addy.io/aliases',
    'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
    'x-xsrf-token': 'eyJpdiI6InhCTXNtN3VrYkI4S0VGNldqdFpJRkE9PSIsInZhbHVlIjoibGUxbStJaktXdGRZbGduTWl2K0xoQ2VVbmhEYnNVMnQwN244M0I3N1N1Ykw4MW1KNlk2THVqWDgxQmhEcXc1RTFmZnVSWUYzOFA5YW9SbnJ0UzllZUlEMkM3S2ZUbDRCRUdyQnd1T1ArakFkTXdFNGwyZFdIQXArZHRBN0NlYk8iLCJtYWMiOiIxYzRlZjhkZmUzNzYzMDNiYWFmODQ4MmRiZDQ5NThmOWQxMzRkYzFmZmM1Y2JhMGVjZjNjNDc1YjhjMDZjOTI5IiwidGFnIjoiIn0=',
}

ADDY_JSON_DATA = {
    'domain': 'anonaddy.me',
    'local_part': '',
    'description': '',
    'format': 'uuid',
    'recipient_ids': [],
}
# --- FOR EMAIL GEN ---

# --- Configuration ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

class WebshareRegisterer:
    """
    A class to automate the registration process on Webshare.io,
    including email generation and reCAPTCHA solving.
    """
    WEBSSHARE_REGISTER_URL = "https://dashboard.webshare.io/register/"
    WEBSSHARE_PROXY_LIST_URL = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=10"
    _email_generation_lock = asyncio.Lock()

    def __init__(
        self,
        headless: bool = False,
        proxy_details: Optional[Dict[str, str]] = None,
        whisper_model: str = "base",
        verbose: bool = False
    ):
        self.proxy_file_path = "proxies.json"
        self.headless = headless
        self.proxy_details = proxy_details
        self.whisper_model = whisper_model
        self.verbose = verbose
        self.SET_SECOND = False
        self._event_close = asyncio.Event()
        self.logger = logging.getLogger(f"{self.__class__.__name__}_{id(self)}")
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO if verbose else logging.WARNING)
        
        self.WEBSHARE_PROXY_PAGE = "https://dashboard.webshare.io/proxy/list?authenticationMethod=%22username_password%22&connectionMethod=%22direct%22&proxyControl=%220%22&rowsPerPage=10&page=0&order=%22asc%22&orderBy=null&searchValue=%22%22&removeType=%22refresh_all%22"
        self._browser: Optional[BrowserContext] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._mouse_x = random.uniform(100, 300)
        self._mouse_y = random.uniform(100, 300)

    async def _random_delay(self, mu: float = 0.5, sigma: float = 0.2):
        await asyncio.sleep(max(0.1, np.random.normal(mu, sigma)))

    async def _human_like_mouse_move(self, page: Page, locator: Locator, start_x: float, start_y: float) -> tuple[float, float]:
        try:
            box = await locator.bounding_box()
            if not box:
                self.logger.warning("Could not get bounding box for mouse move.")
                return start_x, start_y

            end_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
            end_y = box['y'] + box['height'] * random.uniform(0.2, 0.8)
            dist = math.hypot(end_x - start_x, end_y - start_y)
            num_points = max(5, int(dist / 100))
            x_points = np.linspace(start_x, end_x, num=num_points)
            y_points = np.linspace(start_y, end_y, num=num_points)
            if num_points > 2:
                offset_boundary = max(10, dist * 0.1)
                x_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)
                y_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)
            interp_x = PchipInterpolator(np.arange(num_points), x_points)
            interp_y = PchipInterpolator(np.arange(num_points), y_points)
            steps = max(15, int(dist / random.uniform(15, 25)))
            final_x, final_y = start_x, start_y
            for i in range(1, steps + 1):
                t = (i / steps) * (num_points - 1)
                final_x, final_y = interp_x(t), interp_y(t)
                await page.mouse.move(float(final_x), float(final_y))
                await asyncio.sleep(random.uniform(0.002, 0.008))
            return float(final_x), float(final_y)
        except Exception as e:
            self.logger.warning(f"Could not perform human-like mouse move: {e}")
            return start_x, start_y

    async def _human_like_type(self, locator: Locator, text: str):
        try:
            await locator.click(delay=random.uniform(1, 3))
            for char in text:
                await locator.press(char)
                await asyncio.sleep(random.uniform(0.02, 0.2))
        except Exception as e:
            self.logger.warning(f"Could not perform human-like typing: {e}")

    async def _generate_email(self, *args) -> Dict[str, Any]:
        async with self._email_generation_lock:
            self.logger.info("Attempting to generate a new email alias via SimpleLogin...")
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get('https://app.simplelogin.io/auth/login', headers={'User-Agent': random.choice(USER_AGENTS)})
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    csrf_token = soup.find("input", attrs={"name": "csrf_token"}).get("value")
                    
                    data = {'csrf_token': csrf_token, 'email': 'ratiardoteli11@gmail.com', 'password': 'rati1234'}
                    await client.post('https://app.simplelogin.io/auth/login', headers={'User-Agent': random.choice(USER_AGENTS)}, data=data, follow_redirects=True)
                    
                    response = await client.get('https://app.simplelogin.io/dashboard/', follow_redirects=True)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    csrf_token_dashboard = soup.find("input", attrs={"name": "csrf_token"}).get("value")
                    
                    data = {'csrf_token': csrf_token_dashboard, 'form-name': 'create-random-email'}
                    response = await client.post('https://app.simplelogin.io/dashboard/', data=data, follow_redirects=True)
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    div = soup.find("div", id=re.compile(r"^alias-container-\d+"))
                    if not div: raise RuntimeError("Could not find new alias container on dashboard.")

                    alias_id = div['id'].split("alias-container-")[1]
                    email_span = div.find("span", class_="font-weight-bold")
                    email = email_span.text.strip() if email_span else None
                    if not email: raise RuntimeError("Could not extract email address from new alias.")
                    
                    self.logger.info(f"Generated Email: {email} (Alias ID: {alias_id})")
                    return {'email': email, 'alias_id': alias_id, 'alias_name': email, 'csrf_token': csrf_token_dashboard, 'cookies': client.cookies}
            except Exception as e:
                self.logger.error(f"Fatal error during email generation: {e}", exc_info=True)
                raise

    async def cleanup_alias(self, alias_info: Dict[str, Any]):
        async with httpx.AsyncClient(cookies=alias_info['cookies']) as client:
            delete_data = {
                'csrf_token': alias_info['csrf_token'],
                'form-name': 'delete-alias',
                'alias-id': alias_info['alias_id'],
                'alias': alias_info['alias_name'],
            }
            await client.post(
                'https://app.simplelogin.io/dashboard/',
                headers={'User-Agent': random.choice(USER_AGENTS)},
                data=delete_data,
                follow_redirects=True,
            )
            self.logger.info(f"Deletion request sent for alias: {alias_info['alias_name']}")

    async def _is_captcha_solved_on_page(self, page: Page) -> bool:
        try:
            await page.locator("text=Creating Your Proxy List...").wait_for(timeout=2000)
            return True
        except Exception:
            if await page.locator("text=Try again later").is_visible():
                raise RuntimeError("Recaptcha has blocked this IP or browser profile.")
            return False

    async def _handle_response_listener(self, response):
        if self.WEBSSHARE_PROXY_LIST_URL.split('?')[0] in response.url:
            self.logger.info(f"⬅️ Captured Proxy List Response: {response.url}")
            try:
                json_body = await response.json()
                data = []
                if os.path.exists(self.proxy_file_path):
                    with open(self.proxy_file_path, "r") as f:
                        try:
                            existing_data = json.load(f)
                            if isinstance(existing_data, list):
                                data.extend(existing_data)
                        except json.JSONDecodeError: pass
                data.append(json_body)
                with open(self.proxy_file_path, "w") as f:
                    json.dump(data, f, indent=2)
                self.logger.info(f"Saved {len(json_body.get('data', []))} proxies to {self.proxy_file_path}")

                if self.SET_SECOND:
                    self.logger.info("Second proxy list fetched. Closing.")
                    self._event_close.set()
                else:
                    self.SET_SECOND = True
            except Exception as e:
                self.logger.warning(f"❌ Failed to parse proxy response: {e}")

    @staticmethod
    def hide_windows_by_pid(target_pids, logger):
        def enum_handler(hwnd, _):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in target_pids:
                    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            except Exception: pass
        win32gui.EnumWindows(enum_handler, None)

    @staticmethod
    def get_chromium_pids():
        return {p.pid for p in psutil.process_iter(['name']) if p.info['name'] and 'chrome' in p.info['name'].lower()}

    async def register(self) -> bool:
        start_time = time()
        alias_info = None
        try:
            alias_info = await self._generate_email()
            email = alias_info['email']
            password = "bangbang!"

            self.logger.info(f"Starting Webshare registration for Email: {email}")
            async with async_playwright() as p:
                self._browser = await p.chromium.launch(headless=self.headless, proxy=self.proxy_details)
                self._context = await self._browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={'width': 1920, 'height': 1080},
                    locale="en-US",
                )
                await self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
                self._page = await self._context.new_page()

                self.logger.info("Navigating to Webshare registration page...")
                await self._page.goto(self.WEBSSHARE_REGISTER_URL, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(100000)
                await self._page.mouse.move(self._mouse_x, self._mouse_y)
                self.logger.info("Filling out registration form...")
                await self._human_like_type(self._page.locator('input[data-testid="password-input"]'), password)
                await self._human_like_type(self._page.locator('#email-input'), email)

                self.logger.info("Submitting registration form...")
                submit_button_locator = self._page.locator('button[data-testid="signup-button"]')
                self._mouse_x, self._mouse_y = await self._human_like_mouse_move(self._page, submit_button_locator, self._mouse_x, self._mouse_y)
                await submit_button_locator.click()

                if not await self._is_captcha_solved_on_page(self._page):
                    self.logger.info("CAPTCHA challenge detected. Attempting to solve...")
                    solver = RecaptchaAudioSolver(
                        self, self._page, self._mouse_x, self._mouse_y,
                        whisper_model=self.whisper_model, verbose=self.verbose
                    )
                    self._mouse_x, self._mouse_y = await solver.solve()
                    self.logger.info("Captcha solving process completed.")

                await self._page.locator("text=Creating Your Proxy List...").wait_for(timeout=15000)
                self.logger.info("✅ Registration and CAPTCHA successfully completed.")

                await self._page.goto(self.WEBSHARE_PROXY_PAGE)
                self._page.on("response", self._handle_response_listener)

                self.logger.info("Attached response listener. Waiting for proxy list to be fetched.")
                await self._event_close.wait()
                return True

        except Exception as e:
            self.logger.error(f"Registration failed: {e}", exc_info=True)
            if self._page and not self.headless:
                try:
                    await self._page.screenshot(path="webshare_registration_failure.png")
                    self.logger.info("Screenshot taken: webshare_registration_failure.png")
                except Exception as ss_e:
                    self.logger.error(f"Failed to take screenshot: {ss_e}")
            return False
        finally:
            if alias_info:
                self.logger.info(f"Cleaning up alias: {alias_info.get('email', 'N/A')}")
                try:
                    await self.cleanup_alias(alias_info)
                except Exception as e:
                    self.logger.warning(f"⚠️ Could not delete alias. Error: {e}")

            if self._browser:
                await self._browser.close()
            time_taken = round(time() - start_time, 2)
            self.logger.info(f"Total process finished in {time_taken} seconds.")

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    proxy_config =  {
        "server": "http://104.239.105.125:6655",
        "username": "jrkwdmsz",
        "password": "zv9slg5hiiwo"
    }
    tasks = []
    for _ in range(1): # Number of concurrent registrations
        registerer = WebshareRegisterer(verbose=True, proxy_details=proxy_config)
        tasks.append(registerer.register())
        await asyncio.sleep(5) # Stagger the starts

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # Ensure you have the necessary model file for Whisper.
    # It will be downloaded automatically on the first run.
    # Example: whisper.load_model("base")
    asyncio.run(main())