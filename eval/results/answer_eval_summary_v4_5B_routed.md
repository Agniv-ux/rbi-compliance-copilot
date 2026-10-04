# Answer eval summary

Questions: eval/questions.csv (50). System called as a user would: k=5, active documents only. Judge: gpt-5.4 (reasoning effort none, temperature 0, strict JSON schema); the correctness judge also sees the cited sources' text.

Notes: partial and incorrect answers are both "non-correct" and get a diagnosis: retrieval_miss when any expected paragraph is missing from the retrieved top 5, otherwise generation_error. Unanswerable questions count as correct when the answer refuses by meaning. Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv).

**Routing: MANUAL (not what a user gets) - change questions in compare mode; status questions with the document-status record as an extra source; everything else copied from the default run.**

## Before / after

| metric | answers_gpt-5.4-mini_v3_5A | answers_gpt-5.4-mini_v4_5B | this run (gpt-5.4-mini) |
|---|---|---|---|
| correct (all) | 86.0% (43/50) | 88.0% (44/50) | 94.0% (47/50) |
| partial (all) | 8.0% (4/50) | 6.0% (3/50) | 4.0% (2/50) |
| incorrect (all) | 6.0% (3/50) | 6.0% (3/50) | 2.0% (1/50) |
| correct: simple | 90.0% (18/20) | 95.0% (19/20) | 95.0% (19/20) |
| correct: multi_part | 100.0% (15/15) | 100.0% (15/15) | 100.0% (15/15) |
| correct: change | 57.1% (4/7) | 57.1% (4/7) | 71.4% (5/7) |
| correct: status | 33.3% (1/3) | 33.3% (1/3) | 100.0% (3/3) |
| correct: unanswerable | 100.0% (5/5) | 100.0% (5/5) | 100.0% (5/5) |
| correct (answerable) | 84.4% (38/45) | 86.7% (39/45) | 93.3% (42/45) |
| citation accuracy | 90.9% (40/44) | 90.9% (40/44) | 90.9% (40/44) |
| faithfulness: supported | 90.7% (39/43) | 95.3% (41/43) | 95.5% (42/44) |
| faithfulness: partially supported | 9.3% (4/43) | 4.7% (2/43) | 4.5% (2/44) |
| faithfulness: unsupported | 0.0% (0/43) | 0.0% (0/43) | 0.0% (0/44) |
| refusal accuracy (by meaning) | 100.0% (5/5) | 100.0% (5/5) | 100.0% (5/5) |
| refusal: exact sentence | 100.0% (5/5) | 100.0% (5/5) | 100.0% (5/5) |
| false-refusal rate | 4.4% (2/45) | 4.4% (2/45) | 2.2% (1/45) |
| retrieval_miss / generation_error | 6 / 1 | 6 / 0 | 1 / 2 |
| answer tokens in / out (total) | 89,070 / 2,812 | 92,170 / 2,826 | 107,824 / 2,985 |
| answering cost: total / per question | $0.0795 / $0.00159 | $0.0818 / $0.00164 | $0.0943 / $0.00189 |
| judging cost: total / per question | $0.2776 / $0.00555 | $0.2808 / $0.00562 | $0.2901 / $0.00580 |
| avg answer latency | 1.63s | 1.60s | 1.72s |

Questions whose verdict or diagnosis changed vs answers_gpt-5.4-mini_v3_5A:

| id | type | before | after | before diagnosis | after diagnosis |
|---|---|---|---|---|---|
| q004 | change | correct | partial | - | generation_error |
| q005 | simple | partial | correct | generation_error | - |
| q007 | status | incorrect | correct | retrieval_miss | - |
| q041 | change | partial | correct | retrieval_miss | - |
| q042 | change | partial | partial | retrieval_miss | generation_error |
| q043 | status | incorrect | correct | retrieval_miss | - |
| q044 | change | partial | correct | retrieval_miss | - |

Questions whose verdict or diagnosis changed vs answers_gpt-5.4-mini_v4_5B:

| id | type | before | after | before diagnosis | after diagnosis |
|---|---|---|---|---|---|
| q004 | change | correct | partial | - | generation_error |
| q007 | status | incorrect | correct | retrieval_miss | - |
| q041 | change | partial | correct | retrieval_miss | - |
| q042 | change | partial | partial | retrieval_miss | generation_error |
| q043 | status | incorrect | correct | retrieval_miss | - |
| q044 | change | partial | correct | retrieval_miss | - |

