# Known issues

Open gaps in ingestion, retrieval, answering and evaluation. Each row says which eval questions
(eval/questions.csv) it affects, the planned fix, the step it is planned for, and its status.
Update the status when a fix lands (`fixed in step X`), and add new gaps at the end.

Latest measurements (step 5B, gpt-5.4-mini, gpt-5.4 judge):
- default run, as a user would ask: eval/results/answer_eval_summary_v4_5B.md (88% correct, see KI-17)
- manual routing, NOT what a user gets: eval/results/answer_eval_summary_v4_5B_routed.md (94% correct)
- retrieval: eval/results/retrieval_v3_5A.csv (R@5 90.9%)

"Left for the agent" means the capability exists but choosing it per question is manual today;
Step 6's agent has to pick the mode / tool itself.

## Answering and retrieval

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-01 | Source headers in the prompt showed para number and title only, not chapter or section, so "where are the rules located" questions could not name the chapter. | q006 | Put title › chapter › section › para: title, page in each source header. | 5A | fixed in step 5A (q006 partial -> correct) |
| KI-02 | Answers dropped conditions that limit a rule (q029 left out "for customers who have not complied after the advance intimations"). | q029, q028 | System-prompt rule: always keep conditions, exceptions and qualifiers that limit a rule. | 5A | fixed in step 5A for q029; q028 still drops "accounts opened with Aadhaar OTP e-KYC" (the qualifier is in the question; faithfulness partially_supported in 5A and 5B) |
| KI-03 | Change questions need the old version of a rule, but default search is active-only, so repealed, withdrawn and incorporated documents are never retrieved; the model answers the current rule and says the comparison is not covered. | q041, q042, q044 (q004, q045, q046 also touch old documents) | `mode="compare"` in rag/answer.py: top k active + top k superseded, status-tagged headers, "Earlier: ... / Now: ..." rules. | 5B | compare mode added in step 5B. With manual routing q041 and q044 partial -> correct; q042 now gives Earlier/Now but omits the "effective 13 February 2026" date (generation_error). Default mode is unchanged, so routing change questions to compare mode is **left for the agent** (Step 6). |
| KI-04 | Status question about a document's validity: the answer is only in data/metadata.csv (status, replaced_by, notes), which is not indexed. | q007 | rag/status.py get_document_status(): fuzzy lookup in the documents table, no LLM; its record is added as an extra source. | 5B / 6 | lookup added in step 5B; with manual routing q007 incorrect -> correct. Calling it per question is **left for the agent** (Step 6 tool). |
| KI-05 | q043 ("are the earlier directions still in force"): the repeal clause (NBFC Credit Facilities para 112) is at rank 9, not top 5. In 5A the model inferred "they are in force" with no source saying so. | q043 | (a) Safety rule: never infer a document's status. (b) Status lookup as a source. (c) Hybrid search for para 112. | 5B / 5C | (a) fixed in step 5B: 0 of 5 reruns claim the old directions are in force (the eval run's answer only describes the current Directions). (b) with manual routing q043 incorrect -> correct ("withdrawn ... replaced for NBFCs by ... not in force"). (c) open: default mode is still a retrieval_miss. |
| KI-06 | Retrieval miss: the beneficial-owner definition (NBFC KYC para 5) is not in the top 10; the definitions paragraph is split into 18 parts and the right part does not stand out. | q020 | Hybrid search, or index each definition as its own chunk. | 5C | open (false refusal in every run) |
| KI-07 | Retrieval miss: NBFC Credit Facilities para 25 not in the top 10 in the retrieval eval. | q019 | Hybrid search / reranker. | 5C | open (the answer is still judged correct from other chunks) |

