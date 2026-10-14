// Runs the Python game engine (engine.py) in the browser with Pyodide, off the main thread so the
// page stays responsive. Messages in: {id, body}. Messages out: {type: "status", text} while
// loading, then {id, ok, data | error} for each request.

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const PY_FILES = ["engine.py", "draughts.py", "go.py", "scrabble.py", "data/enable1.txt"];
const APP_DIR = "/home/pyodide/app";

importScripts(PYODIDE_URL + "pyodide.js");

const status = text => postMessage({ type: "status", text });
// Python errors arrive as full tracebacks; the last line is the readable part.
const lastLine = err => String(err.message || err).trim().split("\n").pop();

async function start() {
  status("Downloading Python (first visit only, about 10 MB)…");
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

  status("Installing the chess library…");
  await pyodide.loadPackage("micropip");
  await pyodide.pyimport("micropip").install("chess==1.10.0");

  status("Loading the game rules and word list…");
  pyodide.FS.mkdirTree(APP_DIR + "/data");
  await Promise.all(PY_FILES.map(async name => {
    const res = await fetch(name);
    if (!res.ok) throw new Error(`Could not load ${name} (HTTP ${res.status})`);
    pyodide.FS.writeFile(`${APP_DIR}/${name}`, await res.text());
  }));
  pyodide.runPython(`import sys; sys.path.insert(0, "${APP_DIR}")`);
  return pyodide.pyimport("engine").handle;  // also builds the Scrabble word trie, once
}

const ready = start();
ready.then(() => status(""), err => status("Failed to start Python: " + lastLine(err)));

onmessage = async ({ data: { id, body } }) => {
  try {
    const handle = await ready;
    postMessage({ id, ...JSON.parse(handle(JSON.stringify(body))) });
  } catch (err) {
    postMessage({ id, ok: false, error: lastLine(err) });
  }
};
