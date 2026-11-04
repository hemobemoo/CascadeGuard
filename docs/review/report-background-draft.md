# Draft: report background paragraph (human gates 7/8, not approved)

Answers the organizers' question "Was there such an incident before? Explain the use case
background." Not in the report yet; it goes into section 2 only after the human approves the
wording. Every number is listed in `docs/report/background-sources.yaml`, with its source;
`tests/integration/test_technical_report.py` checks this.

**Precedents.** We found no documented incident that combines this whole chain; the scenario stays hypothetical, with synthetic data. Each link has an analogous real incident, not this scenario. In 2023 a routing change after a software upgrade caused a 12-hour Optus outage in Australia, affecting an estimated 10.2 million subscribers, hospitals, banking and payments; 2,145 people could not reach emergency calls. In 2024 a faulty CrowdStrike update crashed an estimated 8.5 million Windows devices, and a peer-reviewed study measured coinciding disruptions at 759 US hospitals, including patient portals. Automated risk flags have also hit legitimate users at scale: Bank of America's fraud filter froze unemployment-benefit accounts, and a Dutch tax system used nationality to mark applications as risky.
