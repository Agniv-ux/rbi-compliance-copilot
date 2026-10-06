# Answer eval summary

Questions: eval/questions.csv (50). System called as a user would: k=5, active documents only, retrieval method **vector**. Answers: gpt-5.4-mini-2026-03-17 (temperature 0). Judge: openai gpt-5.4-nano-2026-03-17 (lowest thinking level, temperature 0, structured JSON; majority of 3 call(s) for correctness, 1 for faithfulness); correctness = key facts present / missing / contradicted, verdict computed in code.

**Judge changed in Step 5C**: Step 5B (v4_5B) was graded by gpt-5.4 with a holistic verdict; this run is graded by openai gpt-5.4-nano-2026-03-17 checking key facts. Scores are therefore not directly comparable to v4_5B: a change can come from the system or from the judge.

Notes: partial and incorrect answers are both "non-correct" and get a diagnosis: retrieval_miss when any expected paragraph is missing from the retrieved top 5, otherwise generation_error. Unanswerable questions count as correct when the answer refuses by meaning. Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv). Costs count cached calls at their original cost.

**Routing: MANUAL (not what a user gets) - change questions in compare mode; status questions with the document-status record as an extra source; everything else copied from the default run.**

## Before / after

| metric | answers_gpt-5.4-mini_v4_5B_routed | answers_gpt-5.4-mini-2026-03-17_v5_5C | this run (gpt-5.4-mini-2026-03-17) |
|---|---|---|---|
| correct (all) | 94.0% (47/50) | 86.0% (43/50) | 94.0% (47/50) |
| partial (all) | 4.0% (2/50) | 8.0% (4/50) | 4.0% (2/50) |
| incorrect (all) | 2.0% (1/50) | 6.0% (3/50) | 2.0% (1/50) |
| correct: simple | 95.0% (19/20) | 95.0% (19/20) | 95.0% (19/20) |
| correct: multi_part | 100.0% (15/15) | 100.0% (15/15) | 100.0% (15/15) |
| correct: change | 71.4% (5/7) | 42.9% (3/7) | 85.7% (6/7) |
| correct: status | 100.0% (3/3) | 33.3% (1/3) | 66.7% (2/3) |
| correct: unanswerable | 100.0% (5/5) | 100.0% (5/5) | 100.0% (5/5) |
| correct (answerable) | 93.3% (42/45) | 84.4% (38/45) | 93.3% (42/45) |
| citation accuracy | 90.9% (40/44) | 90.9% (40/44) | 88.6% (39/44) |
| faithfulness: supported | 95.5% (42/44) | 93.0% (40/43) | 97.7% (43/44) |
| faithfulness: partially supported | 4.5% (2/44) | 4.7% (2/43) | 2.3% (1/44) |
| faithfulness: unsupported | 0.0% (0/44) | 2.3% (1/43) | 0.0% (0/44) |
| refusal accuracy (by meaning) | 100.0% (5/5) | 100.0% (5/5) | 100.0% (5/5) |
| refusal: exact sentence | 100.0% (5/5) | 100.0% (5/5) | 100.0% (5/5) |
| false-refusal rate | 2.2% (1/45) | 4.4% (2/45) | 2.2% (1/45) |
| retrieval_miss / generation_error | 1 / 2 | 7 / 0 | 2 / 1 |
| judge agreement (share of votes = majority) | n/a | 99.8% | 99.3% |
| answer tokens in / out (total) | 107,824 / 2,985 | 92,170 / 2,722 | 108,144 / 2,941 |
| answering cost: total / per question | $0.0943 / $0.00189 | $0.0814 / $0.00163 | $0.0943 / $0.00189 |
| judging cost: total / per question | $0.2901 / $0.00580 | $0.0572 / $0.00114 | $0.0579 / $0.00116 |
| avg answer latency | 1.72s | 1.67s | 1.82s |

Questions whose verdict or diagnosis changed vs answers_gpt-5.4-mini_v4_5B_routed:

| id | type | before | after | before diagnosis | after diagnosis |
|---|---|---|---|---|---|
| q042 | change | partial | correct | generation_error | - |
| q043 | status | correct | partial | - | retrieval_miss |

Questions whose verdict or diagnosis changed vs answers_gpt-5.4-mini-2026-03-17_v5_5C:

