"""Stand-ins for the preview process in tests: one that never answers, one that dies."""
import os
import time


def hang(request):
    time.sleep(60)


def crash(request):
    os._exit(3)
