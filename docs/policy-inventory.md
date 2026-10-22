# Policy source inventory (Phase 1a)

The 19 PDFs in `policies/sources/`, from `policies/extracted/_inventory.json`
(`uv run python scripts/extract_pdf_text.py`). "No-text pages" = fewer than 20 non-space
characters extracted. Issuer and date are as printed in the document; "not printed" means the PDF
does not state one (PDF file metadata is not used, since several copies were re-saved in 2026).

| # | File | Title | Issuer | Date | Pages | No-text pages | Clean? |
|---|---|---|---|---|---|---|---|
| 1 | `5 AI RMF Core - Excerpt from the NIST AI…(2023)..pdf` | AI RMF 1.0 Core (excerpt) | NIST (US) | 2023 | 10 | — | Yes (table cells separated by `\|`) |
| 2 | `887026278-TDRA-Telecom-Law-Final-English-o.pdf` | Federal Law by Decree No. 3 of 2003 (Telecom), as amended | UAE; consolidated text by TDRA | 2003, consolidated 2022 | 47 | 4, **13–47** | **No — see below** |
| 3 | `AI-Adoption-Guideline-in-Government-Services-Eng.pdf` | AI Adoption Guideline in Government Services | UAE Ministry of Cabinet Affairs / Prime Minister's Office (with partners) | not printed | 65 | 2, 5, 56, 59, 62, 65 (image pages) | Mostly; multi-column layout |
| 4 | `AIGuide_EN_v1-online.pdf` | Artificial Intelligence Guide (National Program for AI) | UAE National Program for AI | not printed | 39 | 1 (cover) | Mostly; two-column interleaving |
| 5 | `Artificial Intelligence Ethics and International Law…Abhivardhan.pdf` | *AI Ethics and International Law*, 2nd ed. (book) | Abhivardhan (author) | — | 270 | 1, 2, 4, 182, 256 | Yes. **Book: context only, not committed** |
| 6 | `Dubai Law No. (26) of 2015.pdf` | Law No. 26 of 2015 Regulating Data Dissemination and Exchange in Dubai | Government of Dubai | 2015 | 9 | — | Yes |
| 7 | `EU AI Act, Regulation (EU) 2024-1689.pdf` | Regulation (EU) 2024/1689 (AI Act) | European Union | 2024-06-13 | 144 | — | Yes |
| 8 | `Federal Decree by Law No. (45) of 2021…Personal Data.pdf` | Federal Decree-Law No. 45 of 2021 (PDPL) | UAE (federal) | 2021 | 29 | — | Yes |
| 9 | `GDPR-Regulation (EU) 2016-679.pdf` | Regulation (EU) 2016/679 (GDPR), consolidated | European Union | 2016-04-27 | 78 | — | Yes |
| 10 | `Health Data Protection and Confidentiality Policy_EN2022810559.pdf` | Policy for Data and Health Information Protection and Confidentiality (DHA/HRS/HISHD/PP-11) | Dubai Health Authority | 2022-08-10 | 50 | — | Yes (Arabic header lines extract reversed) |
| 11 | `MOCAI-AI-Ethics-EN-1.pdf` | AI Ethics Principles & Guidelines | UAE Minister of State for AI | 2022-12 | 25 | 25 | Partly; two-page spreads interleave columns |
| 12 | `OCED-Towards a common reporting framework for AI incidents.pdf` | Towards a Common Reporting Framework for AI Incidents (AI Papers No. 34) | OECD | 2025-02 | 27 | — | Yes |
| 13 | `Responsible-Metaverse-Self-governance-Framework-2023-EN.pdf` | Responsible Metaverse Self-governance Framework (white paper) | Agile Nations Metaverse Working Group | 2023 | 35 | — | Yes; not used by this scenario |
| 14 | `T-AI4G-AI4GOOD-2025-6-PDF-E.pdf` | AI Ready: Analysis Towards a Standardized Readiness Framework, Report 2.0 | ITU | 2026-01 | 55 | — | Yes |
| 15 | `T-REC-Y.3172-201906-I!!PDF-E.pdf` | ITU-T Y.3172, ML in future networks | ITU-T | 2019-06 | 34 | 6, 32, 33 (blank) | Yes (requirement IDs sit in a margin column) |
| 16 | `The Oxford Handbook of AI Governance…pdf` | *The Oxford Handbook of AI Governance* (book) | Bullock, Chen et al. (eds.) | — | 1006 | — | Yes. **Book: context only, not committed** |
| 17 | `UAE Federal Law No. 2 of 2019…Health Fields..pdf` | Federal Law No. 2 of 2019 on ICT in Health Fields (English translation) | UAE (federal) | 2019 | 7 | — | Yes |
| 18 | `UAE Policy Foundation.pdf` | Unofficial compilation of UAE policy pages (contents below) | not printed (unofficial compilation); Charter part: UAE AI, Digital Economy and Remote Work Applications Office (human decision) | unknown; Charter part: 2024-07 (human decision) | 16 | — | Yes |
| 19 | `UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf` | UAE National Strategy for AI 2031 | UAE Government (not printed on extracted pages) | not printed | 25 | 1, 25 (covers) | Yes |

## Contents of `UAE Policy Foundation.pdf`

An unofficial compilation (issuer and date not printed). Each part keeps its own issuer and date
when a clause is drafted from it; only the Charter part has been decided by the human.

| Pages | Document | Issuer / date used for clauses |
|---|---|---|
| 1–3 | UAE Charter for the Development and Use of Artificial Intelligence | UAE AI, Digital Economy and Remote Work Applications Office · 2024-07 · binding false |
| 3–4 | Personal Data Protection Law (summary of Federal Decree-Law No. 45 of 2021) | not decided (summary, not the law; quote the law itself) |
| 4–5 | Data and privacy protection: list of other related laws (consumer protection, ICT in health, cybercrimes, IAM policy, electronic transactions, Constitution Art. 31, IP, credit information, Dubai Data law, UAE Data Office) | not decided (summaries only) |
| 5–7 | The National Cyber Security Policy for Artificial Intelligence (summary) | not decided |
| 7–16 | UAE National Digital Government Strategy 2025: dimensions, objectives, KPIs, maturity model, SDGs, alignment with national strategies (pp. 12–14) and local eGovernment strategies (pp. 14–16, incl. Abu Dhabi "Once only" policy, p. 16) | not decided |

## Pages that need the human

- **Telecom Law (#2), pages 13–47.** No characters and no images: the text is drawn as vector
  outlines, so it cannot be extracted without OCR. These pages probably contain TDRA's competences
  and licensee obligations. Nothing from them is quoted; the two rules the scenario needs are
  `illustrative`. Page 4 is a chapter title page.
- **Other no-text pages** are covers, blank pages or full-page images (#3, #4, #5, #11, #15, #19).
  None is needed by the scenario.

Not scanned in the OCR sense: no PDF is an image-only scan.
