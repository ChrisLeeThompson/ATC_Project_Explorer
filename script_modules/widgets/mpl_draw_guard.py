"""
Matplotlib Draw Guard

Protects an embedded matplotlib canvas from a draw that is still pending
when Qt deletes the widget (for example, a detached site window closed
mid-drag).
"""


def install_stale_draw_guard(canvas) -> None:
    """Defuse matplotlib's zero-delay draw timer for a canvas that Qt
    is about to delete.

    ``FigureCanvasQT.draw_idle`` schedules ``QTimer.singleShot(0,
    self._draw_idle)``, a callback that cannot be cancelled and is not
    tied to the canvas's Qt lifetime.  If the canvas is deleted with a
    draw pending, the callback still fires and calls ``self.height()``
    on the freed C++ widget: a RuntimeError at best, heap corruption at
    worst.

    ``_draw_idle`` checks the pure-Python ``_draw_pending`` flag before
    touching any C++ state, so clearing the flag when Qt reports the
    destruction makes the stale callback a harmless no-op.  Writing an
    attribute on the Python wrapper is safe after C++ deletion.

    :param canvas: A ``FigureCanvasQTAgg`` instance.
    """
    def _cancel_pending_draw(*_args):
        canvas._draw_pending = False

    canvas.destroyed.connect(_cancel_pending_draw)
