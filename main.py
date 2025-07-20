# webshare_registerer.py
# https://relay.firefox.com/accounts/profile/? #TODO
import asyncio
import logging
import random
import os
import math
import json
import string
# import win32gui, win32con, win32process
from time import time
from typing import Dict, Any, Optional
import re
import psutil
import argparse
import traceback
from datetime import datetime, timedelta, timezone

import proxy_checker
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import httpx
import numpy as np
from playwright.async_api import async_playwright, Page, FrameLocator, Locator, BrowserContext
from scipy.interpolate import PchipInterpolator

# Import the separated solver class
from recaptcha_solver import RecaptchaAudioSolver

# --- Configuration ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]
class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.ERROR: "\033[38;2;128;0;0m",    # Red
        logging.CRITICAL: "\033[38;2;128;0;0m", # Red
        logging.WARNING: "\033[33m",  # Yellow
        logging.INFO: "\033[0m",      # Default (reset)
        logging.DEBUG: "\033[0m",     # Default (reset)
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"
def _rand_str(length:int = 10):
    return ''.join([random.choice(string.ascii_lowercase) for _ in range(length)])
class WebshareRegisterer:
    """
    A class to automate the registration process on Webshare.io,
    including email generation and reCAPTCHA solving.
    """
    WEBSHARE_PROXY_HEADERS = {
        'authorization': 'Token %token%',
    }

    WEBSHARE_PROXY_PARAMS = {
        'mode': 'direct',
        'page': '1',
        'page_size': '10',
    }
    WEBSHARE_REGISTER_API_URL = "https://proxy.webshare.io/api/v2/register/"
    WEBSSHARE_REGISTER_URL = "https://dashboard.webshare.io/register/"
    WEBSSHARE_PROXY_LIST_URL = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=10"
    
    _email_generation_lock = asyncio.Lock()
    _proxy_lock = asyncio.Lock()
    proxies = []
    _last_load_time = None
    _reload_interval = timedelta(minutes=1)

    def __init__(
        self,
        headless: bool = False,
        whisper_model: str = "base",
        verbose: bool = False,
        proxy_file: str = "proxies.json",
        instance_id=None
    ):
        self.proxy_file_path = proxy_file
        self.headless = headless
        self.whisper_model = whisper_model
        self.verbose = verbose
        self._event_request_catched = asyncio.Future()
        log_identifier = instance_id if instance_id is not None else id(self)
        self.logger = self.setup_logger(log_identifier)
        self.WEBSHARE_PROXY_PAGE = "https://dashboard.webshare.io/proxy/list?authenticationMethod=%22username_password%22&connectionMethod=%22direct%22&proxyControl=%220%22&rowsPerPage=10&page=0&order=%22asc%22&orderBy=null&searchValue=%22%22&removeType=%22refresh_all%22"
        self._browser: Optional[BrowserContext] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._mouse_x = random.uniform(100, 300)
        self._mouse_y = random.uniform(100, 300)
        asyncio.create_task(self.log_and_flush_loop())

    @classmethod
    async def create(
        cls,
        headless: bool = False,
        whisper_model: str = "base",
        verbose: bool = False,
        proxy_file: str = "proxies.json",
        instance_id=None
    ):
        self = cls(
            headless=headless,
            whisper_model=whisper_model,
            verbose=verbose,
            proxy_file=proxy_file,
            instance_id=instance_id
        )
        await self.setup_client()  
        return self
    async def load_proxies_if_needed(self):
        async with type(self)._proxy_lock:
            now = datetime.now(timezone.utc)
            if (
                not type(self).proxies
                or type(self)._last_load_time is None
                or now - type(self)._last_load_time > type(self)._reload_interval
            ):
                type(self).proxies = await proxy_checker.check_proxies_from_file(
                    logger=self.logger,
                    input_file=self.proxy_file_path,
                    output_file=self.proxy_file_path
                )
                type(self)._last_load_time = now
    async def setup_client(self):
        try:
            await self.load_proxies_if_needed()

            if type(self).proxies:
                proxy_info = random.choice(type(self).proxies)
                proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['proxy_address']}:{proxy_info['port']}"
                self.client = httpx.AsyncClient(
                    proxy=proxy_url,
                    headers={"user-agent": random.choice(USER_AGENTS)},
                    timeout=30
                )
            else:
                self.client = httpx.AsyncClient(
                    headers={"user-agent": random.choice(USER_AGENTS)},
                    timeout=30
                )
        except Exception as e:
            self.logger.critical(f"❌ Couldn't setup httpx client: {e}")
            raise RuntimeError(e)
    def setup_logger(self, identifier):
        class_name = self.__class__.__name__
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)

        logger_name = f"{class_name}_{identifier}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            log_path = os.path.join(log_dir, f"{class_name}_{identifier}.log")
            file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # Colored formatter for console only
            console_handler = logging.StreamHandler()
            colored_formatter = ColoredFormatter('%(asctime)s - [%(levelname)s] - %(message)s')
            console_handler.setFormatter(colored_formatter)
            logger.addHandler(console_handler)

            logger.propagate = False

        return logger
    async def _random_delay(self, mu: float = 0.5, sigma: float = 0.2):
        await asyncio.sleep(max(0.1, np.random.normal(mu, sigma)))
    async def log_and_flush_loop(self):
        while True:
            for handler in self.logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    handler.flush()
            await asyncio.sleep(1)
    async def _human_like_mouse_move(self, page: Page, locator: Locator, start_x: float, start_y: float) -> tuple[float, float]:
        try:
            # 1. Simulate human reaction delay
            await asyncio.sleep(random.uniform(0.2, 0.6))

            box = await locator.bounding_box()
            if not box:
                self.logger.warning("Could not get bounding box for mouse move.")
                return start_x, start_y

            # 2. Choose random target location inside element
            target_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
            target_y = box['y'] + box['height'] * random.uniform(0.2, 0.8)

            # 3. Optional overshoot
            overshoot_chance = 0.3
            if random.random() < overshoot_chance:
                overshoot_x = target_x + random.uniform(-10, 10)
                overshoot_y = target_y + random.uniform(-10, 10)
            else:
                overshoot_x, overshoot_y = target_x, target_y

            # 4. Build path with jitter and curvature
            dist = math.hypot(overshoot_x - start_x, overshoot_y - start_y)
            num_points = max(6, int(dist / 80))
            x_points = np.linspace(start_x, overshoot_x, num=num_points)
            y_points = np.linspace(start_y, overshoot_y, num=num_points)

            if num_points > 2:
                offset_boundary = max(5, dist * 0.05)
                x_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)
                y_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)

            interp_x = PchipInterpolator(np.arange(num_points), x_points)
            interp_y = PchipInterpolator(np.arange(num_points), y_points)

            # 5. Ease-in, ease-out movement
            steps = max(15, int(dist / random.uniform(10, 20)))
            ease = lambda t: t * t * (3 - 2 * t)  # smoothstep function

            final_x, final_y = start_x, start_y
            for i in range(1, steps + 1):
                t = ease(i / steps) * (num_points - 1)
                jitter_x = random.uniform(-1.2, 1.2)
                jitter_y = random.uniform(-1.2, 1.2)
                final_x = interp_x(t) + jitter_x
                final_y = interp_y(t) + jitter_y
                await page.mouse.move(float(final_x), float(final_y))
                await asyncio.sleep(random.uniform(0.005, 0.015))

            # 6. Final correction if overshoot happened
            if (overshoot_x, overshoot_y) != (target_x, target_y):
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.mouse.move(float(target_x), float(target_y))

            # 7. Optional hover pause
            await asyncio.sleep(random.uniform(0.05, 0.2))

            return float(target_x), float(target_y)

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

    async def _generate_email(self) -> Dict[str, Any]:
        async with self._email_generation_lock:
            self.logger.info("Attempting to generate a new email alias via SimpleLogin...")
            try:
                response = await self.client.get('https://app.simplelogin.io/auth/login', headers={'User-Agent': random.choice(USER_AGENTS)})
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                csrf_token = soup.find("input", attrs={"name": "csrf_token"}).get("value")
                
                data = {'csrf_token': csrf_token, 'email': 'shiu93306@gmail.com', 'password': 'rati1234'}
                await self.client.post('https://app.simplelogin.io/auth/login', headers={'User-Agent': random.choice(USER_AGENTS)}, data=data, follow_redirects=True)
                
                response = await self.client.get('https://app.simplelogin.io/dashboard/', follow_redirects=True)
                soup = BeautifulSoup(response.text, 'html.parser')
                csrf_token_dashboard = soup.find("input", attrs={"name": "csrf_token"}).get("value")
                
                data = {'csrf_token': csrf_token_dashboard, 'form-name': 'create-random-email'}
                response = await self.client.post('https://app.simplelogin.io/dashboard/', data=data, follow_redirects=True)
                
                soup = BeautifulSoup(response.text, 'html.parser')
                div = soup.find("div", id=re.compile(r"^alias-container-\d+"))
                if not div: raise RuntimeError("Could not find new alias container on dashboard.")

                alias_id = div['id'].split("alias-container-")[1]
                email_span = div.find("span", class_="font-weight-bold")
                email = email_span.text.strip() if email_span else None
                if not email: raise RuntimeError("Could not extract email address from new alias.")
                
                self.logger.info(f"Generated Email: {email} (Alias ID: {alias_id})")
                return {'email': email, 'alias_id': alias_id, 'alias_name': email, 'csrf_token': csrf_token_dashboard, 'cookies': self.client.cookies}
            except Exception as e:
                self.logger.error(f"Fatal error during email generation: {e}", exc_info=True)
                raise
    async def cleanup_alias(self, alias_info: Dict[str, Any]):
        self.logger.info(f"Trying to delete alias {alias_info['alias_name']}")
        delete_data = {
            'csrf_token': alias_info['csrf_token'],
            'form-name': 'delete-alias',
            'alias-id': alias_info['alias_id'],
            'alias': alias_info['alias_name'],
        }
        await self.client.post(
            'https://app.simplelogin.io/dashboard/',
            headers={'User-Agent': random.choice(USER_AGENTS)},
            data=delete_data,
            follow_redirects=True,
            cookies=alias_info['cookies']
        )
        self.logger.info(f"Deletion request sent for alias: {alias_info['alias_name']}")
    async def start_routing(self):
        await self._page.route(
            "**/*",
            lambda route, request: asyncio.create_task(self._handle_request_listener(route, request))
        )
    
    async def manual_register(self, post_data: str):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = await self.client.post(
                    self.WEBSHARE_REGISTER_API_URL,
                    json=json.loads(post_data),
                    headers={"user-agent": random.choice(USER_AGENTS)},
                    follow_redirects=True,
                )
                
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    self.logger.error(f"HTTP error on register attempt {attempt}: {e.response.status_code} - {e.response.text}")
                    raise  # re-raise after logging
                
                if response.status_code == 200:
                    json_data = response.json()
                    self.token = json_data.get('token')
                    self.logger.info(f"Registration successful, token: {self.token}")
                else:
                    self.logger.warning(f"Unexpected status code on register attempt {attempt}: {response.status_code}")
                    return False

                copied_headers = self.WEBSHARE_PROXY_HEADERS.copy()

                copied_headers['authorization'] = self.WEBSHARE_PROXY_HEADERS['authorization'].replace("%token%", self.token)
                copied_headers['User-Agent'] = random.choice(USER_AGENTS)

                response = await self.client.get(
                    url=self.WEBSSHARE_PROXY_LIST_URL,
                    params=self.WEBSHARE_PROXY_PARAMS,
                    headers=copied_headers,
                    follow_redirects=True,
                )

                self.logger.info(f"Proxy list fetch status: {response.status_code}")
                self.logger.info(f"Proxy list response text: {response.text}")
                json_body = response.json()
                extracted = []
                for proxy in json_body['results']:
                    extracted.append(proxy)

                data = []
                if os.path.exists(self.proxy_file_path):
                    with open(self.proxy_file_path, "r") as f:
                        try:
                            existing_data = json.load(f)
                            if isinstance(existing_data, list):
                                data.extend(existing_data)
                        except json.JSONDecodeError:
                            pass

                data.extend(extracted)

                with open(self.proxy_file_path, "w") as f:
                    json.dump(data, f, indent=2)

                self.logger.info(f"Saved {len(extracted)} proxies to {self.proxy_file_path}")

                return True
            
            except Exception as e:
                self.logger.error(f"Attempt {attempt} failed with error: {e}")
                self.logger.error(traceback.format_exc())

                if attempt == max_retries:
                    self.logger.error("Max retries reached. Giving up.")
                    return False
                else:
                    backoff = 2 ** attempt
                    self.logger.info(f"Retrying in {backoff} seconds...")
                    await asyncio.sleep(backoff)

    async def _handle_request_listener(self,route, request): 
        try:
            if request.url == self.WEBSHARE_REGISTER_API_URL and request.method == "POST":
                # print(f"URL: {request.url}")
                # print(f"Method: {request.method}")
                # print("Headers:", request.headers)
                try:
                    post_data = request.post_data
                    if post_data:
                        self.logger.info("Post Data:" + str(post_data))
                    else:
                        self.logger.warning("No Post Data")
                    
                    await route.abort()
                    self._event_request_catched.set_result(post_data)

                except Exception as e:
                    self.logger.error("Error accessing post data:"+ str(e))
            else:
                await route.continue_()
        except Exception as e:
            self.logger.info("Error processing request:" +  str(e))
    async def register(self) -> bool:
        start_time = time()
        alias_info = None
        try:
            # alias_info = await self._generate_email()
            # email = alias_info['email']
            email = _rand_str(8) + "@simplelogin.com"
            password = _rand_str(6) + "A!"

            self.logger.info(f"Starting Webshare registration for Email: {email}")
            async with Stealth().use_async(async_playwright()) as p:
                if self.headless:
                    args = [
                        '--window-position=-10000,-10000',
                        '--window-size=1,1'
                    ]
                    self.logger.info("Self headless is true")
                else:
                    args = []
                self._browser = await p.chromium.launch(args=args, headless=False)
    
                self._context = await self._browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={'width': 1920, 'height': 1080},
                    locale="en-US",
                    java_script_enabled=True,
                )
                
                self._page = await self._context.new_page()
                asyncio.create_task(self.start_routing())


                self.logger.info("Navigating to Webshare registration page...")
                await self._page.goto(self.WEBSSHARE_REGISTER_URL, wait_until="domcontentloaded", timeout=60000)
                await self._page.mouse.move(self._mouse_x, self._mouse_y)
                self.logger.info("Filling out registration form...")
                await self._human_like_type(self._page.locator('input[data-testid="password-input"]'), password)
                await self._human_like_type(self._page.locator('#email-input'), email)

                self.logger.info("Submitting registration form...")
                submit_button_locator = self._page.locator('button[data-testid="signup-button"]')
                self._mouse_x, self._mouse_y = await self._human_like_mouse_move(self._page, submit_button_locator, self._mouse_x, self._mouse_y)
                await submit_button_locator.click()

                self.logger.info("Attempting to solve CAPTCHA challange...")
                solver = RecaptchaAudioSolver(
                    self, self._page, self._mouse_x, self._mouse_y,
                    whisper_model=self.whisper_model, verbose=self.verbose
                )
                solved = await solver.solve()
                if solved:
                    self.logger.info("Captcha solving process completed.")
                else:
                    raise RuntimeError("❌ Couldn't solve Captcha.")
                self.logger.info("Registration successfully completed. Now waiting for register data.")
                register_payload_data = await self._event_request_catched
                self.logger.info(f"Got post data result. Continuing.")
                await self.manual_register(register_payload_data)
                return True

        except Exception as e:
            self.logger.error(f"Registration failed: {e}", exc_info=True)
            return False
        finally:
            if alias_info:
                self.logger.info(f"Cleaning up alias: {alias_info.get('email', 'N/A')}")
                try:
                    await self.cleanup_alias(alias_info)
                except Exception as e:
                    self.logger.warning(f"⚠️ Could not delete alias. Error: {e}")
                    
            time_taken = round(time() - start_time, 2)
            self.logger.info(f"Total process finished in {time_taken} seconds.")

