# woo-coupon-doctor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/woo-coupon-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/woo-coupon-doctor/issues)

A zero-dependency Python CLI that audits a WooCommerce coupons CSV
export for the mistakes that quietly cost a store money: expired
coupons still published, usage limits already passed, discounts
over 100 percent, and duplicate codes that differ only by case.

The cleanup plugins that already exist (WooCommerce Data Cleaner,
Bulk Cleanup, and the $29 Auto-Coupon Expiry Cleanup extension) all
run inside WordPress and delete expired coupons. This tool is the
offline audit before any deletion: it reads the exported CSV, flags
every problem with a rule name and a severity, and never touches
your store.

## Install

Requires Python 3.10 or newer. No dependencies beyond the standard
library.

```bash
pip install woo-coupon-doctor
```

Or run it straight from the source checkout:

```bash
python3 woo_coupon_doctor.py examples/coupons.csv --as-of 2026-11-08
```

## Input format

A CSV export with a header row. Columns used: `code`,
`discount_type` (percent, fixed_cart, fixed_product), `amount`,
`usage_count`, `usage_limit`, `expiry_date`, `date_created`,
`minimum_amount`, `maximum_amount`, `free_shipping`, `status`,
`individual_use`. Extra columns are ignored, so a full WooCommerce
export works as-is. Dates accept ISO form (2026-11-08) and day-first
form (08/11/2026). A UTF-8 BOM header is handled.

```csv
code,discount_type,amount,usage_count,usage_limit,expiry_date,date_created,minimum_amount,maximum_amount,free_shipping,status,individual_use
WELCOME10,percent,10,45,100,2027-01-31,2026-01-05,0,,no,publish,no
FREESHIP,fixed_cart,0,12,,2027-06-30,2026-02-01,0,,yes,publish,no
CLEAN5,fixed_cart,5,3,20,2027-03-01,2026-01-10,25,,no,publish,no
```

## What it checks

Errors, the ones that cost money or break checkout:

* `expired-published`: expired but still published, so customers
  see a code that can never work.
* `usage-over-limit`: used more times than the usage limit allows.
* `limit-reached-published`: usage limit reached but the coupon is
  still published.
* `percent-out-of-range`: percent discount at or below 0, or above
  100.
* `fixed-amount-zero`: fixed discount of zero, unless it is a
  free-shipping-only coupon.
* `duplicate-code`: the same code twice, ignoring case. WooCommerce
  codes are case-insensitive, so WELCOME10 and welcome10 are the
  same coupon.
* `invalid-discount-type`: not percent, fixed_cart, or
  fixed_product.
* `minimum-above-maximum`: minimum spend above maximum spend.
* `expiry-before-created`: expiry date before the creation date.
* `missing-code`: an empty code.
* `invalid-amount`, `invalid-expiry-date`, `invalid-usage-count`,
  `invalid-usage-limit`, `negative-usage-count`: unparseable or
  impossible values.

Warnings, hygiene issues worth fixing:

* `expired-unused`: expired and never cleaned up (draft or other
  non-published status).
* `no-expiry-date`: percent coupon with no expiry date.
* `unbounded-coupon`: no expiry date, no usage limit, and no
  minimum spend, so the coupon can be used forever by anyone.
* `code-spaces`: code contains spaces, which customers mistype at
  checkout.
* `invalid-status`: status is not a known WooCommerce status.

## Usage

```bash
python3 woo_coupon_doctor.py examples/coupons.csv --as-of 2026-11-08
```

Captured output:

```
ERROR [expired-published] SAVE20: expired on 2026-10-01 but still published, so customers see a code that can never work
ERROR [usage-over-limit] BIG50: used 120 times against a limit of 100
ERROR [percent-out-of-range] MEGA150: percent discount 150.0 must be above 0 and at most 100
ERROR [duplicate-code] welcome10: code duplicates WELCOME10 (codes are case-insensitive)
WARNING [expired-unused] OLDDEAL: expired on 2025-01-01 and never cleaned up
WARNING [no-expiry-date] NODEAL: percent coupon has no expiry date
WARNING [unbounded-coupon] NODEAL: no expiry date, no usage limit, and no minimum spend: this coupon can be used forever by anyone
ERROR [invalid-discount-type] BADTYPE: discount_type 'bogus' is not one of percent, fixed_cart, fixed_product
ERROR [minimum-above-maximum] MINMAX: minimum spend 200.0 is above maximum spend 100.0
ERROR [expiry-before-created] BACKWARD: expiry 2026-10-01 is before the coupon was created on 2026-11-01
ERROR [expired-published] BACKWARD: expired on 2026-10-01 but still published, so customers see a code that can never work
WARNING [code-spaces] SPACED CODE: code contains spaces, which customers mistype at checkout
ERROR [missing-code] (missing code): coupon code is empty

Coupons: 14, findings: 13, errors: 9, warnings: 4
```

The sample has 14 coupons and 13 findings. Two coupons are clean
(WELCOME10 and FREESHIP, a free-shipping-only coupon with a zero
fixed amount), plus CLEAN5. BACKWARD carries two errors at once: its
expiry is before its creation date, and it is expired while still
published.

Use it as a CI gate: `--check` exits 1 when any error is found,
and 0 otherwise. On the sample above it exits 1:

```bash
python3 woo_coupon_doctor.py examples/coupons.csv --as-of 2026-11-08 --check
```

On `examples/clean.csv`, three clean coupons, it exits 0:

```
Coupons: 3, findings: 0, errors: 0, warnings: 0
All coupons clean.
```

With `--strict`, `--check` also fails on warnings. `--status
publish` audits only published coupons (13 of the 14 in the
sample, 12 findings). `--json` emits the summary and findings as
JSON, and `--out` writes the report to a file. `--as-of` sets the
reference date for expiry checks; without it, today is used.

## Options

| Flag | Meaning |
| --- | --- |
| `--as-of` | Reference date YYYY-MM-DD for expiry checks (default: today) |
| `--status` | Only audit coupons with this status, for example publish |
| `--json` | Emit JSON instead of text |
| `--check` | Exit 1 if any error is found |
| `--strict` | With --check, also exit 1 on warnings |
| `--out` | Write the report to a file |

## Edge cases

* A fixed-cart coupon with amount 0 and free shipping set to yes
  is a free-shipping-only coupon, not an error.
* An unparseable expiry date is one error, not an error plus a
  no-expiry warning.
* A usage limit of 0 is invalid, and does not also trigger a
  usage-over-limit finding.
* Duplicate detection is case-insensitive and ignores surrounding
  spaces.
* A coupon expired exactly on the reference date is not expired;
  expiry is checked as strictly before the reference date.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

40 tests, all passing: every rule, error and warning severities,
duplicate detection, date parsing, status filtering, summary
counts, JSON output shape, and `--check` and `--strict` exit codes.

## License

MIT. See [LICENSE](LICENSE).
