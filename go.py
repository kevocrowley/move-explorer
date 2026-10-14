"""Go rules for 9x9, 13x13 and 19x19 boards.

Black plays first. A move is any empty point except suicide (leaving your own group with no
liberties) or recreating an earlier board position (positional superko, which covers ordinary ko).
Passing is always legal; two passes in a row end the game. Scoring is area scoring (stones plus
surrounded empty points) with 7.5 komi for White. Dead stones are not removed before scoring.

Points are named the usual way: columns A-T without I, rows 1-N from the bottom (e.g. D4, Q16).
"""

import random

COLUMNS = "ABCDEFGHJKLMNOPQRST"
EMPTY, BLACK, WHITE = 0, 1, 2
KOMI = 7.5
SIZES = (9, 13, 19)
_TABLES = {}


def _tables(size):
    """Neighbour lists and Zobrist hash keys for a board size (built once per size)."""
    if size not in _TABLES:
        n = size * size
        neighbours = []
        for p in range(n):
            r, c = divmod(p, size)
            neighbours.append([q for q, ok in ((p - size, r > 0), (p + size, r < size - 1),
                                               (p - 1, c > 0), (p + 1, c < size - 1)) if ok])
        rng = random.Random(size)
        zobrist = [(0, rng.getrandbits(64), rng.getrandbits(64)) for _ in range(n)]
        _TABLES[size] = neighbours, zobrist
    return _TABLES[size]


def point_name(p, size):
    r, c = divmod(p, size)
    return f"{COLUMNS[c]}{size - r}"  # row 0 is the top of the board


def parse_point(name, size):
    c = COLUMNS.index(name[0].upper())
    r = size - int(name[1:])
    if not (0 <= r < size and 0 <= c < size):
        raise ValueError(name)
    return r * size + c


def star_points(size):
    edge = 2 if size < 13 else 3
    lines = [edge, size // 2, size - 1 - edge]
    if size == 9:
        return {r * size + c for r in lines for c in lines if (r == c == size // 2) or (r != size // 2 and c != size // 2)}
    return {r * size + c for r in lines for c in lines}


class GoBoard:
    def __init__(self, size=19):
        if size not in SIZES:
            raise ValueError(f"Board size must be one of {SIZES}")
        self.size = size
        self.neighbours, self.zobrist = _tables(size)
        self.board = [EMPTY] * (size * size)
        self.turn = BLACK
        self.captures = {BLACK: 0, WHITE: 0}  # stones each colour has captured
        self.passes = 0
        self.hash = 0
        self.seen = {0}  # hashes of every board position so far (for superko)

    def _group(self, p):
        """Stones in the group at p, and its liberties."""
        colour = self.board[p]
        stones, libs, stack = {p}, set(), [p]
        while stack:
            for q in self.neighbours[stack.pop()]:
                v = self.board[q]
                if v == EMPTY:
                    libs.add(q)
                elif v == colour and q not in stones:
                    stones.add(q)
                    stack.append(q)
        return stones, libs

    def _all_groups(self):
        """Label every stone with a group id; return (ids per point, [(stones, liberties), ...])."""
        gid = [-1] * len(self.board)
        groups = []
        for p, v in enumerate(self.board):
            if v != EMPTY and gid[p] < 0:
                stones, libs = self._group(p)
                for s in stones:
                    gid[s] = len(groups)
                groups.append((stones, libs))
        return gid, groups

    def legal_moves(self):
        """Return ([(point, stones captured)], {point: reason} for empty points you can't play)."""
        me, opp = self.turn, 3 - self.turn
        gid, groups = self._all_groups()
        legal, illegal = [], {}
        for p, v in enumerate(self.board):
            if v != EMPTY:
                continue
            breathes = False
            captured = set()
            for q in self.neighbours[p]:
                w = self.board[q]
                if w == EMPTY:
                    breathes = True
                elif w == me:
                    breathes |= len(groups[gid[q]][1]) > 1
                elif len(groups[gid[q]][1]) == 1:
                    captured.add(gid[q])
            if not breathes and not captured:
                illegal[p] = "suicide"
                continue
            h = self.hash ^ self.zobrist[p][me]
            for g in captured:
                for s in groups[g][0]:
                    h ^= self.zobrist[s][opp]
            if h in self.seen:
                illegal[p] = "ko"
                continue
            legal.append((p, sum(len(groups[g][0]) for g in captured)))
        return legal, illegal

    def push(self, move):
        """Play 'pass' or a point name; return (notation, points touched). Raise ValueError if illegal."""
        if self.passes >= 2:
            raise ValueError("The game is over")
        me, opp = self.turn, 3 - self.turn
        if move == "pass":
            self.passes += 1
            self.turn = opp
            return "Pass", []
        try:
            p = parse_point(move, self.size)
        except (ValueError, IndexError):
            raise ValueError(f"Not a point on a {self.size}x{self.size} board: {move}")
        if self.board[p] != EMPTY:
            raise ValueError(f"{move} is already occupied")
        self.board[p] = me
        h = self.hash ^ self.zobrist[p][me]
        captured = set()
        for q in self.neighbours[p]:
            if self.board[q] == opp and q not in captured:
                stones, libs = self._group(q)
                if not libs:
                    captured |= stones
        for s in captured:
            self.board[s] = EMPTY
            h ^= self.zobrist[s][opp]
        if not captured and not self._group(p)[1]:
            self.board[p] = EMPTY
            raise ValueError(f"{move} is suicide")
        if h in self.seen:
            self.board[p] = EMPTY
            for s in captured:
                self.board[s] = opp
            raise ValueError(f"{move} repeats an earlier position (ko)")
        self.hash = h
        self.seen.add(h)
        self.captures[me] += len(captured)
        self.passes = 0
        self.turn = opp
        return move + (f" (x{len(captured)})" if captured else ""), [point_name(p, self.size)]

    @property
    def over(self):
        return self.passes >= 2

    def score(self):
        """Area score: stones on the board plus empty regions bordered by only one colour."""
        totals = {BLACK: self.board.count(BLACK), WHITE: self.board.count(WHITE)}
        seen = set()
        for p, v in enumerate(self.board):
            if v != EMPTY or p in seen:
                continue
            region, borders, stack = {p}, set(), [p]
            while stack:
                for q in self.neighbours[stack.pop()]:
                    w = self.board[q]
                    if w == EMPTY and q not in region:
                        region.add(q)
                        stack.append(q)
                    elif w != EMPTY:
                        borders.add(w)
            seen |= region
            if len(borders) == 1:
                totals[borders.pop()] += len(region)
        return totals[BLACK], totals[WHITE] + KOMI
