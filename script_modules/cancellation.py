"""
Cancellation primitives.

Provides the exception used to unwind long-running project-load
operations when the user requests cancellation.  It lives in its own
bottom-of-stack module (no project imports) so the parsers, the
metadata writer, and the load worker can all import it *downward*
without any of them depending on the worker or the Qt layer.

The cooperative-cancellation contract is a plain callable
``cancel_check: Callable[[], bool]``.  Long-running loops accept such a
callable, poll it periodically, and raise :class:`OperationCancelled`
when it returns ``True``.  Expressing the contract as a callable keeps
the parsing and writing layers independent of *how* cancellation is
signalled (a worker flag, a test stub, etc.).
"""


class OperationCancelled(Exception):
    """Raised to unwind a long-running operation when a caller's
    ``cancel_check`` reports that cancellation was requested.

    This represents control flow, not a failure: callers should catch
    it and treat it as a clean, user-initiated stop (no error dialog).
    """