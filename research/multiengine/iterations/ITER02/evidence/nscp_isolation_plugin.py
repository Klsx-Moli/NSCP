"""pytest-only plugin: retire stale application-wide Qt event filters after each test.

Production source untouched. ContextHelpButton installs an app-wide event filter;
when several MainWindow instances coexist, every event is dispatched through every
filter, making stylesheet re-polish superlinear. This plugin removes those filters
between tests but keeps widget objects alive, preserving fixture semantics.
"""
import gc

import pytest

_installed = []


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    from npsc_gui.help_popover import ContextHelpButton
    if getattr(ContextHelpButton, "_nscp_filter_tracked", False):
        return
    original = ContextHelpButton.__init__

    def tracked_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        _installed.append(self)

    ContextHelpButton.__init__ = tracked_init
    ContextHelpButton._nscp_filter_tracked = True


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        for button in list(_installed):
            try:
                app.removeEventFilter(button)
            except Exception:
                pass
    _installed.clear()
    gc.collect()
