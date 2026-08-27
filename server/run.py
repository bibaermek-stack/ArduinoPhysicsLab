"""Production entrypoint for Railway/Docker. Avoids shell scripts and CRLF."""

from __future__ import annotations

import os
import sys


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    print(f"Arduino Physics Lab starting on 0.0.0.0:{port}", flush=True)
    print(f"PYTHONPATH={os.environ.get('PYTHONPATH', '')}", flush=True)
    print(f"cwd={os.getcwd()}", flush=True)
    import uvicorn

    uvicorn.run(
        "server.app.main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",
    )


if __name__ == "__main__":
    sys.exit(main())
