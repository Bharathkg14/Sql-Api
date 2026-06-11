# Sql-Api


1. Audit existing DQ checks

	•	Pull all current DQ rules from the centralized DBT rule tables
	•	Categorize them: redundant / false alerts / low value / valid

2. Profiling-driven gap analysis

	•	Use your data profiling results to validate which checks actually fire
	•	Identify columns with nulls, anomalies, cardinality issues that have no check currently

3. Propose improved DQ strategy

	•	Remove redundant checks
	•	Add anomaly-detection style checks based on profiling stats
	•	Align checks to business expectations per layer

4. POC

	•	Pick 1–2 tables (Bronze layer ideally)
	•	Implement revised DQ checks in DBT
	•	Show before/after — false alert detection
