"""
Cancellation primitives.

The cooperative-cancellation contract is a plain callable
``cancel_check: Callable[[], bool]``.  Long-running loops accept such a
callable, poll it periodically, and raise :class:`OperationCancelled`
when it returns ``True``.  The callable form keeps the parsing and
writing layers independent of how cancellation is signalled (a worker
flag, a test stub, etc.), and this module has no project imports so
all of them can depend on it.
"""


class OperationCancelled(Exception):
    """Raised to unwind a long-running operation when a caller's
    ``cancel_check`` reports that cancellation was requested.

    This represents control flow, not a failure: callers should catch
    it and treat it as a clean, user-initiated stop (no error dialog).
    """