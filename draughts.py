"""English draughts (checkers) rules on an 8x8 board.

Squares use chess-style names (a1 is a dark, playable square) so the web board can share
rendering with chess. Notation uses the standard 1-32 numbering: Black starts on 1-12 at the
top, White on 21-32 at the bottom, and Black moves first.

Rules: men move and capture diagonally forward only; kings move and capture one square in any
diagonal direction; captures are compulsory and a multi-jump must be completed; a man that
reaches the far row is crowned and its move ends. A side with no legal moves loses. Draws
(simplified): threefold repetition, or 40 moves each with no capture and no man moving.
"""

from collections import Counter

FILES = "abcdefgh"
DRAW_QUIET_PLIES = 80


def square_name(sq):
    return FILES[sq[0]] + str(sq[1] + 1)


def parse_square(name):
    return FILES.index(name[0]), int(name[1:]) - 1


def square_number(sq):
    """Standard draughts number 1-32 (1 = b8, 4 = h8, 29 = a1, 32 = g1)."""
    file, rank = sq
    return (7 - rank) * 4 + file // 2 + 1


class DraughtsBoard:
    def __init__(self):
        self.pieces = {}  # (file, rank) -> 'b', 'B' (black man/king), 'w', 'W'
        for rank in range(8):
            for file in range(8):
                if (file + rank) % 2 == 0:
                    if rank <= 2:
                        self.pieces[(file, rank)] = "w"
                    elif rank >= 5:
                        self.pieces[(file, rank)] = "b"
        self.turn = "b"
        self.quiet_plies = 0  # plies since the last capture or man move
        self.seen = Counter([self.key()])

    def key(self):
        return self.turn, frozenset(self.pieces.items())

    # --- move generation -------------------------------------------------

    @staticmethod
    def _directions(piece):
        if piece.isupper():
            return [(1, 1), (-1, 1), (1, -1), (-1, -1)]
        return [(1, 1), (-1, 1)] if piece == "w" else [(1, -1), (-1, -1)]

    @staticmethod
    def _crowns(piece, sq):
        return (piece == "w" and sq[1] == 7) or (piece == "b" and sq[1] == 0)

    @staticmethod
    def _on_board(sq):
        return 0 <= sq[0] < 8 and 0 <= sq[1] < 8

    def _jumps(self, start, piece):
        """All complete capture paths for the piece on `start`, as (path, captured) tuples."""
        results = []

        def search(sq, path, captured):
            extended = False
            for df, dr in self._directions(piece):
                over = (sq[0] + df, sq[1] + dr)
                land = (sq[0] + 2 * df, sq[1] + 2 * dr)
                if not self._on_board(land) or over in captured:
                    continue
                victim = self.pieces.get(over)
                if victim is None or victim.lower() == self.turn:
                    continue
                if land != start and land in self.pieces:  # start square is empty once we leave it
                    continue
                extended = True
                if not piece.isupper() and self._crowns(piece, land):
                    results.append((path + [land], captured + [over]))  # crowning ends the move
                else:
                    search(land, path + [land], captured + [over])
            if not extended and captured:
                results.append((path, captured))

        search(start, [start], [])
        return results

    def legal_moves(self):
        """List of (path, captured) tuples. Captures are compulsory."""
        mine = [(sq, p) for sq, p in self.pieces.items() if p.lower() == self.turn]
        captures = [j for sq, p in mine for j in self._jumps(sq, p)]
        if captures:
            return captures
        moves = []
        for sq, p in mine:
            for df, dr in self._directions(p):
                to = (sq[0] + df, sq[1] + dr)
                if self._on_board(to) and to not in self.pieces:
                    moves.append(([sq, to], []))
        return moves

    # --- move ids and notation ---------------------------------------------

    @staticmethod
    def move_id(path):
        return "-".join(square_name(sq) for sq in path)

    @staticmethod
    def notation(path, captured):
        sep = "x" if captured else "-"
        return sep.join(str(square_number(sq)) for sq in path)

    def push(self, move_id):
        """Play a move given as e.g. 'c3-d4' or 'c3-e5-g7'; return its notation."""
        for path, captured in self.legal_moves():
            if self.move_id(path) == move_id:
                break
        else:
            raise ValueError(f"Illegal draughts move {move_id}")
        piece = self.pieces.pop(path[0])
        for sq in captured:
            del self.pieces[sq]
        man_moved = piece.islower()
        if man_moved and self._crowns(piece, path[-1]):
            piece = piece.upper()
        self.pieces[path[-1]] = piece
        self.quiet_plies = 0 if captured or man_moved else self.quiet_plies + 1
        self.turn = "w" if self.turn == "b" else "b"
        self.seen[self.key()] += 1
        return self.notation(path, captured)

    # --- game state ---------------------------------------------------------

    def draw_reason(self):
        if self.seen[self.key()] >= 3:
            return "Draw by threefold repetition"
        if self.quiet_plies >= DRAW_QUIET_PLIES:
            return "Draw: 40 moves each with no capture and no man moving"
        return None

    def side_name(self, side=None):
        return "Black" if (side or self.turn) == "b" else "White"
