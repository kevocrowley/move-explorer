"""Move Explorer engine: replays a game of chess, draughts, Scrabble or Go and reports every legal move
available after each move, with running totals.

It runs in the browser under Pyodide (see worker.js); `handle` is the entry point the page calls.
"""

import json
import math
import random
from functools import lru_cache

import chess

import go
import scrabble
from draughts import DraughtsBoard, square_name, square_number

ATOMS_ON_EARTH = 133 * 10**48  # ~1.33 x 10^50

PIECE_NAMES = {
    chess.PAWN: "Pawn",
    chess.KNIGHT: "Knight",
    chess.BISHOP: "Bishop",
    chess.ROOK: "Rook",
    chess.QUEEN: "Queen",
    chess.KING: "King",
}


class ChessGame:
    side_names = {"white": "White", "black": "Black"}

    @staticmethod
    def new(opts):
        return chess.Board()

    @staticmethod
    def push(board, uci):
        """Play a UCI move; return (notation, squares it touched). Raise ValueError if illegal."""
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move {uci} in position {board.fen()}")
        san = board.san(move)
        board.push(move)
        return san, [chess.square_name(move.from_square), chess.square_name(move.to_square)]

    @staticmethod
    def status(board):
        if board.is_checkmate():
            winner = "Black" if board.turn == chess.WHITE else "White"
            return f"Checkmate — {winner} wins"
        if board.is_stalemate():
            return "Stalemate — draw"
        if board.is_insufficient_material():
            return "Insufficient material — draw"
        if board.can_claim_threefold_repetition():
            return "Threefold repetition (draw can be claimed)"
        if board.can_claim_fifty_moves():
            return "Fifty-move rule (draw can be claimed)"
        side = "White" if board.turn == chess.WHITE else "Black"
        return f"{side} to move" + (" — in check" if board.is_check() else "")

    @classmethod
    def describe(cls, board):
        moves = []
        for move in board.legal_moves:
            piece = board.piece_at(move.from_square)
            moves.append({
                "uci": move.uci(),
                "san": board.san(move),
                "from": chess.square_name(move.from_square),
                "to": chess.square_name(move.to_square),
                "piece": PIECE_NAMES[piece.piece_type],
                "capture": board.is_capture(move),
                "check": board.gives_check(move),
                "promotion": chess.piece_symbol(move.promotion) if move.promotion else None,
            })
        moves.sort(key=lambda m: (list(PIECE_NAMES.values()).index(m["piece"]), m["san"]))
        return {
            "pieces": {chess.square_name(sq): p.symbol() for sq, p in board.piece_map().items()},
            "turn": "white" if board.turn == chess.WHITE else "black",
            "status": cls.status(board),
            "game_over": board.is_game_over(claim_draw=False),
            "check_square": chess.square_name(board.king(board.turn)) if board.is_check() else None,
            "legal_moves": moves,
        }


class DraughtsGame:
    side_names = {"white": "White", "black": "Black"}

    @staticmethod
    def new(opts):
        return DraughtsBoard()

    @staticmethod
    def push(board, move_id):
        try:
            notation = board.push(move_id)
        except (ValueError, KeyError, IndexError):
            raise ValueError(f"Illegal draughts move {move_id}")
        return notation, move_id.split("-")

    @staticmethod
    def describe(board):
        side = board.side_name()
        draw = board.draw_reason()
        legal = [] if draw else board.legal_moves()
        moves = []
        for path, captured in legal:
            piece = board.pieces[path[0]]
            moves.append({
                "uci": board.move_id(path),
                "san": board.notation(path, captured),
                "from": square_name(path[0]),
                "to": square_name(path[-1]),
                "piece": "King" if piece.isupper() else "Man",
                "capture": bool(captured),
                "check": False,
                "promotion": "king" if piece.islower() and board._crowns(piece, path[-1]) else None,
            })
        moves.sort(key=lambda m: (m["piece"] == "King", [int(n) for n in m["san"].replace("x", "-").split("-")]))

        if draw:
            status = draw
        elif not moves:
            status = f"{board.side_name('w' if board.turn == 'b' else 'b')} wins — {side} has no moves left"
        else:
            status = f"{side} to move" + (" (must capture)" if moves[0]["capture"] else "")
        return {
            "pieces": {square_name(sq): p for sq, p in board.pieces.items()},
            "numbers": {square_name((f, r)): square_number((f, r))
                        for f in range(8) for r in range(8) if (f + r) % 2 == 0},
            "turn": "black" if board.turn == "b" else "white",
            "status": status,
            "game_over": not moves,
            "check_square": None,
            "legal_moves": moves,
        }