async def main(concurrent: int, headless: bool, total: int):    
    completed = 0
    while total == -1 or completed < total:
        batch_size = min(concurrent, total - completed) if total != -1 else concurrent
        tasks = []
        for _ in range(batch_size):
            registerer = await WebshareRegisterer.create(verbose=True, headless=headless)
            task = asyncio.create_task(registerer.register())
            tasks.append(task)

        await asyncio.gather(*tasks)
        completed += len(tasks)

async def run_gui_instance(headless: bool, instance_id: str, concurrent: int = 1, total: int = -1):
    """
    Runs concurrent registration tasks for the GUI instance,
    creating separate log files per coroutine with naming:
    logs/WebshareRegisterer_{instance_id}_coro_{i}.log
    """

    async def coro_task(idx: int):
        # Compose a unique instance id per coroutine for logging and identification
        coro_instance_id = f"{instance_id}_coro_{idx}"

        # Prepare logger
        logger = logging.getLogger(coro_instance_id)
        logger.setLevel(logging.DEBUG)

        # Clear existing handlers
        if logger.hasHandlers():
            logger.handlers.clear()

        os.makedirs("logs", exist_ok=True)
        log_path = os.path.join("logs", f"WebshareRegisterer_{coro_instance_id}.log")

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Instantiate your existing class with the coro_instance_id and headless mode
        registerer = await WebshareRegisterer.create(verbose=True, headless=headless, instance_id=coro_instance_id)
        registerer.logger = logger  # Inject our file logger

        try:
            logger.info(f"Coroutine {idx} started with instance ID: {coro_instance_id}")
            await registerer.register()
            logger.info(f"Coroutine {idx} completed.")
        except Exception as e:
            logger.error(f"An error occurred in coroutine {idx}: {e}", exc_info=True)
        finally:
            logger.info("---DONE LOGGER---")

    if total == -1:
        # Run forever, spawning the concurrent coros in each batch
        while True:
            await asyncio.gather(*(coro_task(i) for i in range(concurrent)))
    else:
        count = 0
        while count < total:
            # Run coroutines concurrently in batches of 'concurrent'
            await asyncio.gather(*(coro_task(i) for i in range(concurrent)))
            count += concurrent



