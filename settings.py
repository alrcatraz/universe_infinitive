# settings.py
import math

# --- 全局物理常量 (真实单位：吨, 千米, 秒) ---
G = 6.6743e-17
SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 768
FPS = 60

# --- 颜色库 ---
COLORS = {
    "yellow": (255, 255, 0), "blue": (100, 149, 237), "red": (205, 92, 92),
    "cyan": (0, 255, 255), "white": (255, 255, 255), "gray": (150, 150, 150),
    "dark_gray": (50, 50, 50), "green": (0, 255, 0), "orange": (255, 165, 0),
    "ui_bg": (20, 30, 40, 200),
    "menu_bg": (10, 15, 25),
    "highlight": (200, 200, 200, 50)
}