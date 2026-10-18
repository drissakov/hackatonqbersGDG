"""Production entrypoint honoring Render's actual PORT without shell expansion."""

import os

import uvicorn


def main():
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, access_log=False)


if __name__ == "__main__":
    main()
