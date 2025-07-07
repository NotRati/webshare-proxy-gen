import asyncio
import logging
import random
import os
import math
import json
from time import time
from typing import Dict, Any, Optional
import re

from bs4 import BeautifulSoup
import httpx
import numpy as np
from playwright.async_api import async_playwright, Page, FrameLocator, Locator, BrowserContext
# --- CORRECTED IMPORT FOR v2.0.0 ---
from playwright_stealth import stealth_async, Config
from scipy.interpolate import PchipInterpolator

# Assume recaptcha_solver.py is in the same directory
from recaptcha_solver import RecaptchaAudioSolver

# --- ENHANCED FINGERPRINTING CONSTANTS ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {'width': 1920, 'height': 1080},
    {'width': 1366, 'height': 768},
    {'width': 1536, 'height': 864},
    {'width': 1440, 'height': 900},
]


class CaptchaTokenHarvester:
    """
    A class to solve a reCAPTCHA on Webshare.io and harvest the g-recaptcha-response token
    WITHOUT completing the registration. This version is enhanced for stealth and updated for playwright-stealth v2.0.0.
    """
    WEBSSHARE_REGISTER_URL = "https://dashboard.webshare.io/register/"
    
    def __init__(
        self,
        headless: bool = False,
        whisper_model: str = "base",
        proxy: Optional[str] = None,
        verbose: bool = False
    ):
        self.headless = headless
        self.whisper_model = whisper_model
        self.proxy = proxy
        self.verbose = verbose
        self.logger = logging.getLogger(f"{self.__class__.__name__}_{id(self)}")
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO if self.verbose else logging.WARNING)
        self._mouse_x = random.uniform(200, 800)
        self._mouse_y = random.uniform(200, 600)

    # --- All the _human_like... and _idle_behavior methods remain the same ---
    # (They are omitted here for brevity, but they should be kept in your file)
    async def _random_delay(self, mu: float = 0.8, sigma: float = 0.3):
        await asyncio.sleep(max(0.2, np.random.normal(mu, sigma)))
    async def _idle_behavior(self, page: Page):
        self.logger.info("Performing idle behavior to mimic user...")
        for _ in range(random.randint(1, 3)):
            await page.mouse.move(self._mouse_x + random.uniform(-50, 50),self._mouse_y + random.uniform(-50, 50),steps=random.randint(5, 10))
            await asyncio.sleep(random.uniform(0.1, 0.4))
        scroll_amount = random.randint(-200, 200)
        await page.mouse.wheel(0, scroll_amount)
        self.logger.info(f"Scrolled by {scroll_amount} pixels.")
        await self._random_delay()
    async def _human_like_mouse_move(self, page: Page, locator: Locator, start_x: float, start_y: float) -> tuple[float, float]:
        try:
            box = await locator.bounding_box()
            if not box:
                self.logger.warning("Could not get bounding box for mouse move.")
                return start_x, start_y
            end_x = box['x'] + box['width'] * random.uniform(0.25, 0.75)
            end_y = box['y'] + box['height'] * random.uniform(0.25, 0.75)
            dist = math.hypot(end_x - start_x, end_y - start_y)
            num_points = max(3, int(dist / 200)) 
            x_points = np.linspace(start_x, end_x, num=num_points)
            y_points = np.linspace(start_y, end_y, num=num_points)
            if num_points > 2:
                offset_boundary = max(15, dist * 0.15) 
                x_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)
                y_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)
            interp_x = PchipInterpolator(np.arange(num_points), x_points)
            interp_y = PchipInterpolator(np.arange(num_points), y_points)
            steps = max(20, int(dist / random.uniform(10, 20))) 
            final_x, final_y = start_x, start_y
            for i in range(1, steps + 1):
                t = (i / steps) * (num_points - 1)
                final_x, final_y = interp_x(t), interp_y(t)
                await page.mouse.move(float(final_x), float(final_y))
                await asyncio.sleep(random.uniform(0.001, 0.01))
            return float(final_x), float(final_y)
        except Exception as e:
            self.logger.warning(f"Could not perform human-like mouse move: {e}")
            return start_x, start_y
    async def _human_like_type(self, locator: Locator, text: str):
        try:
            await locator.click(delay=random.uniform(80, 150))
            for char in text:
                await locator.press(char)
                await asyncio.sleep(random.uniform(0.06, 0.22))
        except Exception as e:
            self.logger.warning(f"Could not perform human-like typing: {e}")

    async def harvest_token(self) -> Optional[str]:
        """
        Solves the CAPTCHA and returns the token. 
        Updated to use playwright-stealth v2.0.0 API.
        """
        start_time = time()
        browser = None
        context = None
        
        email = f"test-{int(time()*100)}@{random.choice(['gmx.com', 'yahoo.com', 'proton.me'])}"
        password = f"Dummy-P@ssword{random.randint(1000, 9999)}!"
        
        try:
            async with async_playwright() as p:
                
                # --- PROXY CONFIGURATION ---
                proxy_settings = None
                if self.proxy:
                    self.logger.info(f"Using proxy: {self.proxy.split('@')[-1]}")
                    proxy_settings = {"server": self.proxy}

                # --- APPLY STEALTH PATCHES (THE NEW WAY for v2.0.0) ---
                # This creates a stealthed playwright object that we use to launch the browser.
                # You can customize which evasions to use in the Config.
                stealth_config = Config(
                    vendor="Google Inc.",
                    platform="Win32",
                    webdriver=False,
                    # Add any other specific configurations here
                )
                self.logger.info("Applying stealth patches to Playwright instance...")
                stealthed_playwright = await stealth_async(p, stealth_config)

                # Now, launch the browser using the stealthed playwright object
                browser = await stealthed_playwright.chromium.launch(
                    headless=self.headless,
                    proxy=proxy_settings
                )
                
                # --- BROWSER CONTEXT SETUP (CRITICAL FOR STEALTH) ---
                user_agent = random.choice(USER_AGENTS)
                viewport = random.choice(VIEWPORTS)
                self.logger.info(f"Using Fingerprint: UA='{user_agent}', Viewport={viewport}")

                context = await browser.new_context(
                    user_agent=user_agent,
                    viewport=viewport,
                    locale="en-US",
                    timezone_id="America/New_York",
                    geolocation={'longitude': -74.0060, 'latitude': 40.7128},
                    permissions=['geolocation'],
                    screen=viewport
                )
                
                # --- THE OLD `await stealth_async(context)` CALL IS NO LONGER NEEDED AND IS REMOVED ---
                
                page = await context.new_page()
                
                # --- The rest of the logic is identical ---
                self.logger.info(f"Navigating to {self.WEBSSHARE_REGISTER_URL}")
                await page.goto(self.WEBSSHARE_REGISTER_URL, timeout=90000, wait_until='domcontentloaded')
                await self._idle_behavior(page)
                await self._random_delay()
                
                self.logger.info("Filling dummy details into registration form...")
                await self._human_like_type(page.locator('#email-input'), email)
                await self._random_delay(0.5, 0.2)
                await self._human_like_type(page.locator('input[data-testid="password-input"]'), password)

                self.logger.info("Moving mouse to submit button...")
                submit_button_locator = page.locator('button[data-testid="signup-button"]')
                self._mouse_x, self._mouse_y = await self._human_like_mouse_move(page, submit_button_locator, self._mouse_x, self._mouse_y)
                
                await self._random_delay(0.2, 0.1) 
                
                self.logger.info("Clicking submit button to trigger CAPTCHA...")
                await submit_button_locator.click()

                self.logger.info("Initializing solver to handle CAPTCHA challenge...")
                solver = RecaptchaAudioSolver(
                    self, page, self._mouse_x, self._mouse_y,
                    whisper_model=self.whisper_model, verbose=self.verbose
                )
                
                self._mouse_x, self._mouse_y = await solver.solve()
                self.logger.info("Captcha solving process finished.")
                
                self.logger.info("Polling for g-recaptcha-response token...")
                token = None
                for i in range(25):
                    token_element = page.locator('#g-recaptcha-response')
                    if await token_element.count() > 0:
                        token_value = await token_element.input_value()
                        if token_value and len(token_value) > 100:
                            token = token_value
                            self.logger.info(f"✅ Successfully harvested token (first {20} chars): {token[:20]}...")
                            break
                    await asyncio.sleep(0.5)

                if not token:
                    self.logger.error("Failed to find CAPTCHA token textarea after successful solve.")
                    raise RuntimeError("Failed to find g-recaptcha-response token.")
                
                self.logger.info("Blocking network requests to prevent account registration.")
                await context.route('**/*', lambda route: route.abort())

                await context.close()
                await browser.close()
                browser = None
                
                time_taken = round(time() - start_time, 2)
                self.logger.info(f"Token harvesting finished in {time_taken} seconds.")
                return token

        except Exception as e:
            self.logger.error(f"Token harvesting failed: {e}", exc_info=True)
            if 'page' in locals() and page and not page.is_closed():
                try:
                    await page.screenshot(path="captcha_harvest_failure.png")
                    self.logger.info("Screenshot taken: captcha_harvest_failure.png")
                except Exception as ss_e:
                    self.logger.error(f"Failed to take screenshot: {ss_e}")
            return None
        finally:
            if browser:
                await browser.close()
            time_taken = round(time() - start_time, 2)
            self.logger.info(f"Total process finished in {time_taken} seconds.")

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    harvester = CaptchaTokenHarvester(
        verbose=True, 
        headless=False,
    )
    recaptcha_token = await harvester.harvest_token()
    if recaptcha_token:
        print("\n" + "="*50)
        print("🎉 Successfully Harvested reCAPTCHA Token! 🎉")
        print("="*50)
        print(recaptcha_token[:100] + "...")
        print("="*50)
        with open("captcha_token.txt", "w") as f:
            f.write(recaptcha_token)
        print("Token saved to captcha_token.txt")
        return recaptcha_token
    else:
        print("\n" + "="*50)
        print("❌ Failed to harvest a reCAPTCHA token.")
        print("="*50)

if __name__ == "__main__":
    asyncio.run(main())