# Changelog

## 1.0.0 - 2026-11-08

Initial release.

* Coupon audit over a WooCommerce coupons CSV export: expired
  coupons still published, usage counts over the usage limit,
  limits reached but still published, percent discounts over 100,
  fixed discounts of zero, duplicate codes (case-insensitive),
  invalid discount types, minimum spend above maximum spend,
  expiry before the creation date, and missing codes.
* Hygiene warnings: expired drafts never cleaned up, percent
  coupons with no expiry date, unbounded coupons with no expiry, no
  usage limit, and no minimum spend, codes containing spaces, and
  unknown statuses.
* Findings carry a coupon code, rule name, severity (error or
  warning), and message; errors and warnings are counted in the
  summary.
* Text and --json output, --out file output, --as-of reference date
  for expiry checks, --status filter, and a --check CI gate that
  exits 1 on errors (and on warnings with --strict).
* Zero dependencies, Python 3.10 or newer.
