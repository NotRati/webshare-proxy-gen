import asyncio
import logging
from playwright.async_api import async_playwright, Page, Locator

from human_interaction import HumanInteraction # import your class here


async def demo():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("human_demo")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # show browser
        page = await browser.new_page()

        await page.goto("https://example.com")
        

        human = HumanInteraction(logger=logger)
        await page.evaluate("""
() => {
  // 1. Check if a cursor already exists to avoid creating multiple.
  if (document.getElementById('python-playwright-cursor')) {
    return;
  }

  // 2. Create the div element for our cursor.
  const cursorDiv = document.createElement('div');
  cursorDiv.id = 'python-playwright-cursor'; // Give it a unique ID

  // 3. Apply all the necessary styles directly.
  Object.assign(cursorDiv.style, {
    // Use 'fixed' positioning to place it relative to the viewport.
    position: 'fixed',
    top: '0px',
    left: '0px',

    // Visual appearance (let's make it green this time).
    width: '25px',
    height: '25px',
    backgroundColor: 'rgba(0, 200, 100, 0.5)',
    border: '2px solid darkgreen',
    borderRadius: '50%',

    // CRITICAL: Center the div on the actual cursor point.
    transform: 'translate(-50%, -50%)',

    // CRITICAL: Allow clicks and other events to pass through to elements underneath.
    pointerEvents: 'none',

    // Ensure the cursor is on top of all other content.
    zIndex: '99999'
  });

  // 4. Append the new div to the body of the document.
  document.body.appendChild(cursorDiv);

  // 5. Add an event listener to the document to track the mouse.
  document.addEventListener('mousemove', (event) => {
    // On every move, update the div's 'left' and 'top' style properties.
    // This provides the raw, unsmoothed tracking as requested.
    cursorDiv.style.left = `${event.clientX}px`;
    cursorDiv.style.top = `${event.clientY}px`;
  });
}

                """)
        # Let's say we want to move to the 'More information...' link
        locator = page.locator("a[href='https://www.iana.org/domains/example']")

        # Move mouse cursor human-like
        await human.human_like_mouse_move(page, locator)

        # Type something into an input (for demo, let's inject an input box)
        await page.evaluate("""() => {
            const input = document.createElement('input');
            input.id = 'demo-input';
            document.body.appendChild(input);
        }""")

        input_locator = page.locator("#demo-input")
        await input_locator.focus()

        await human.human_like_type(page, input_locator, "Hello, Playwright!")

        await asyncio.sleep(3)  # just to see result before closing
        await browser.close()


if __name__ == "__main__":
    asyncio.run(demo())