| id | type | before | after | before diagnosis | after diagnosis |
|---|---|---|---|---|---|
| q004 | change | partial | partial | retrieval_miss | generation_error |
| q007 | status | incorrect | correct | retrieval_miss | - |
| q041 | change | partial | correct | retrieval_miss | - |
| q042 | change | partial | correct | retrieval_miss | - |
| q043 | status | incorrect | partial | retrieval_miss | retrieval_miss |
| q044 | change | partial | correct | retrieval_miss | - |

## gpt-5.4-mini-2026-03-17

Correctness (all 50): correct 94.0% (47/50), partial 4.0% (2/50), incorrect 2.0% (1/50)

| type | n | correct | partial | incorrect |
|---|---|---|---|---|
| simple | 20 | 95.0% (19/20) | 0.0% (0/20) | 5.0% (1/20) |
| multi_part | 15 | 100.0% (15/15) | 0.0% (0/15) | 0.0% (0/15) |
| change | 7 | 85.7% (6/7) | 14.3% (1/7) | 0.0% (0/7) |
| status | 3 | 66.7% (2/3) | 33.3% (1/3) | 0.0% (0/3) |
| unanswerable | 5 | 100.0% (5/5) | 0.0% (0/5) | 0.0% (0/5) |

- Citation accuracy (answerable, expected paragraph known): 88.6% (39/44)
- Faithfulness (answers that make claims): supported 97.7% (43/44), partially supported 2.3% (1/44), unsupported 0.0% (0/44)
- Refusal accuracy (unanswerable, by meaning): 100.0% (5/5); exact refusal sentence: 100.0% (5/5)
- False-refusal rate (answerable): 2.2% (1/45)
- Non-correct answers: retrieval_miss 2, generation_error 1
- Cost: answering $0.0943 total ($0.00189/question); judging $0.0579 total ($0.00116/question)

Non-correct answers:

| id | type | verdict | facts | diagnosis | judge reason |
|---|---|---|---|---|---|
| q004 | change | partial | 2/3 | generation_error | The system answer correctly states the no-reverification rule and the condition of current/compliant CKYCR records. However, it omits the specific allocation of responsibility to the RE that last uploaded/updated the KYC record. |
| q020 | simple | incorrect | 0/3 | retrieval_miss | false refusal: the question is answerable from the documents |
| q043 | status | partial | 2/3 | retrieval_miss | The system answer clearly states the earlier Digital Lending Directions 2025 are withdrawn/not in force and replaced for NBFCs by the Credit Facilities Directions 2025. However, it does not explicitly mention that the digital lending rules are now in Chapter III. |

## 10 random judge verdicts (gpt-5.4-mini-2026-03-17, seed 42)

### q002 (simple) - correct

- **Question:** How often must periodic KYC updation be done for medium-risk and low-risk customers?
- **Key facts:** Medium-risk customers: at least once every eight years | Low-risk customers: at least once every ten years
- **System answer:** Periodic updation of KYC must be done once in every eight years for medium-risk customers and once in every 10 years for low-risk customers, from the date of opening of the account / last KYC updation. [S1]
- **Fact statuses:** present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly gives the required periodic KYC updation frequency for both medium-risk (8 years) and low-risk (10 years) customers, matching the key facts.

### q006 (status) - correct

- **Question:** Where are the digital lending rules for NBFCs located now?
- **Key facts:** The rules are in the RBI (NBFC – Credit Facilities) Directions 2025 | Specifically in Chapter III (Digital Lending)
- **System answer:** The digital lending rules for NBFCs are now in the Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities) Directions 2025, specifically Chapter III - Digital Lending. [S6]
- **Fact statuses:** present | present
- **Verdict:** correct
- **Reason:** The system answer correctly identifies both the document (NBFC – Credit Facilities Directions 2025) and the location within it (Chapter III: Digital Lending).

### q007 (status) - correct

- **Question:** Is the Master Direction on KYC 2016 still in force?
- **Key facts:** No, it is not in force | It was repealed on 28 November 2025 | For NBFCs it was replaced by the RBI (NBFC – KYC) Directions 2025
- **System answer:** No. The document status record says the Master Direction – Know Your Customer (KYC) Direction 2016 was **REPEALED on 2025-11-28**, replaced for NBFCs by the Reserve Bank of India (Non-Banking Financial Companies – Know Your Customer) Directions 2025, and is **NOT in force**. [S6]
- **Fact statuses:** present | present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly covers all three key facts: not in force, repealed on 28 Nov 2025, and NBFC replacement by the 2025 NBFC KYC Directions.

### q008 (change) - correct

