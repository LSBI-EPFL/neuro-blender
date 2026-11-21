"""
The results that one run of the tool keeps, so that going back is fast: the shapes of the mask file, the layer
images, the device map, the 3D scenes and the test renders.

flow.run() clears all of them at the start of each run. So a new run (example: Start again after a change of the
mask file) never uses a result of an old run. Inside one run, going back uses the kept results.
"""
_results = {}       # {kind: {key: result}}


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


def clear():
    """Forget all the results. flow.run() calls this at the start of each run."""
    _results.clear()
