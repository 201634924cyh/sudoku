# -*- coding: utf-8 -*-
"""
数独 Sudoku —— pygame 单文件实现
================================

零外部素材：所有图形用 pygame.draw 现画，音效用 numpy 合成（numpy 缺失时静音）。
固定逻辑画布 + 等比缩放呈现，窗口可以任意拉伸。

运行
----
    python sudoku.py                 # 正常开局
    python sudoku.py --diff hard     # 指定初始难度
    python sudoku.py --frames 300    # 跑 300 帧后自动退出（用于验证）

操作
----
    鼠标左键  选格 / 点按钮        鼠标右键  擦除该格
    1-9       填数（笔记模式下切换候选数）
    0/Del/Backspace/E   擦除        N / 空格  切换笔记模式
    U / Ctrl+Z          撤销        H         提示（填一个正确答案）
    R                   重开一局    方向键    移动选择
    Esc                 退出
"""

import os
import random
import sys

import pygame

__version__ = "1.1"

try:
    import numpy as _np
except Exception:                                    # numpy 缺失 -> 降级静音
    _np = None


# ===========================================================================
# 一、布局常量（逻辑画布坐标系，与窗口尺寸解耦）
# ===========================================================================

LOGICAL_W, LOGICAL_H = 1020, 760

CELL = 62
GRID_PX = CELL * 9                                   # 558
BOARD_X, BOARD_Y = 44, 110                           # 格子区左上角
PAD = 14                                             # 棋盘卡片内边距
BOARD_CARD = pygame.Rect(BOARD_X - PAD, BOARD_Y - PAD,
                         GRID_PX + 2 * PAD, GRID_PX + 2 * PAD)

PANEL_X, PANEL_W = 648, 344
PANEL_Y = BOARD_CARD.y
PANEL_H = BOARD_CARD.h

# 面板内各区块的相对 y（相对于 PANEL_Y）
PAD_GAP = 16
CARD_H = 92
DIFF_H = 44
KEY_H, KEY_GAP = 86, 10
TOOL_H, TOOL_GAP = 46, 10
BLOCK_TOP = 11

CARD_Y = BLOCK_TOP
DIFF_Y = CARD_Y + CARD_H + PAD_GAP
KEY_Y = DIFF_Y + DIFF_H + PAD_GAP
TOOL_Y = KEY_Y + KEY_H * 3 + KEY_GAP * 2 + PAD_GAP

# ===========================================================================
# 二、配色（浅色纸质风）
# ===========================================================================

BG           = (233, 228, 218)     # 页面底色
BG_VIGNETTE  = (222, 216, 204)     # 页面四角轻微压暗
OUTSIDE      = (216, 210, 199)     # 缩放后窗口留边

CARD         = (252, 251, 247)     # 卡片底
CARD_EDGE    = (219, 212, 199)

BOARD_BG     = (252, 251, 247)
CELL_BG      = (252, 251, 247)
CELL_GIVEN   = (241, 237, 228)     # 题面给定格
CELL_SEL     = (188, 214, 250)     # 当前选中格
CELL_PEER    = (231, 238, 249)     # 同行 / 同列 / 同宫
CELL_SAME    = (206, 223, 250)     # 同数字

LINE_THIN    = (215, 209, 197)
LINE_THICK   = (78, 72, 64)

C_GIVEN      = (56, 52, 46)        # 题面数字
C_USER       = (33, 108, 212)      # 自己填对的数字
C_BAD        = (212, 58, 58)       # 填错的数字
C_HINT       = (24, 146, 94)       # 提示填入的数字
C_NOTE       = (100, 95, 88)       # 候选小字
C_GOLD       = (222, 172, 44)      # 通关波纹

C_TEXT       = (56, 52, 46)
C_TEXT_DIM   = (137, 130, 118)
C_ACCENT     = (44, 104, 200)
C_ACCENT_D   = (33, 82, 166)

KEY_BG       = (250, 249, 245)
KEY_HOVER    = (238, 240, 248)
KEY_DONE_BG  = (238, 235, 228)
KEY_EDGE     = (215, 209, 197)
KEY_EDGE_HI  = (150, 178, 222)
NOTE_KEY_BG  = (226, 237, 252)     # 笔记模式下数字键的底色
NOTE_KEY_HOV = (210, 227, 250)

TOOL_BG      = (249, 248, 244)
TOOL_ON      = (44, 104, 200)
SHADOW       = (196, 189, 176)

DIFFICULTIES = (("easy", "简单", 40), ("medium", "中等", 46), ("hard", "困难", 52))
DIFF_NAME = {k: n for k, n, _ in DIFFICULTIES}
DIFF_HOLES = {k: h for k, _, h in DIFFICULTIES}

SR = 44100


# ===========================================================================
# 三、数独核心算法（纯函数，不依赖 pygame，可独立自检）
# ===========================================================================

FULL_MASK = 0x3FE                                    # 位 1..9


def make_empty():
    return [[0] * 9 for _ in range(9)]