- **Question:** What relief did the June 2025 KYC amendment give to low-risk individual customers?
- **Key facts:** Low-risk individual customers can continue to transact | KYC updation is allowed within one year of falling due or by 30 June 2026, whichever is later | Such accounts are subject to regular monitoring
- **System answer:** For an individual customer categorised as low-risk, the NBFC shall allow all transactions and ensure the updation of KYC within one year of its falling due for KYC or up to June 30, 2026, whichever is later; the NBFC shall subject such accounts to regular monitoring, and this also applies to low-risk individual customers for whom periodic updation of KYC has already fallen due. [S2]
- **Fact statuses:** present | present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly covers all three key relief points: continued transactions, the extended KYC updation deadline, and regular monitoring for low-risk individual customers.

### q009 (simple) - correct

- **Question:** What must the Key Facts Statement disclose additionally for digital loans?
- **Key facts:** The cooling-off / look-up period during which no penalty is charged on prepayment | Details of the LSP acting as recovery agent and authorised to approach the borrower
- **System answer:** For digital loans, the specific disclosures that may be furnished additionally include: the cooling off / look-up period, in terms of the RE's board approved policy, during which borrower shall not be charged any penalty on prepayment of loan; and details of LSP acting as recovery agent authorized to approach the borrower. [S2]
- **Fact statuses:** present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly includes both additional digital-loan disclosures: the cooling-off/look-up period with no prepayment penalty and the LSP details as recovery agent authorized to approach the borrower.

### q015 (simple) - correct

- **Question:** What type of entity must an LSP be to provide a DLG to an NBFC?
- **Key facts:** The LSP must be a company | Incorporated under the Companies Act, 2013
- **System answer:** The LSP providing DLG shall be incorporated as a company under the Companies Act, 2013. [S1]
- **Fact statuses:** present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly states that the LSP must be a company and that it must be incorporated under the Companies Act, 2013, matching both key facts.

### q016 (simple) - correct

- **Question:** Can an NBFC automatically increase a digital borrower's credit limit?
- **Key facts:** No automatic increase in the credit limit | Only on an explicit request from the borrower | The request must be evaluated and kept on record
- **System answer:** No. An NBFC shall ensure that there is no automatic increase in credit limit unless an explicit request is received, evaluated and kept on record from the borrower for such increase. [S1]
- **Fact statuses:** present | present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly states all three required conditions: no automatic increase, only with an explicit borrower request, and that the request is evaluated and kept on record.

### q018 (simple) - correct

- **Question:** Can an NBFC or its LSP collect or store a digital borrower's biometric data?
- **Key facts:** No, the NBFC and its LSP may not collect or store biometric data | Exception: unless allowed under existing statutory guidelines
- **System answer:** No. An NBFC shall ensure that no biometric data is stored / collected by the NBFC and LSP, unless allowed under extant statutory guidelines. [S1]
- **Fact statuses:** present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly states that biometric data cannot be stored/collected by the NBFC or its LSP, with the stated exception for cases allowed under extant statutory guidelines.

### q035 (multi_part) - correct

- **Question:** How often must LSPs with DLG arrangements publish their DLG disclosures, and what is the deadline?
- **Key facts:** Disclosures are published monthly | No later than 7 working days after the end of each month
- **System answer:** LSPs with whom NBFCs have a DLG arrangement shall publish the disclosure on a monthly basis. [S1] The disclosure for any given month must be provided no later than seven (7) working days following the conclusion of that month. [S1]
- **Fact statuses:** present | present
- **Verdict:** correct
- **Reason:** The system answer clearly specifies both the monthly frequency and the exact deadline (within 7 working days after month-end) for DLG disclosures.

### q041 (change) - correct

- **Question:** Who decides the cooling-off period for digital loans, and did this change from the Digital Lending Directions 2025 to the NBFC Credit Facilities Directions 2025?
- **Key facts:** Earlier: the lender's Board set it in the loan policy | Now: the NBFC sets it in its credit policy | The minimum of one day did not change
- **System answer:** Earlier: the cooling-off period was determined by the Board of the RE as laid down in their loan policy, subject to the period so determined not being less than one day. [S6] / Now: the cooling-off period shall be determined by the NBFC in terms of their credit policy, subject to the period so determined not being less than one day. [S1] Yes, it changed: from the Board of the RE in the loan policy [S6] to the NBFC in its credit policy [S1].
- **Fact statuses:** present | present | present
- **Verdict:** correct
- **Reason:** The system answer correctly states who determines the cooling-off period in both regimes (Board of RE vs NBFC) and preserves the unchanged minimum of one day. It also correctly indicates the change between the two directions.
