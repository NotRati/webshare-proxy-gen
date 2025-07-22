from .human_keyboard_type import _human_like_type
from .human_mouse_move import _human_like_mouse_move
from .key_distance import _key_distance
import logging
class HumanInteraction:
    human_like_type = _human_like_type
    human_like_mouse_move = _human_like_mouse_move
    _key_distance = staticmethod(_key_distance)
    def __init__(self, mouse_x: float = 0.0, mouse_y: float = 0.0, logger:logging.Logger= None):
        self.mouse_x = mouse_x
        self.mouse_y = mouse_y
        self.logger = logger