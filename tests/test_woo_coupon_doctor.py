"""Tests for woo_coupon_doctor."""

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import woo_coupon_doctor as wcd

AS_OF = date(2026, 11, 8)


def row(**overrides):
    """A clean coupon row, with optional field overrides."""
    base = {"code": "WELCOME10", "discount_type": "percent",
            "amount": "10", "usage_count": "5", "usage_limit": "100",
            "expiry_date": "2027-01-31",
            "date_created": "2026-01-05", "minimum_amount": "0",
            "maximum_amount": "", "free_shipping": "no",
            "status": "publish", "individual_use": "no"}
    base.update(overrides)
    return base


def rules(findings):
    """Return the sorted rule names of a findings list."""
    return sorted(f.rule for f in findings)


class TestAuditRow(unittest.TestCase):
    def test_clean_coupon(self):
        self.assertEqual(wcd.audit_row(row(), AS_OF, {}), [])

    def test_free_shipping_zero_amount_is_clean(self):
        findings = wcd.audit_row(
            row(discount_type="fixed_cart", amount="0",
                free_shipping="yes"), AS_OF, {})
        self.assertEqual(findings, [])

    def test_expired_published_is_error(self):
        findings = wcd.audit_row(row(expiry_date="2026-10-01"),
                                 AS_OF, {})
        self.assertEqual(rules(findings), ["expired-published"])
        self.assertEqual(findings[0].severity, "error")

    def test_expired_draft_is_warning(self):
        findings = wcd.audit_row(
            row(expiry_date="2026-10-01", status="draft"), AS_OF, {})
        self.assertEqual(rules(findings), ["expired-unused"])
        self.assertEqual(findings[0].severity, "warning")

    def test_not_yet_expired_is_clean(self):
        findings = wcd.audit_row(row(expiry_date="2026-11-08"),
                                 AS_OF, {})
        self.assertEqual(findings, [])

    def test_percent_over_100(self):
        findings = wcd.audit_row(row(amount="150"), AS_OF, {})
        self.assertEqual(rules(findings), ["percent-out-of-range"])

    def test_percent_zero(self):
        findings = wcd.audit_row(row(amount="0"), AS_OF, {})
        self.assertEqual(rules(findings), ["percent-out-of-range"])

    def test_fixed_zero_without_shipping(self):
        findings = wcd.audit_row(
            row(discount_type="fixed_cart", amount="0"), AS_OF, {})
        self.assertEqual(rules(findings), ["fixed-amount-zero"])

    def test_negative_amount(self):
        findings = wcd.audit_row(row(amount="-5"), AS_OF, {})
        self.assertIn("percent-out-of-range", rules(findings))

    def test_duplicate_code_case_insensitive(self):
        seen = {"welcome10": "WELCOME10"}
        findings = wcd.audit_row(row(code="welcome10"), AS_OF, seen)
        self.assertEqual(rules(findings), ["duplicate-code"])
        self.assertIn("WELCOME10", findings[0].message)

    def test_first_code_is_recorded(self):
        seen = {}
        wcd.audit_row(row(), AS_OF, seen)
        self.assertEqual(seen, {"welcome10": "WELCOME10"})

    def test_usage_over_limit(self):
        findings = wcd.audit_row(
            row(usage_count="120", usage_limit="100"), AS_OF, {})
        self.assertEqual(rules(findings), ["usage-over-limit"])

    def test_limit_reached_still_published(self):
        findings = wcd.audit_row(
            row(usage_count="100", usage_limit="100"), AS_OF, {})
        self.assertEqual(rules(findings),
                         ["limit-reached-published"])

    def test_limit_reached_draft_is_clean(self):
        findings = wcd.audit_row(
            row(usage_count="100", usage_limit="100", status="draft"),
            AS_OF, {})
        self.assertEqual(findings, [])

    def test_minimum_above_maximum(self):
        findings = wcd.audit_row(
            row(minimum_amount="200", maximum_amount="100"), AS_OF, {})
        self.assertEqual(rules(findings), ["minimum-above-maximum"])

    def test_expiry_before_created(self):
        findings = wcd.audit_row(
            row(expiry_date="2026-10-01",
                date_created="2026-11-01"), AS_OF, {})
        self.assertIn("expiry-before-created", rules(findings))
        self.assertIn("expired-published", rules(findings))

    def test_invalid_discount_type(self):
        findings = wcd.audit_row(row(discount_type="bogus"), AS_OF, {})
        self.assertEqual(rules(findings), ["invalid-discount-type"])

    def test_missing_code(self):
        findings = wcd.audit_row(row(code=""), AS_OF, {})
        self.assertEqual(rules(findings), ["missing-code"])

    def test_code_with_spaces(self):
        findings = wcd.audit_row(row(code="SPACED CODE"), AS_OF, {})
        self.assertEqual(rules(findings), ["code-spaces"])

    def test_unbounded_percent_coupon(self):
        findings = wcd.audit_row(
            row(expiry_date="", usage_limit="", minimum_amount="0"),
            AS_OF, {})
        self.assertEqual(rules(findings),
                         ["no-expiry-date", "unbounded-coupon"])

    def test_no_expiry_but_usage_limit_is_not_unbounded(self):
        findings = wcd.audit_row(row(expiry_date=""), AS_OF, {})
        self.assertEqual(rules(findings), ["no-expiry-date"])

    def test_fixed_coupon_without_expiry_is_clean(self):
        findings = wcd.audit_row(
            row(discount_type="fixed_cart", expiry_date=""), AS_OF, {})
        self.assertEqual(findings, [])

    def test_invalid_expiry_date(self):
        findings = wcd.audit_row(row(expiry_date="not-a-date"),
                                 AS_OF, {})
        self.assertEqual(rules(findings), ["invalid-expiry-date"])

    def test_invalid_amount(self):
        findings = wcd.audit_row(row(amount="ten"), AS_OF, {})
        self.assertEqual(rules(findings), ["invalid-amount"])

    def test_invalid_status_is_warning(self):
        findings = wcd.audit_row(row(status="weird"), AS_OF, {})
        self.assertEqual(rules(findings), ["invalid-status"])
        self.assertEqual(findings[0].severity, "warning")

    def test_day_first_date_parses(self):
        findings = wcd.audit_row(row(expiry_date="31/01/2027"),
                                 AS_OF, {})
        self.assertEqual(findings, [])

    def test_negative_usage_count(self):
        findings = wcd.audit_row(row(usage_count="-1"), AS_OF, {})
        self.assertEqual(rules(findings), ["negative-usage-count"])

    def test_zero_usage_limit(self):
        findings = wcd.audit_row(row(usage_limit="0"), AS_OF, {})
        self.assertEqual(rules(findings), ["invalid-usage-limit"])