## Evaluation

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-08 | Correctness judge saw only the evidence quote, so a true extra fact from the same paragraph ("past default rates on similar portfolios", para 20(3)) was marked wrong. | q034 (nano) | Correctness judge also gets the full text of the cited sources; extra facts they support are not wrong. | 5A | fixed in step 5A |
| KI-09 | Diagnosis for two-source questions counted generation_error when only one of the expected sources was retrieved. | q004, q041, q042, q044 | retrieval_miss if ANY expected source is missing from the top 5. | 5A | fixed in step 5A |
| KI-10 | Refusals were scored by exact sentence only; a refusal in other words (nano: "does not state a specific minimum age") counted as incorrect. | q049 (nano) | Unanswerable: correct if the answer refuses by meaning (judge); exact-sentence matches reported separately. | 5A | fixed in step 5A |
| KI-15 | The judges saw each cited source's text and para label, but not the header (chapter / section / status) the answer model sees, so a correct chapter name was flagged as unsupported. | q006 | Judges get exactly the same source block as the answer model (rag.answer.source_block). | 5B | fixed in step 5B (q006 faithfulness partially_supported -> supported) |
| KI-16 | Answers varied between runs at the default temperature (q005 dropped a qualifier once in 5 runs). | q005 | Answer with temperature 0 (reasoning effort none). | 5B | partly fixed in step 5B: temperature 0 is sent, but OpenAI is still not deterministic (the identical q043 prompt gave 2 different answers in 4 calls). Treat a 1-question change as noise; for decisions, compare several runs or vote. |
| KI-17 | Judge inconsistency: q004 got the same answer in Run A and Run B (neither says the entity that last uploaded the record is responsible), but the Run A judge said "correct" and claimed that fact was there; Run B said "partial". Run A's true score is therefore 43/50 (86%), not 44/50. | q004 | Majority vote of 3 judge calls, or run the judge with reasoning effort "low" (temperature cannot then be set) and check agreement on a fixed sample. | 5C | open |
| KI-18 | For the document-status source, the faithfulness judge does not count the header label ("REPEALED on 2025-11-28 ... - NOT in force") as source text, so quoting "not in force" is flagged. | q007 (routed run) | Put the status label inside the status record text as well (rag.status.status_text). | 5C | open |

## Ingestion and chunking

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-11 | OCR-like words and scrambled word order in the Key Facts Statement template table (NBFC Responsible Business Conduct, Annex I): table cells are read out of order, e.g. "details of LSP acting as recovery authorized to approach the borrower agent". | q009 (answer is correct but garbled) | Re-parse the KFS table with table-structure output (row-wise cells), or a manual text override for that annex. | later | open |
| KI-12 | 2016 KYC MD Annex IV (list of repealed circulars) is parsed as mixed tables: rows of circular numbers and dates from several tables run together, giving 10 very long preamble chunks. Compare mode now searches superseded documents, so such circular lists can take source slots (q041's compare run retrieved the Digital Lending Directions' "List of circulars to be repealed" annex). | none scored wrong yet | Mark repealed-circular lists (2016 Annex IV, Digital Lending Annex III) as boilerplate so search skips them. | 5C | open (more relevant since 5B) |
| KI-13 | 42-character stray chunk in kyc_md_2016 ("Communications from International Agencies"): the Chapter IX title wraps onto a second line and the second line became a preamble chunk. | none | Chunker: a chapter title ending in a dash continues on the next line (generic). | 5A | fixed in step 5A (chunk removed; 9 Chapter IX chunks now carry the full chapter title) |
| KI-14 | 12 chunks exceed BGE's 512-token limit, so their tails are not embedded: 10 are the 2016 Annex IV tables (690-949 tokens, see KI-12) and 2 are NBFC Responsible Business Conduct para 29 parts 2 and 4 (APR computation tables, 542 and 601 tokens; tables tokenize to more tokens per character than prose). | none directly (para 29 tail is searchable only through its first ~512 tokens) | Split by tokens instead of characters (or a lower MAX_CHARS for table-heavy text); KI-12 fix removes the other 10. | later | open |