## gpt-5.4-mini

Correctness (all 50): correct 94.0% (47/50), partial 4.0% (2/50), incorrect 2.0% (1/50)

| type | n | correct | partial | incorrect |
|---|---|---|---|---|
| simple | 20 | 95.0% (19/20) | 0.0% (0/20) | 5.0% (1/20) |
| multi_part | 15 | 100.0% (15/15) | 0.0% (0/15) | 0.0% (0/15) |
| change | 7 | 71.4% (5/7) | 28.6% (2/7) | 0.0% (0/7) |
| status | 3 | 100.0% (3/3) | 0.0% (0/3) | 0.0% (0/3) |
| unanswerable | 5 | 100.0% (5/5) | 0.0% (0/5) | 0.0% (0/5) |

- Citation accuracy (answerable, expected paragraph known): 90.9% (40/44)
- Faithfulness (answers that make claims): supported 95.5% (42/44), partially supported 4.5% (2/44), unsupported 0.0% (0/44)
- Refusal accuracy (unanswerable, by meaning): 100.0% (5/5); exact refusal sentence: 100.0% (5/5)
- False-refusal rate (answerable): 2.2% (1/45)
- Non-correct answers: retrieval_miss 1, generation_error 2
- Cost: answering $0.0943 total ($0.00189/question); judging $0.2901 total ($0.00580/question)

Non-correct answers:

| id | type | verdict | diagnosis | judge reason |
|---|---|---|---|---|
| q004 | change | partial | generation_error | The answer correctly says re-verification is not required if the CKYCR record is current and compliant with the PML Act/Rules. However, it omits the expected fact that responsibility for verification lies with the entity that last uploaded or updated the CKYCR record. |
| q020 | simple | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q042 | change | partial | generation_error | The answer correctly states the old rule and the substance of the new rule, but it does not explicitly mention that the substitution was effective from 13 February 2026, and it names the IRACP Directions by full title rather than identifying them as the NBFC IRACP Directions tied to the change described. |

## 10 random judge verdicts (gpt-5.4-mini, seed 42)

### q002 (simple) - correct

- **Question:** How often must periodic KYC updation be done for medium-risk and low-risk customers?
- **Expected:** At least once every eight years for medium-risk and once every ten years for low-risk customers
- **System answer:** Periodic KYC updation must be done once in every eight years for medium-risk customers and once in every 10 years for low-risk customers, from the date of opening of the account / last KYC updation. [S1]
- **Verdict:** correct
- **Reason:** The system answer fully matches the expected frequencies for medium-risk and low-risk customers. Its added detail about counting from account opening or last KYC updation is supported by the cited source and does not conflict with the expected answer.

### q006 (status) - correct

- **Question:** Where are the digital lending rules for NBFCs located now?
- **Expected:** In Chapter III (Digital Lending) of the RBI (Non-Banking Financial Companies – Credit Facilities) Directions 2025
- **System answer:** The digital lending rules for NBFCs are now in the Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities) Directions 2025, specifically in Chapter III - Digital Lending. [S6][S1][S2][S3][S5]
- **Verdict:** correct
- **Reason:** The system answer matches the expected answer exactly in substance: the rules are located in Chapter III (Digital Lending) of the RBI (Non-Banking Financial Companies – Credit Facilities) Directions 2025. It does not add any contradictory or unsupported claim.

### q007 (status) - correct

- **Question:** Is the Master Direction on KYC 2016 still in force?
- **Expected:** No. Per RBI's Master Directions list (recorded in data/metadata.csv), it was repealed on 28 November 2025 and replaced by entity-wise KYC directions; for NBFCs it is the RBI (NBFC – KYC) Directions 2025.
- **System answer:** No. The document status record says the Master Direction – Know Your Customer (KYC) Direction 2016 was repealed on 2025-11-28 and is not in force, and was replaced for NBFCs by the Reserve Bank of India (Non-Banking Financial Companies – Know Your Customer) Directions 2025. [S6]
- **Verdict:** correct
- **Reason:** The answer correctly states that the 2016 KYC Master Direction is no longer in force, gives the repeal date of 2025-11-28, and identifies the NBFC replacement direction for 2025. It matches the cited status record and does not contradict the evidence.

### q008 (change) - correct

