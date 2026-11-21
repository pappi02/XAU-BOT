# Manual scripts

Exploratory scripts, run by hand. **Not tests**, despite their original names.

They were called `test_*.py` and sat in the repository root, where pytest would
try to import them. One of them (`data/test_data.py`) called `quit()` at module
level and aborted the entire test run with INTERNALERROR — which is why the
suite collected zero tests before Phase 1.7. They are renamed `check_*` and
moved here so that cannot happen again.

`test_execute_trade.py` was deleted rather than moved: its whole purpose was to
construct `TradeExecutor(None, None, None)` and exercise the mock-broker
fallback, which Phase 6.3 removed as audit finding M-05. Its coverage now lives
in `tests/test_execution_phase6.py`.
