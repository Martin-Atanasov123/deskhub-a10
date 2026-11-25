"""Entry point for the packaged DeskHub.exe (PyInstaller needs a plain script, not a package module)."""
import multiprocessing

from deskhub.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
