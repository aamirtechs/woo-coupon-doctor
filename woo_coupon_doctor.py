"""WooCommerce coupon audit CLI.

Reads a WooCommerce coupons CSV export and audits every coupon for
the mistakes that quietly cost a store money: expired coupons still
published, usage limits already passed, discounts over 100 percent,
duplicate codes that differ only by case, minimum spends above the
maximum spend, and coupons with no expiry, no usage limit, and no
minimum spend at all.

Each problem is a finding with a coupon code, a rule name, a
severity (error or warning), and a message. Errors are the ones
that cost money or break checkout; warnings are hygiene issues
worth fixing. --check exits 1 when any error is found, and --strict
also fails on warnings.

Zero dependencies, Python 3.10 or newer, standard library only.

Usage:
    python3 woo_coupon_doctor.py examples/coupons.csv
    python3 woo_coupon_doctor.py coupons.csv --json --check
"""

import argparse
import csv
import sys
from datetime import date, datetime

__version__ = "1.0.0"

VALID_TYPES = ("percent", "fixed_cart", "fixed_product")
VALID_STATUSES = ("publish", "draft", "pending", "private", "trash")
TRUE_VALUES = ("1", "yes", "true", "y", "on")


class Finding:
    """One audit finding for one coupon."""

    def __init__(self, code, rule, severity, message):
        self.code = code
        self.rule = rule
        self.severity = severity
        self.message = message

    def as_dict(self):
        """Return the finding as a plain dict."""
        return {"code": self.code, "rule": self.rule,
                "severity": self.severity, "message": self.message}

    def __str__(self):
        return "%s [%s] %s: %s" % (self.severity.upper(), self.rule,
                                   self.code, self.message)


def parse_date(value, code, rule):
    """Parse a date string, or return None when blank.

    Accepts ISO dates (2026-11-08) and day-first forms
    (08/11/2026, 08-11-2026). Raises ValueError on anything else.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("coupon %s: %s has an unparseable date: %r"
                     % (code, rule, value))


def parse_number(value, code, field):
    """Parse a number, or return None when blank."""
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError("coupon %s: %s is not a number: %r"
                         % (code, field, value))


def is_true(value):
    """True for the common truthy spellings in a CSV export."""
    return str(value).strip().lower() in TRUE_VALUES


def normalize_code(code):
    """Lowercase and strip a coupon code for duplicate detection."""
    return code.strip().lower()


def audit_row(row, as_of, seen_codes):
    """Audit one CSV row. Returns a list of Finding objects."""
    findings = []
    code = str(row.get("code") or "").strip()
    display = code if code else "(missing code)"

    if not code:
        findings.append(Finding(display, "missing-code", "error",
                                "coupon code is empty"))
        return findings
    if code != code.strip():
        findings.append(Finding(code, "code-whitespace", "warning",
                                "code has leading or trailing spaces"))
    if any(ch.isspace() for ch in code):
        findings.append(Finding(code, "code-spaces", "warning",
                                "code contains spaces, which "
                                "customers mistype at checkout"))

    lowered = normalize_code(code)
    if lowered in seen_codes:
        findings.append(Finding(
            code, "duplicate-code", "error",
            "code duplicates %s (codes are case-insensitive)"
            % seen_codes[lowered]))
    else:
        seen_codes[lowered] = code

    discount_type = str(row.get("discount_type") or "").strip().lower()
    if discount_type and discount_type not in VALID_TYPES:
        findings.append(Finding(
            code, "invalid-discount-type", "error",
            "discount_type %r is not one of %s"
            % (discount_type, ", ".join(VALID_TYPES))))
    free_shipping = is_true(row.get("free_shipping"))

    try:
        amount = parse_number(row.get("amount"), code, "amount")
    except ValueError as exc:
        findings.append(Finding(code, "invalid-amount", "error",
                                str(exc)))
        amount = None
    if amount is not None:
        if discount_type == "percent" and (amount <= 0
                                           or amount > 100):
            findings.append(Finding(
                code, "percent-out-of-range", "error",
                "percent discount %s must be above 0 and at most 100"
                % amount))
        elif discount_type in ("fixed_cart", "fixed_product") \
                and amount <= 0 and not free_shipping:
            findings.append(Finding(
                code, "fixed-amount-zero", "error",
                "fixed discount amount %s must be above 0 "
                "(unless this is a free-shipping-only coupon)"
                % amount))
        elif amount < 0:
            findings.append(Finding(code, "negative-amount", "error",
                                    "discount amount %s is negative"
                                    % amount))

    try:
        usage_count = parse_number(row.get("usage_count"), code,
                                   "usage_count")
    except ValueError as exc:
        findings.append(Finding(code, "invalid-usage-count", "error",
                                str(exc)))
        usage_count = None
    try:
        usage_limit = parse_number(row.get("usage_limit"), code,
                                   "usage_limit")
    except ValueError as exc:
        findings.append(Finding(code, "invalid-usage-limit", "error",
                                str(exc)))
        usage_limit = None
    if usage_count is not None and usage_count < 0:
        findings.append(Finding(code, "negative-usage-count", "error",
                                "usage_count %s is negative"
                                % usage_count))
    if usage_limit is not None and usage_limit <= 0:
        findings.append(Finding(code, "invalid-usage-limit", "error",
                                "usage_limit %s must be above 0"
                                % usage_limit))
    if usage_count is not None and usage_limit is not None \
            and usage_limit > 0:
        if usage_count > usage_limit:
            findings.append(Finding(
                code, "usage-over-limit", "error",
                "used %s times against a limit of %s"
                % (int(usage_count), int(usage_limit))))

    status = str(row.get("status") or "").strip().lower()
    if status and status not in VALID_STATUSES:
        findings.append(Finding(code, "invalid-status", "warning",
                                "status %r is not a known "
                                "WooCommerce status" % status))

    try:
        expiry = parse_date(row.get("expiry_date"), code, "expiry_date")
        expiry_invalid = False
    except ValueError as exc:
        findings.append(Finding(code, "invalid-expiry-date", "error",
                                str(exc)))
        expiry = None
        expiry_invalid = True
    try:
        created = parse_date(row.get("date_created"), code,
                             "date_created")
    except ValueError as exc:
        findings.append(Finding(code, "invalid-created-date", "error",
                                str(exc)))
        created = None
    if expiry is not None and created is not None \
            and expiry < created:
        findings.append(Finding(
            code, "expiry-before-created", "error",
            "expiry %s is before the coupon was created on %s"
            % (expiry, created)))
    if expiry is not None and expiry < as_of:
        if status == "publish":
            findings.append(Finding(
                code, "expired-published", "error",
                "expired on %s but still published, so customers "
                "see a code that can never work" % expiry))
        else:
            findings.append(Finding(
                code, "expired-unused", "warning",
                "expired on %s and never cleaned up" % expiry))
    if expiry is None and discount_type == "percent" \
            and not expiry_invalid:
        findings.append(Finding(
            code, "no-expiry-date", "warning",
            "percent coupon has no expiry date"))

    try:
        minimum = parse_number(row.get("minimum_amount"), code,
                               "minimum_amount")
    except ValueError as exc:
        findings.append(Finding(code, "invalid-minimum-amount",
                                "error", str(exc)))
        minimum = None
    try:
        maximum = parse_number(row.get("maximum_amount"), code,
                               "maximum_amount")
    except ValueError as exc:
        findings.append(Finding(code, "invalid-maximum-amount",
                                "error", str(exc)))
        maximum = None
    if minimum is not None and maximum is not None \
            and minimum > maximum:
        findings.append(Finding(
            code, "minimum-above-maximum", "error",
            "minimum spend %s is above maximum spend %s"
            % (minimum, maximum)))
    if usage_count is not None and usage_limit is not None \
            and usage_count == usage_limit and status == "publish":
        findings.append(Finding(
            code, "limit-reached-published", "error",
            "usage limit of %s reached but the coupon is still "
            "published" % int(usage_limit)))

    unbounded = (expiry is None and not expiry_invalid
                 and usage_limit is None
                 and (minimum is None or minimum == 0))
    if unbounded and discount_type == "percent":
        findings.append(Finding(
            code, "unbounded-coupon", "warning",
            "no expiry date, no usage limit, and no minimum spend: "
            "this coupon can be used forever by anyone"))
    return findings


def audit(rows, as_of, status_filter=None):
    """Audit all CSV rows. Returns (findings, coupons_seen)."""
    findings = []
    seen_codes = {}
    coupons_seen = 0
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status_filter and status != status_filter:
            continue
        coupons_seen += 1
        findings.extend(audit_row(row, as_of, seen_codes))
    return findings, coupons_seen


def summarize(findings, coupons_seen):
    """Count findings by severity."""
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return {"coupons": coupons_seen, "findings": len(findings),
            "errors": errors, "warnings": warnings}


def format_text(findings, summary):
    """Render findings and the summary as text."""
    lines = [str(f) for f in findings]
    lines.append("")
    lines.append("Coupons: %d, findings: %d, errors: %d, warnings: %d"
                 % (summary["coupons"], summary["findings"],
                    summary["errors"], summary["warnings"]))
    if summary["errors"] == 0 and summary["warnings"] == 0:
        lines.append("All coupons clean.")
    return "\n".join(lines) + "\n"


def read_csv(path):
    """Read a coupons CSV export. Returns a list of row dicts."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("%s has no header row" % path)
        return list(reader)


