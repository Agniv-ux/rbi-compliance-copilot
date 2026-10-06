# Known issues

Open gaps in ingestion, retrieval, answering and evaluation. Each row says which eval questions
(eval/questions.csv) it affects, the planned fix, the step it is planned for, and its status.
Update the status when a fix lands (`fixed in step X`), and add new gaps at the end.

Latest measurements:
- retrieval: eval/results/retrieval_ablation_v5_5C.md (vector / keyword / hybrid, R@1-R@30)
- answers, Step 5B (gpt-5.4 holistic judge): answer_eval_summary_v4_5B.md (default) and
  answer_eval_summary_v4_5B_routed.md (manual routing)
- answers, Step 5C (gpt-5.4-nano key-fact judge, 3 votes; faithfulness 1 vote):
  answer_eval_summary_v5_5C.md (default: 86% correct) and answer_eval_summary_v5_5C_routed.md (manual
  routing: 94%). Judge changed, so 5C scores are not directly comparable to 5B (see KI-21).

"Left for the agent" means the capability exists but choosing it per question is manual today;
Step 6's agent has to pick the mode / tool itself.

## Answering and retrieval

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-01 | Source headers in the prompt showed para number and title only, not chapter or section, so "where are the rules located" questions could not name the chapter. | q006 | Put title › chapter › section › para: title, page in each source header. | 5A | fixed in step 5A |
| KI-02 | Answers dropped conditions that limit a rule (q029 left out "for customers who have not complied after the advance intimations"). | q029, q028 | System-prompt rule: always keep conditions, exceptions and qualifiers that limit a rule. | 5A | fixed in step 5A for q029; q028 still drops "accounts opened with Aadhaar OTP e-KYC" (the qualifier is in the question) |
| KI-03 | Change questions need the old version of a rule, but default search is active-only. | q041, q042, q044 (q004, q045, q046 also touch old documents) | `mode="compare"` in rag/answer.py. | 5B | compare mode added in step 5B. 5C manual routing: change questions 6/7 correct (q041, q042, q044 correct; q004 partial = generation_error). Default mode: 3/7. Routing per question is **left for the agent** (Step 6). |
| KI-04 | Status question about a document's validity: the answer is only in data/metadata.csv. | q007 | rag/status.py get_document_status() record as an extra source. | 5B / 6 | lookup added in step 5B (manual routing: q007 -> correct). Calling it per question is **left for the agent**. |
| KI-05 | q043: the repeal clause (NBFC Credit Facilities para 112) is not in the top 5 (vector rank 8, keyword >30, hybrid 18). In 5A the model inferred "they are in force". | q043 | (a) Safety rule: never infer a document's status. (b) Status lookup as a source. (c) Better retrieval. | 5B / 5D | (a) fixed in step 5B (5C default run: "the documents do not state whether ... in force" - safe, scored incorrect); (b) works with manual routing (5C: partial 2/3 - says "withdrawn ... NOT in force" but omits "now in Chapter III", although the status record's notes contain it); (c) open: hybrid does not help (rank 18). Para 112 is in vector's and hybrid's top 20, so a reranker over 20 candidates could reach it (step 5D). |
| KI-06 | q020: the beneficial-owner definition for companies (NBFC KYC para 5 part 1 of 18) is not retrieved. | q020 | Hybrid search, a reranker, or one chunk per definition. | 5C / 5D | hybrid tried in step 5C: para 5 moves to rank 2 (vector 15) but the part found is part 2 (partnership firms), not part 1 (companies) - see KI-19. Open; reranker in step 5D. |
| KI-07 | q019: NBFC Credit Facilities para 25 not retrieved by vector search (rank >30). | q019 | Keyword / hybrid search, reranker. | 5C / 5D | keyword search finds it at rank 4, hybrid at 13 (in the top-20 pool). Open; reranker in step 5D. The answer is judged correct from other chunks anyway. |
| KI-20 | Hybrid search (RRF of top 20 vector + top 20 keyword) is not better than vector at the answer's k=5: R@1 75.0% vs 70.5%, R@5 90.9% vs 93.2%; it helps simple questions (R@5 95% vs 90%) but pushes status / change paragraphs down (q006 5 -> 10, q046 5 -> 6). In its favour: hybrid R@20 = 100% (vector 97.7%). | q006, q046 (worse); q020 (better) | Keep vector as the answer() default; test hybrid again as the candidate pool for a reranker. | 5D | open (decision in step 5C: vector stays the default, based on R@5) |

