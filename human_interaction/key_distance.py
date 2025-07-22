# @staticmethod
def _key_distance(c1: str, c2: str) -> int:
    # Pre-computed layout for O(1) lookups instead of iterating lists
    _KEYBOARD_LAYOUT = {
        '1': (0, 0), '2': (0, 1), '3': (0, 2), '4': (0, 3), '5': (0, 4), '6': (0, 5), '7': (0, 6), '8': (0, 7), '9': (0, 8), '0': (0, 9),
        'q': (1, 0), 'w': (1, 1), 'e': (1, 2), 'r': (1, 3), 't': (1, 4), 'y': (1, 5), 'u': (1, 6), 'i': (1, 7), 'o': (1, 8), 'p': (1, 9),
        'a': (2, 0), 's': (2, 1), 'd': (2, 2), 'f': (2, 3), 'g': (2, 4), 'h': (2, 5), 'j': (2, 6), 'k': (2, 7), 'l': (2, 8),
        'z': (3, 0), 'x': (3, 1), 'c': (3, 2), 'v': (3, 3), 'b': (3, 4), 'n': (3, 5), 'm': (3, 6)
    }
    if not c1 or not c2:
        return 2 # Default distance for initial character or non-mappable chars

    pos1 = _KEYBOARD_LAYOUT.get(c1.lower())
    pos2 = _KEYBOARD_LAYOUT.get(c2.lower())

    if pos1 is None or pos2 is None:
        return 3 # Higher distance for special chars like '@' or '%'
    
    # Manhattan distance
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])