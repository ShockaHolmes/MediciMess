# Instructor Fraud Guide (Phase 4)

## Instructor-Only Notice

INSTRUCTOR ONLY - DO NOT DISTRIBUTE TO STUDENTS

This guide contains expected findings and answer-key values for the hidden embezzlement investigation lab.

## Fraud Scenario Summary

Students are investigating a hidden embezzlement trail embedded in normal Medici Bank operating activity.

The scheme is designed to look like routine branch expenses rather than obvious ledger-breaking fraud. The suspicious behavior is concentrated in Florence expense flows and appears as repeated payments to vendors that can pass casual review unless analyzed with forensic methods.

## Expected Core Findings

1. Fictitious supplier candidate:
Mercato Maintenance Works

2. Expected suspicious date range:
1390-06-17 to 1440-10-14

3. Expected estimated total fraud amount:
2,022,455.41

4. Expected suspicious transaction count under the notebook estimator:
242

## How the Expected Findings Were Derived

The answer-key values are derived from the student notebook workflow and assumptions:

1. Filter to Florence branch expenses using transaction type and expense-account logic.
2. Group by vendor and compute spend share.
3. Apply Benford-style first-digit deviation scoring by vendor.
4. Apply vendor concentration scoring by account and vendor share thresholds.
5. Build a composite risk score from:
- Vendor expense share rank (50%)
- Benford MAD rank (30%)
- Concentration-flag count rank (20%)
6. Select top ranked supplier as suspicious candidate.
7. Estimate suspicious amount with a 5% baseline cap per month-account bucket:
- expected_max = 5% * monthly account total
- estimated_excess = max(0, vendor_amount - expected_max)
8. Use months with positive estimated_excess to derive suspicious transaction window and date range.

## Detection Methods to Expect in Strong Student Submissions

1. Transaction profiling:
- branch and type counts
- Florence-focused subset

2. Vendor spend concentration:
- vendor share of expense categories
- high-share outliers

3. Benford diagnostics:
- first-significant-digit distribution
- deviation metrics such as MAD and/or chi-squared

4. Duplicate review:
- exact and near-duplicate checks by date, amount, description, and account pair

5. Round-number clustering review:
- large rounded-value frequency versus baseline behavior

## Interpretation Guidance for Instructors

1. Accept defensible alternate supplier candidates if the student provides quantitative justification.
2. Reward transparent assumptions and reproducible logic over exact numerical matching.
3. Evaluate whether students discuss false positives and model risk, especially for Benford and concentration checks.
4. Minor numerical variance is acceptable if the methodology is consistent and clearly documented.

## Discussion Questions

1. Why can vendor concentration flags reveal fraud that basic balancing checks do not?
2. What kinds of legitimate business behavior can create false positives in Benford analysis?
3. How would findings change if the baseline share threshold were 10% instead of 5%?
4. What additional fields or controls would improve confidence in the fraud estimate?
5. How should investigators prioritize between statistical anomalies and operational context?

## Suggested Grading Rubric (100 points)

1. Data loading and preparation (10)
- Correct parsing of dates and amounts
- Clean handling of missing values

2. Transaction exploration (10)
- Correct branch/type profiling and summary counts

3. Florence expense scope definition (15)
- Reasonable, explicit filtering logic

4. Vendor aggregation and concentration analysis (15)
- Correct share calculations and anomaly interpretation

5. Benford application (15)
- Correct first-digit method and evidence-based discussion

6. Suspicious supplier identification (10)
- Clear evidence for supplier selection

7. Fraud amount estimation (10)
- Transparent baseline assumption and excess calculation

8. Fraud date range derivation (5)
- Correct linkage from suspicious windows to date range

9. Communication quality (10)
- Clarity, reproducibility, and forensic reasoning quality

## Expected Top-Risk Vendor Context (Reference)

In this dataset run, the top vendor risk ordering begins with:

1. Mercato Maintenance Works
2. Arno Lamp Oil Merchants
3. San Lorenzo Couriers
4. Santa Maria Scribes
5. Guildhall Security Company

This ranking supports the expected fictitious supplier candidate but should be treated as model-driven guidance, not absolute ground truth.