@lru_cache(maxsize=256)
def scrabble_legal_moves(board, rack, can_exchange):
    """Every legal Scrabble move as a list of move dicts: words (best score first), exchanges, pass."""
    words = sorted(scrabble.placements(board, rack).values(), key=lambda m: (-m["score"], m["word"]))
    moves = [{
        "uci": m["id"],
        "san": scrabble.notation(m),
        "score": m["score"],
        "piece": "Word",
        "tiles": [[r, c, ch] for r, c, ch in m["tiles"]],
        "capture": False, "check": False, "promotion": None,
    } for m in words]
    if can_exchange:
        moves += [{"uci": f"X:{t}", "san": f"Exchange {t}", "score": 0, "piece": "Exchange",
                   "capture": False, "check": False, "promotion": None} for t in scrabble.exchanges(rack)]
    moves.append({"uci": "PASS", "san": "Pass", "score": 0, "piece": "Pass",
                  "capture": False, "check": False, "promotion": None})
    return moves


class ScrabbleGame:
    side_names = {"white": "Player 1", "black": "Player 2"}
    # Positions can have tens of thousands of plays, so responses list only the best-scoring ones
    # (the counts always cover every move).
    list_limit_history = 100
    list_limit_current = 5000

    @staticmethod
    def new(opts):
        seed = opts.get("seed")
        return scrabble.ScrabbleBoard(seed if seed is not None else random.randrange(10**9))

    @staticmethod
    def push(board, move_id):
        return board.push(move_id)

    @staticmethod
    def describe(board):
        name = board.player_name(board.turn)
        if board.over:
            moves = []
            a, b = board.scores
            result = "it's a draw" if a == b else f"{board.player_name(0 if a > b else 1)} wins"
            status = f"Game over: {result} {a}–{b} ({board.end_note})"
        else:
            moves = scrabble_legal_moves(board.board_str(), board.rack_str(), len(board.bag) >= 7)
            status = f"{name} to move"
        return {
            "pieces": {f"{i // scrabble.SIZE},{i % scrabble.SIZE}": ch for i, ch in enumerate(board.board) if ch != scrabble.EMPTY},
            "turn": "white" if board.turn == 0 else "black",
            "status": status,
            "game_over": board.over,
            "check_square": None,
            "legal_moves": list(moves),
            "racks": ["".join(r) for r in board.racks],
            "scores": list(board.scores),
            "bag": len(board.bag),
        }


