import asyncio
import logging
import random
import os
import math


import httpx
import numpy as np
from playwright.async_api import Page, FrameLocator, Locator, BrowserContext
from scipy.interpolate import PchipInterpolator
import whisper

class RecaptchaAudioSolver:
        _IFRAME_CHECKBOX_SELECTOR = 'iframe[title="reCAPTCHA"]'
        _IFRAME_CHALLENGE_SELECTOR = 'iframe[title*="recaptcha challenge"]'
        _CHECKBOX_SELECTOR = '#recaptcha-anchor'
        _AUDIO_BUTTON_SELECTOR = '#recaptcha-audio-button'
        _AUDIO_DOWNLOAD_LINK_SELECTOR = '.rc-audiochallenge-tdownload-link'
        _AUDIO_RESPONSE_INPUT_SELECTOR = '#audio-response'
        _VERIFY_BUTTON_SELECTOR = '#recaptcha-verify-button'

        def __init__(self,  page: Page, mouse_x: float, mouse_y: float, whisper_model: str = "base", verbose: bool = False):
            # self.outer_instance = outer_instance # Reference to the parent WebshareRegisterer instance
            self.page = page
            self.verbose = verbose
            self.logger = logging.getLogger(f"{self.__class__.__name__}_{id(self)}")
            self.logger.propagate = False # Prevent double logging
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)

            if not verbose: self.logger.setLevel(logging.WARNING)
            else: self.logger.setLevel(logging.INFO)

            self.model = whisper.load_model(whisper_model)
            self.mouse_x = mouse_x
            self.mouse_y = mouse_y
        async def _random_delay(self, mu: float = 0.5, sigma: float = 0.2):
            """Introduces a random delay to simulate human behavior."""
            await asyncio.sleep(max(0.1, np.random.normal(mu, sigma)))

        async def _human_like_mouse_move(self, page: Page, locator: Locator, start_x: float, start_y: float) -> tuple[float, float]:
            """
            Moves the mouse in a human-like, curved path to a locator's approximate center.
            Returns the final coordinates.
            """
            try:
                box = await locator.bounding_box()
                if not box:
                    self.logger.warning("Could not get bounding box for mouse move.")
                    return start_x, start_y

                end_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
                end_y = box['y'] + box['height'] * random.uniform(0.2, 0.8)

                dist = math.hypot(end_x - start_x, end_y - start_y)
                num_points = max(5, int(dist / 100)) # Adjust granularity based on distance
                
                x_points = np.linspace(start_x, end_x, num=num_points)
                y_points = np.linspace(start_y, end_y, num=num_points)

                # Introduce slight random offsets to interior points for a more natural curve
                if num_points > 2:
                    offset_boundary = max(10, dist * 0.1) # Offset proportional to distance
                    x_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)
                    y_points[1:-1] += np.random.uniform(-offset_boundary, offset_boundary, num_points - 2)

                # Use PchipInterpolator for a smooth, monotonic curve
                interp_x = PchipInterpolator(np.arange(num_points), x_points)
                interp_y = PchipInterpolator(np.arange(num_points), y_points)

                steps = max(15, int(dist / random.uniform(15, 25))) # Number of mouse move events
                
                final_x, final_y = start_x, start_y
                for i in range(1, steps + 1):
                    t = (i / steps) * (num_points - 1)
                    final_x, final_y = interp_x(t), interp_y(t)
                    await page.mouse.move(float(final_x), float(final_y))
                    await asyncio.sleep(random.uniform(0.002, 0.008)) # Small delays between moves

                return float(final_x), float(final_y)
            except Exception as e:
                self.logger.warning(f"Could not perform human-like mouse move: {e}")
                return start_x, start_y

        async def _human_like_type(self, locator: Locator, text: str):
            """Types text into a locator one character at a time with random delays."""
            try:
                await locator.click(delay=random.uniform(1, 3)) # Small delay before typing starts
                for char in text:
                    await locator.press(char)
                    await asyncio.sleep(random.uniform(0.02, 0.2)) # Delay between characters
            except Exception as e:
                self.logger.warning(f"Could not perform human-like typing: {e}")
        async def solve(self) -> tuple[float, float]:
            """
            Attempts to solve the reCAPTCHA using audio challenge.
            Returns the final mouse coordinates after solving attempts.
            """

            # if await self._is_solved():
            #     self.logger.info("✅ Captcha was solved on page load (high trust).")
            #     return self.mouse_x, self.mouse_y

            # await self._click_checkbox_if_needed()
            # if await self._is_solved():
            #     self.logger.info("✅ Captcha solved after checkbox click (medium trust).")
            #     return self.mouse_x, self.mouse_y
            
            #^^^ Doesn't work if the checkbox is invisible or captcha is self triggered

            try:
                challenge_frame = self.page.frame_locator(self._IFRAME_CHALLENGE_SELECTOR)
                await self._solve_audio_challenge(challenge_frame)
            except Exception as e:
                self.logger.warning(f"Could not proceed to audio challenge. Assuming solved or error. ({e})", exc_info=self.verbose)
            
            return self.mouse_x, self.mouse_y

        async def _click_checkbox_if_needed(self):
            try:
                checkbox_frame = self.page.frame_locator(self._IFRAME_CHECKBOX_SELECTOR)
                checkbox_locator = checkbox_frame.locator(self._CHECKBOX_SELECTOR)
                await checkbox_locator.wait_for(timeout=1000) # Wait for checkbox iframe to appear
                


                if not await self._is_solved():
                    self.logger.info("Moving to and clicking the reCAPTCHA checkbox...")
                    self.mouse_x, self.mouse_y = await self.outer_instance._human_like_mouse_move(self.page, checkbox_locator, self.mouse_x, self.mouse_y)
                    await checkbox_locator.click(delay=random.uniform(50, 100))
                    await self.outer_instance._random_delay(1.5, 0.4)
            except Exception as e:
                self.logger.info(f"Checkbox not found or challenge appeared directly: {e.__class__.__name__} - {e}")

        async def _solve_audio_challenge(self, frame: FrameLocator, max_retries: int = 3):
            try:
                await frame.locator(self._AUDIO_BUTTON_SELECTOR).wait_for(timeout=4000)
                self.logger.info("Switching to audio challenge...")
                audio_btn_locator = frame.locator(self._AUDIO_BUTTON_SELECTOR)
                self.mouse_x, self.mouse_y = await self.outer_instance._human_like_mouse_move(self.page, audio_btn_locator, self.mouse_x, self.mouse_y)
                await audio_btn_locator.click()
                await self.outer_instance._random_delay(1, 0.3) # Give time for audio challenge to load
            except Exception as e:
                 raise RuntimeError(f"Could not find button to switch to audio challenge: {e}") from e
            
            for attempt in range(max_retries):
                try:
                    self.logger.info(f"Audio challenge attempt {attempt + 1}/{max_retries}")
                    audio_bytes = await self._download_audio(frame)
                    transcribed_text = self._transcribe_audio(audio_bytes)
                    self.logger.info(f"Transcription result: '{transcribed_text}'")
                    
                    if not transcribed_text:
                        self.logger.warning("Whisper returned empty text, reloading challenge.")
                        reload_button = frame.locator('#recaptcha-reload-button')
                        if await reload_button.is_visible():
                            await reload_button.click()
                        else:
                            self.logger.warning("Reload button not found, trying again without reload.")
                        await self.outer_instance._random_delay(2, 0.5)
                        continue

                    response_input_locator = frame.locator(self._AUDIO_RESPONSE_INPUT_SELECTOR)
                    await self.outer_instance._human_like_type(response_input_locator, transcribed_text)
                    await self.outer_instance._random_delay()
                    
                    verify_btn_locator = frame.locator(self._VERIFY_BUTTON_SELECTOR)
                    self.mouse_x, self.mouse_y = await self.outer_instance._human_like_mouse_move(self.page, verify_btn_locator, self.mouse_x, self.mouse_y)
                    await verify_btn_locator.click()
                    await self.outer_instance._random_delay(1.5, 0.3)
                    
                    if await self._is_solved():
                        self.logger.info("Captcha solved during audio challenge.")
                        return
                    else:
                        self.logger.warning("Verification failed, trying new audio.")
                        # Click reload button if available to get new audio
                        reload_button = frame.locator('#recaptcha-reload-button')
                        if await reload_button.is_visible():
                            await reload_button.click()
                            await self.outer_instance._random_delay(2, 0.5)

                except Exception as e:
                    self.logger.error(f"Error in audio attempt loop: {e}", exc_info=self.verbose)
                    if attempt == max_retries - 1: raise # Re-raise if last attempt fails

        async def _download_audio(self, frame: FrameLocator) -> bytes:
            download_link = frame.locator(self._AUDIO_DOWNLOAD_LINK_SELECTOR)
            await download_link.wait_for(timeout=10000)
            audio_url = await download_link.get_attribute('href')
            if not audio_url: raise ValueError("Could not find href for audio download.")
            async with httpx.AsyncClient() as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                return response.content

        def _transcribe_audio(self, audio_bytes: bytes) -> str:
            temp_file_path = "temp_audio_for_whisper.mp3"
            try:
                with open(temp_file_path, "wb") as f: f.write(audio_bytes)
                result = self.model.transcribe(temp_file_path, fp16=False)
                return result['text'].strip()
            finally:
                if os.path.exists(temp_file_path): os.remove(temp_file_path)

        async def _is_solved(self) -> bool:
            try:
                if await self.page.locator("text=Press PLAY to listen").is_visible() or await self.page.locator(self._IFRAME_CHALLENGE_SELECTOR).is_visible():
                    return False
                if await self.page.locator("text=Try again later").is_visible():
                    return False
                self.logger.info('Solved.')
                return True
                
            except Exception:
                if await self.page.locator("text=Try again later").is_visible():
                    raise RuntimeError("Recaptcha caught us for automation")
                return True