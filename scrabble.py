"""Scrabble rules on the standard 15x15 board with the English 100-tile set.

Words come from the public-domain ENABLE list (data/enable1.txt). Moves are generated with the
anchor/cross-check method (Appel & Jacobson): for every row, and every column via a transposed
board, find each placement of rack tiles that makes a word along the line and valid words across it.

Tiles on the board are uppercase letters; a blank played as a letter is stored lowercase (worth 0).
A rack blank is '?'. Tile draws are deterministic for a given seed, so a game replays identically.

Move ids: 'A7,3:WORD' (across, starting row 7 col 3, zero-based) or 'D...' for down; the word
includes existing board letters, lowercase = blank. 'X:ABC' exchanges those tiles; 'PASS' passes.
"""

import itertools
import random
from collections import Counter
from functools import lru_cache
from pathlib import Path

SIZE = 15
CENTER = (7, 7)
COLS = "ABCDEFGHIJKLMNO"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
EMPTY = "."

VALUES = dict(zip(ALPHABET, [1, 3, 3, 2, 1, 4, 2, 4, 1, 8, 5, 1, 3, 1, 1, 3, 10, 1, 1, 1, 1, 4, 4, 8, 4, 10]))
VALUES["?"] = 0
COUNTS = dict(zip(ALPHABET, [9, 2, 2, 4, 12, 2, 3, 2, 9, 1, 1, 4, 2, 6, 8, 2, 1, 6, 4, 6, 4, 2, 2, 1, 2, 1]))
COUNTS["?"] = 2
BINGO_BONUS = 50
MAX_SCORELESS_TURNS = 6


def _premium_squares():
    layout = {}
    for r, c in [(0, 0), (0, 7), (0, 14), (7, 0), (7, 14), (14, 0), (14, 7), (14, 14)]:
        layout[(r, c)] = "TW"
    for i in [1, 2, 3, 4, 10, 11, 12, 13]:
        layout[(i, i)] = layout[(i, 14 - i)] = "DW"
    layout[CENTER] = "DW"
    for r, c in [(1, 5), (1, 9), (5, 1), (5, 5), (5, 9), (5, 13), (9, 1), (9, 5), (9, 9), (9, 13), (13, 5), (13, 9)]:
        layout[(r, c)] = "TL"
    for r, c in [(0, 3), (0, 11), (2, 6), (2, 8), (3, 0), (3, 7), (3, 14), (6, 2), (6, 6), (6, 8), (6, 12),
                 (7, 3), (7, 11), (8, 2), (8, 6), (8, 8), (8, 12), (11, 0), (11, 7), (11, 14), (12, 6),
                 (12, 8), (14, 3), (14, 11)]:
        layout[(r, c)] = "DL"
    return layout


PREMIUMS = _premium_squares()  # symmetric about the main diagonal, so it also fits the transposed board


def _load_words():
    words = set()
    for line in (Path(__file__).parent / "data" / "enable1.txt").read_text().split():
        if 2 <= len(line) <= SIZE:
            words.add(line.upper())
    trie = {}
    for w in words:
        node = trie
        for ch in w:
            node = node.setdefault(ch, {})
        node["$"] = True
    return words, trie


WORDS, TRIE = _load_words()


def tile_value(ch):
    return 0 if ch.islower() or ch == "?" else VALUES[ch]


