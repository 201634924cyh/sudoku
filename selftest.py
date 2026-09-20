# -*- coding: utf-8 -*-
"""
数独 —— 无窗口自检
==================

    python selftest.py            # 全部检查
    python selftest.py --shots    # 额外保存截图并做像素扫描

设计要点（照着 pygame-game-dev 技能的方法论来）：
  * 算法层先独立验证：终盘合法、题面唯一解、题面是终盘的子集。
  * 交互层**只走真实事件**（pygame.event.post 鼠标/键盘），顺手验证
    window -> canvas 的反缩放换算。
  * 用一个不偷看答案的约束推理求解器，通过公开输入接口**真的打通一局**，
    断言 mistakes 保持为 0 —— 这比逐个函数单测有价值得多。
  * 渲染后必须真的用眼睛看截图（颜色断言查不出图层顺序类 bug）。
"""

import os
import random
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import sudoku as S  # noqa: E402

SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview")
FAILURES = []
CHECKS = [0]              # 已执行的断言总数（成功也计），用于 README 徽章


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(msg)
        print("  [FAIL] " + msg)
    return bool(cond)


def note(msg):
    print("  [ ok ] " + msg)


# ---------------------------------------------------------------------------
# 事件注入工具
# ---------------------------------------------------------------------------

def wpos(game, lx, ly):
    """逻辑画布坐标 -> 窗口坐标（走真实的缩放换算）。"""
    dw, dh, ox, oy = game._view
    sx = dw / float(S.LOGICAL_W)
    sy = dh / float(S.LOGICAL_H)
    return (int(round(lx * sx + ox)), int(round(ly * sy + oy)))


def click(game, lx, ly, button=1):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=wpos(game, lx, ly),
                                         button=button))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=wpos(game, lx, ly),
                                         button=button))
    game.process_events()


def click_cell(game, r, c, button=1):
    lx, ly = game.cell_center(r, c)
    click(game, lx, ly, button)


def key(game, k, mod=0):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod,
                                         unicode="", scancode=0))
    game.process_events()


NUMK = [getattr(pygame, "K_%d" % i) for i in range(1, 10)]


def type_digit(game, d):
    key(game, NUMK[d - 1])


# ---------------------------------------------------------------------------
# 约束推理求解器：只看得到盘面，不偷看 solution
# ---------------------------------------------------------------------------

