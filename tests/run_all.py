"""
Run all the tests, and show one result.

Run:  python tests/run_all.py          the tests that need no screen and no Blender (back end, terminal questions)
      python tests/run_all.py --all    also the window test (it opens windows for some seconds) and the image
                                       regression test (it needs Blender, about 10 s)
The exit code is 0 only if all the tests pass.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["test_backend.py", "test_questions.py"]
WITH_SCREEN_OR_BLENDER = ["test_window.py", "test_render.py"]

files = FILES + (WITH_SCREEN_OR_BLENDER if "--all" in sys.argv else [])
results = []
for name in files:
    print(f"\n== {name}", flush=True)
    passed = subprocess.run([sys.executable, os.path.join(HERE, name)]).returncode == 0
    results.append((name, passed))

print("\n== Result")
for name, passed in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name}")
sys.exit(0 if all(passed for _, passed in results) else 1)
