import sys
import os

print("Python version:", sys.version)
try:
    import gui.tabs.users_tab as ut
    print("Loaded users_tab from:", ut.__file__)
except Exception as e:
    print("Error importing:", e)
