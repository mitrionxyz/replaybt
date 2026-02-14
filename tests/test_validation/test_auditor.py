"""Tests for the BacktestAuditor."""

import tempfile
from pathlib import Path

import pytest

from replaybt.validation.auditor import BacktestAuditor, Issue, audit_file


# -- Fixtures: source code snippets --

CLEAN_SOURCE = '''\
import pandas as pd

SLIPPAGE = 0.0002
FEE = 0.00015

pending_order = None

for i in range(len(df)):
    row = df.iloc[i]

    # Phase 1: Execute pending
    if pending_order:
        entry_price = row['open'] * (1 + SLIPPAGE)
        pending_order = None

    # Phase 3: Check exits
    if position:
        o = row['open']
        if o <= position.stop_loss:
            exit_price = o
        elif row['low'] <= position.stop_loss:
            exit_price = position.stop_loss

    # Phase 4: New signals
    if not position and rsi < 25:
        pending_order = 'LONG'
'''

SAME_BAR_SOURCE = '''\
for i in range(len(df)):
    row = df.iloc[i]
    if rsi < 25:
        entry_price = row['close']
'''

NO_PENDING_SOURCE = '''\
SLIPPAGE = 0.0002
FEE = 0.00015

for i in range(len(df)):
    row = df.iloc[i]
    if rsi < 25:
        entry_price = row['close']
'''

FUTURE_ACCESS_SOURCE = '''\
SLIPPAGE = 0.0002
FEE = 0.00015
pending_order = None

for i in range(len(df)):
    next_bar = df.iloc[i+1]
    if next_bar['close'] > 100:
        pending_order = 'LONG'
'''

NO_SLIPPAGE_SOURCE = '''\
pending_order = None
FEE = 0.00015

for i in range(len(df)):
    row = df.iloc[i]
    if pending_order:
        entry_price = row['open']
        pending_order = None
'''

NO_FEES_SOURCE = '''\
SLIPPAGE = 0.0002
pending_order = None

for i in range(len(df)):
    row = df.iloc[i]
    if pending_order:
        entry_price = row['open']
        pending_order = None
'''

GAP_NO_CHECK_SOURCE = '''\
SLIPPAGE = 0.0002
FEE = 0.00015
pending_order = None

def check_exit(pos, row):
    if row['low'] <= pos.stop_loss:
        return pos.stop_loss, 'SL'
    return None, None
'''

WRAPPER_SOURCE = '''\
from backtest_combined_clean import TrendMasterBacktest

bt = TrendMasterBacktest()
bt.run()
'''

ENTRY_CLOSE_VAR_SOURCE = '''\
SLIPPAGE = 0.0002
FEE = 0.00015

for i in range(len(df)):
    row = df.iloc[i]
    close = row['close']
    if rsi < 25:
        entry_price = close
'''


class TestCleanCode:
    def test_clean_code_no_issues(self):
        auditor = BacktestAuditor(CLEAN_SOURCE, "clean.py")
        issues = auditor.audit()
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert len(critical) == 0

    def test_is_clean_true(self):
        auditor = BacktestAuditor(CLEAN_SOURCE, "clean.py")
        auditor.audit()
        assert auditor.is_clean is True


class TestSameBarExecution:
    def test_detected_row_close(self):
        auditor = BacktestAuditor(SAME_BAR_SOURCE, "bad.py")
        issues = auditor.audit()
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert any("close price" in i.message.lower() for i in critical)

    def test_detected_close_variable(self):
        auditor = BacktestAuditor(ENTRY_CLOSE_VAR_SOURCE, "bad2.py")
        issues = auditor.audit()
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert any("close price" in i.message.lower() for i in critical)


class TestMissingPendingOrder:
    def test_no_pending_flagged(self):
        auditor = BacktestAuditor(NO_PENDING_SOURCE, "no_pending.py")
        issues = auditor.audit()
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert any("pending" in i.message.lower() for i in critical)


class TestFutureDataAccess:
    def test_iloc_plus_detected(self):
        auditor = BacktestAuditor(FUTURE_ACCESS_SOURCE, "future.py")
        issues = auditor.audit()
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert any("future bar" in i.message.lower() for i in critical)


class TestSlippageAndFees:
    def test_missing_slippage(self):
        auditor = BacktestAuditor(NO_SLIPPAGE_SOURCE, "no_slip.py")
        issues = auditor.audit()
        warnings = [i for i in issues if i.severity == "WARNING"]
        assert any("slippage" in i.message.lower() for i in warnings)

    def test_missing_fees(self):
        auditor = BacktestAuditor(NO_FEES_SOURCE, "no_fees.py")
        issues = auditor.audit()
        warnings = [i for i in issues if i.severity == "WARNING"]
        assert any("fees" in i.message.lower() for i in warnings)


class TestWrapperScript:
    def test_wrapper_detected(self):
        auditor = BacktestAuditor(WRAPPER_SOURCE, "wrapper.py")
        issues = auditor.audit()
        assert len(issues) == 1
        assert issues[0].severity == "INFO"
        assert "wrapper" in issues[0].message.lower()

    def test_wrapper_skips_detailed_checks(self):
        """Wrapper should only have the one INFO issue, no detailed checks."""
        auditor = BacktestAuditor(WRAPPER_SOURCE, "wrapper.py")
        issues = auditor.audit()
        assert len(issues) == 1


class TestReportFormatting:
    def test_report_clean(self):
        auditor = BacktestAuditor(CLEAN_SOURCE, "clean.py")
        auditor.audit()
        report = auditor.report()
        assert "BACKTEST AUDIT: clean.py" in report
        assert "NO ISSUES FOUND" in report

    def test_report_with_issues(self):
        auditor = BacktestAuditor(SAME_BAR_SOURCE, "bad.py")
        auditor.audit()
        report = auditor.report()
        assert "CRITICAL" in report
        assert "VERDICT" in report
        assert "UNRELIABLE" in report

    def test_report_warnings_only(self):
        auditor = BacktestAuditor(NO_SLIPPAGE_SOURCE, "warn.py")
        auditor.audit()
        report = auditor.report()
        assert "WARNINGS" in report
        assert "NEEDS REVIEW" in report


class TestIsCleanProperty:
    def test_is_clean_false_with_critical(self):
        auditor = BacktestAuditor(SAME_BAR_SOURCE, "bad.py")
        auditor.audit()
        assert auditor.is_clean is False

    def test_is_clean_true_warnings_only(self):
        auditor = BacktestAuditor(NO_SLIPPAGE_SOURCE, "warn.py")
        auditor.audit()
        assert auditor.is_clean is True


class TestAuditFileConvenience:
    def test_audit_file_works(self, tmp_path):
        source_file = tmp_path / "test_bt.py"
        source_file.write_text(CLEAN_SOURCE)
        issues = audit_file(source_file)
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert len(critical) == 0

    def test_audit_file_str_path(self, tmp_path):
        source_file = tmp_path / "test_bt2.py"
        source_file.write_text(SAME_BAR_SOURCE)
        issues = audit_file(str(source_file))
        critical = [i for i in issues if i.severity == "CRITICAL"]
        assert len(critical) > 0