def logic_solve(grid):
    """回溯求解，返回 [(r, c, d), ...] 的填充顺序；无解返回 None。"""
    g = [row[:] for row in grid]

    def cand(r, c):
        used = set()
        for i in range(9):
            used.add(g[r][i])
            used.add(g[i][c])
        br, bc = (r // 3) * 3, (c // 3) * 3
        for rr in range(br, br + 3):
            for cc in range(bc, bc + 3):
                used.add(g[rr][cc])
        return [d for d in range(1, 10) if d not in used]

    seq = []

    def rec():
        best = None
        best_c = None
        for r in range(9):
            for c in range(9):
                if g[r][c]:
                    continue
                cs = cand(r, c)
                if not cs:
                    return False
                if best is None or len(cs) < len(best_c):
                    best = (r, c)
                    best_c = cs
                    if len(cs) == 1:
                        break
            else:
                continue
            break
        if best is None:
            return True
        r, c = best
        for d in best_c:
            g[r][c] = d
            if rec():
                seq.append((r, c, d))
                return True
            g[r][c] = 0
        return False

    if not rec():
        return None
    seq.reverse()
    return seq


# ---------------------------------------------------------------------------
# 1. 算法层
# ---------------------------------------------------------------------------

def test_algorithms():
    print("-" * 66)
    rng = random.Random(20260919)

    for i in range(40):
        g = S.generate_full(rng)
        check(S.board_is_valid(g), "第 %d 个终盘不合法" % i)
        check(all(g[r][c] for r in range(9) for c in range(9)),
              "第 %d 个终盘有空格" % i)
        check(S.solve_count([row[:] for row in g], 2) == 1, "终盘解数不为 1")
    note("40 个随机终盘：合法、无空格、解数恰为 1")

    solved = S.generate_full(random.Random(1))
    check(S.solve_count([row[:] for row in solved], 2) == 1, "已解盘面解数应为 1")

    bad = [row[:] for row in S.make_empty()]
    bad[0][0] = 5
    bad[0][1] = 5
    check(S.solve_count(bad, 2) == 0, "行内重复却报有解")
    check(not S.board_is_valid(bad), "board_is_valid 漏判行内重复")

    # 同值落在同一行 / 列 / 宫 -> 无解；落在不同单元 -> 仍有解
    for a, b, label in (((0, 0), (1, 1), "同宫"), ((0, 0), (0, 5), "同行"),
                        ((0, 0), (5, 0), "同列")):
        g = S.make_empty()
        g[a[0]][a[1]] = 3
        g[b[0]][b[1]] = 3
        check(S.solve_count(g, 2) == 0, "%s 放同值却报有解" % label)
        check(not S.board_is_valid(g), "%s 放同值 board_is_valid 漏判" % label)

    g = S.make_empty()
    g[0][0] = 3
    g[4][4] = 3
    g[8][8] = 3
    check(S.solve_count(g, 2) >= 1, "三个互不相干的 3 不应导致无解")

    for diff, _n, target in S.DIFFICULTIES:
        holes_seen = []
        for k in range(6):
            puz, sol, holes = S.make_puzzle(diff, random.Random(500 + k))
            holes_seen.append(holes)
            check(holes == target, "%s 空洞数 %d != 目标 %d" % (diff, holes, target))
            check(S.solve_count([row[:] for row in puz], 2) == 1,
                  "%s 题面不是唯一解" % diff)
            for r in range(9):
                for c in range(9):
                    if puz[r][c]:
                        check(puz[r][c] == sol[r][c], "%s 题面给定值与终盘不符" % diff)
            seq = logic_solve(puz)
            check(seq is not None, "%s 题面推理器解不出" % diff)
            if seq:
                g = [row[:] for row in puz]
                for r, c, d in seq:
                    g[r][c] = d
                check(g == sol, "%s 推理器解与终盘不一致" % diff)
        note("%-6s 空洞 %s，唯一解 / 题面一致 / 推理器可解" % (diff, holes_seen))


# ---------------------------------------------------------------------------
# 2. 交互层
# ---------------------------------------------------------------------------

def fresh_game(window, diff="easy", seed=99):
    g = S.Game(window, rng=random.Random(seed))
    g.new_game(diff)
    return g


def first_empty(game, pred=None):
    for r in range(9):
        for c in range(9):
            if game.grid[r][c] == 0 and (pred is None or pred(r, c)):
                return (r, c)
    return None


def test_mouse_and_selection(game):
    print("-" * 66)
    game.new_game("easy")
    check(game.sel is None, "新局不应有选中格")

    for cell in ((0, 0), (4, 7), (8, 8), (2, 3)):
        click_cell(game, *cell)
        check(game.sel == cell, "点击 %s 后选中变成 %s" % (cell, game.sel))
    note("1x 窗口下点选 4 个格子，反缩放换算正确")

    # 棋盘外点击不应改变选择
    keep = game.sel
    click(game, S.BOARD_X - 40, S.BOARD_Y + 20)
    check(game.sel == keep, "点击棋盘外却改变了选中格")

    # 方向键移动
    click_cell(game, 4, 4)
    key(game, pygame.K_LEFT)
    check(game.sel == (4, 3), "方向键左移失败：%s" % (game.sel,))
    key(game, pygame.K_UP)
    check(game.sel == (3, 3), "方向键上移失败：%s" % (game.sel,))
    for _ in range(9):
        key(game, pygame.K_LEFT)                     # 撞左边界
    check(game.sel == (3, 0), "方向键未在左边界停住：%s" % (game.sel,))
    note("方向键移动与边界夹紧正常")


def test_fill_and_mistakes(game):
    print("-" * 66)
    game.new_game("easy")

    given = next((r, c) for r in range(9) for c in range(9) if game.puzzle[r][c])
    click_cell(game, *given)
    type_digit(game, game.solution[given[0]][given[1]] + 1
               if game.solution[given[0]][given[1]] < 9 else 1)
    check(game.grid[given[0]][given[1]] == game.puzzle[given[0]][given[1]],
          "题面给定格被改写了")
    note("题面给定格不可修改")

    cell = first_empty(game)
    r, c = cell
    wrong = game.solution[r][c] % 9 + 1
    click_cell(game, r, c)
    type_digit(game, wrong)
    check(game.grid[r][c] == wrong, "填数未生效")
    check(game.mistakes == 1, "填错未计错误，mistakes=%d" % game.mistakes)
    check(game.is_wrong(r, c), "填错的格子未被标记")
    note("填入错误数字：落盘 + 计错 + 标记")

    type_digit(game, wrong)                          # 再按同一个数字 = 取消
    check(game.grid[r][c] == 0, "重复按同数字未取消，得到 %r" % game.grid[r][c])
    check(game.mistakes == 1, "取消不应退还错误计数")
    note("重复按同数字可取消（错误计数不回退）")

    type_digit(game, game.solution[r][c])
    check(game.grid[r][c] == game.solution[r][c], "正确数字未填入")
    check(not game.is_wrong(r, c), "正确数字被误标为错误")
    check(game.mistakes == 1, "填对不应增加错误计数")
    note("填入正确数字：落盘且不计错")


def test_notes_erase_undo(game):
    print("-" * 66)
    game.new_game("easy")

    cell = first_empty(game)
    r, c = cell
    click_cell(game, r, c)
    key(game, pygame.K_n)
    check(game.note_mode is True, "N 未开启笔记模式")
    type_digit(game, 3)
    type_digit(game, 7)
    check(game.notes[r][c] >> 3 & 1 and game.notes[r][c] >> 7 & 1, "候选标记未写入")
    type_digit(game, 3)
    check(not (game.notes[r][c] >> 3 & 1), "再次按同数字未取消候选")
    check(game.notes[r][c] >> 7 & 1, "取消候选时误删了其它候选")
    note("笔记模式：标记 / 取消 / 互不干扰")

    key(game, pygame.K_u)
    check(game.notes[r][c] >> 3 & 1, "撤销未恢复被取消的候选")
    check(game.notes[r][c] >> 7 & 1, "撤销破坏了其它候选")
    note("撤销恢复笔记")

    key(game, pygame.K_n)
    check(game.note_mode is False, "N 未关闭笔记模式")

    # 自动清理同行候选 + 撤销恢复
    game.new_game("easy")
    anchor = None
    for r in range(9):
        for c in range(9):
            if game.grid[r][c]:
                continue
            v = game.solution[r][c]
            for cc in range(9):
                if cc != c and game.grid[r][cc] == 0:
                    anchor = (r, c, cc, v)
                    break
            if anchor:
                break
        if anchor:
            break
    check(anchor is not None, "找不到用于测试自动清理的格子")
    if anchor:
        r, c, cc, v = anchor
        click_cell(game, r, cc)
        key(game, pygame.K_n)
        type_digit(game, v)
        key(game, pygame.K_n)
        check(game.notes[r][cc] >> v & 1, "同行候选未标上")
        click_cell(game, r, c)
        type_digit(game, v)
        check(not (game.notes[r][cc] >> v & 1),
              "填入后未自动清掉同行候选")
        key(game, pygame.K_u)
        check(game.notes[r][cc] >> v & 1, "撤销未恢复被自动清理的候选")
        check(game.grid[r][c] == 0, "撤销未回退填数")
        note("自动清理同行候选，撤销可完整恢复")

    # 擦除：键盘 + 右键
    cell = first_empty(game)
    r, c = cell
    click_cell(game, r, c)
    type_digit(game, game.solution[r][c])
    key(game, pygame.K_DELETE)
    check(game.grid[r][c] == 0, "Delete 未擦除")
    type_digit(game, game.solution[r][c])
    click_cell(game, r, c, button=3)
    check(game.grid[r][c] == 0, "鼠标右键未擦除")
    note("擦除：键盘 Delete 与鼠标右键均生效")

    # 撤销栈空时不应出错
    game.new_game("easy")
    check(game.history == [], "新局撤销栈应为空")
    key(game, pygame.K_u)
    check(game.state == S.Game.STATE_PLAY, "空栈撤销导致状态异常")
    note("空撤销栈安全")


def test_hint(game):
    print("-" * 66)
    game.new_game("medium")
    before = game.filled_count()
    rect = game.tool_rects["hint"]
    click(game, rect.centerx, rect.centery)
    check(game.hints == 1, "点击提示按钮未生效，hints=%d" % game.hints)
    check(game.filled_count() == before + 1, "提示未填入数字")
    r, c = game.sel
    check(game.grid[r][c] == game.solution[r][c], "提示填的不是正确答案")
    check((r, c) in game.hint_cells, "提示格未标记")
    check(game.mistakes == 0, "提示不应计入错误")

    key(game, pygame.K_h)
    check(game.hints == 2, "键盘 H 提示未生效")

    game.grid = [row[:] for row in game.solution]      # 已填满时提示应无效
    game.hint_cells = set()
    check(game.hint() is False, "已填满仍能提示")
    note("提示：按钮/键盘均可，填正确答案、单独计数、不计错误、填满后失效")


def test_buttons(game):
    print("-" * 66)
    game.new_game("easy")
    check(game.diff == "easy", "初始难度不对")

    rect = game.diff_rects["hard"]
    click(game, rect.centerx, rect.centery)
    check(game.diff == "hard", "点击难度按钮未切换：%s" % game.diff)
    check(game.state == S.Game.STATE_PLAY, "切换难度后未进入新局面")
    check(game.given_count == 81 - S.DIFF_HOLES["hard"], "困难难度给定数不对")
    note("难度按钮切换 + 立即开新局")

    cell = first_empty(game)
    click_cell(game, *cell)
    rect = game.key_rects[4]
    click(game, rect.centerx, rect.centery)
    check(game.grid[cell[0]][cell[1]] == 4, "点击数字键盘未填入")
    note("数字键盘点击填入")

    rect = game.tool_rects["note"]
    click(game, rect.centerx, rect.centery)
    check(game.note_mode is True, "笔记按钮未生效")
    click(game, rect.centerx, rect.centery)
    check(game.note_mode is False, "笔记按钮未切回")
    note("工具按钮：笔记开关")

    rect = game.tool_rects["undo"]
    click(game, rect.centerx, rect.centery)
    check(game.grid[cell[0]][cell[1]] == 0, "撤销按钮未生效")
    note("工具按钮：撤销")

    before = game.given_count
    rect = game.tool_rects["new"]
    click(game, rect.centerx, rect.centery)
    check(game.history == [] and game.mistakes == 0, "新游戏按钮未重置状态")
    check(game.given_count == before, "新游戏换了难度")
    note("工具按钮：新游戏（同难度）")


def test_rescale_clicking(window):
    print("-" * 66)
    game = S.Game(window, rng=random.Random(7))
    game.new_game("easy")
    for size in ((S.LOGICAL_W, S.LOGICAL_H), (2040, 1520), (700, 900), (1600, 500)):
        window = pygame.display.set_mode(size, pygame.RESIZABLE)
        game.window = window
        game.compute_view()
        game.draw()
        game.present()
        dw, dh, ox, oy = game._view
        check(dw <= size[0] and dh <= size[1], "%s 下缩放框超出窗口" % (size,))
        ok = True
        for cell in ((0, 0), (3, 5), (8, 8)):
            click_cell(game, *cell)
            if game.sel != cell:
                ok = False
        check(ok, "窗口 %s 下点击落点错位（sel=%s）" % (size, game.sel))
        print("      %-14s view=%s -> 点击落点正确" % (str(size), (dw, dh, ox, oy)))
    pygame.display.set_mode((S.LOGICAL_W, S.LOGICAL_H), pygame.RESIZABLE)
    game.window = window = pygame.display.get_surface()
    game.compute_view()
    return game


def test_full_playthrough(game):
    print("-" * 66)
    game.new_game("hard")
    seq = logic_solve(game.puzzle)
    check(seq is not None, "困难题推理器解不出")
    if seq is None:
        return
    check(len(seq) == S.DIFF_HOLES["hard"], "待填格数 %d != %d"
          % (len(seq), S.DIFF_HOLES["hard"]))

    # 每一步都走真实事件：鼠标点格 + 键盘敲数字
    for i, (r, c, d) in enumerate(seq):
        click_cell(game, r, c)
        if game.sel != (r, c):
            check(False, "第 %d 步点选 %s 失败" % (i, (r, c)))
            return
        type_digit(game, d)
        game.update(1.0 / 60.0, None)                # 像真实游戏那样推进一帧
        if game.grid[r][c] != d:
            check(False, "第 %d 步填入 %s=%d 失败" % (i, (r, c), d))
            return
        if game.state == S.Game.STATE_WON and i < len(seq) - 1:
            check(False, "第 %d 步就提前通关了" % i)
            return

    check(game.state == S.Game.STATE_WON, "填满后未进入通关态：%s" % game.state)
    check(game.mistakes == 0, "推理器正确解全程却累计了 %d 次错误" % game.mistakes)
    check(game.hints == 0, "未用提示却有提示计数")
    check(game.elapsed > 0, "用时应大于 0")
    check(game.grid == game.solution, "终盘与答案不一致")
    note("走真实事件打通困难局：%d 步，state=%s，mistakes=%d，用时 %s"
         % (len(seq), game.state, game.mistakes, S.fmt_time(game.elapsed)))

    # 通关后输入必须全部失效
    snap_grid = [row[:] for row in game.grid]
    snap_hist = len(game.history)
    cell = (0, 0)
    click_cell(game, *cell)
    type_digit(game, 5)
    key(game, pygame.K_h)
    key(game, pygame.K_DELETE)
    key(game, pygame.K_u)
    check(game.grid == snap_grid, "通关后盘面被改动")
    check(len(game.history) == snap_hist, "通关后仍在写入撤销栈")
    note("通关后所有输入失效")

    before = game.elapsed
    for _ in range(60):
        game.update(1.0 / 60.0, None)
    check(game.elapsed == before, "通关后计时器仍在走")
    check(game.won_t > 0, "通关波纹计时未推进")
    note("通关后计时停止，波纹动画推进")

    t0 = time.perf_counter()
    for _ in range(90):
        game.draw()
        game.present()
    print("      通关画面绘制 90 帧 %.0f ms" % ((time.perf_counter() - t0) * 1000))

    # 结算卡上的按钮
    rect = game.over_rects["again"]
    click(game, rect.centerx, rect.centery)
    check(game.state == S.Game.STATE_PLAY, "再来一局未重开")
    check(game.elapsed < 0.001 and game.mistakes == 0 and game.history == [],
          "重开后状态未复位")
    check(game.grid == game.puzzle, "重开后盘面不是新题面")
    note("结算「再来一局」重开且状态复位")

    game.state = S.Game.STATE_WON
    game.won_t = 1.0
    rect = game.over_rects["diff_easy"]
    click(game, rect.centerx, rect.centery)
    check(game.diff == "easy" and game.state == S.Game.STATE_PLAY,
          "结算卡上换难度失败")
    note("结算「换难度」直接开新局")


# ---------------------------------------------------------------------------
# 3. 渲染 / 性能
# ---------------------------------------------------------------------------

def test_render_and_perf(game):
    print("-" * 66)
    # 每种状态都画一遍，包括容易被忽略的分支
    game.new_game("easy")
    for t in ("empty", "selected", "notes", "wrong"):
        if t == "selected":
            click_cell(game, 4, 4)
        elif t == "notes":
            cell = first_empty(game)
            click_cell(game, *cell)
            game.note_mode = True
            for d in (1, 4, 5, 8, 9):
                game.input_digit(d)
            game.note_mode = False
        elif t == "wrong":
            cell = first_empty(game)
            click_cell(game, *cell)
            game.input_digit(game.solution[cell[0]][cell[1]] % 9 + 1)
        for _ in range(30):
            game.update(1.0 / 60.0, None)
            game.draw()
        note("状态渲染：%s" % t)

    game.note_mode = True
    game.history = []                                # 走「撤销不可用」分支
    game.draw()
    game.note_mode = False
    game.history = [{"kind": "note", "r": 0, "c": 0, "prev_notes": 0}]
    game.draw()
    note("工具按钮的可用/不可用分支均可绘制")

    # 动画衰减
    game.new_game("easy")
    game.anim[(0, 0)] = 1.0
    for _ in range(60):
        game.update(1.0 / 60.0, None)
    check((0, 0) not in game.anim, "格子动画未衰减干净")
    check(len(game.anim) < 200, "动画表无限增长")

    # 持续按键路径（keys 下标接口）
    class Keys:
        def __init__(self):
            self.h = set()

        def __getitem__(self, k):
            return k in self.h

    k = Keys()
    k.h = {pygame.K_RIGHT}
    start = game.sel
    game.update(1.0 / 60.0, k)
    check(game.sel != start, "长按方向键未移动（keys 路径）")
    note("keys 下标接口输入路径可用")

    # 帧率压力。注意**不能**在这里调 clock.tick —— 它会把帧率限流到 60，
    # 测出来的是被 sleep 撑满的 16.67ms，而不是真实耗时。
    game.new_game("hard")
    game.sel = (4, 4)
    for i in range(40):
        r, c = divmod(i, 9)
        if not game.puzzle[r][c]:
            game.grid[r][c] = 0
    n = 300
    t0 = time.perf_counter()
    for _ in range(n):
        game.update(1.0 / 60.0, None)
        game.draw()
    per_draw = (time.perf_counter() - t0) / n * 1000

    t0 = time.perf_counter()
    for _ in range(n):
        game.present()
    per_present = (time.perf_counter() - t0) / n * 1000

    # 缩小窗口时 present 要走 smoothscale，单独测一遍
    small = pygame.display.set_mode((680, 500), pygame.RESIZABLE)
    game.window = small
    game.compute_view()
    t0 = time.perf_counter()
    for _ in range(n):
        game.present()
    per_scaled = (time.perf_counter() - t0) / n * 1000
    pygame.display.set_mode((S.LOGICAL_W, S.LOGICAL_H), pygame.RESIZABLE)
    game.window = pygame.display.get_surface()
    game.compute_view()

    print("      update+draw %.2f ms | present(1:1) %.2f ms | present(0.67x) %.2f ms"
          % (per_draw, per_present, per_scaled))
    print("      -> 最坏组合 %.2f ms/帧，约 %.0f FPS 上限"
          % (per_draw + per_scaled, 1000 / max(0.01, per_draw + per_scaled)))
    check(per_draw < 12.0, "update+draw 超过预算：%.2f ms" % per_draw)
    check(per_draw + per_scaled < 16.6,
          "最坏单帧超过 60FPS 预算：%.2f ms" % (per_draw + per_scaled))

    # 文字缓存不能无限膨胀
    check(len(S._TEXT_CACHE) <= 4000, "文字缓存超上限：%d" % len(S._TEXT_CACHE))
    note("文字缓存受控（%d 条）" % len(S._TEXT_CACHE))


def scan_pure_background():
    """在「只该有纯色背景」的区域里找异常像素。

    比全屏扫「比背景更暗」靠谱：网格线、数字、文字本来就该是深色，
    全屏扫会全是假阳性。这里只查卡片之间的缝隙和页面边缘。
    """
    print("-" * 66)
    # 填错时棋盘会左右抖动最多 7px，扫描区必须把这份余量让出来，
    # 否则会把「卡片抖过来压住背景」误判成渲染 bug。
    slack = 10
    check(S.BOARD_CARD.left >= slack + 2, "棋盘卡片左边距容不下抖动")
    check(S.PANEL_X - S.BOARD_CARD.right >= 2 * slack, "卡片间缝隙容不下抖动")
    gaps = [
        pygame.Rect(S.BOARD_CARD.right + slack, S.BOARD_CARD.y,
                    S.PANEL_X - S.BOARD_CARD.right - 2 * slack, S.BOARD_CARD.h),
        pygame.Rect(S.PANEL_X + S.PANEL_W + slack, 0,
                    S.LOGICAL_W - (S.PANEL_X + S.PANEL_W) - slack, S.LOGICAL_H),
        pygame.Rect(0, 0, S.BOARD_CARD.left - slack, S.LOGICAL_H),
    ]
    total_bad = 0
    for fn in sorted(os.listdir(SHOT_DIR)):
        if not fn.endswith(".png"):
            continue
        img = pygame.image.load(os.path.join(SHOT_DIR, fn))
        bad = 0
        sample = None
        for zone in gaps:
            for y in range(zone.top, zone.bottom):
                for x in range(zone.left, zone.right):
                    px = img.get_at((x, y))
                    if (abs(px[0] - S.BG[0]) > 26 or abs(px[1] - S.BG[1]) > 26
                            or abs(px[2] - S.BG[2]) > 26):
                        bad += 1
                        if sample is None:
                            sample = (x, y, px[:3])
        total_bad += bad
        print("      %-22s 纯背景区异常像素 %5d   sample=%s" % (fn, bad, sample))
    check(total_bad == 0, "纯背景区出现 %d 个异常像素（疑似 draw.* 擦背景）" % total_bad)

    # 粗网格线必须还在（防止被格子贴图/数字覆写擦掉）
    img = pygame.image.load(os.path.join(SHOT_DIR, sorted(os.listdir(SHOT_DIR))[0]))
    x_line = S.BOARD_X + 3 * S.CELL
    y_probe = S.BOARD_Y + 30
    found = any(img.get_at((x, y_probe))[0] < 120 for x in range(x_line - 3, x_line + 4))
    check(found, "3 宫分界粗线在棋盘上缺失（疑似被覆写擦掉）")
    note("3 宫分界粗线完整存在")


def shoot(game, name):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, name + ".png")
    pygame.image.save(game.canvas, path)
    print("      -> %s" % path)


