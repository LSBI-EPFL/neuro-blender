"""
The results that one run of the tool keeps, so that going back is fast: the shapes of the mask file, the layer
images, the device map, the 3D scenes and the test renders.

The results stay for the next run with the same mask file (example: Start again, then "change answers"), so the
tool does not read the file again. flow.run() calls use_mask_file(): if the file is a different file, or if it
changed on disk (modification time or size), the tool forgets all the results. Inside one run, going back uses the
kept results.
"""
import os

_results = {}       # {kind: {key: result}}
_mask_stamp = None  # (path, modification time, size) of the mask file of the kept results


def get(kind, key, make):
    """Return the result of this kind for this key. The first time in a run, make it with make()."""
    store = _results.setdefault(kind, {})
    if key not in store:
        store[key] = make()
    return store[key]


def has(kind, key):
    """True if this run made the result of this kind for this key already (example: images on disk)."""
    return key in _results.get(kind, {})


def add(kind, key):
    """Record that this run made the result of this kind for this key (example: images on disk)."""
    _results.setdefault(kind, {})[key] = True


def use_mask_file(mask_file):
    """Keep the results only if they come from this mask file, and the file did not change since then."""
    global _mask_stamp
    try:
        info = os.stat(mask_file)
        stamp = (os.path.normcase(os.path.abspath(mask_file)), info.st_mtime_ns, info.st_size)
    except OSError:
        stamp = None
    if stamp is None or stamp != _mask_stamp:
        clear()
    _mask_stamp = stamp


def clear():
    """Forget all the results."""
    global _mask_stamp
    _results.clear()
    _mask_stamp = None
