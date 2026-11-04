# Draft: report background paragraph (human gates 7/8, not approved)

Answers the organizers' question "Was there such an incident before? Explain the use case
background." Not in the report yet; it goes into section 2 only after the human approves the
wording. Every number is listed in `docs/report/background-sources.yaml`, with its source;
`tests/integration/test_technical_report.py` checks this.

**Precedents.** We found no documented incident combining this whole chain; the scenario stays hypothetical, with synthetic data. Several links have analogous real incidents, not this scenario. In 2023 Optus attributed a 12-hour Australian outage to a routing change after a software upgrade; it affected an estimated 10.2 million subscribers, hospitals, banking and payments, and 2,145 people could not reach emergency calls. In 2024 a faulty CrowdStrike update affected an estimated 8.5 million Windows devices; a peer-reviewed study measured coinciding disruptions at 759 US hospitals, including patient portals. Automated risk flags have also hit legitimate users: Bank of America's fraud filter froze thousands of benefit accounts, and the Dutch DPA found a tax system used nationality to mark applications as risky.