def make_shots(game):
    print("-" * 66)
    if os.path.isdir(SHOT_DIR):
        for f in os.listdir(SHOT_DIR):
            os.remove(os.path.join(SHOT_DIR, f))

    game.new_game("hard")
    game.mouse = (-1, -1)
    game.draw()
    shoot(game, "01_initial")

    click_cell(game, 4, 4)
    cell = first_empty(game, lambda r, c: r == 4)
    click_cell(game, *cell)
    game.note_mode = True
    for d in (1, 3, 6, 9):
        game.input_digit(d)
    game.note_mode = False
    for _ in range(40):
        game.update(1.0 / 60.0, None)
    game.draw()
    shoot(game, "02_notes_selected")

    r, c = first_empty(game, lambda r, c: r == 1)
    click_cell(game, r, c)
    wrong = game.solution[r][c] % 9 + 1
    game.input_digit(wrong)
    game.note_mode = True
    game.draw()
    shoot(game, "03_wrong_and_notemode")

    game.note_mode = False
    game.hint()
    game.draw()
    shoot(game, "04_hint")

    game.new_game("easy")
    for r, c, d in logic_solve(game.puzzle):
        game.grid[r][c] = d
    game.elapsed = 213.0
    game.mistakes = 2
    game.hints = 1
    game.sel = (4, 4)
    game.won_t = 3.0
    game.state = S.Game.STATE_WON
    game.mouse = (-1, -1)
    game.draw()
    shoot(game, "05_won")

    game.won_t = 0.35
    game.draw()
    shoot(game, "06_won_ripple")

    game.state = S.Game.STATE_PLAY
    game.new_game("easy")
    game.mouse = game.key_rects[5].center
    game.draw()
    shoot(game, "07_hover")
    note("已保存 7 张状态截图")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    t0 = time.perf_counter()
    try:
        pygame.mixer.pre_init(S.SR, -16, 2, 512)
    except Exception:
        pass
    pygame.init()

    # 重新初始化后旧 Font 已失效，必须清缓存（不清会在 render 时段错误）
    S.reset_font_cache()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    print("=" * 66)
    print("HARNESS  python %s" % sys.version.split()[0])
    print("pygame   %s  video=%s  audio=%s  numpy=%s"
          % (pygame.version.ver,
             pygame.display.get_driver() if pygame.display.get_init() else "-",
             "on" if pygame.mixer.get_init() else "off",
             "yes" if S._np is not None else "no"))

    # 合成音效是按 SR 生成的，采样率对不上会变调
    init = pygame.mixer.get_init()
    if init:
        check(init[0] == S.SR,
              "mixer 采样率 %s != %s，合成音效会变调" % (init[0], S.SR))
        check(len(S.Sfx().sounds) >= 7, "音效未全部合成成功")
        note("mixer %s，8 个音效合成正常" % (init,))

    window = pygame.display.set_mode((S.LOGICAL_W, S.LOGICAL_H), pygame.RESIZABLE)

    test_algorithms()

    game = fresh_game(window)
    test_mouse_and_selection(game)
    test_fill_and_mistakes(game)
    test_notes_erase_undo(game)
    test_hint(game)
    test_buttons(game)
    game = test_rescale_clicking(window)
    test_full_playthrough(game)
    test_render_and_perf(game)

    # ------------------------------------------------------------------
    note("中文字体字形校验（跨平台不出现豆腐块）")
    bad_path = pygame.font.match_font("dejavusans,arial,liberationsans")
    bad_font = None
    if bad_path and os.path.exists(bad_path):
        try:
            bad_font = pygame.font.Font(bad_path, 24)
        except Exception:
            bad_font = None
    check(bad_font is not None and not S.font_covers_cjk(bad_font),
          "反面样本：本机取不到「名字沾边但没有汉字字形」的字体（path=%s）" % bad_path)
    check(not S.font_covers_cjk(pygame.font.Font(None, 24)),
          "探针：默认字体 Font(None) 应被判定为画不出汉字")

    usable = None
    for _p in S.FONT_CANDIDATES:
        if not os.path.exists(_p):
            continue
        try:
            _pf = pygame.font.Font(_p, 24)
        except Exception:
            continue
        if S.font_covers_cjk(_pf):
            usable = _p
            break
    if usable:
        check(S.font_covers_cjk(S.get_font(24)),
              "正向：系统装了中文字体时，get_font 选中的字体应能画出汉字（可用候选 %s）" % usable)
    else:
        note("本机没有任何候选中文字体，正向断言跳过")

    if bad_font is not None:
        _same, _src = S.font_regression(bad_path)
        check(_same,
              "反事实：候选全是无汉字字体时应退回默认字体，而不是拿来就用（实际采用 %s）" % _src)
    else:
        note("取不到无汉字反面样本，反事实断言跳过")

    if "--shots" in sys.argv:
        make_shots(game)
        scan_pure_background()

    print("=" * 66)
    if FAILURES:
        print("HARNESS FAILED  %d / %d checks" % (len(FAILURES), CHECKS[0]))
        for m in FAILURES:
            print("   - " + m)
        pygame.quit()
        return 1
    print("HARNESS PASSED  %d checks  %.2fs" % (CHECKS[0], time.perf_counter() - t0))
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
