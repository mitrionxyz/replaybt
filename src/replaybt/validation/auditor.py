"""Static bias detection for backtest source code.

Port of audit_backtest.py into the replaybt package.
Detects 11 types of look-ahead bias and execution issues
using regex-based pattern matching (no AST dependency).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union


@dataclass(frozen=True)
class Issue:
    """A single audit finding."""
    severity: str  # "CRITICAL", "WARNING", "INFO"
    line: int
    code: str
    message: str
    fix: str


class BacktestAuditor:
    """Static bias checker for backtest source code.

    Detects 11 types of look-ahead bias and execution issues:
    1. Same-bar execution (signal + entry on same bar)
    2. Indicator lookahead (using incomplete bar)
    3. Exit price assumptions (no gap protection)
    4. Missing pending_order system
    5. Resampled time alignment (incomplete bar lookup)
    6. Missing slippage/fees
    7. Future data access (iloc[i+1])
    8. Signal/exit same iteration
    9. Missing 1-minute data
    10. Wrapper script delegation
    11. Scale-in bias

    Args:
        source: Python source code text to audit.
        filename: Optional filename for report headers.
    """

    def __init__(self, source: str, filename: str = "<unknown>"):
        self.source = source
        self.filename = filename
        self.lines = source.split("\n")
        self.issues: List[Issue] = []

    def audit(self) -> List[Issue]:
        """Run all checks. Returns list of Issues."""
        self.issues = []

        # First check if this is a wrapper script
        if self._is_wrapper_script():
            return self.issues

        self._check_same_bar_execution()
        self._check_indicator_lookahead()
        self._check_exit_price_assumptions()
        self._check_pending_order_system()
        self._check_resampled_time_alignment()
        self._check_slippage_and_fees()
        self._check_iloc_patterns()
        self._check_signal_exit_same_iteration()
        self._check_1m_data_usage()
        self._check_scale_in_bias()
        return self.issues

    def report(self) -> str:
        """Return formatted audit report string."""
        parts = []
        parts.append("=" * 70)
        parts.append(f"BACKTEST AUDIT: {self.filename}")
        parts.append("=" * 70)

        if not self.issues:
            parts.append("")
            parts.append("NO ISSUES FOUND - Backtest appears clean")
            parts.append("")
            return "\n".join(parts)

        critical = [i for i in self.issues if i.severity == "CRITICAL"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]
        info = [i for i in self.issues if i.severity == "INFO"]

        if critical:
            parts.append("")
            parts.append(
                f"CRITICAL ({len(critical)} issues)"
                " - Must fix before trusting results:"
            )
            parts.append("-" * 70)
            for issue in critical:
                parts.append(f"  Line {issue.line}: {issue.message}")
                if issue.code:
                    parts.append(f"    Code: {issue.code[:70]}")
                parts.append(f"    Fix:  {issue.fix}")
                parts.append("")

        if warnings:
            parts.append("")
            parts.append(
                f"WARNINGS ({len(warnings)} issues) - Should investigate:"
            )
            parts.append("-" * 70)
            for issue in warnings:
                parts.append(f"  Line {issue.line}: {issue.message}")
                if issue.code:
                    parts.append(f"    Code: {issue.code[:70]}")
                parts.append(f"    Fix:  {issue.fix}")
                parts.append("")

        if info:
            parts.append("")
            parts.append(
                f"INFO ({len(info)} issues) - Best practice suggestions:"
            )
            parts.append("-" * 70)
            for issue in info:
                parts.append(f"  {issue.message}")
                if issue.code:
                    parts.append(f"    Code: {issue.code[:70]}")
                parts.append(f"    Fix:  {issue.fix}")
                parts.append("")

        parts.append("-" * 70)
        if critical:
            verdict = "UNRELIABLE"
        elif warnings:
            verdict = "NEEDS REVIEW"
        else:
            verdict = "CLEAN"
        parts.append(f"VERDICT: {verdict}")
        parts.append(
            f"  Critical: {len(critical)}"
            f" | Warnings: {len(warnings)}"
            f" | Info: {len(info)}"
        )
        parts.append("")
        return "\n".join(parts)

    @property
    def is_clean(self) -> bool:
        """True if no CRITICAL issues."""
        return not any(i.severity == "CRITICAL" for i in self.issues)

    # ------------------------------------------------------------------
    # Internal checks (ported from audit_backtest.py)
    # ------------------------------------------------------------------

    def _is_wrapper_script(self) -> bool:
        """Detect if this script delegates backtest logic to an imported class."""
        imports_backtest = bool(re.search(
            r"from\s+(?:backtest_\w+|backtest_combined_clean)\s+import",
            self.source,
        ))
        subclasses_backtest = bool(re.search(
            r"class\s+\w+\(.*(?:Backtest|ScalperBacktest|TrendMaster)\w*\)",
            self.source,
        ))
        code_lines = "\n".join(
            line for line in self.lines if not line.strip().startswith("#")
        )
        has_own_loop = bool(re.search(
            r"for\s+\w+.*(?:iterrows|range|enumerate)\s*\(",
            code_lines,
        ))
        if (imports_backtest or subclasses_backtest) and not has_own_loop:
            self.issues.append(Issue(
                severity="INFO",
                line=0,
                code="",
                message=(
                    "Wrapper script — backtest logic delegated to imported module"
                ),
                fix="Audit the imported backtest module instead",
            ))
            return True
        return False

    def _check_same_bar_execution(self) -> None:
        """CRITICAL: Signal and execution should not happen on same bar."""
        patterns = [
            (
                r"entry_price\s*=\s*(?:row|df\.iloc\[i\]|candle)\[.close.\]",
                "Entry at close price (should be next bar's open)",
            ),
            (
                r"entry_price\s*=\s*close",
                "Entry at close price (should be next bar's open)",
            ),
        ]
        for pattern, msg in patterns:
            for match in re.finditer(
                pattern, self.source, re.IGNORECASE | re.MULTILINE
            ):
                line_num = self.source[:match.start()].count("\n") + 1
                self.issues.append(Issue(
                    severity="CRITICAL",
                    line=line_num,
                    code=self.lines[line_num - 1].strip(),
                    message=msg,
                    fix=(
                        "Use pending_order system: signal sets pending,"
                        " next bar executes at open"
                    ),
                ))

    def _check_indicator_lookahead(self) -> None:
        """WARNING: Indicators pre-calculated without safeguards."""
        indicator_calcs = re.findall(
            r"df\w*\[.[a-z_]+.\]\s*=\s*.*\.(rolling|ewm|diff|shift)\(",
            self.source, re.IGNORECASE,
        )
        if indicator_calcs:
            has_pending = bool(re.search(
                r"pending_order|pending_signal", self.source,
            ))
            has_completed_bar = bool(re.search(
                r"completed_.*time|bar_.*-.*timedelta|floor.*-", self.source,
            ))
            if not has_pending and not has_completed_bar:
                self.issues.append(Issue(
                    severity="WARNING",
                    line=0,
                    code="",
                    message=(
                        "Pre-calculated indicators without pending_order"
                        " or completed-bar lookup"
                    ),
                    fix=(
                        "Use pending_order system OR look up completed bars"
                        " (T-1) for signals"
                    ),
                ))

    def _check_exit_price_assumptions(self) -> None:
        """WARNING: Exits should account for gaps via Open price check."""
        exit_patterns = re.finditer(
            r"return\s+(?:pos\.)?(?:stop_loss|take_profit|sl|tp)\s*,",
            self.source, re.IGNORECASE,
        )
        for match in exit_patterns:
            context_start = max(0, match.start() - 500)
            context = self.source[context_start:match.start()]
            has_gap_check = bool(re.search(
                r"(?:open|(?:^|\s)o\s*(?:<=|>=|<|>)).*(?:stop|sl|tp|take_profit)",
                context, re.IGNORECASE | re.MULTILINE,
            ))
            if not has_gap_check:
                line_num = self.source[:match.start()].count("\n") + 1
                self.issues.append(Issue(
                    severity="WARNING",
                    line=line_num,
                    code=self.lines[line_num - 1].strip(),
                    message=(
                        "Exit at stop level without preceding"
                        " gap protection check"
                    ),
                    fix="Check if Open gapped past stop before checking High/Low",
                ))

    def _check_pending_order_system(self) -> None:
        """CRITICAL: Must have pending_order system or equivalent."""
        has_pending = bool(re.search(
            r"pending_order|pending_signal", self.source,
        ))
        has_entry_at_open = bool(re.search(
            r"entry.*=.*(?:row|bar|candle).*\[.open.\]",
            self.source, re.IGNORECASE,
        ))
        if not has_pending:
            if has_entry_at_open:
                self.issues.append(Issue(
                    severity="INFO",
                    line=0,
                    code="",
                    message=(
                        "No pending_order system found,"
                        " but entries use open price"
                    ),
                    fix="Consider using explicit pending_order for clarity",
                ))
            else:
                self.issues.append(Issue(
                    severity="CRITICAL",
                    line=0,
                    code="",
                    message=(
                        "No pending_order system and"
                        " no clear next-bar execution"
                    ),
                    fix=(
                        "Implement pending_order: signal sets pending,"
                        " next iteration executes at open"
                    ),
                ))

    def _check_resampled_time_alignment(self) -> None:
        """INFO: Resampled data lookups may use incomplete bars."""
        has_resample = bool(re.search(r"\.resample\(", self.source))
        if not has_resample:
            return
        loc_lookups = re.finditer(r"(df_\w+)\.loc\[(\w+)\]", self.source)
        for match in loc_lookups:
            var_name = match.group(2)
            var_definition = re.search(
                rf"{var_name}\s*=.*(?:floor|timedelta|-\s*\w*td)",
                self.source, re.IGNORECASE,
            )
            if not var_definition:
                if (
                    "completed" not in var_name.lower()
                    and "prev" not in var_name.lower()
                ):
                    line_num = self.source[:match.start()].count("\n") + 1
                    line_content = self.lines[line_num - 1].strip()
                    if (
                        "load" not in line_content.lower()
                        and "read" not in line_content.lower()
                    ):
                        self.issues.append(Issue(
                            severity="INFO",
                            line=line_num,
                            code=line_content,
                            message=(
                                f"Resampled data lookup with '{var_name}'"
                                " — verify this is a completed bar"
                            ),
                            fix=(
                                "Use: df.loc[time - timedelta]"
                                " to access last completed bar"
                            ),
                        ))

    def _check_slippage_and_fees(self) -> None:
        """WARNING: All backtests should include slippage and fees."""
        has_slippage = bool(re.search(
            r"slippage|SLIPPAGE|slip", self.source, re.IGNORECASE,
        ))
        has_fees = bool(re.search(
            r"\bfee\b|\bFEE\b|commission", self.source, re.IGNORECASE,
        ))
        if not has_slippage:
            self.issues.append(Issue(
                severity="WARNING",
                line=0,
                code="",
                message="No slippage found in backtest",
                fix=(
                    "Add SLIPPAGE = 0.0002 (0.02%)"
                    " applied adversely on entry/exit"
                ),
            ))
        if not has_fees:
            self.issues.append(Issue(
                severity="WARNING",
                line=0,
                code="",
                message="No fees found in backtest",
                fix="Add FEE = 0.00015 (0.015%) per side for Hyperliquid",
            ))

    def _check_iloc_patterns(self) -> None:
        """CRITICAL: Check for future data access via iloc[i+N]."""
        future_access = re.finditer(
            r"\.iloc\[i\s*\+\s*(\d+)\]", self.source,
        )
        for match in future_access:
            # Check if this is a slice (e.g. .iloc[start:i+1]) by looking
            # for a colon inside the brackets only
            bracket_start = self.source.rfind("[", 0, match.start() + 1)
            bracket_content = self.source[bracket_start:match.end()]
            if ":" not in bracket_content:  # Not a slice
                line_num = self.source[:match.start()].count("\n") + 1
                self.issues.append(Issue(
                    severity="CRITICAL",
                    line=line_num,
                    code=self.lines[line_num - 1].strip(),
                    message=f"Accessing future bar data (i+{match.group(1)})",
                    fix="Only access current (i) or past (i-1, i-2) bars",
                ))

    def _check_signal_exit_same_iteration(self) -> None:
        """WARNING: Signal and exit in same loop without pending."""
        for_blocks = re.finditer(
            r"for\s+\w+.*(?:range|iterrows|enumerate)\s*\(.*:\s*\n"
            r"((?:.*\n)*?)(?=\nfor\s|\ndef\s|\nclass\s|\Z)",
            self.source,
        )
        for block in for_blocks:
            block_content = block.group(1)
            has_entry = bool(re.search(
                r"entry_price\s*=|Position\(|LivePosition\(",
                block_content,
            ))
            has_exit = bool(re.search(
                r"_close_position|_check_exit|exit_price\s*=",
                block_content,
            ))
            has_pending = bool(re.search(
                r"pending", block_content, re.IGNORECASE,
            ))
            if has_entry and has_exit and not has_pending:
                line_num = self.source[:block.start()].count("\n") + 1
                self.issues.append(Issue(
                    severity="WARNING",
                    line=line_num,
                    code="for loop block",
                    message=(
                        "Entry and exit in same iteration"
                        " without pending_order system"
                    ),
                    fix=(
                        "Order should be: 1) Execute pending,"
                        " 2) Check exits, 3) Check new signals"
                    ),
                ))

    def _check_1m_data_usage(self) -> None:
        """WARNING: All backtests should use 1m data for intra-bar exits."""
        has_1m = bool(re.search(r"1m|_1m|1min", self.source, re.IGNORECASE))
        has_resample = bool(re.search(r"\.resample\(", self.source))
        has_iterrows = bool(re.search(r"iterrows|for.*range", self.source))
        if has_iterrows and has_resample and not has_1m:
            self.issues.append(Issue(
                severity="WARNING",
                line=0,
                code="",
                message=(
                    "Resampled data used but no 1-minute data"
                    " detected for intra-bar exits"
                ),
                fix=(
                    "Load 1m data and check SL/TP on each 1m bar"
                    " within higher timeframe bars"
                ),
            ))

    def _check_scale_in_bias(self) -> None:
        """INFO: Scale-in should not fill on same bar as entry."""
        has_scale_in = bool(re.search(
            r"scale_in|pending_scale", self.source, re.IGNORECASE,
        ))
        if not has_scale_in:
            return
        setup_before_check = bool(re.search(
            r"pending_scale_in\s*=\s*\{.*\}.*\n.*\n.*PHASE\s*1\.5|"
            r"pending_order\s*=\s*None\s*\n\s*\n.*scale_in",
            self.source, re.IGNORECASE | re.DOTALL,
        ))
        if not setup_before_check:
            self.issues.append(Issue(
                severity="INFO",
                line=0,
                code="",
                message=(
                    "Scale-in detected — verify it cannot fill"
                    " on the same bar as entry"
                ),
                fix=(
                    "Scale-in limit check should happen AFTER"
                    " entry execution in the loop"
                ),
            ))


def audit_file(path: Union[str, Path]) -> List[Issue]:
    """Convenience: audit a file by path."""
    p = Path(path)
    source = p.read_text()
    auditor = BacktestAuditor(source, filename=p.name)
    return auditor.audit()