- **Question:** What relief did the June 2025 KYC amendment give to low-risk individual customers?
- **Expected:** Allowed transactions to continue and KYC updation within one year of it falling due or up to 30 June 2026 whichever is later with regular monitoring
- **System answer:** For an individual customer categorised as low-risk, the NBFC shall allow all transactions and ensure the updation of KYC within one year of its falling due for KYC or up to June 30, 2026, whichever is later; the NBFC shall subject such accounts to regular monitoring. This also applies to low-risk individual customers for whom periodic updation of KYC has already fallen due. [S2]
- **Verdict:** correct
- **Reason:** The system answer includes all key facts: it applies to low-risk individual customers, allows transactions to continue, permits KYC updation within one year of due date or up to 30 June 2026 whichever is later, and requires regular monitoring. The added note about already-overdue periodic updation is supported by the cited source.

### q009 (simple) - correct

- **Question:** What must the Key Facts Statement disclose additionally for digital loans?
- **Expected:** (i) The cooling-off/look-up period during which the borrower is not charged any penalty on prepayment of the loan; (ii) details of the LSP acting as recovery agent and authorised to approach the borrower.
- **System answer:** For digital loans, the Key Fact Statement may additionally furnish: the cooling off / look-up period, in terms of the RE’s board approved policy, during which the borrower shall not be charged any penalty on prepayment of loan; and details of the LSP acting as recovery agent authorized to approach the borrower. [S2]
- **Verdict:** correct
- **Reason:** The system answer includes both required additional disclosures for digital loans: the cooling-off/look-up period with no prepayment penalty, and the details of the LSP acting as recovery agent authorized to approach the borrower. It matches the expected answer and evidence.

### q015 (simple) - correct

- **Question:** What type of entity must an LSP be to provide a DLG to an NBFC?
- **Expected:** A company incorporated under the Companies Act, 2013.
- **System answer:** The LSP providing DLG shall be incorporated as a company under the Companies Act, 2013. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the expected answer and is directly supported by the cited regulation text.

### q016 (simple) - correct

- **Question:** Can an NBFC automatically increase a digital borrower's credit limit?
- **Expected:** No. Only if the borrower explicitly requests it, and the request is evaluated and kept on record.
- **System answer:** No. An NBFC shall ensure that there is no automatic increase in credit limit unless an explicit request is received, evaluated and kept on record from the borrower for such increase. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the expected answer and the cited regulation: no automatic increase is allowed unless the borrower explicitly requests it, and the request is evaluated and kept on record.

### q018 (simple) - correct

- **Question:** Can an NBFC or its LSP collect or store a digital borrower's biometric data?
- **Expected:** No, unless allowed under existing statutory guidelines.
- **System answer:** No. An NBFC shall ensure that no biometric data is stored / collected by the NBFC and LSP, unless allowed under extant statutory guidelines. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the expected answer and evidence: biometric data cannot be collected or stored by the NBFC or its LSP unless existing statutory guidelines permit it.

### q035 (multi_part) - correct

- **Question:** How often must LSPs with DLG arrangements publish their DLG disclosures, and what is the deadline?
- **Expected:** Monthly, no later than 7 working days after the end of each month.
- **System answer:** LSPs with whom NBFCs have a DLG arrangement shall publish the disclosure on a monthly basis. The disclosure for any given month must be provided no later than seven (7) working days following the conclusion of that month. [S1]
- **Verdict:** correct
- **Reason:** The system answer matches both key facts: the disclosures must be made monthly, and each month's disclosure is due no later than 7 working days after that month ends.

### q041 (change) - correct

- **Question:** Who decides the cooling-off period for digital loans, and did this change from the Digital Lending Directions 2025 to the NBFC Credit Facilities Directions 2025?
- **Expected:** Earlier the Board of the lender set it in the loan policy; now the NBFC sets it in its credit policy. The minimum of one day did not change.
- **System answer:** Earlier: the cooling-off period was determined by the Board of the RE as laid down in their loan policy, subject to the period so determined not being less than one day. [S6] Now: the cooling-off period shall be determined by the NBFC in terms of their credit policy, subject to the period so determined not being less than one day. [S1] This changed from the Board of the RE to the NBFC, while the minimum period of not being less than one day remained the same. [S6][S1]
- **Verdict:** correct
- **Reason:** The answer captures both key changes accurately: earlier the Board of the RE decided it under the loan policy, and now the NBFC decides it under its credit policy. It also correctly states that the minimum cooling-off period remained at not less than one day.
