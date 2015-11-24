import contextlib

@contextlib.contextmanager
def suppress(*exceptions):
    try:
        yield
    except exceptions:
        pass