class TestAudit(unittest.TestCase):
    def test_summary_counts(self):
        findings, seen = wcd.audit(
            [row(), row(code="BAD", amount="150")], AS_OF)
        summary = wcd.summarize(findings, seen)
        self.assertEqual(summary["coupons"], 2)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["warnings"], 0)

    def test_status_filter(self):
        findings, seen = wcd.audit(
            [row(), row(code="DRAFT1", status="draft",
                        expiry_date="2025-01-01")],
            AS_OF, status_filter="publish")
        self.assertEqual(seen, 1)
        self.assertEqual(findings, [])

    def test_text_output(self):
        findings, seen = wcd.audit([row(code="BAD", amount="150")],
                                   AS_OF)
        text = wcd.format_text(findings, wcd.summarize(findings, seen))
        self.assertIn("percent-out-of-range", text)
        self.assertIn("errors: 1", text)

    def test_clean_text_output(self):
        text = wcd.format_text([], wcd.summarize([], 3))
        self.assertIn("All coupons clean.", text)


class TestCli(unittest.TestCase):
    def run_cli(self, args, content):
        """Run main() against a temp CSV file, capturing stdout."""
        with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                        delete=False) as handle:
            handle.write(content)
            path = handle.name
        try:
            saved = sys.stdout
            sys.stdout = io.StringIO()
            try:
                code = wcd.main([path] + args)
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = saved
            return code, output
        finally:
            os.unlink(path)

    HEADER = ("code,discount_type,amount,usage_count,usage_limit,"
              "expiry_date,date_created,minimum_amount,"
              "maximum_amount,free_shipping,status,individual_use\n")
    CLEAN_CSV = HEADER + ("WELCOME10,percent,10,5,100,2027-01-31,"
                          "2026-01-05,0,,no,publish,no\n")
    BAD_CSV = HEADER + ("SAVE20,percent,20,0,50,2026-10-01,2026-08-15,"
                        "0,,no,publish,no\n")

    def test_cli_clean_exit_zero(self):
        code, output = self.run_cli(["--as-of", "2026-11-08"],
                                    self.CLEAN_CSV)
        self.assertEqual(code, 0)
        self.assertIn("All coupons clean.", output)

    def test_cli_check_fails_on_error(self):
        code, output = self.run_cli(
            ["--as-of", "2026-11-08", "--check"], self.BAD_CSV)
        self.assertEqual(code, 1)
        self.assertIn("expired-published", output)

    def test_cli_check_passes_without_flag_on_warnings(self):
        code, output = self.run_cli(
            ["--as-of", "2026-11-08", "--check"],
            self.HEADER + ("OLD,percent,15,0,,2025-01-01,2024-12-01,"
                           "0,,no,draft,no\n"))
        self.assertEqual(code, 0)

    def test_cli_strict_fails_on_warning(self):
        code, output = self.run_cli(
            ["--as-of", "2026-11-08", "--check", "--strict"],
            self.HEADER + ("OLD,percent,15,0,,2025-01-01,2024-12-01,"
                           "0,,no,draft,no\n"))
        self.assertEqual(code, 1)

    def test_cli_json_flag(self):
        code, output = self.run_cli(
            ["--as-of", "2026-11-08", "--json"], self.BAD_CSV)
        self.assertEqual(code, 0)
        parsed = json.loads(output)
        self.assertEqual(parsed["summary"]["errors"], 1)
        self.assertEqual(parsed["findings"][0]["rule"],
                         "expired-published")

    def test_cli_missing_file(self):
        code = wcd.main(["/nonexistent/coupons.csv"])
        self.assertEqual(code, 2)

    def test_cli_bad_as_of(self):
        code, output = self.run_cli(["--as-of", "yesterday"],
                                    self.CLEAN_CSV)
        self.assertEqual(code, 2)

    def test_cli_bom_header(self):
        code, output = self.run_cli(["--as-of", "2026-11-08"],
                                    "\ufeff" + self.CLEAN_CSV)
        self.assertEqual(code, 0)
        self.assertIn("All coupons clean.", output)


if __name__ == "__main__":
    unittest.main()
