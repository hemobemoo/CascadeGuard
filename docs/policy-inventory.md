# Policy source inventory (Phase 1a; #20–22 added in Phase 6d)

The 22 PDFs in `policies/sources/` (plus one derived OCR copy, listed after the table, and the
seven web transcriptions in `policies/sources/web/`, listed at the end), from
`policies/extracted/_inventory.json`
(`uv run python scripts/extract_pdf_text.py`). "No-text pages" = fewer than 20 non-space
characters extracted. Issuer and date are as printed in the document; "not printed" means the PDF
does not state one (PDF file metadata is not used, since several copies were re-saved in 2026).

| # | File | Title | Issuer | Date | Pages | No-text pages | Clean? |
|---|---|---|---|---|---|---|---|
| 1 | `5 AI RMF Core - Excerpt from the NIST AI…(2023)..pdf` | AI RMF 1.0 Core (excerpt) | NIST (US) | 2023 | 10 | — | Yes (table cells separated by `\|`) |
| 2 | `887026278-TDRA-Telecom-Law-Final-English-o.pdf` | Federal Law by Decree No. 3 of 2003 (Telecom), as amended | UAE; consolidated text by TDRA | 2003, consolidated 2022 | 47 | 4, **13–47** | **No — see below; OCR copy available** |
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
| 20 | `OECD_Recommendation_AI.pdf` | Recommendation of the Council on Artificial Intelligence, OECD/LEGAL/0449 (official original) | OECD Council | adopted 2019-05-22; revised 2023-11-08 and 2024-05-03 | 12 | — | Yes (running header `O_E_C_D_/L_E_G_A_L` on each page) |
| 21 | `UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf` | Recommendation on the Ethics of AI, SHS/BIO/PI/2021/1 (official original) | UNESCO General Conference | 2021-11-23 | 44 | 8, 12, 16, 24 (section divider images, page number only) | Two columns: read column by column where the gutter is clear (20 pages, records `"columns": 2`); pages 2, 4, 26, 27, 30, 33, 35–37, 39, 41–43 have a full-width heading and still interleave |
| 22 | `UAE_National_Cybersecurity_Strategy.pdf` | National Cyber Security Strategy (TRA era) | Telecommunications Regulatory Authority (TRA) | **unknown** (not printed) | 16 | — | **No — see below** |

**SHA-256 of the committed originals** (Phase 6d; the two books are not committed and not
listed). Originals are never modified, renamed or deleted; `tests/unit/test_web_sources.py` checks these.

`ea092ad2929a8ace15adda9599306b3b6ac9c8bdcba94d2b8f7ad26b79b9d10f`  `5 AI RMF Core - Excerpt from the NIST AI Risk Management Framework 1.0 (2023)..pdf`
`f6c6d4a90bcdc16bf9b564929189962c34fd130c23f171e619aa311fa84e1abb`  `887026278-TDRA-Telecom-Law-Final-English-o.pdf`
`c5604dc6e9261146cb943490f4d234ecf4b24313724c9e65ef44752898aa2748`  `AI-Adoption-Guideline-in-Government-Services-Eng.pdf`
`68ca40517e49d9e055c4885809ad297cd9b7d7d7429e91122d4cbc66e189cadb`  `AIGuide_EN_v1-online.pdf`
`0050b8414ce6635cf3088556aef41c065cace091d28025821c157a2a3ffb39d8`  `Dubai Law No. (26) of 2015.pdf`
`bba630444b3278e881066774002a1d7824308934f49ccfa203e65be43692f55e`  `EU AI Act, Regulation (EU) 2024-1689.pdf`
`d5d5f9e93bd6c0dc2afe79776f3101bcd599e4400a67309bc0b378b2812bcf3a`  `Federal Decree by Law No. (45) of 2021 Concerning the Protection of Personal Data.pdf`
`18e6c90c505143021c086d72fb93ac898ba2e078e2f1b8236e8ce2ff237c052c`  `GDPR-Regulation (EU) 2016-679.pdf`
`2088229d1b29bdc44eec0f01d077afd4ea37eaf79fb48d9fc76ccbc0d3a43d7a`  `Health Data Protection and Confidentiality Policy_EN2022810559.pdf`
`f761ec3b18915038f65265ae60a365164ee5674fee73041e973163895723f56d`  `MOCAI-AI-Ethics-EN-1.pdf`
`e8c1a12dd0f69b56641a83c96a728e378732966b517cc48672b3f424de67f3d1`  `OCED-Towards a common reporting framework for AI incidents.pdf`
`88227000e69be9aad5864155bd3e06ebead1e76c5b7cf662d63c1605408e5060`  `OECD_Recommendation_AI.pdf`
`76424266be7fa8559271942d7fd8665113f234a9a805778f209952d82c4d6b44`  `Responsible-Metaverse-Self-governance-Framework-2023-EN.pdf`
`71191768d46b60778c15f8d62b162aff73a319785cfc31ebf76bb944b0c68273`  `T-AI4G-AI4GOOD-2025-6-PDF-E.pdf`
`e42f9a3be3f951d3e19b9007f876f0b389c81b4693f0d8576e18185a1acfe67b`  `T-REC-Y.3172-201906-I!!PDF-E.pdf`
`ba81b0e36026c46569008ce83d00632dbc4bd8d185029862379c38a90b2c6296`  `UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf`
`849644db7579a2e8b9bcec8e8033d80e37bb6b0a70aa2a2f68a5d5b3546297f9`  `UAE Policy Foundation.pdf`
`79e05c502d1fc1247165fc744205984675d6422a490a70201dc4c05bf9aed693`  `UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf`
`dd9767dcc6528d3982363ee75a85502641a8d19ad325baa39029444ac11fbbf7`  `UAE_National_Cybersecurity_Strategy.pdf`
`faf8887e89c3b43aa373a1e95433f1322eae14fae4fe7db59373fe6a2ed6d675`  `UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf`