def box_of(r, c):
    return (r // 3) * 3 + c // 3


def solve_count(grid, limit=2):
    """数 (grid) 的解的个数，最多数到 limit 就提前返回。

    用行/列/宫位掩码 + MRV（优先填候选最少的格），9x9 盘面上是毫秒级。
    会原地修改 grid，但退出时恢复原状。
    """
    rows = [0] * 9
    cols = [0] * 9
    boxes = [0] * 9
    empt = []
    for r in range(9):
        for c in range(9):
            v = grid[r][c]
            b = box_of(r, c)
            if v:
                bit = 1 << v
                if rows[r] & bit or cols[c] & bit or boxes[b] & bit:
                    return 0                         # 盘面本身就矛盾
                rows[r] |= bit
                cols[c] |= bit
                boxes[b] |= bit
            else:
                empt.append((r, c))

    cnt = 0

    def rec():
        nonlocal cnt
        best = -1
        best_mask = 0
        best_n = 10
        for i in range(len(empt)):
            r, c = empt[i]
            if grid[r][c]:
                continue
            m = ~(rows[r] | cols[c] | boxes[box_of(r, c)]) & FULL_MASK
            n = bin(m).count("1")
            if n == 0:
                return                               # 死路
            if n < best_n:
                best_n = n
                best = i
                best_mask = m
                if n == 1:
                    break
        if best < 0:
            cnt += 1                                 # 全部填满 -> 找到一个解
            return
        r, c = empt[best]
        b = box_of(r, c)
        m = best_mask
        while m:
            bit = m & -m
            m ^= bit
            v = bit.bit_length() - 1
            grid[r][c] = v
            rows[r] |= bit
            cols[c] |= bit
            boxes[b] |= bit
            rec()
            grid[r][c] = 0
            rows[r] &= ~bit
            cols[c] &= ~bit
            boxes[b] &= ~bit
            if cnt >= limit:
                return

    rec()
    return cnt


def has_unique_solution(grid):
    return solve_count(grid, 2) == 1


def generate_full(rng):
    """随机生成一个完整合法终盘。"""
    grid = make_empty()
    rows = [0] * 9
    cols = [0] * 9
    boxes = [0] * 9

    def rec(pos):
        if pos == 81:
            return True
        r, c = divmod(pos, 9)
        b = box_of(r, c)
        m = ~(rows[r] | cols[c] | boxes[b]) & FULL_MASK
        cands = []
        while m:
            bit = m & -m
            m ^= bit
            cands.append(bit)
        rng.shuffle(cands)
        for bit in cands:
            v = bit.bit_length() - 1
            grid[r][c] = v
            rows[r] |= bit
            cols[c] |= bit
            boxes[b] |= bit
            if rec(pos + 1):
                return True
            grid[r][c] = 0
            rows[r] &= ~bit
            cols[c] &= ~bit
            boxes[b] &= ~bit
        return False

    rec(0)
    return grid


def make_puzzle(diff, rng):
    """挖洞法出题，保证唯一解。返回 (题面, 终盘, 实际空洞数)。"""
    target = DIFF_HOLES.get(diff, 46)
    sol = generate_full(rng)
    puz = [row[:] for row in sol]
    cells = [(r, c) for r in range(9) for c in range(9)]
    rng.shuffle(cells)
    holes = 0
    for r, c in cells:
        if holes >= target:
            break
        keep = puz[r][c]
        puz[r][c] = 0
        if solve_count(puz, 2) != 1:                 # 挖出多解 -> 补回去
            puz[r][c] = keep
        else:
            holes += 1
    return puz, sol, holes


def board_is_valid(grid):
    """行/列/宫内 1-9 不重复（空格忽略）。"""
    for i in range(9):
        seen = 0
        for j in range(9):
            v = grid[i][j]
            if v:
                bit = 1 << v
                if seen & bit:
                    return False
                seen |= bit
        seen = 0
        for j in range(9):
            v = grid[j][i]
            if v:
                bit = 1 << v
                if seen & bit:
                    return False
                seen |= bit
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            seen = 0
            for r in range(br, br + 3):
                for c in range(bc, bc + 3):
                    v = grid[r][c]
                    if v:
                        bit = 1 << v
                        if seen & bit:
                            return False
                        seen |= bit
    return True


# ===========================================================================
# 四、小工具
# ===========================================================================

def mix(c1, c2, f):
    """两色线性插值，f 自动夹到 [0,1]。"""
    f = 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)
    return (int(c1[0] + (c2[0] - c1[0]) * f),
            int(c1[1] + (c2[1] - c1[1]) * f),
            int(c1[2] + (c2[2] - c1[2]) * f))