async def run_standalone(concurrent: int, headless: bool, total: int):
    """
    This is your original logic for running multiple tasks concurrently
    when the script is started directly, not from the GUI.
    """
    print(f"Standalone mode: Running {concurrent} concurrent tasks.")
    completed = 0
    while total == -1 or completed < total:
        batch_size = min(concurrent, total - completed) if total != -1 else concurrent
        tasks = []
        for _ in range(batch_size):
            # In this mode, we don't pass an instance_id, so it will use the old
            # id(self) method for logging, which is fine for standalone use.
            registerer = await WebshareRegisterer.create(verbose=True, headless=headless)
            task = asyncio.create_task(registerer.register())
            tasks.append(task)

        await asyncio.gather(*tasks)
        completed += len(tasks)
        print(f"Batch completed. Total registrations: {completed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Your original arguments
    parser.add_argument("--concurrent", type=int, default=1, help="Number of concurrent registrations (standalone mode)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--total", type=int, default=1, help="Total number of registrations (-1 for infinite, standalone mode)")
    
    # Add the new argument from the launcher GUI. Default is None.
    parser.add_argument("--instance-id", type=str, default=None, help="[For GUI Use] Unique ID provided by the launcher.")

    args = parser.parse_args()

    # --- Logic to select run mode ---
    if args.instance_id:
        asyncio.run(run_gui_instance(args.headless, args.instance_id, args.concurrent, args.total))
    else:
        asyncio.run(run_standalone(args.concurrent, args.headless, args.total))
# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--concurrent", type=int, default=1, help="Number of concurrent registrations")
#     parser.add_argument("--headless", action="store_true", help="Run in headless mode")
#     parser.add_argument("--total", type=int, default=-1, help="Total number of registrations (-1 for infinite)")

#     args = parser.parse_args()

#     asyncio.run(main(args.concurrent, args.headless, args.total))