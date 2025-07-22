import asyncio
import random
from playwright.async_api import Page, Locator
import math 

async def _human_like_mouse_move(self, page: Page, locator: Locator) -> tuple[float, float]:
    try:
        await asyncio.sleep(random.uniform(0.1, 0.4))

        box = await locator.bounding_box()
        if not box:
            self.logger.warning("Could not get bounding box for mouse move.")
            return self.mouse_x, self.mouse_y

        target_x = box['x'] + box['width'] / 2
        target_y = box['y'] + box['height'] / 2

        dist = math.hypot(target_x - self.mouse_x, target_y - self.mouse_y)

        if dist < 1:
            await page.mouse.move(float(target_x), float(target_y), steps=2)
            self.mouse_x, self.mouse_y = float(target_x), float(target_y)
            return self.mouse_x, self.mouse_y

        offset = max(10, dist * 0.2) * random.uniform(0.8, 1.2)
        angle_to_target = math.atan2(target_y - self.mouse_y, target_x - self.mouse_x)
        # Control points will be offset perpendicular to the line between start and end
        rand_angle_offset = math.radians(random.uniform(-90, 90))
        
        control_1_angle = angle_to_target - rand_angle_offset
        control_2_angle = angle_to_target + rand_angle_offset
        
        cp1_dist_ratio = random.uniform(0.2, 0.4)
        cp2_dist_ratio = random.uniform(0.6, 0.8)

        control_1_x = self.mouse_x + (dist * cp1_dist_ratio) * math.cos(control_1_angle)
        control_1_y = self.mouse_y + (dist * cp1_dist_ratio) * math.sin(control_1_angle)
        control_2_x = self.mouse_x + (dist * cp2_dist_ratio) * math.cos(control_2_angle)
        control_2_y = self.mouse_y + (dist * cp2_dist_ratio) * math.sin(control_2_angle)


        steps = max(20, int(dist / random.uniform(8, 15))) # More steps for longer distances
        
        def cubic_bezier(t, p0, p1, p2, p3):
            return (p0 * (1-t)**3) + (3 * p1 * t * (1-t)**2) + (3 * p2 * t**2 * (1-t)) + (p3 * t**3)

        for i in range(1, steps + 1):
            t = i / steps
            ease_t = t * t * (3.0 - 2.0 * t) # Ease-in-out
            
            x = cubic_bezier(ease_t, self.mouse_x, control_1_x, control_2_x, target_x)
            y = cubic_bezier(ease_t, self.mouse_y, control_1_y, control_2_y, target_y)

            await page.mouse.move(float(x), float(y))
            
            sleep_t = 0.5 - abs(t - 0.5)
            base_sleep = 0.015
            await asyncio.sleep(random.uniform(base_sleep * 0.5, base_sleep + sleep_t * 0.03))


        final_x, final_y = target_x, target_y # Start with the target
        # for _ in range(random.randint(1, 3)):
        #     fidget_x = target_x + random.uniform(-3, 3)
        #     fidget_y = target_y + random.uniform(-3, 3)
        #     await page.mouse.move(float(fidget_x), float(fidget_y), steps=random.randint(2, 4))
        #     await asyncio.sleep(random.uniform(0.03, 0.08))
        #     # Update the final position after each fidget
        #     final_x, final_y = fidget_x, fidget_y

        self.mouse_x, self.mouse_y = float(final_x), float(final_y)
        return self.mouse_x, self.mouse_y


    except Exception as e:
        self.logger.warning(f"Could not perform human-like mouse move: {e}")
        return self.mouse_x, self.mouse_y