def _generate_lines(lines, rack, first, across, found):
    """Find placements along each line of `lines` (rows of the board, or columns if transposed)."""
    counts = Counter(rack)
    for r in range(SIZE):
        row = lines[r]
        # Cross-checks: for each empty square with tiles above/below it, the letters allowed there
        # and the score of those perpendicular tiles.
        cross = [None] * SIZE
        for c in range(SIZE):
            if row[c] != EMPTY:
                continue
            up, rr = "", r - 1
            while rr >= 0 and lines[rr][c] != EMPTY:
                up = lines[rr][c] + up
                rr -= 1
            down, rr = "", r + 1
            while rr < SIZE and lines[rr][c] != EMPTY:
                down += lines[rr][c]
                rr += 1
            if up or down:
                u, d = up.upper(), down.upper()
                cross[c] = ({L for L in ALPHABET if u + L + d in WORDS}, sum(map(tile_value, up + down)))

        def is_anchor(c):
            if row[c] != EMPTY:
                return False
            if first:
                return (r, c) == CENTER
            return any(0 <= rr < SIZE and 0 <= cc < SIZE and lines[rr][cc] != EMPTY
                       for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)))

        anchors = [c for c in range(SIZE) if is_anchor(c)]
        anchor_set = set(anchors)

        def record(start, end, tiles):
            placed = dict(tiles)
            main = cross_total = 0
            word_mult = 1
            word = []
            for col in range(start, end):
                if col in placed:
                    ch = placed[col]
                    prem = PREMIUMS.get((r, col))
                    v = tile_value(ch) * (3 if prem == "TL" else 2 if prem == "DL" else 1)
                    wm = 3 if prem == "TW" else 2 if prem == "DW" else 1
                    main += v
                    word_mult *= wm
                    if cross[col] is not None:
                        cross_total += (cross[col][1] + v) * wm
                else:
                    ch = row[col]
                    main += tile_value(ch)
                word.append(ch)
            score = main * word_mult + cross_total + (BINGO_BONUS if len(tiles) == 7 else 0)
            coords = [((r, col) if across else (col, r), ch) for col, ch in tiles]
            key = frozenset(coords)
            if key not in found:
                sr, sc = (r, start) if across else (start, r)
                found[key] = {
                    "id": f"{'A' if across else 'D'}{sr},{sc}:{''.join(word)}",
                    "across": across, "row": sr, "col": sc, "word": "".join(word),
                    "tiles": [(rr, cc, ch) for (rr, cc), ch in coords], "score": score,
                }

        def extend(c, node, tiles, start, anchor):
            if c < SIZE and row[c] != EMPTY:
                nxt = node.get(row[c].upper())
                if nxt:
                    extend(c + 1, nxt, tiles, start, anchor)
                return
            if node.get("$") and tiles and c > anchor and c - start >= 2:
                record(start, c, tiles)
            if c >= SIZE:
                return
            allowed = cross[c][0] if cross[c] is not None else None
            for L, child in node.items():
                if L == "$" or (allowed is not None and L not in allowed):
                    continue
                if counts[L]:
                    counts[L] -= 1
                    extend(c + 1, child, tiles + [(c, L)], start, anchor)
                    counts[L] += 1
                if counts["?"]:
                    counts["?"] -= 1
                    extend(c + 1, child, tiles + [(c, L.lower())], start, anchor)
                    counts["?"] += 1

        def left_part(anchor, node, tiles, limit):
            extend(anchor, node, tiles, anchor - len(tiles), anchor)
            if limit == 0:
                return
            for L, child in node.items():
                if L == "$":
                    continue
                for ch, key in ((L, L), (L.lower(), "?")):
                    if counts[key]:
                        counts[key] -= 1
                        # left-part tiles occupy the squares just before the anchor; shift them left
                        shifted = [(col - 1, t) for col, t in tiles] + [(anchor - 1, ch)]
                        left_part(anchor, child, shifted, limit - 1)
                        counts[key] += 1

        for anchor in anchors:
            if anchor > 0 and row[anchor - 1] != EMPTY:
                start = anchor - 1
                while start > 0 and row[start - 1] != EMPTY:
                    start -= 1
                node = TRIE
                for ch in row[start:anchor]:
                    node = node.get(ch.upper()) if node else None
                if node:
                    extend(anchor, node, [], start, anchor)
            else:
                limit, cc = 0, anchor - 1
                while cc >= 0 and row[cc] == EMPTY and cc not in anchor_set:
                    limit += 1
                    cc -= 1
                left_part(anchor, TRIE, [], limit)


@lru_cache(maxsize=256)
def placements(board, rack):
    """All legal word placements for `rack` on `board` (a 225-char string), keyed by move id."""
    rows = [board[i * SIZE:(i + 1) * SIZE] for i in range(SIZE)]
    first = set(board) == {EMPTY}
    found = {}
    _generate_lines(rows, rack, first, True, found)
    _generate_lines(["".join(col) for col in zip(*rows)], rack, first, False, found)
    return {m["id"]: m for m in found.values()}