class GoGame:
    side_names = {"black": "Black", "white": "White"}
    list_limit_history = 40  # up to 362 moves per position; earlier positions list only a sample

    @staticmethod
    def new(opts):
        return go.GoBoard(int(opts.get("size", 19)))

    @staticmethod
    def push(board, move):
        return board.push(move)

    @staticmethod
    def describe(board):
        size = board.size
        side = "Black" if board.turn == go.BLACK else "White"
        if board.over:
            legal, illegal = [], {}
            b, w = board.score()
            result = "It's a draw" if b == w else f"{'Black' if b > w else 'White'} wins by {abs(b - w):g}"
            status = (f"Game over: {result} "
                      f"(area score {b:g}–{w:g} incl. {go.KOMI:g} komi; dead stones not removed)")
        else:
            legal, illegal = board.legal_moves()
            status = f"{side} to move" + (" (White passed)" if board.passes and board.turn == go.BLACK
                                          else " (Black passed)" if board.passes else "")
        moves = [{
            "uci": go.point_name(p, size),
            "san": go.point_name(p, size) + (f" (x{caps})" if caps else ""),
            "piece": "Point",
            "capture": bool(caps), "check": False, "promotion": None,
        } for p, caps in legal]
        if not board.over:
            moves.append({"uci": "pass", "san": "Pass", "piece": "Pass",
                          "capture": False, "check": False, "promotion": None})
        return {
            "pieces": {go.point_name(p, size): "b" if v == go.BLACK else "w"
                       for p, v in enumerate(board.board) if v != go.EMPTY},
            "illegal_points": {go.point_name(p, size): why for p, why in illegal.items()},
            "size": size,
            "star_points": [go.point_name(p, size) for p in go.star_points(size)],
            "captures": {"black": board.captures[go.BLACK], "white": board.captures[go.WHITE]},
            "turn": "black" if board.turn == go.BLACK else "white",
            "status": status,
            "game_over": board.over,
            "check_square": None,
            "legal_moves": moves,
        }


GAMES = {"chess": ChessGame, "draughts": DraughtsGame, "scrabble": ScrabbleGame, "go": GoGame}


class MoveError(ValueError):
    pass


def position(body):
    """Given the moves played so far, return the position after each ply with its legal moves.

    Body: {"game": "chess"|"draughts"|"scrabble"|"go", "moves": [...], "random_moves": n,
    "seed": s (Scrabble), "size": 9|13|19 (Go)}.
    The optional random_moves extends the line with n random legal moves (stopping when the game
    ends). Scrabble uses the seed to decide the tile draws, so a game replays identically.
    """
    game = GAMES.get(body.get("game", "chess"))
    if game is None:
        raise MoveError(f"Unknown game {body.get('game')!r}")
    moves = list(body.get("moves", []))
    random_left = int(body.get("random_moves", 0))

    board = game.new(body)
    history = []
    white_sum = black_sum = 0
    product = 1  # product of the move counts at every position before this one
    san = squares = None
    ply = 0
    while True:
        entry = game.describe(board)
        count = len(entry["legal_moves"])
        if entry["turn"] == "white":
            white_sum += count
        else:
            black_sum += count
        entry.update({
            "legal_count": count,
            "ply": ply,
            "san": san,
            "move_squares": squares,
            "white_sum": white_sum,
            "black_sum": black_sum,
            "total_sum": white_sum + black_sum,
            "product": str(product),
            "product_log10": math.log10(product),
        })
        history.append(entry)

        if ply == len(moves):
            if random_left <= 0 or entry["game_over"]:
                break
            moves.append(random.choice(entry["legal_moves"])["uci"])
            random_left -= 1
        san, squares = game.push(board, moves[ply])
        product *= count
        ply += 1

    # Trim long move lists (Scrabble) to keep the response small; legal_count keeps the real total.
    for i, entry in enumerate(history):
        limit = getattr(game, "list_limit_current" if i == len(history) - 1 else "list_limit_history", None)
        if limit and len(entry["legal_moves"]) > limit:
            entry["legal_moves"] = entry["legal_moves"][:limit]
            entry["legal_truncated"] = True

    return {
        "game": body.get("game", "chess"),
        "side_names": game.side_names,
        "layout": {f"{r},{c}": p for (r, c), p in scrabble.PREMIUMS.items()} if game is ScrabbleGame else None,
        "moves": moves,
        "history": history,
        "atoms_on_earth_log10": math.log10(ATOMS_ON_EARTH),
    }


def handle(body_json):
    """JSON in, JSON out: {"ok": true, "data": {...}} or {"ok": false, "error": "..."}."""
    try:
        return json.dumps({"ok": True, "data": position(json.loads(body_json))})
    except ValueError as e:  # illegal moves, bad options
        return json.dumps({"ok": False, "error": str(e)})
