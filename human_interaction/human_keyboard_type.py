import random
import asyncio
from playwright.async_api import Locator, Page
async def _human_like_type(self, page:Page, locator: Locator, text: str):
    # Configuration for human-like typing
    base_delay_ms = 20       # Average delay between keystrokes
    mistake_prob = 0.09      # 4% chance to make a typo on a character
    word_pause_mean_ms = 100 # Average pause after a word

    # Create a map of nearby keys for simulating typos
    _KEYBOARD_LAYOUT = {
        k: (r, c) for r, row in enumerate(["qwertyuiop", "asdfghjkl", "zxcvbnm"]) for c, k in enumerate(row)
    }
    _NEARBY_KEYS = {
        key: [k for k, pos2 in _KEYBOARD_LAYOUT.items() if abs(pos1[0] - pos2[0]) <= 1 and abs(pos1[1] - pos2[1]) <= 1 and k != key]
        for key, pos1 in _KEYBOARD_LAYOUT.items()
    }

    try:
        await self.human_like_mouse_move(page=page, locator=locator)
        await locator.click() # A user always clicks the input field first
        prev_char = ""
        for char in text:
            # 1. SIMULATE MISTAKES
            if char.lower() in _NEARBY_KEYS and random.random() < mistake_prob:
                mistake_char = random.choice(_NEARBY_KEYS[char.lower()])
                await locator.type(mistake_char, delay=random.uniform(70, 120))
                # Pause to "realize" the mistake
                await asyncio.sleep(random.uniform(0.1, 0.3))
                # Correct the mistake
                await locator.page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.15))

            # 2. CALCULATE DELAY with randomness
            distance = self._key_distance(prev_char, char)
            # Use a Gaussian distribution for more natural timing
            delay = random.gauss(
                mu=base_delay_ms + (distance * 12),  # Mean delay depends on key distance
                sigma=base_delay_ms / 3              # Standard deviation adds jitter
            )
            delay_ms = max(40, delay) # Ensure delay is not unrealistically fast

            await locator.type(char, delay=delay_ms)
            # self.logger.info(f"Typing char: '{char}' with delay of {int(delay_ms)}ms")
            
            # 3. ADD PAUSES after words or punctuation
            if char in " ,.;-!?":
                pause_duration_ms = random.gauss(word_pause_mean_ms, word_pause_mean_ms / 4)
                await asyncio.sleep(max(0.05, pause_duration_ms / 1000))

            prev_char = char
    except Exception as e:
        self.logger.warning(f"Could not fill text with human-like typing: {e}")