def exchanges(rack):
    """Every distinct non-empty set of tiles that can be exchanged."""
    counts = sorted(Counter(rack).items())
    result = []
    for picks in itertools.product(*[range(n + 1) for _, n in counts]):
        tiles = "".join(ch * k for (ch, _), k in zip(counts, picks))
        if tiles:
            result.append(tiles)
    return result


def notation(m):
    coord = f"{m['row'] + 1}{COLS[m['col']]}" if m["across"] else f"{COLS[m['col']]}{m['row'] + 1}"
    return f"{coord} {m['word']}"


class ScrabbleBoard:
    def __init__(self, seed):
        self.seed = str(seed)
        self.bag = [ch for ch, n in COUNTS.items() for _ in range(n)]
        random.Random(f"{self.seed}:start").shuffle(self.bag)
        self.board = [EMPTY] * (SIZE * SIZE)
        self.racks = [self._draw(7), self._draw(7)]
        self.scores = [0, 0]
        self.turn = 0  # 0 = Player 1, 1 = Player 2
        self.ply = 0
        self.scoreless = 0
        self.over = False
        self.end_note = None

    def _draw(self, n):
        drawn = self.bag[-n:] if n else []
        del self.bag[len(self.bag) - len(drawn):]
        return drawn

    def board_str(self):
        return "".join(self.board)

    def rack_str(self):
        return "".join(sorted(self.racks[self.turn]))

    def word_moves(self):
        return placements(self.board_str(), self.rack_str())

    def exchange_moves(self):
        return exchanges(self.rack_str()) if len(self.bag) >= 7 else []

    def _take_from_rack(self, tiles):
        rack = self.racks[self.turn]
        for t in tiles:
            rack.remove(t)

    def push(self, move_id):
        """Play a move; return (notation, squares touched). Raise ValueError if illegal."""
        if self.over:
            raise ValueError("The game is over")
        squares = []
        if move_id == "PASS":
            text = "Pass"
            self.scoreless += 1
        elif move_id.startswith("X:"):
            tiles = move_id[2:]
            if len(self.bag) < 7 or tiles not in self.exchange_moves():
                raise ValueError(f"Illegal exchange {move_id}")
            self._take_from_rack(tiles)
            self.racks[self.turn] += self._draw(len(tiles))
            self.bag += list(tiles)
            random.Random(f"{self.seed}:{self.ply}").shuffle(self.bag)
            text = f"Exchange {tiles}"
            self.scoreless += 1
        else:
            m = self.word_moves().get(move_id)
            if m is None:
                raise ValueError(f"Illegal Scrabble move {move_id}")
            for r, c, ch in m["tiles"]:
                self.board[r * SIZE + c] = ch
                squares.append(f"{r},{c}")
            self._take_from_rack(["?" if ch.islower() else ch for _, _, ch in m["tiles"]])
            self.racks[self.turn] += self._draw(min(len(m["tiles"]), len(self.bag)))
            self.scores[self.turn] += m["score"]
            self.scoreless = 0 if m["score"] else self.scoreless + 1
            text = f"{notation(m)} ({m['score']})"
        self._check_end()
        self.turn = 1 - self.turn
        self.ply += 1
        return text, squares

    def _check_end(self):
        me, other = self.turn, 1 - self.turn
        if not self.racks[me] and not self.bag:
            bonus = sum(map(tile_value, self.racks[other]))
            self.scores[me] += bonus
            self.scores[other] -= bonus
            self.over = True
            self.end_note = f"{self.player_name(me)} went out (+{bonus} from the other rack)"
        elif self.scoreless >= MAX_SCORELESS_TURNS:
            for p in (0, 1):
                self.scores[p] -= sum(map(tile_value, self.racks[p]))
            self.over = True
            self.end_note = "six scoreless turns in a row; unplayed tiles deducted"

    @staticmethod
    def player_name(p):
        return f"Player {p + 1}"
