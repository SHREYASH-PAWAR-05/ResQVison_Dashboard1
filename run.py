"""
Single-command launcher for the ResQVision dashboard.

Usage:
    python run.py

Then open http://localhost:8000 in a browser.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
