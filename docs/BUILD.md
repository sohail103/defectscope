# Build and run

## Requirements
Python 3.11+, Node 18+, npm. Internet is needed only to `pip install`, `npm install`, and (optionally) download the NASA datasets.

## Backend
```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```
Run it alone: `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`

## Frontend
```bash
cd frontend && npm install
npm run dev      # http://127.0.0.1:5173 (proxies /api to :8000)
npm run build    # produces frontend/dist, which the backend serves on :8000
```

## One command
* `./scripts/dev.sh`: backend (auto-reload) + Vite dev server.
* `./scripts/start.sh`: builds the UI if needed and serves everything from http://127.0.0.1:8000.

## Configuration (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| `DEFECTSCOPE_HOME` | repo root | where workspaces/, models/, experiments/, datasets/ live |
| `DEFECTSCOPE_MAX_UPLOAD_MB` | 200 | maximum ZIP upload size |
| `DEFECTSCOPE_MAX_EXTRACTED_MB` | 800 | maximum expanded size |
| `DEFECTSCOPE_MAX_FILES` | 50000 | maximum files per upload |
| `DEFECTSCOPE_ALLOW_LOCAL_PATHS` | 0 | set to 1 to enable `POST /api/projects/local-path` (copies a directory from this machine) |

The server binds to 127.0.0.1 only. Do not change `--host` unless you understand that anyone who can reach the port can upload files.

## Optional tools
Clang, clang-tidy, cppcheck, Ruff, Pylint and Bandit are **not used yet** (see LIMITATIONS). Nothing needs installing for current features.

## Offline dataset install
If the download fails (network policy), download https://github.com/klainfo/NASADefectDataset as a ZIP and use
Model lab → Datasets → *Import ZIP manually*.

## Tests
`cd backend && python -m pytest -q` (15 tests; the NASA-specific one skips if data is absent).
