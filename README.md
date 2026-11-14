# Face Liveness + Access Kiosk (HID Hackathon)

Decides ALLOW / STEP-UP / DENY from a webcam in under 2 seconds by checking liveness,
identity and the campus schedule. Runs locally, so it keeps working offline.

```
scripts/get_models.sh
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
scripts/run.sh
open http://localhost:8000
```

- How it works and how to explain it: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Current state and next steps: [docs/HANDOFF.md](docs/HANDOFF.md)
- The brief: [docs/brief/](docs/brief/)

The earlier PCA/Eigenfaces prototype is kept in `legacy/` and is not used.
