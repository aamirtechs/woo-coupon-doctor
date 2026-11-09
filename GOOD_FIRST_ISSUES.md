# Good first issues

Seeded issues for new contributors. File each one on GitHub with the
`good first issue` and `help wanted` labels.

## 1. Add a cleanup list export

Title: Export a CSV of coupons safe to trash

Description: Add a --trash-out flag that writes a CSV of the codes
flagged expired-published or expired-unused, with their rule and
expiry date, so a store owner can review the list and delete exactly
those coupons in WooCommerce. The tool itself must never delete
anything.

Difficulty: Easy

Acceptance criteria: the export lists only the expired coupons from
the sample file; a test round-trips the export; README documents the
flag.

## 2. Add a per-coupon usage report

Title: Show the most-used coupons in the summary

Description: After the findings, print a short table of the five
most-used coupons (code, usage count, usage limit, percent of limit
used), so a store owner can see which promotions actually drove
orders.

Difficulty: Easy

Acceptance criteria: the table appears in text output with the
correct top five; JSON output is unchanged; a test checks the table
rows.

## 3. Support HPOS order totals for minimum spend sanity

Title: Flag minimum spends above the store's average order value

Description: Add an optional --average-order-value flag. When
given, flag any coupon whose minimum_amount is above twice the
average order value as a warning (rule name
minimum-above-typical-order), since almost no order will ever
qualify for it.

Difficulty: Medium

Acceptance criteria: a coupon with a minimum of 500 and an average
order value of 100 is flagged; a minimum of 150 is not; a test
covers both cases; README documents the flag.

## 4. Add a duplicate-code merge suggestion

Title: Suggest which duplicate code to keep

Description: When duplicate codes are found, add a suggestion to
the finding message naming the code with the higher usage count as
the one to keep, so the owner knows which copy holds the real usage
history.

Difficulty: Easy

Acceptance criteria: the duplicate finding for the sample file
names WELCOME10 as the keeper over welcome10; a test covers the
suggestion; README documents the rule.
