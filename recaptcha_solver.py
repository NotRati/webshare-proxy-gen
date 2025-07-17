# recaptcha_solver.py

import asyncio
import logging
import random
import os
from typing import Any

import httpx
import whisper
from playwright.async_api import Page, FrameLocator, Locator

class RecaptchaAudioSolver:
    """
    Solves reCAPTCHA challenges by transcribing the audio challenge using Whisper.
    This class is designed to be used by a parent automation script that provides
    human-like interaction methods and the Playwright page object.
    """
    # Selectors for various reCAPTCHA elements
    _IFRAME_CHALLENGE_SELECTOR = 'iframe[title*="recaptcha challenge"]'
    _AUDIO_BUTTON_SELECTOR = '#recaptcha-audio-button'
    _AUDIO_DOWNLOAD_LINK_SELECTOR = '.rc-audiochallenge-tdownload-link'
    _AUDIO_RESPONSE_INPUT_SELECTOR = '#audio-response'
    _VERIFY_BUTTON_SELECTOR = '#recaptcha-verify-button'

    def __init__(
        self,
        outer_instance: Any,  # The WebshareRegisterer instance
        page: Page,
        mouse_x: float,
        mouse_y: float,
        whisper_model: str = "base",
        verbose: bool = False,
    ):
        """
        Initializes the solver.

        Args:
            outer_instance: The parent class instance that provides human-like interaction methods
                            (e.g., _human_like_mouse_move, _human_like_type).
            page: The Playwright Page object where the CAPTCHA is located.
            mouse_x: The current X coordinate of the virtual mouse.
            mouse_y: The current Y coordinate of the virtual mouse.
            whisper_model: The name of the Whisper model to use for transcription.
            verbose: If True, enables detailed logging.
        """
        self.outer_instance = outer_instance
        self.page = page
        self.verbose = verbose
        self.logger = outer_instance.logger

        # self.logger.propagate = False
        # if not self.logger.handlers:
        #     handler = logging.StreamHandler()
        #     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        #     handler.setFormatter(formatter)
        #     self.logger.addHandler(handler)

        # self.logger.setLevel(logging.INFO if verbose else logging.WARNING)

        self.model = whisper.load_model(whisper_model)
        self.mouse_x = mouse_x
        self.mouse_y = mouse_y

    async def solve(self) -> tuple[float, float]:
        """
        Main method to orchestrate the solving of the reCAPTCHA.
        Returns the final mouse coordinates after all interactions.
        """
        try:
            challenge_frame = self.page.frame_locator(self._IFRAME_CHALLENGE_SELECTOR)
            await self._solve_audio_challenge(challenge_frame)
        except Exception as e:
            self.logger.error(f"Failed to solve audio challenge: {e}", exc_info=self.verbose)
            raise RuntimeError("Failed to solve CAPTCHA.") from e

        return self.mouse_x, self.mouse_y

    async def _solve_audio_challenge(self, frame: FrameLocator, max_retries: int = 3):
        try:
            await frame.locator(self._AUDIO_BUTTON_SELECTOR).wait_for(timeout=5000)
            self.logger.info("Switching to audio challenge...")
            audio_btn_locator = frame.locator(self._AUDIO_BUTTON_SELECTOR)
            self.mouse_x, self.mouse_y = await self.outer_instance._human_like_mouse_move(self.page, audio_btn_locator, self.mouse_x, self.mouse_y)
            await audio_btn_locator.click()
            await self.outer_instance._random_delay(1, 0.3)
        except Exception as e:
            raise RuntimeError(f"Could not find or click button to switch to audio challenge: {e}") from e

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
                    await self.outer_instance._random_delay(2, 0.5)
                    continue

                response_input_locator = frame.locator(self._AUDIO_RESPONSE_INPUT_SELECTOR)
                await self.outer_instance._human_like_type(response_input_locator, transcribed_text)
                await self.outer_instance._random_delay()

                verify_btn_locator = frame.locator(self._VERIFY_BUTTON_SELECTOR)
                self.mouse_x, self.mouse_y = await self.outer_instance._human_like_mouse_move(self.page, verify_btn_locator, self.mouse_x, self.mouse_y)
                await verify_btn_locator.click()
                await self.outer_instance._random_delay(2, 0.4)  # Wait for verification

                if await self._is_solved():
                    self.logger.info("Captcha solved successfully.")
                    return
                else:
                    self.logger.warning("Verification failed, trying new audio.")

            except Exception as e:
                self.logger.error(f"Error in audio attempt loop: {e}", exc_info=self.verbose)
                if attempt == max_retries - 1:
                    raise RuntimeError("Exceeded max retries for audio challenge.")

    async def _download_audio(self, frame: FrameLocator) -> bytes:
        download_link = frame.locator(self._AUDIO_DOWNLOAD_LINK_SELECTOR)
        await download_link.wait_for(timeout=10000)
        audio_url = await download_link.get_attribute('href')
        if not audio_url:
            raise ValueError("Could not find href for audio download.")
        async with httpx.AsyncClient() as client:
            response = await client.get(audio_url)
            response.raise_for_status()
            return response.content

    def _transcribe_audio(self, audio_bytes: bytes) -> str:
        temp_file_path = f"temp_audio_{random.randint(1000,9999)}.mp3"
        try:
            with open(temp_file_path, "wb") as f:
                f.write(audio_bytes)
            # Use fp16=False for CPU, which is more stable
            result = self.model.transcribe(temp_file_path, fp16=False)
            return result.get('text', '').strip()
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    async def _is_solved(self) -> bool:
        """Checks if the CAPTCHA is solved (i.e., the challenge frame is gone)."""
        try:
            # If the challenge iFrame is still visible after a short wait, it's not solved.
            challenge_frame = self.page.locator(self._IFRAME_CHALLENGE_SELECTOR)
            await challenge_frame.wait_for(state="hidden", timeout=2000)
            self.logger.info('Captcha appears to be solved (challenge frame is hidden).')
            return True
        except Exception:
            # A timeout here means the frame is still visible.
            self.logger.warning("CAPTCHA challenge frame is still visible. Not solved yet.")
            return False