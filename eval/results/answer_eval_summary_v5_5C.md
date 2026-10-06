# Answer eval summary

Questions: eval/questions.csv (50). System called as a user would: k=5, active documents only, retrieval method **vector**. Answers: gpt-5.4-mini-2026-03-17 (temperature 0). Judge: openai gpt-5.4-nano-2026-03-17 (lowest thinking level, temperature 0, structured JSON; majority of 3 call(s) for correctness, 1 for faithfulness); correctness = key facts present / missing / contradicted, verdict computed in code.

**Judge changed in Step 5C**: Step 5B (v4_5B) was graded by gpt-5.4 with a holistic verdict; this run is graded by openai gpt-5.4-nano-2026-03-17 checking key facts. Scores are therefore not directly comparable to v4_5B: a change can come from the system or from the judge.

Notes: partial and incorrect answers are both "non-correct" and get a diagnosis: retrieval_miss when any expected paragraph is missing from the retrieved top 5, otherwise generation_error. Unanswerable questions count as correct when the answer refuses by meaning. Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv). Costs count cached calls at their original cost.

**Routing: none - every question in default current mode, as a user would ask it.**

## Before / after

| metric | answers_gpt-5.4-mini_v4_5B | this run (gpt-5.4-mini-2026-03-17) |
|---|---|---|
| correct (all) | 88.0% (44/50) | 86.0% (43/50) |
| partial (all) | 6.0% (3/50) | 8.0% (4/50) |
| incorrect (all) | 6.0% (3/50) | 6.0% (3/50) |
| correct: simple | 95.0% (19/20) | 95.0% (19/20) |
| correct: multi_part | 100.0% (15/15) | 100.0% (15/15) |
| correct: change | 57.1% (4/7) | 42.9% (3/7) |
| correct: status | 33.3% (1/3) | 33.3% (1/3) |
| correct: unanswerable | 100.0% (5/5) | 100.0% (5/5) |
| correct (answerable) | 86.7% (39/45) | 84.4% (38/45) |
| citation accuracy | 90.9% (40/44) | 90.9% (40/44) |
| faithfulness: supported | 95.3% (41/43) | 93.0% (40/43) |
| faithfulness: partially supported | 4.7% (2/43) | 4.7% (2/43) |
| faithfulness: unsupported | 0.0% (0/43) | 2.3% (1/43) |
| refusal accuracy (by meaning) | 100.0% (5/5) | 100.0% (5/5) |
| refusal: exact sentence | 100.0% (5/5) | 100.0% (5/5) |
| false-refusal rate | 4.4% (2/45) | 4.4% (2/45) |
| retrieval_miss / generation_error | 6 / 0 | 7 / 0 |
| judge agreement (share of votes = majority) | n/a | 99.8% |
| answer tokens in / out (total) | 92,170 / 2,826 | 92,170 / 2,722 |
| answering cost: total / per question | $0.0818 / $0.00164 | $0.0814 / $0.00163 |
| judging cost: total / per question | $0.2808 / $0.00562 | $0.0572 / $0.00114 |
| avg answer latency | 1.60s | 1.67s |

Questions whose verdict or diagnosis changed vs answers_gpt-5.4-mini_v4_5B:

| id | type | before | after | before diagnosis | after diagnosis |
|---|---|---|---|---|---|
| q004 | change | correct | partial | - | retrieval_miss |

## gpt-5.4-mini-2026-03-17

Correctness (all 50): correct 86.0% (43/50), partial 8.0% (4/50), incorrect 6.0% (3/50)

| type | n | correct | partial | incorrect |
|---|---|---|---|---|
| simple | 20 | 95.0% (19/20) | 0.0% (0/20) | 5.0% (1/20) |
| multi_part | 15 | 100.0% (15/15) | 0.0% (0/15) | 0.0% (0/15) |
| change | 7 | 42.9% (3/7) | 57.1% (4/7) | 0.0% (0/7) |
| status | 3 | 33.3% (1/3) | 0.0% (0/3) | 66.7% (2/3) |
| unanswerable | 5 | 100.0% (5/5) | 0.0% (0/5) | 0.0% (0/5) |

- Citation accuracy (answerable, expected paragraph known): 90.9% (40/44)
- Faithfulness (answers that make claims): supported 93.0% (40/43), partially supported 4.7% (2/43), unsupported 2.3% (1/43)
- Refusal accuracy (unanswerable, by meaning): 100.0% (5/5); exact refusal sentence: 100.0% (5/5)
- False-refusal rate (answerable): 4.4% (2/45)
- Non-correct answers: retrieval_miss 7, generation_error 0
- Cost: answering $0.0814 total ($0.00163/question); judging $0.0572 total ($0.00114/question)