def parse_args(argv):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit a WooCommerce coupons CSV export.")
    parser.add_argument("input", help="coupons CSV export file")
    parser.add_argument("--as-of", default=None,
                        help="reference date YYYY-MM-DD for expiry "
                        "checks (default: today)")
    parser.add_argument("--status", default=None,
                        help="only audit coupons with this status, "
                        "for example publish")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of text")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any error is found")
    parser.add_argument("--strict", action="store_true",
                        help="with --check, also exit 1 on warnings")
    parser.add_argument("--out", default=None,
                        help="write the report to a file")
    return parser.parse_args(argv)


def main(argv=None):
    """Entry point."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.as_of:
        try:
            as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
        except ValueError:
            print("ERROR: --as-of must be YYYY-MM-DD, got %r"
                  % args.as_of, file=sys.stderr)
            return 2
    else:
        as_of = date.today()
    try:
        rows = read_csv(args.input)
    except OSError as exc:
        print("ERROR: cannot read %s: %s" % (args.input, exc),
              file=sys.stderr)
        return 2
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    findings, coupons_seen = audit(
        rows, as_of,
        status_filter=(args.status.strip().lower()
                       if args.status else None))
    summary = summarize(findings, coupons_seen)
    if args.json:
        import json
        text = json.dumps(
            {"summary": summary,
             "findings": [f.as_dict() for f in findings]},
            indent=2)
    else:
        text = format_text(findings, summary)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            print("ERROR: cannot write %s: %s" % (args.out, exc),
                  file=sys.stderr)
            return 2
    else:
        sys.stdout.write(text)
    if args.check and (summary["errors"]
                       or (args.strict and summary["warnings"])):
        return 1
    return 0


def main_entry():
    """Console script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    main_entry()
