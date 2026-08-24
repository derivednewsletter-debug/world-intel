"""One-shot collection — `python -m app.collect`."""
import time

from .collectors import run_all
from .db import init_db


def main() -> None:
    import sys
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    init_db()
    t0 = time.time()
    print("Collecting from all sources…")
    run_all()
    print(f"Done in {(time.time() - t0):.1f}s")


if __name__ == "__main__":
    main()