Non-correct answers:

| id | type | verdict | facts | diagnosis | judge reason |
|---|---|---|---|---|---|
| q004 | change | partial | 2/3 | retrieval_miss | The system answer correctly states the no-reverification rule and the condition about current/compliant CKYCR records. However, it omits the key point that the last uploader/updater of the CKYCR record is responsible for verification. |
| q007 | status | incorrect | 0/3 | retrieval_miss | false refusal: the question is answerable from the documents |
| q020 | simple | incorrect | 0/3 | retrieval_miss | false refusal: the question is answerable from the documents |
| q041 | change | partial | 2/3 | retrieval_miss | The system answer clearly states the current decision-maker (NBFC via credit policy) and the one-day minimum. It does not state the earlier rule about the lender’s Board, and it does not confirm whether the change occurred between the two specified directions. |
| q042 | change | partial | 2/3 | retrieval_miss | The system answer clearly states the current rule for asset classification/provisioning under the NBFC IRACP Directions and includes DLG-specific consequences. However, it does not state the earlier position about lender responsibility for NPA recognition irrespective of DLG cover. |
| q043 | status | incorrect | 0/3 | retrieval_miss | The system answer explicitly states that the provided documents do not state whether earlier credit facility directions are still in force, and it does not assert the specific repeal/Chapter III points required by the key facts. |
| q044 | change | partial | 1/2 | retrieval_miss | The system answer correctly gives the deadline as not later than 1 January 2026. However, it does not confirm that this deadline is unchanged from the June 2025 amendment; it instead indicates the sources do not state whether it changed. |

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
- **System answer:** The digital lending rules for NBFCs are located in the Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities) Directions 2025, Chapter III - Digital Lending. [S1][S2][S3][S5]
- **Fact statuses:** present | present
- **Verdict:** correct
- **Reason:** The system answer correctly identifies both the document (RBI NBFC – Credit Facilities Directions 2025) and the location within it (Chapter III: Digital Lending).

### q007 (status) - incorrect

- **Question:** Is the Master Direction on KYC 2016 still in force?
- **Key facts:** No, it is not in force | It was repealed on 28 November 2025 | For NBFCs it was replaced by the RBI (NBFC – KYC) Directions 2025
- **System answer:** Not covered in the provided RBI documents.
- **Fact statuses:** -
- **Verdict:** incorrect
- **Reason:** false refusal: the question is answerable from the documents

### q008 (change) - correct

- **Question:** What relief did the June 2025 KYC amendment give to low-risk individual customers?
- **Key facts:** Low-risk individual customers can continue to transact | KYC updation is allowed within one year of falling due or by 30 June 2026, whichever is later | Such accounts are subject to regular monitoring
- **System answer:** For an individual customer categorised as low-risk, the NBFC shall allow all transactions and ensure the updation of KYC within one year of its falling due for KYC or up to June 30, 2026, whichever is later. This also applies to low-risk individual customers for whom periodic updation of KYC has already fallen due, and the accounts of such customers shall be subject to regular monitoring. [S2]
- **Fact statuses:** present | present | present
- **Verdict:** correct
- **Reason:** The system answer explicitly covers all three required relief points: continued transactions, the one-year/30 June 2026 deadline for KYC updation (whichever later), and regular monitoring for low-risk individual customers.

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

### q041 (change) - partial

- **Question:** Who decides the cooling-off period for digital loans, and did this change from the Digital Lending Directions 2025 to the NBFC Credit Facilities Directions 2025?
- **Key facts:** Earlier: the lender's Board set it in the loan policy | Now: the NBFC sets it in its credit policy | The minimum of one day did not change
- **System answer:** The cooling-off period is determined by the NBFC in terms of its credit policy, subject to the period so determined not being less than one day. [S1] The provided sources do not state any earlier Digital Lending Directions 2025 rule for comparison, so whether this changed is not covered in the provided RBI documents.
- **Fact statuses:** missing | present | present
- **Verdict:** partial
- **Reason:** The system answer clearly states the current decision-maker (NBFC via credit policy) and the one-day minimum. It does not state the earlier rule about the lender’s Board, and it does not confirm whether the change occurred between the two specified directions.