**English translations not verified as official** (human decision 2026-10-29). Clauses quoted
from these files carry "English translation" in their label (`TRANSLATIONS` in
`src/cascadeguard/domain/policies.py`; tested against this list). Each is the English text of UAE
legislation whose Arabic text is authoritative, and nothing in the repository verifies the English
as an official translation (Dubai Law 26/2015 says so itself on its first page). The DHA policy (#10)
is not listed: it is the issuer's own English version, though it says the Arabic version prevails.

- `887026278-TDRA-Telecom-Law-Final-English-o.pdf`
- `ocr/887026278-TDRA-Telecom-Law-Final-English-o.ocr.pdf`
- `Dubai Law No. (26) of 2015.pdf`
- `Federal Decree by Law No. (45) of 2021 Concerning the Protection of Personal Data.pdf`
- `UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf`

**#4 `AIGuide_EN_v1-online.pdf`:** no official source was found for it (README, question 3x),
and no clause in `policies/reviewed/` quotes it (checked 2026-10-23). It is context only.

## Derived OCR source

| File | Derived from | Pages | No-text pages | Output |
|---|---|---|---|---|
| `ocr/887026278-TDRA-Telecom-Law-Final-English-o.ocr.pdf` | #2 (original unchanged) | 47 | 4 (chapter title page) | `887026278-TDRA-Telecom-Law-Final-English-o.ocr.jsonl`, every page `"ocr": true` |

OCR text is not quoted as-is: quotes are corrected against the page image and flagged
"OCR — check against image" (provenance and known errors in `docs/policy-methodology.md`).
Printed page = PDF page index − 2 on pages 5–47 (e.g. Art 12–13 on index 13 = printed 11;
Art 14 on index 14–16 = printed 12–14; Art 28–31 on index 21 = printed 19).

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

- **Telecom Law (#2), pages 13–47.** No characters and no images in the original: the text is
  drawn as vector outlines. The human supplied an OCR'd copy (above). One clause is quoted from it
  (`uae.telecom-law.art14-5`, corrected against the page image); the incident-report rule stays
  illustrative. Page 4 is a chapter title page.
- **Other no-text pages** are covers, blank pages or full-page images (#3, #4, #5, #11, #15, #19).
  None is needed by the scenario.

- **#22 `UAE_National_Cybersecurity_Strategy.pdf`.** Garbled, not guessed: page 5 (the "Cyber
  Security Strategy Framework" circle diagram) extracts as scattered letters; pages 6–16 are
  diagram and table pages whose labels run together across columns
  (worst: 7, 9, 11, 14, 16). Text must be checked against the page image before any quote.

**#22 is historical context; superseded by the 2025 National Cybersecurity Strategy** (human
decision 2026-10-28). It is undated (`document_date: unknown`; its file metadata says 2019, which
is not used) and from the TRA era. No clause is drafted from it. The 2025 strategy itself is not in
`policies/sources/`; the 03 web transcription is its only source here.

**#22 is not searched** (human decision 2026-10-28): it is kept out of `--extracted-context`
retrieval and out of the extracted digest (`NOT_SEARCHED` in `src/cascadeguard/knowledge/retrieval.py`),
so no snippet from it reaches any agent. Reason: superseded by the 2025 strategy, and its
extraction is unreliable (page 5; pages 6–16). The PDF, its SHA-256, this entry and its extracted
`.jsonl` stay as historical provenance.

Not scanned in the OCR sense: no PDF is an image-only scan.

## Web transcriptions (`policies/sources/web/`, Phase 6c)

Official web pages printed to PDF by the human on 2026-10-27; unverified. Official URLs, issuers,
dates and types are in `policies/sources/web/MANIFEST.md`. Every page has extractable text.

| File | Pages | Clauses drafted |
|---|---|---|
| `01_uae_smart_health_ai_policy.pdf` | 5 | 3 (`uae.mohap-smart-health.*`) |
| `02_uae_international_ai_policy.pdf` | 8 | none (source only) |
| `03_uae_national_cybersecurity_strategy.pdf` | 3 | 2 (`uae.cyber-strategy-2025.*`; announcement summaries, not the strategy) |
| `04_uae_digital_government_strategy_2025.pdf` | 14 | none (source only) |
| `05_uae_ai_government_policies.pdf` | 7 | none (source only) |
| `06_unesco_ai_ethics_recommendation.pdf` | 6 | none since Phase 6d (superseded by #21) |
| `07_oecd_ai_principles.pdf` | 10 | none since Phase 6d (superseded by #20) |