## Evaluation

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-08 | Correctness judge saw only the evidence quote, so a true extra fact was marked wrong. | q034 (nano) | Judge also gets the cited sources' text. | 5A | fixed in step 5A |
| KI-09 | Diagnosis for two-source questions counted generation_error when only one source was retrieved. | q004, q041, q042, q044 | retrieval_miss if ANY expected source is missing from the top 5. | 5A | fixed in step 5A |
| KI-10 | Refusals were scored by exact sentence only. | q049 (nano) | Refusal judged by meaning; exact-sentence matches reported separately. | 5A | fixed in step 5A |
| KI-15 | The judges did not see the source header the answer model sees. | q006 | Judges get the same source block (rag.answer.source_block). | 5B | fixed in step 5B |
| KI-16 | Answers vary between runs even at temperature 0 (the identical q043 prompt gave 2 different answers in 4 calls). | q005, q043 | Temperature 0 + dated snapshots + cache answers so re-runs are identical; `--repeat N` to measure the noise. A fixed seed is not possible: the Responses API rejects `seed`, and Chat Completions' best-effort seed gave the same 2-in-6 variation. | 5B / 5C | mitigated in step 5C: snapshots gpt-5.4-mini-2026-03-17 / gpt-5.4-nano-2026-03-17, answer + judge cache (eval/cache/), `--repeat N`. Noise level not measured yet (`--repeat` skipped for budget). |
| KI-17 | Judge inconsistency: the same q004 answer was "correct" in one run and "partial" in another (holistic gpt-5.4 judge). | q004 | Key-fact judge (present / missing / contradicted per fact, verdict computed in code), `--judge-votes N`, human gold set. | 5C | addressed in step 5C: key-fact judge; q004 is now partial in both runs (the "last uploader is responsible" fact is missing although it is in the cited chunk). The nano judge first credited that fact because it is in the cited source; fixed with an explicit rule ("only the system answer counts; a fact only in the sources is missing") and 3 votes (agreement 99.8%). Gold set graded **by Claude (AI), not a human** (labelled in the file): nano agrees on 14/15 (93%), same as the Step 5B gpt-5.4 judge; the one disagreement is q004 (reference partial, nano correct), and nano also judged that same answer partial in Run A - it is unstable on q004 even with 3 votes. Still open: human grading of the gold set; consider 5 votes or a stricter fact-3 check for q004-type cases. |
| KI-18 | The faithfulness judge did not count the status label in the header as source text. | q007 (routed) | Put the status label inside the status record text. | 5C | fixed in step 5C (rag/status.py status_text) |
| KI-19 | The retrieval eval matches at paragraph level, so a hit on any part of a long split paragraph counts. For q020 hybrid "finds" para 5 at rank 2, but that is part 2 (partnership firms); the company rule is part 1 (hybrid rank 14), so the answer still refuses. Recall is overstated for long, split paragraphs. | q020 (para 5 has 18 parts); possibly others with split paragraphs | Record the expected part (or a text snippet from evidence_quote) and match on it. | 5D | open |
| KI-21 | Judge changed in step 5C. Planned: Gemini Flash (free tier). But the free tier allows only **20 requests per day per model per project** (quota GenerateRequestsPerDayPerProjectPerModel-FreeTier) and a run needs ~115 judge calls; gemini-3.5-flash and gemini-3.6-flash both ran out. The 5C runs were therefore judged by **gpt-5.4-nano** (3 votes for correctness, 1 for faithfulness; ~$0.06 per run). A smaller model grades mini's answers; its reliability is unproven until the gold set is graded. | all | Gemini code stays in place (throttle, backoff, fail fast with QuotaExhausted when the server asks to wait > 2 min). Decision (after step 5C): **gpt-5.4-nano is the judge going forward** (default in .env / rag/llm.py). Validated against AI-graded reference verdicts: 14/15 (see KI-17); human validation still to do. Compare runs only under the same judge. | 5D | decided; validation open |
| KI-23 | The nano faithfulness judge is strict in two ways: (a) it marks an answer that only says "the documents do not state X" as unsupported (q043 default run); (b) it does not accept a chapter name taken from the source header as supported (q006, both runs). | q043, q006 | Tell the faithfulness judge that statements about what the sources do not contain are not claims, and that the header is part of the source (already in the prompt; nano ignores it); check on the gold set. | 5D | open |
| KI-22 | Key facts: q001 and q022 have a single key fact ("at least once every two / six months"), outside the planned 2-5, because "at least" was merged into the period fact. | q001, q022 | none needed | - | accepted |

## Ingestion and chunking

| id | description | affected questions | planned fix | target | status |
|---|---|---|---|---|---|
| KI-11 | OCR-like words and scrambled word order in the Key Facts Statement template table (NBFC Responsible Business Conduct, Annex I). | q009 (answer correct but garbled) | Re-parse the KFS table with table-structure output, or a manual text override. | later | open |
| KI-12 | Lists of repealed circulars (2016 KYC MD Annex IV, Digital Lending Annex III) took source slots, especially in compare mode. | none scored wrong | Generic detector (chunker.is_circular_list: most lines are circular reference numbers or numbered rows ending in a date) marks them boilerplate. | 5C | fixed in step 5C: 11 chunks flagged (10 in 2016 Annex IV, 1 in Digital Lending Annex III); the FPI KYC tables in Annex IV stay searchable; 0 re-embedded. Vector R@5 rose 90.9% -> 93.2%. |
| KI-13 | 42-character stray chunk in kyc_md_2016 (Chapter IX title wrapped onto a second line). | none | Chunker: a chapter title ending in a dash continues on the next line. | 5A | fixed in step 5A |
| KI-14 | 12 chunks exceed BGE's 512-token limit: 10 in the 2016 Annex IV tables and 2 in NBFC Responsible Business Conduct para 29 (APR tables). | none directly | Split by tokens instead of characters. | later | partly fixed in step 5C: all 10 over-limit Annex IV chunks (circular lists) are now boilerplate and not searched; the 2 para 29 chunks remain |
