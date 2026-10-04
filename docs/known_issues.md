# Known issues

Open gaps in ingestion, retrieval, answering and evaluation. Each row says which eval questions
(eval/questions.csv) it affects, the planned fix, the step it is planned for, and its status.
Update the status when a fix lands (`fixed in step X`), and add new gaps at the end.

Latest measurements: eval/results/answer_eval_summary_v3_5A.md, eval/results/retrieval_v3_5A.csv.

## Answering and retrieval

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-01 | Source headers in the prompt showed para number and title only, not chapter or section, so "where are the rules located" questions could not name the chapter. | q006 | Put title › chapter › section › para: title, page in each source header. | 5A | fixed in step 5A (q006 partial -> correct) |
| KI-02 | Answers dropped conditions that limit a rule (q029 left out "for customers who have not complied after the advance intimations"). | q029 | System-prompt rule: always keep conditions, exceptions and qualifiers that limit a rule. | 5A | fixed in step 5A for q029 (faithfulness partial -> supported); q028 still drops the qualifier "accounts opened with Aadhaar OTP e-KYC" (it is in the question; faithfulness judge flags it) |
| KI-03 | Change questions need the old version of a rule, but search is active-only, so repealed, withdrawn and incorporated documents (2016 KYC MD, June/Aug 2025 KYC amendments, Digital Lending Directions 2025, NBFC KYC amendment Dec 2025) are never retrieved. The model answers the current rule and says the comparison is not covered. | q004, q041, q042, q044 (also q045, q046 depend on old documents) | Version-aware retrieval: for change/status questions also search superseded documents and label them with their status in the prompt (or a "compare versions" mode). | 5B | open |
| KI-04 | Status question about a document's validity: the answer is only in data/metadata.csv (status, replaced_by, notes), which is not indexed. | q007 | Index one "document status" record per document from metadata.csv, or give the answerer a metadata lookup. | 6 | open |
| KI-05 | Retrieval miss: the repeal clause (NBFC Credit Facilities para 112) is at rank 9 (not top 5) for "are the earlier directions still in force". | q043 | Hybrid search (BM25 on the existing `tsv` column + vector), or a larger k for status questions; together with KI-03. Since 5A the model no longer refuses here: it answers with an unsupported inference ("they are in force"), consistently over 5 runs. | 5B | open |
| KI-06 | Retrieval miss: the beneficial-owner definition (NBFC KYC para 5) is not in the top 10; the definitions paragraph is split into 18 parts and the right part does not stand out. | q020 | Hybrid search, or index each definition as its own chunk. | 5B | open |
| KI-07 | Retrieval miss: NBFC Credit Facilities para 25 not in the top 10 in the retrieval eval. | q019 | Hybrid search / reranker. | 5B | open |

## Evaluation

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-08 | Correctness judge saw only the evidence quote, so a true extra fact from the same paragraph ("past default rates on similar portfolios", para 20(3)) was marked wrong. | q034 (nano) | Correctness judge also gets the full text of the cited sources; extra facts they support are not wrong. | 5A | fixed in step 5A |
| KI-09 | Diagnosis for two-source questions counted generation_error when only one of the expected sources was retrieved. | q004, q041, q042, q044 | retrieval_miss if ANY expected source is missing from the top 5. | 5A | fixed in step 5A |
| KI-10 | Refusals were scored by exact sentence only; a refusal in other words (nano: "does not state a specific minimum age") counted as incorrect. | q049 (nano) | Unanswerable: correct if the answer refuses by meaning (judge); exact-sentence matches reported separately. | 5A | fixed in step 5A |
| KI-15 | The faithfulness judge sees each cited source's text and para label, but not the header path (chapter / section) the answer model sees, so a correct chapter name is flagged as unsupported. | q006 (faithfulness partially_supported in 5A) | Give both judges the same source header as the answer prompt (rag.answer.location). | 5B | open |
| KI-16 | The answer model runs at its default temperature, so answers vary between runs: q005 dropped "set by the NBFC in its credit policy" in the 5A eval run but gave the full answer in 4 of 4 reruns. One or two verdicts per run can flip from noise. | q005 (5A run) | Answer with temperature 0 (supported with reasoning effort none), or score the mean of several runs. | 5B | open |

## Ingestion and chunking

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-11 | OCR-like words and scrambled word order in the Key Facts Statement template table (NBFC Responsible Business Conduct, Annex I): table cells are read out of order, e.g. "details of LSP acting as recovery authorized to approach the borrower agent". | q009 (answer is correct but garbled) | Re-parse the KFS table with table-structure output (row-wise cells), or a manual text override for that annex. | later | open |
| KI-12 | 2016 KYC MD Annex IV (list of repealed circulars) is parsed as mixed tables: rows of circular numbers and dates from several tables run together, giving 10 very long preamble chunks. | none (document is repealed; not searched by default) | Low priority: mark Annex IV as boilerplate or skip it; it holds no rules. | later | open |
| KI-13 | 42-character stray chunk in kyc_md_2016 ("Communications from International Agencies"): the Chapter IX title wraps onto a second line and the second line became a preamble chunk. | none | Chunker: a chapter title ending in a dash continues on the next line (generic). | 5A | fixed in step 5A (chunk removed; 9 Chapter IX chunks now carry the full chapter title) |
| KI-14 | 12 chunks exceed BGE's 512-token limit, so their tails are not embedded: 10 are the 2016 Annex IV tables (690-949 tokens, see KI-12) and 2 are NBFC Responsible Business Conduct para 29 parts 2 and 4 (APR computation tables, 542 and 601 tokens; tables tokenize to more tokens per character than prose). | none directly (para 29 tail is searchable only through its first ~512 tokens) | Split by tokens instead of characters (or a lower MAX_CHARS for table-heavy text); KI-12 fix removes the other 10. | later | open |