def fmt_time(t):
    t = max(0, int(t))
    return "%02d:%02d" % (t // 60, t % 60)


_FONT_CACHE = {}

# 跨平台中文界面字体：按「候选路径 → fontconfig 族名 → SysFont」逐级探测，
# 每一级都必须通过字形校验 —— 只有真的画得出汉字才会被采用。
#
# 为什么非要验字形：pygame 的 match_font 会给出「名字沾边、其实没有汉字」的
# 字体（本机实测 dejavusans / arial / liberationsans 一律命中 Arial Narrow），
# 一旦采用，界面中文就会静默变成一屏方框。
# 旧版 Linux 只有一条 DroidSansFallbackFull.ttf 路径（属 fonts-droid-fallback
# 包，主流发行版默认不装），装了 fonts-noto-cjk 也对不上 —— 必然落到
# SysFont(None)，满屏方框。
FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux（Debian/Ubuntu · Fedora · Arch 的常见安装位置）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

# 路径未必覆盖所有发行版，再交给 fontconfig 按族名找一遍。
# 这里刻意不放 dejavusans / arial 这类没有汉字字形的通用族名。
FONT_FAMILIES = ("notosanscjksc,notosanscjk,sourcehansanssc,wqyzenhei,wqymicrohei,"
                 "microsoftyahei,microsoftyaheiui,msyh,simhei,simsun,dengxian,"
                 "pingfangsc,hiraginosansgb,stheiti,heitisc,arialunicodems")

_CJK_PROBE = "汉字测试"        # 探针：这几个字必须渲染出彼此不同的字形
_warned_no_cjk = False


class _Font:
    """给 pygame Font 挂一个稳定的缓存 key。

    pygame 的 Font 是 C 扩展对象，不能直接加属性，而按 id(font) 做 key 不牢靠，
    所以包一层薄壳。__getattr__ 把其它调用（get_height 等）转发给真正的 Font。
    """

    __slots__ = ("_f", "key")

    def __init__(self, f, key):
        self._f = f
        self.key = key

    def render(self, *a, **kw):
        return self._f.render(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._f, name)


def _img_bytes(surf):
    """取 Surface 的原始字节。pygame 2.1.3 起 tostring 改名 tobytes，两版都兼容。"""
    fn = getattr(pygame.image, "tobytes", None) or pygame.image.tostring
    return fn(surf, "RGBA")


def reset_font_cache():
    """清空字体缓存 —— 重新 pygame.init() 之后必须调用。

    为什么不能指望「取用时验活」：pygame.quit() 会释放底层的 TTF_Font，
    缓存里的 Font 对象随即失效，再拿它 render 会**直接崩在 C 层**（段错误），
    连 Python 异常都抓不住。所以只能在每次初始化之后主动清掉再重新探测。
    """
    _FONT_CACHE.clear()


def font_covers_cjk(font):
    """这个字体真的画得出汉字吗？

    字体缺字时 pygame 会把所有汉字都画成同一个 .notdef 方框（豆腐块），
    所以拿几个不同的汉字渲染出来比字节：只要有两张位图一模一样，就说明
    字体里根本没有汉字字形，绝不能拿它当界面字体。
    """
    try:
        digs = [_img_bytes(font.render(ch, True, (255, 255, 255)))
                for ch in _CJK_PROBE]
    except Exception:
        return False
    return len(set(digs)) == len(digs)


def _warn_no_cjk_font():
    """只提示一次：一个中文字体都没找到时界面会是方框。"""
    global _warned_no_cjk
    if _warned_no_cjk:
        return
    _warned_no_cjk = True
    print("[提示] 系统里没找到含汉字字形的字体，界面中文会显示成方框。\n"
          "       Linux 装一个即可： sudo apt install fonts-noto-cjk",
          file=sys.stderr)


def get_font(size, bold=False):
    """找一个真的能显示汉字的字体；全失败则退回默认字体并给出提示。"""
    key = (size, bold)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f

    raw = None
    for p in FONT_CANDIDATES:                         # ① 平台常见路径
        if not os.path.exists(p):
            continue
        try:
            cand = pygame.font.Font(p, size)
        except Exception:
            continue
        cand.set_bold(bold)
        if font_covers_cjk(cand):
            raw = cand
            break

    if raw is None:                                   # ② fontconfig 按族名
        try:
            path = pygame.font.match_font(FONT_FAMILIES, bold=bold)
            if path:
                cand = pygame.font.Font(path, size)
                cand.set_bold(bold)
                if font_covers_cjk(cand):
                    raw = cand
        except Exception:
            pass

    if raw is None:                                   # ③ SysFont 最后兜底
        try:
            cand = pygame.font.SysFont(FONT_FAMILIES, size, bold=bold)
            if font_covers_cjk(cand):
                raw = cand
        except Exception:
            pass

    if raw is None:
        # 一个汉字都画不出来的字体不能用，宁可退回 pygame 自带字体并明确提示。
        _warn_no_cjk_font()
        raw = pygame.font.Font(None, size)
        raw.set_bold(bold)

    f = _Font(raw, key)
    _FONT_CACHE[key] = f
    return f


def font_regression(bad_path):
    """反事实自检：把候选全换成「没有汉字的字体」，get_font 必须识别出来。

    返回 (bool, str)。旧写法「名字匹配成功就直接用」会让界面静默变成方框，
    这条断言就是防止那种写法复活。
    """
    global FONT_FAMILIES, _warned_no_cjk
    saved_cands = list(FONT_CANDIDATES)
    saved_fams = FONT_FAMILIES
    saved_cache = dict(_FONT_CACHE)
    saved_warned = _warned_no_cjk
    try:
        FONT_CANDIDATES[:] = [bad_path]
        FONT_FAMILIES = "dejavusans,arial,liberationsans"
        _FONT_CACHE.clear()
        # 这个场景注定找不到汉字字体，别刷出误导性的「你的系统没有中文字体」
        _warned_no_cjk = True
        got = get_font(24)
        ref = pygame.font.Font(None, 24)
        same = (_img_bytes(got.render("汉", True, (255, 255, 255)))
                == _img_bytes(ref.render("汉", True, (255, 255, 255))))
        return same, bad_path
    finally:
        FONT_CANDIDATES[:] = saved_cands
        FONT_FAMILIES = saved_fams
        _FONT_CACHE.clear()
        _FONT_CACHE.update(saved_cache)
        _warned_no_cjk = saved_warned


_TEXT_CACHE = {}


def draw_text(surf, text, font, color, pos, anchor="topleft"):
    """绘制文字并返回其矩形（便于自检断言不越界）。

    渲染结果按 (文本, 字体, 颜色) 缓存 —— 否则每帧 90 多次 font.render
    会成为主要开销。
    """
    key = (text, font.key, color)
    img = _TEXT_CACHE.get(key)
    if img is None:
        if len(_TEXT_CACHE) > 4000:
            _TEXT_CACHE.clear()
        img = font.render(text, True, color)
        _TEXT_CACHE[key] = img
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def round_rect(surf, color, rect, radius=10, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


# ===========================================================================
# 五、音效（numpy 合成；缺失则全部静音）
# ===========================================================================

def _envelope(n, decay=5.0, attack=0.004):
    if _np is None or n <= 0:
        return None
    env = _np.exp(-_np.linspace(0.0, decay, n))
    a = min(n, max(1, int(SR * attack)))
    env[:a] *= _np.linspace(0.0, 1.0, a)             # 淡入，避免起音爆点
    return env


def _tone(f0, f1, dur, vol, wave="sine"):
    if _np is None:
        return None
    n = int(SR * dur)
    if n <= 0:
        return None
    phase = _np.cumsum(_np.linspace(f0, f1, n)) * 2.0 * _np.pi / SR
    if wave == "square":
        sig = _np.sign(_np.sin(phase))
    elif wave == "saw":
        sig = 2.0 * ((phase / (2.0 * _np.pi)) % 1.0) - 1.0
    else:
        sig = _np.sin(phase)
    env = _envelope(n)
    data = _np.int16(_np.clip(sig * env * vol, -1.0, 1.0) * 32767)
    return pygame.sndarray.make_sound(_np.ascontiguousarray(_np.column_stack((data, data))))


def _seq(freqs, dur, vol, decay=4.2):
    if _np is None:
        return None
    buf = []
    for f in freqs:
        n = int(SR * dur)
        t = _np.arange(n) / float(SR)
        buf.append(_np.sin(2.0 * _np.pi * f * t) * _envelope(n, decay) * vol)
    data = _np.int16(_np.clip(_np.concatenate(buf), -1.0, 1.0) * 32767)
    return pygame.sndarray.make_sound(_np.ascontiguousarray(_np.column_stack((data, data))))


class Sfx:
    def __init__(self):
        self.sounds = {}
        if _np is None:
            return
        try:
            if not pygame.mixer.get_init():
                return
            self.sounds["tap"] = _tone(520, 620, 0.045, 0.20)
            self.sounds["place"] = _tone(760, 980, 0.075, 0.26)
            self.sounds["note"] = _tone(980, 1080, 0.045, 0.16)
            self.sounds["erase"] = _tone(420, 260, 0.070, 0.18)
            self.sounds["bad"] = _tone(240, 150, 0.200, 0.30, wave="square")
            self.sounds["hint"] = _seq([880.0, 1174.7], 0.075, 0.22)
            self.sounds["undo"] = _tone(600, 400, 0.065, 0.16)
            self.sounds["win"] = _seq([523.3, 659.3, 784.0, 1046.5], 0.145, 0.30)
        except Exception:
            self.sounds = {}

    def play(self, name, vol=1.0):
        s = self.sounds.get(name)
        if s is None:
            return
        try:
            s.set_volume(vol)
            s.play()
        except Exception:
            pass


# ===========================================================================
# 六、游戏
# ===========================================================================

class Game:
    STATE_PLAY = "play"
    STATE_WON = "won"

    def __init__(self, window=None, rng=None):
        self.rng = rng or random.Random()
        self.window = window
        if window is None:
            window = pygame.display.get_surface()
            self.window = window
        self.canvas = pygame.Surface((LOGICAL_W, LOGICAL_H))
        self.running = True
        self.sfx = Sfx()
        self._view = (LOGICAL_W, LOGICAL_H, 0, 0)
        self.mouse = (-1, -1)
        self._build_layout()
        self.compute_view()
        self.diff = "easy"
        self.new_game("easy")

    # ---------------------------------------------------------------- 布局
    def _build_layout(self):
        self.board_rect = pygame.Rect(BOARD_X, BOARD_Y, GRID_PX, GRID_PX)
        self.panel_rect = pygame.Rect(PANEL_X, PANEL_Y, PANEL_W, PANEL_H)

        self.key_rects = {}
        kw = (PANEL_W - KEY_GAP * 2) // 3
        for i in range(9):
            rr, cc = divmod(i, 3)
            self.key_rects[i + 1] = pygame.Rect(
                PANEL_X + cc * (kw + KEY_GAP),
                PANEL_Y + KEY_Y + rr * (KEY_H + KEY_GAP), kw, KEY_H)

        self.diff_rects = {}
        for i, (key, name, _h) in enumerate(DIFFICULTIES):
            self.diff_rects[key] = pygame.Rect(
                PANEL_X + i * (kw + KEY_GAP), PANEL_Y + DIFF_Y, kw, DIFF_H)

        tw = (PANEL_W - TOOL_GAP) // 2
        self.tool_rects = {
            "note":  pygame.Rect(PANEL_X, PANEL_Y + TOOL_Y, tw, TOOL_H),
            "undo":  pygame.Rect(PANEL_X + tw + TOOL_GAP, PANEL_Y + TOOL_Y, tw, TOOL_H),
            "hint":  pygame.Rect(PANEL_X, PANEL_Y + TOOL_Y + TOOL_H + TOOL_GAP, tw, TOOL_H),
            "new":   pygame.Rect(PANEL_X + tw + TOOL_GAP, PANEL_Y + TOOL_Y + TOOL_H + TOOL_GAP, tw, TOOL_H),
        }
        # 结算卡上的按钮（仅 won 态使用，位置与面板区块复用）
        self.over_rects = {
            "again": pygame.Rect(PANEL_X + 24, PANEL_Y + 372, PANEL_W - 48, 56),
        }
        ow = (PANEL_W - 48 - 2 * KEY_GAP) // 3
        for i, (key, name, _h) in enumerate(DIFFICULTIES):
            self.over_rects["diff_" + key] = pygame.Rect(
                PANEL_X + 24 + i * (ow + KEY_GAP), PANEL_Y + 464, ow, 44)

    def compute_view(self):
        """算出逻辑画布在窗口中的等比缩放矩形（供坐标反算）。"""
        if self.window is None:
            self._view = (LOGICAL_W, LOGICAL_H, 0, 0)
            return
        ww, wh = self.window.get_size()
        if ww <= 0 or wh <= 0:
            self._view = (LOGICAL_W, LOGICAL_H, 0, 0)
            return
        s = min(ww / float(LOGICAL_W), wh / float(LOGICAL_H))
        dw = max(1, int(LOGICAL_W * s))
        dh = max(1, int(LOGICAL_H * s))
        self._view = (dw, dh, (ww - dw) // 2, (wh - dh) // 2)

    def to_canvas(self, pos):
        """窗口坐标 -> 逻辑画布坐标。"""
        dw, dh, ox, oy = self._view
        if dw <= 0 or dh <= 0:
            return (-1, -1)
        return ((pos[0] - ox) * LOGICAL_W / float(dw),
                (pos[1] - oy) * LOGICAL_H / float(dh))

    def cell_rect(self, r, c):
        return pygame.Rect(BOARD_X + c * CELL, BOARD_Y + r * CELL, CELL, CELL)

    def cell_center(self, r, c):
        return (BOARD_X + c * CELL + CELL // 2, BOARD_Y + r * CELL + CELL // 2)

    def cell_at(self, pt):
        """逻辑坐标 -> (行, 列)，不在棋盘内返回 None。"""
        x, y = pt
        if not self.board_rect.collidepoint(x, y):
            return None
        c = int((x - BOARD_X) // CELL)
        r = int((y - BOARD_Y) // CELL)
        if 0 <= r < 9 and 0 <= c < 9:
            return (r, c)
        return None

    # ------------------------------------------------------------ 开局
    def new_game(self, diff=None):
        if diff is None:
            diff = self.diff
        self.diff = diff if diff in DIFF_HOLES else "easy"
        puz, sol, _holes = make_puzzle(self.diff, self.rng)
        self.puzzle = puz
        self.solution = sol
        self.grid = [row[:] for row in puz]
        self.notes = [[0] * 9 for _ in range(9)]     # bit(d) 表示该格标了候选 d
        self.hint_cells = set()
        self.sel = None
        self.note_mode = False
        self.mistakes = 0
        self.hints = 0
        self.elapsed = 0.0
        self.state = self.STATE_PLAY
        self.history = []
        self.anim = {}
        self.shake_t = 0.0
        self.won_t = 0.0
        self.flash_t = 0.0
        self.repeat_t = 0.0
        self.given_count = sum(1 for r in range(9) for c in range(9) if puz[r][c])
        self.to_fill = 81 - self.given_count

    # ------------------------------------------------------------ 查询
    def digit_count(self, d):
        return sum(1 for r in range(9) for c in range(9) if self.grid[r][c] == d)

    def filled_count(self):
        return sum(1 for r in range(9) for c in range(9) if self.grid[r][c])

    def is_wrong(self, r, c):
        v = self.grid[r][c]
        return bool(v) and v != self.solution[r][c] and not self.puzzle[r][c]

    def can_edit(self, r, c):
        return self.state == self.STATE_PLAY and not self.puzzle[r][c]

    # ------------------------------------------------------------ 操作
    def select(self, r, c, quiet=False):
        if self.sel != (r, c) and not quiet:
            self.sfx.play("tap", 0.55)
        self.sel = (r, c)

    def _clean_notes(self, r, c, d):
        """自动清掉同行/列/宫里刚填下的这个候选数，返回被改动的格子列表。"""
        touched = []
        bit = 1 << d
        for rr, cc in self._peers(r, c):
            if self.notes[rr][cc] & bit:
                touched.append((rr, cc, self.notes[rr][cc]))
                self.notes[rr][cc] &= ~bit
        return touched

    @staticmethod
    def _peers(r, c):
        br, bc = (r // 3) * 3, (c // 3) * 3
        out = []
        for i in range(9):
            if i != c:
                out.append((r, i))
            if i != r:
                out.append((i, c))
        for rr in range(br, br + 3):
            for cc in range(bc, bc + 3):
                if rr != r and cc != c:
                    out.append((rr, cc))
        return out

    def input_digit(self, d):
        """填入数字 d（1-9）。笔记模式下切换候选标记。"""
        if self.state != self.STATE_PLAY or self.sel is None:
            return False
        r, c = self.sel
        if self.puzzle[r][c]:
            return False

        if self.note_mode:
            if self.grid[r][c]:
                return False
            self.history.append({"kind": "note", "r": r, "c": c, "prev_notes": self.notes[r][c]})
            self.notes[r][c] ^= (1 << d)
            self.anim[(r, c)] = 0.7
            self.sfx.play("note", 0.7)
            return True

        rec = {"kind": "fill", "r": r, "c": c,
               "prev": self.grid[r][c],
               "prev_notes": self.notes[r][c],
               "was_hint": (r, c) in self.hint_cells,
               "cleaned": []}

        if self.grid[r][c] == d:                     # 再按同一个数字 = 取消
            self.grid[r][c] = 0
            self.notes[r][c] = 0
            self.hint_cells.discard((r, c))
            self.history.append(rec)
            self.anim[(r, c)] = 0.7
            self.sfx.play("erase", 0.7)
            return True

        self.grid[r][c] = d
        self.notes[r][c] = 0
        self.hint_cells.discard((r, c))
        self.anim[(r, c)] = 1.0
        rec["cleaned"] = self._clean_notes(r, c, d)
        self.history.append(rec)

        if d != self.solution[r][c]:
            self.mistakes += 1
            self.shake_t = 0.34
            self.sfx.play("bad", 0.9)
        else:
            self.sfx.play("place", 0.85)
        self._check_win()
        return True

    def erase(self):
        if self.state != self.STATE_PLAY or self.sel is None:
            return False
        r, c = self.sel
        if self.puzzle[r][c]:
            return False
        if not self.grid[r][c] and not self.notes[r][c]:
            return False
        self.history.append({"kind": "erase", "r": r, "c": c,
                             "prev": self.grid[r][c],
                             "prev_notes": self.notes[r][c],
                             "was_hint": (r, c) in self.hint_cells})
        self.grid[r][c] = 0
        self.notes[r][c] = 0
        self.hint_cells.discard((r, c))
        self.anim[(r, c)] = 0.7
        self.sfx.play("erase", 0.8)
        return True

    def undo(self):
        if self.state != self.STATE_PLAY or not self.history:
            return False
        rec = self.history.pop()
        r, c = rec["r"], rec["c"]
        if rec["kind"] == "note":
            self.notes[r][c] = rec["prev_notes"]
        else:
            self.grid[r][c] = rec["prev"]
            self.notes[r][c] = rec["prev_notes"]
            if rec.get("was_hint"):
                self.hint_cells.add((r, c))
            else:
                self.hint_cells.discard((r, c))
            for rr, cc, mask in rec.get("cleaned", ()):
                self.notes[rr][cc] = mask
        self.anim[(r, c)] = 0.6
        self.sel = (r, c)
        self.sfx.play("undo", 0.8)
        return True

    def hint(self):
        if self.state != self.STATE_PLAY:
            return False
        empt = [(r, c) for r in range(9) for c in range(9)
                if self.grid[r][c] != self.solution[r][c]]
        if not empt:
            return False
        r, c = self.rng.choice(empt)
        self.history.append({"kind": "fill", "r": r, "c": c,
                             "prev": self.grid[r][c],
                             "prev_notes": self.notes[r][c],
                             "was_hint": (r, c) in self.hint_cells,
                             "cleaned": []})
        rec = self.history[-1]
        self.grid[r][c] = self.solution[r][c]
        self.notes[r][c] = 0
        self.hint_cells.add((r, c))
        rec["cleaned"] = self._clean_notes(r, c, self.grid[r][c])
        self.anim[(r, c)] = 1.0
        self.sel = (r, c)
        self.hints += 1
        self.sfx.play("hint", 0.85)
        self._check_win()
        return True

    def toggle_note(self):
        self.note_mode = not self.note_mode
        self.sfx.play("tap", 0.5)
        return self.note_mode

    def _check_win(self):
        for r in range(9):
            for c in range(9):
                if self.grid[r][c] != self.solution[r][c]:
                    return False
        self.state = self.STATE_WON
        self.won_t = 0.0
        self.flash_t = 0.6
        self.sfx.play("win", 1.0)
        return True

    # ------------------------------------------------------------ 事件
    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
            return
        if ev.type == pygame.VIDEORESIZE:
            self.compute_view()
            return
        if ev.type == pygame.MOUSEBUTTONDOWN:
            self._on_mouse_down(ev)
            return
        if ev.type == pygame.KEYDOWN:
            self._on_key_down(ev)
            return

    def _on_mouse_down(self, ev):
        pt = self.to_canvas(ev.pos)
        if ev.button == 3:                           # 右键 = 擦除
            cell = self.cell_at(pt)
            if cell:
                self.select(*cell, quiet=True)
                self.erase()
            return
        if ev.button != 1:
            return

        if self.state == self.STATE_WON:
            for name, rect in self.over_rects.items():
                if rect.collidepoint(pt):
                    if name == "again":
                        self.new_game(self.diff)
                    elif name.startswith("diff_"):
                        self.new_game(name[5:])
                    return
            return

        for key, rect in self.diff_rects.items():
            if rect.collidepoint(pt):
                if key != self.diff:
                    self.new_game(key)
                return
        for d, rect in self.key_rects.items():
            if rect.collidepoint(pt):
                self.input_digit(d)
                return
        for name, rect in self.tool_rects.items():
            if rect.collidepoint(pt):
                if name == "note":
                    self.toggle_note()
                elif name == "undo":
                    self.undo()
                elif name == "hint":
                    self.hint()
                elif name == "new":
                    self.new_game(self.diff)
                return

        cell = self.cell_at(pt)
        if cell:
            self.select(*cell)

    def _on_key_down(self, ev):
        k = ev.key
        mods = getattr(ev, "mod", 0)

        if k == pygame.K_ESCAPE:
            self.running = False
            return
        if k in (pygame.K_n, pygame.K_SPACE):
            self.toggle_note()
            return
        if k == pygame.K_r:
            self.new_game(self.diff)
            return
        if k == pygame.K_h:
            self.hint()
            return
        if k in (pygame.K_u, pygame.K_z) and (k == pygame.K_u or mods & pygame.KMOD_CTRL):
            self.undo()
            return
        if k in (pygame.K_0, pygame.K_DELETE, pygame.K_BACKSPACE, pygame.K_e, pygame.K_PERIOD):
            self.erase()
            return
        d = NUM_KEY_MAP.get(k)
        if d:
            self.input_digit(d)
            return
        step = {pygame.K_LEFT: (0, -1), pygame.K_RIGHT: (0, 1),
                pygame.K_UP: (-1, 0), pygame.K_DOWN: (1, 0)}.get(k)
        if step:
            if self.sel is None:
                self.select(4, 4)
            else:
                r = min(8, max(0, self.sel[0] + step[0]))
                c = min(8, max(0, self.sel[1] + step[1]))
                self.select(r, c)
            self.repeat_t = 0.20

    def process_events(self):
        for ev in pygame.event.get():
            self.handle_event(ev)

    # ------------------------------------------------------------ 更新
    def update(self, dt, keys):
        if self.state == self.STATE_PLAY:
            self.elapsed += dt
        else:
            self.won_t += dt

        self.shake_t = max(0.0, self.shake_t - dt)
        self.flash_t = max(0.0, self.flash_t - dt * 2.0)

        if self.anim:
            for k in list(self.anim.keys()):
                v = self.anim[k] - dt * 3.2
                if v <= 0.0:
                    del self.anim[k]
                else:
                    self.anim[k] = v

        # 方向键长按重复移动（持续输入走 keys 下标接口）
        if keys is not None:
            dr = dc = 0
            if keys[pygame.K_LEFT]:
                dc -= 1
            if keys[pygame.K_RIGHT]:
                dc += 1
            if keys[pygame.K_UP]:
                dr -= 1
            if keys[pygame.K_DOWN]:
                dr += 1
            if dr or dc:
                self.repeat_t -= dt
                if self.repeat_t <= 0.0:
                    self.repeat_t = 0.11
                    r0, c0 = self.sel if self.sel else (4, 4)
                    self.select(min(8, max(0, r0 + dr)), min(8, max(0, c0 + dc)), quiet=True)
            else:
                self.repeat_t = 0.0

        try:
            self.mouse = self.to_canvas(pygame.mouse.get_pos())
        except Exception:
            self.mouse = (-1, -1)

    # ------------------------------------------------------------ 渲染
    def draw(self):
        cv = self.canvas
        cv.fill(BG)
        self._draw_backdrop(cv)
        self._draw_header(cv)
        self._draw_board(cv)
        if self.state == self.STATE_WON:
            self._draw_over_panel(cv)
        else:
            self._draw_panel(cv)
        self._draw_footer(cv)

    def _draw_backdrop(self, cv):
        """四角极轻的压暗，让中间内容浮起来一点。纯装饰。"""
        for i in range(8):
            a = 10 - i
            if a <= 0:
                break
            col = mix(BG, BG_VIGNETTE, (i + 1) / 9.0)
            pygame.draw.rect(cv, col, pygame.Rect(i * 2, i * 2, LOGICAL_W - i * 4, LOGICAL_H - i * 4), 3,
                             border_radius=26)

    def _draw_header(self, cv):
        draw_text(cv, "数独", get_font(34, True), C_TEXT, (30, 34))
        draw_text(cv, "SUDOKU", get_font(14, True), C_TEXT_DIM, (104, 50))
        draw_text(cv, "唯一解出题 · 题库实时生成", get_font(13), C_TEXT_DIM,
                  (LOGICAL_W - 30, 44), anchor="topright")

    # ---------------- 棋盘 ----------------
    def _draw_board(self, cv):
        shake = 0
        if self.shake_t > 0.0:
            shake = int(self.shake_t / 0.34 * 7.0 * (1 if int(self.shake_t * 60) % 2 else -1))

        card = BOARD_CARD.move(shake, 0)
        # 卡片投影
        shadow = card.move(0, 5)
        round_rect(cv, SHADOW, shadow, 16)
        round_rect(cv, CARD, card, 16)
        round_rect(cv, CARD_EDGE, card, 16, 1)

        board = self.board_rect.move(shake, 0)
        round_rect(cv, BOARD_BG, board, 8)

        self._draw_cells(cv, shake)
        self._draw_grid_lines(cv, shake)
        self._draw_digits(cv, shake)
        self._draw_selection_ring(cv, shake)

        if self.state == self.STATE_WON:
            self._draw_win_ripple(cv, shake)

    def _cell_bg(self, r, c):
        base = CELL_GIVEN if self.puzzle[r][c] else CELL_BG
        sel = self.sel
        if sel is not None:
            sr, sc = sel
            if (r, c) == sel:
                base = CELL_SEL
            else:
                sv = self.grid[sr][sc]
                if sv and self.grid[r][c] == sv:
                    base = CELL_SAME
                elif r == sr or c == sc or box_of(r, c) == box_of(sr, sc):
                    base = CELL_PEER
        t = self.anim.get((r, c), 0.0)
        if t > 0.0:
            base = mix(base, CELL_SEL, t * 0.75)
        return base

    def _draw_cells(self, cv, shake):
        for r in range(9):
            for c in range(9):
                rect = self.cell_rect(r, c).move(shake, 0)
                pygame.draw.rect(cv, self._cell_bg(r, c), rect)

    def _draw_grid_lines(self, cv, shake):
        x0 = BOARD_X + shake
        y0 = BOARD_Y
        for i in range(1, 9):
            if i % 3 == 0:
                col, wd = LINE_THICK, 3
            else:
                col, wd = LINE_THIN, 1
            pygame.draw.line(cv, col, (x0 + i * CELL, y0), (x0 + i * CELL, y0 + GRID_PX), wd)
            pygame.draw.line(cv, col, (x0, y0 + i * CELL), (x0 + GRID_PX, y0 + i * CELL), wd)
        pygame.draw.rect(cv, LINE_THICK,
                         pygame.Rect(x0, y0, GRID_PX, GRID_PX), 3)

    def _draw_digits(self, cv, shake):
        f_big = get_font(40, True)
        f_note = get_font(16, True)
        for r in range(9):
            for c in range(9):
                v = self.grid[r][c]
                cx, cy = self.cell_center(r, c)
                cx += shake
                if v:
                    if self.puzzle[r][c]:
                        col = C_GIVEN
                    elif (r, c) in self.hint_cells:
                        col = C_HINT
                    elif v != self.solution[r][c]:
                        col = C_BAD
                    else:
                        col = C_USER
                    draw_text(cv, str(v), f_big, col, (cx, cy + 1), anchor="center")
                else:
                    mask = self.notes[r][c]
                    if mask:
                        for d in range(1, 10):
                            if mask >> d & 1:
                                dr, dc = divmod(d - 1, 3)
                                nx = BOARD_X + c * CELL + dc * (CELL / 3.0) + CELL / 6.0
                                ny = BOARD_Y + r * CELL + dr * (CELL / 3.0) + CELL / 6.0
                                draw_text(cv, str(d), f_note, C_NOTE,
                                          (nx + shake, ny), anchor="center")

    def _draw_selection_ring(self, cv, shake):
        if self.sel is None or self.state != self.STATE_PLAY:
            return
        r, c = self.sel
        rect = self.cell_rect(r, c).move(shake, 0).inflate(-6, -6)
        pygame.draw.rect(cv, C_ACCENT, rect, 3, border_radius=6)

    def _draw_win_ripple(self, cv, shake):
        wave = self.won_t
        for r in range(9):
            for c in range(9):
                d = (r + c) * 0.055
                if wave <= d:
                    continue
                k = (wave - d) / 0.30
                if k > 1.0:
                    k = 1.0
                rect = self.cell_rect(r, c).move(shake, 0).inflate(-4, -4)
                col = mix(self._cell_bg(r, c), C_GOLD, k)
                pygame.draw.rect(cv, col, rect, 3, border_radius=5)

    # ---------------- 右侧面板 ----------------
    def _draw_panel(self, cv):
        card = self.panel_rect
        round_rect(cv, SHADOW, card.move(0, 5), 16)
        round_rect(cv, CARD, card, 16)
        round_rect(cv, CARD_EDGE, card, 16, 1)

        self._draw_status_card(cv)
        self._draw_diff_row(cv)
        self._draw_keys(cv)
        self._draw_tools(cv)

    def _draw_status_card(self, cv):
        x = PANEL_X + 16
        y = PANEL_Y + CARD_Y
        w = PANEL_W - 32
        rect = pygame.Rect(x, y, w, CARD_H)
        round_rect(cv, (245, 243, 237), rect, 12)
        round_rect(cv, CARD_EDGE, rect, 12, 1)

        draw_text(cv, "用时", get_font(13), C_TEXT_DIM, (x + 16, y + 12))
        draw_text(cv, fmt_time(self.elapsed), get_font(28, True), C_TEXT, (x + 16, y + 30))

        rx = x + w - 16
        draw_text(cv, "错误", get_font(13), C_TEXT_DIM, (rx, y + 12), anchor="topright")
        mcol = C_BAD if self.mistakes else C_TEXT
        draw_text(cv, str(self.mistakes), get_font(28, True), mcol, (rx, y + 30), anchor="topright")

        # 进度条
        by = y + CARD_H - 18
        bw = w - 32
        done = max(0, self.filled_count() - self.given_count)
        frac = min(1.0, done / float(max(1, self.to_fill)))
        pygame.draw.rect(cv, (226, 221, 210), pygame.Rect(x + 16, by, bw, 7), border_radius=4)
        if frac > 0:
            pygame.draw.rect(cv, C_ACCENT,
                             pygame.Rect(x + 16, by, max(7, int(bw * frac)), 7), border_radius=4)

    def _draw_diff_row(self, cv):
        for key, name, _h in DIFFICULTIES:
            rect = self.diff_rects[key]
            on = (key == self.diff)
            hover = self.mouse and rect.collidepoint(self.mouse)
            if on:
                col = C_ACCENT
                tcol = (255, 255, 255)
            else:
                col = KEY_HOVER if hover else KEY_BG
                tcol = C_TEXT
            round_rect(cv, col, rect, 10)
            round_rect(cv, C_ACCENT if on else KEY_EDGE, rect, 10, 1)
            draw_text(cv, name, get_font(17, True), tcol, rect.center, anchor="center")

    def _draw_keys(self, cv):
        """数字键盘。笔记模式下整排键换底色 + 蓝边框，一眼能看出当前输入模式。"""
        f_big = get_font(34, True)
        f_sm = get_font(14, True)
        dead = (196, 190, 178)
        note = self.note_mode
        for d, rect in self.key_rects.items():
            left = 9 - self.digit_count(d)
            hover = self.mouse and rect.collidepoint(self.mouse)
            if left <= 0:
                bg, tcol, edge = KEY_DONE_BG, (170, 164, 152), KEY_EDGE
            elif note:
                bg = NOTE_KEY_HOV if hover else NOTE_KEY_BG
                tcol, edge = C_ACCENT, C_ACCENT
            elif hover:
                bg, tcol, edge = KEY_HOVER, C_TEXT, KEY_EDGE_HI
            else:
                bg, tcol, edge = KEY_BG, C_TEXT, KEY_EDGE
            round_rect(cv, bg, rect, 12)
            round_rect(cv, edge, rect, 12, 1)
            draw_text(cv, str(d), f_big, tcol, (rect.centerx, rect.centery - 4), anchor="center")
            sub = "笔记" if note else "剩 %d" % max(0, left)
            draw_text(cv, sub, f_sm, dead if left <= 0 else (C_ACCENT if note else C_TEXT_DIM),
                      (rect.centerx, rect.bottom - 8), anchor="midbottom")

    def _tool_style(self, name):
        if name == "note":
            on = self.note_mode
            return ("笔记  N", TOOL_ON if on else TOOL_BG,
                    (255, 255, 255) if on else C_TEXT,
                    TOOL_ON if on else KEY_EDGE)
        if name == "undo":
            dis = not self.history
            return ("撤销  U", TOOL_BG, C_TEXT_DIM if dis else C_TEXT, KEY_EDGE)
        if name == "hint":
            return ("提示  H", TOOL_BG, C_TEXT, KEY_EDGE)
        return ("新游戏  R", C_ACCENT, (255, 255, 255), C_ACCENT_D)

    def _draw_tools(self, cv):
        f = get_font(16, True)
        for name in ("note", "undo", "hint", "new"):
            rect = self.tool_rects[name]
            label, bg, tcol, edge = self._tool_style(name)
            hover = self.mouse and rect.collidepoint(self.mouse)
            if hover and name != "note":
                bg = mix(bg, C_ACCENT, 0.14)
            round_rect(cv, bg, rect, 10)
            round_rect(cv, edge, rect, 10, 1)
            draw_text(cv, label, f, tcol, rect.center, anchor="center")

    # ---------------- 结算 ----------------
    def _draw_over_panel(self, cv):
        card = self.panel_rect
        round_rect(cv, SHADOW, card.move(0, 5), 16)
        round_rect(cv, CARD, card, 16)
        round_rect(cv, C_GOLD, card, 16, 2)

        cx = PANEL_X + PANEL_W // 2
        # 顶部金色圆章
        pygame.draw.circle(cv, (250, 245, 230), (cx, PANEL_Y + 74), 38)
        pygame.draw.circle(cv, C_GOLD, (cx, PANEL_Y + 74), 38, 3)
        pygame.draw.lines(cv, C_GOLD, False,
                          [(cx - 15, PANEL_Y + 74), (cx - 4, PANEL_Y + 85), (cx + 17, PANEL_Y + 62)], 5)

        draw_text(cv, "完成！", get_font(32, True), C_TEXT, (cx, PANEL_Y + 132), anchor="center")
        draw_text(cv, "%s 难度 · 唯一解" % DIFF_NAME[self.diff], get_font(14),
                  C_TEXT_DIM, (cx, PANEL_Y + 166), anchor="center")

        rows = (("用时", fmt_time(self.elapsed)),
                ("错误", "%d 次" % self.mistakes),
                ("提示", "%d 次" % self.hints),
                ("空格", "%d 个" % self.to_fill))
        y = PANEL_Y + 202
        for i, (k, v) in enumerate(rows):
            yy = y + i * 40
            if i:
                pygame.draw.line(cv, (238, 233, 224),
                                 (PANEL_X + 28, yy - 8), (PANEL_X + PANEL_W - 28, yy - 8), 1)
            draw_text(cv, k, get_font(15), C_TEXT_DIM, (PANEL_X + 28, yy))
            draw_text(cv, v, get_font(20, True), C_TEXT,
                      (PANEL_X + PANEL_W - 28, yy - 3), anchor="topright")

        for name, rect in self.over_rects.items():
            hover = self.mouse and rect.collidepoint(self.mouse)
            if name == "again":
                bg = C_ACCENT_D if hover else C_ACCENT
                round_rect(cv, bg, rect, 12)
                draw_text(cv, "再来一局", get_font(20, True), (255, 255, 255),
                          rect.center, anchor="center")
            else:
                key = name[5:]
                on = (key == self.diff)
                bg = KEY_HOVER if hover else TOOL_BG
                round_rect(cv, bg, rect, 10)
                round_rect(cv, C_ACCENT if on else KEY_EDGE, rect, 10, 1)
                draw_text(cv, DIFF_NAME[key], get_font(15, True), C_TEXT,
                          rect.center, anchor="center")
        draw_text(cv, "按 R 重开 · 方向键继续查看盘面", get_font(13), C_TEXT_DIM,
                  (cx, PANEL_Y + PANEL_H - 24), anchor="center")

    def _draw_footer(self, cv):
        msg = "点击格子 · 按 1-9 填数 · N 笔记 · U 撤销 · H 提示 · R 新局 · 右键擦除"
        if self.state == self.STATE_WON:
            msg = "恭喜通关！用时 %s · 错误 %d 次 · 提示 %d 次" % (
                fmt_time(self.elapsed), self.mistakes, self.hints)
        draw_text(cv, msg, get_font(15), C_TEXT_DIM,
                  (LOGICAL_W // 2, BOARD_CARD.bottom + 26), anchor="center")

    # ------------------------------------------------------------ 呈现
    def present(self):
        if self.window is None:
            return
        ww, wh = self.window.get_size()
        dw, dh, ox, oy = self._view
        if (dw, dh) == (ww, wh):
            self.window.blit(self.canvas, (0, 0))
        else:
            self.window.fill(OUTSIDE)
            self.window.blit(pygame.transform.smoothscale(self.canvas, (dw, dh)), (ox, oy))
        pygame.display.flip()


NUM_KEY_MAP = {}
for _i in range(1, 10):
    NUM_KEY_MAP[getattr(pygame, "K_%d" % _i)] = _i
    _kp = getattr(pygame, "K_KP%d" % _i, None)
    if _kp is not None:
        NUM_KEY_MAP[_kp] = _i


# ===========================================================================
# 七、入口
# ===========================================================================

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        print("sudoku %s" % __version__)
        return 0
    diff = "easy"
    if "--diff" in argv:
        diff = argv[argv.index("--diff") + 1]
    frames = None
    if "--frames" in argv:
        frames = int(argv[argv.index("--frames") + 1])
    seed = None
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])

    # pre_init 必须在 pygame.init() **之前** —— init() 会顺带初始化 mixer，
    # 之后再调 pre_init 不会生效，采样率对不上会让合成音效变调。
    try:
        pygame.mixer.pre_init(SR, -16, 2, 512)
    except Exception:
        pass
    pygame.init()

    # 重新初始化后旧 Font 已失效，必须清缓存（不清会在 render 时段错误）
    reset_font_cache()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    pygame.display.set_caption("数独 Sudoku")
    window = pygame.display.set_mode((LOGICAL_W, LOGICAL_H), pygame.RESIZABLE)

    game = Game(window, rng=random.Random(seed))
    game.new_game(diff if diff in DIFF_HOLES else "easy")

    clock = pygame.time.Clock()
    shown = 0
    while game.running:
        dt = clock.tick(60) / 1000.0
        if dt > 0.05:
            dt = 0.05
        game.process_events()
        game.update(dt, pygame.key.get_pressed())
        game.draw()
        game.present()
        shown += 1
        if frames is not None and shown >= frames:
            break

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
