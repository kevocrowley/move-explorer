# Move Explorer

**Live site: https://kevocrowley.github.io/move-explorer/**

A web app that shows **every legal move available after each move** in four games
(chess, English draughts, Scrabble and Go), and uses those counts to show that there are more possible
games than atoms on planet Earth.

## What it shows

- **This game:** the total number of moves that were available during the one game on the board,
  split by player.
- **All possible games ([Shannon's method](https://en.wikipedia.org/wiki/Shannon_number)):** the
  move counts at each turn multiplied together, compared with about 1.33×10⁵⁰ atoms on Earth and with
  a ladder of other benchmarks: a human, Mount Everest, the Moon, the Sun, the solar system and the
  observable universe.
- The full working for both, plus each game's rules and its history of being played or solved by computers.

| Game | Options at the start | Typically passes Earth's atoms after |
|---|---|---|
| Go 19×19 | 362 | ~20 moves |
| Chess | 20 | ~35 moves |
| Scrabble | hundreds to thousands per rack | depends on the tiles |
| Draughts | 7 | only in long games |

## How it runs

The game logic is Python, but there is no server: the page runs it in the browser with
[Pyodide](https://pyodide.org) inside a Web Worker. The first visit downloads Python (about 10 MB,
then cached), which takes a few seconds; after that, moves are instant. That means the whole site is
static files and is hosted free on GitHub Pages.

To run it locally, serve the folder with any static file server:

```bash
python3 -m http.server 5050
```

Then open http://127.0.0.1:5050.

## Files

- `engine.py`: replays a game and returns every position with its legal moves and running totals
  (`handle()` is the entry point the page calls).
- `worker.js`: loads Pyodide and python-chess, then runs `engine.py` off the main thread.
- `draughts.py`, `scrabble.py`, `go.py`: rules and move generators (chess uses
  [python-chess](https://python-chess.readthedocs.io/)).
- `index.html`: the whole front end.
- `data/enable1.txt`: the ENABLE word list used for Scrabble.

## Rules and simplifications

- **Chess:** standard rules via python-chess.
- **Draughts:** English draughts on 8×8; draws by threefold repetition or 40 moves each without a capture
  or man move are automatic here.
- **Scrabble:** standard English 100-tile set and board. Words come from the public-domain ENABLE list,
  not the official Collins or NWL lists, so a few words (such as QI and ZA) are missing.
- **Go:** 9×9, 13×13 or 19×19; positional superko; area scoring with 7.5 komi. Dead stones are not
  removed before scoring.

The Shannon figure is an estimate: it assumes every other line of play has as many options as the
line actually played. For Scrabble it also ignores the luck of the tile draws, which would make the
true number larger still.

## Credits

- [Pyodide](https://pyodide.org) runs the Python in the browser; chess rules use
  [python-chess](https://python-chess.readthedocs.io/) 1.10.0 (the newest version published in a form Pyodide can install).
- Word list: ENABLE (Enhanced North American Benchmark Lexicon), public domain.
