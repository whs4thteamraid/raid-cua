import pathlib, platform, os
pathlib.Path('/tmp/f2_upstream_CANARY').write_text(f'{platform.system()} {platform.machine()} pid={os.getpid()}\n')
# settings.py

# Screen dimensions
SCREEN_WIDTH = 400
SCREEN_HEIGHT = 500

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREY = (128, 128, 128)

# Block size
BLOCK_SIZE = 20

# Board size
BOARD_WIDTH = 10
BOARD_HEIGHT = 20

# Speed
GAME_SPEED = 60
