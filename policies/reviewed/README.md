# Clause files

Each `*.yaml` file holds `clauses:`, a list of clauses extracted from one or more PDFs in
`policies/sources/`. The engine reads only these files, never the PDFs. See
`docs/policy-methodology.md` for the review workflow.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Lower-case dotted id, e.g. `uae.fl2-2019.art16`. Unique across all files. |
| `title` | yes | Short human title. |
| `text` | yes | Verbatim quotation from the extracted page. `[...]` marks an omission (e.g. interleaved columns). Illustrative clauses carry a plain-language rule, starting "Illustrative rule, not a quotation". |
| `source_file` | yes, unless illustrative | PDF filename in `policies/sources/`. |
| `page` | yes, unless illustrative | PDF viewer page (1-based), the same index as `policies/extracted/`. Not the printed page number. |
| `article` | no | Article or section as printed. |
| `issuer` | yes | Issuing body. |
| `jurisdiction` | yes | Where it applies. |
| `document_date` | yes | `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or `unknown` if the PDF prints no date. |
| `status` | yes | See below. |
| `binding` | yes | `true`, `false`, or `unknown`. Foreign law is `false` for the UAE. |
| `normalized` | no | Machine-checkable reading: `basis`, `mapping_note`, `kind` (obligation, prohibition, permission, safeguard), `actor`, `action`, `counterpart`, `data_category`, `condition`, `deadline_minutes`. `actor` and `action` link to the scenario's `roles.yaml`. `basis: stated` means the text names the actor and the duty or permission and only role names are mapped (e.g. Licensees → `telecom_operator`). `basis: interpreted` means the actor or action is inferred; `mapping_note` (one line, required) says why. If the text only gives a power to regulate, it is never read as an obligation to act; such a rule becomes `illustrative`. The engine treats both bases the same; reports and the UI show "interpreted" next to the status label. Reviewed with the clause. |
| `notes` | required if illustrative | Context, applicability doubts, and why an illustrative rule is needed. |

## Status

- `draft` — written by an agent; not yet checked. **Not loaded by the engine.**
- `reviewed` — checked by the human against the PDF. Only the human sets this.
- `illustrative` — needed by the scenario but supported by no source PDF. Never binding and never
  presented as UAE law.

The test suite checks that every non-illustrative `text` appears on its cited page.
