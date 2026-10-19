"""Frozen Windows entry point; use the same application composition as Python."""

from multiprocessing import freeze_support

from sim_manager.app import main


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
