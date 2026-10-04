# Answer eval summary

Questions: eval/questions.csv (50). System called as a user would: k=5, active documents only. Judge: gpt-5.4 (reasoning effort none, temperature 0, strict JSON schema); the correctness judge also sees the cited sources' text.

Notes: partial and incorrect answers are both "non-correct" and get a diagnosis: retrieval_miss when any expected paragraph is missing from the retrieved top 5, otherwise generation_error. Unanswerable questions count as correct when the answer refuses by meaning. Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv).

## Before / after

| metric | before (answers_gpt-5.4-mini) | after (gpt-5.4-mini) |
|---|---|---|
| correct (all) | 84.0% (42/50) | 86.0% (43/50) |
| partial (all) | 10.0% (5/50) | 8.0% (4/50) |
| incorrect (all) | 6.0% (3/50) | 6.0% (3/50) |
| correct: simple | 95.0% (19/20) | 90.0% (18/20) |
| correct: multi_part | 100.0% (15/15) | 100.0% (15/15) |
| correct: change | 42.9% (3/7) | 57.1% (4/7) |
| correct: status | 0.0% (0/3) | 33.3% (1/3) |
| correct: unanswerable | 100.0% (5/5) | 100.0% (5/5) |
| correct (answerable) | 82.2% (37/45) | 84.4% (38/45) |
| citation accuracy | 90.9% (40/44) | 90.9% (40/44) |
| faithfulness: supported | 92.9% (39/42) | 90.7% (39/43) |
| faithfulness: partially supported | 7.1% (3/42) | 9.3% (4/43) |
| faithfulness: unsupported | 0.0% (0/42) | 0.0% (0/43) |
| refusal accuracy (by meaning) | 100.0% (5/5) | 100.0% (5/5) |
| refusal: exact sentence | 100.0% (5/5) | 100.0% (5/5) |
| false-refusal rate | 6.7% (3/45) | 4.4% (2/45) |
| retrieval_miss / generation_error | 3 / 5 | 6 / 1 |
| answer tokens in / out (total) | 84,999 / 2,660 | 89,070 / 2,812 |
| answering cost: total / per question | $0.0757 / $0.00151 | $0.0795 / $0.00159 |
| judging cost: total / per question | $0.2132 / $0.00426 | $0.2776 / $0.00555 |
| avg answer latency | 1.53s | 1.63s |

Questions whose verdict or diagnosis changed:

| id | type | before | after | before diagnosis | after diagnosis |
|---|---|---|---|---|---|
| q004 | change | partial | correct | generation_error | - |
| q005 | simple | correct | partial | - | generation_error |
| q006 | status | partial | correct | generation_error | - |
| q041 | change | partial | partial | generation_error | retrieval_miss |
| q042 | change | partial | partial | generation_error | retrieval_miss |
| q044 | change | partial | partial | generation_error | retrieval_miss |

## gpt-5.4-mini

Correctness (all 50): correct 86.0% (43/50), partial 8.0% (4/50), incorrect 6.0% (3/50)

| type | n | correct | partial | incorrect |
|---|---|---|---|---|
| simple | 20 | 90.0% (18/20) | 5.0% (1/20) | 5.0% (1/20) |
| multi_part | 15 | 100.0% (15/15) | 0.0% (0/15) | 0.0% (0/15) |
| change | 7 | 57.1% (4/7) | 42.9% (3/7) | 0.0% (0/7) |
| status | 3 | 33.3% (1/3) | 0.0% (0/3) | 66.7% (2/3) |
| unanswerable | 5 | 100.0% (5/5) | 0.0% (0/5) | 0.0% (0/5) |

- Citation accuracy (answerable, expected paragraph known): 90.9% (40/44)
- Faithfulness (answers that make claims): supported 90.7% (39/43), partially supported 9.3% (4/43), unsupported 0.0% (0/43)
- Refusal accuracy (unanswerable, by meaning): 100.0% (5/5); exact refusal sentence: 100.0% (5/5)
- False-refusal rate (answerable): 4.4% (2/45)
- Non-correct answers: retrieval_miss 6, generation_error 1
- Cost: answering $0.0795 total ($0.00159/question); judging $0.2776 total ($0.00555/question)

Non-correct answers:

| id | type | verdict | diagnosis | judge reason |
|---|---|---|---|---|
| q005 | simple | partial | generation_error | The answer correctly states the minimum cooling-off period of not less than one day. However, it omits the key qualifier that the NBFC sets the actual period under its credit policy. |
| q007 | status | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q020 | simple | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q041 | change | partial | retrieval_miss | The answer correctly states the current NBFC rule and the one-day minimum, but it does not convey the comparison to the earlier Digital Lending Directions 2025 that the expected answer requires. |
| q042 | change | partial | retrieval_miss | The answer correctly states the new rule that asset classification/provisioning is governed by the RBI IRACP Directions, but it does not explain the earlier rule or clearly mention that this was a substitution effective 13 February 2026. |
| q043 | status | incorrect | retrieval_miss | The expected answer is 'No' because the 2025 Directions repealed the earlier NBFC credit facility directions and absorbed digital lending rules into Chapter III. The system answer discusses applicability and current digital lending provisions but omits the repeal and therefore fails the core question. |
| q044 | change | partial | retrieval_miss | The answer correctly states the implementation deadline of January 1, 2026. However, it does not convey the expected fact that this deadline remained unchanged from the June 2025 amendment to the 2016 direction, instead saying the excerpts do not show that comparison. |

## 10 random judge verdicts (gpt-5.4-mini, seed 42)

### q002 (simple) - correct

- **Question:** How often must periodic KYC updation be done for medium-risk and low-risk customers?
- **Expected:** At least once every eight years for medium-risk and once every ten years for low-risk customers
- **System answer:** Periodic KYC updation must be done once in every eight years for medium-risk customers and once in every 10 years for low-risk customers, from the date of opening of the account / last KYC updation. [S1]
- **Verdict:** correct
- **Reason:** The system answer states the required frequencies exactly for both medium-risk and low-risk customers, and the added detail about counting from account opening or last KYC updation is supported by the cited source.

### q006 (status) - correct

- **Question:** Where are the digital lending rules for NBFCs located now?
- **Expected:** In Chapter III (Digital Lending) of the RBI (Non-Banking Financial Companies – Credit Facilities) Directions 2025
- **System answer:** The digital lending rules for NBFCs are located in the **Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities) Directions 2025**, specifically **Chapter III – Digital Lending**. [S1][S2][S3][S5]
- **Verdict:** correct
- **Reason:** The system answer matches the expected answer exactly: it identifies the RBI (Non-Banking Financial Companies – Credit Facilities) Directions 2025 and specifies Chapter III – Digital Lending. It does not add any contradictory or unsupported claims.

### q007 (status) - incorrect

- **Question:** Is the Master Direction on KYC 2016 still in force?
- **Expected:** No. Per RBI's Master Directions list (recorded in data/metadata.csv), it was repealed on 28 November 2025 and replaced by entity-wise KYC directions; for NBFCs it is the RBI (NBFC – KYC) Directions 2025.
- **System answer:** Not covered in the provided RBI documents.
- **Verdict:** incorrect (missing: No. Per RBI's Master Directions list (recorded in data/metadata.csv), it was repealed on 28 November 2025 and replaced by entity-wise KYC directions; for NBFCs it is the RBI (NBFC – KYC) Directions 2025.)
- **Reason:** false refusal: the question is answerable from the documents

### q008 (change) - correct

- **Question:** What relief did the June 2025 KYC amendment give to low-risk individual customers?
- **Expected:** Allowed transactions to continue and KYC updation within one year of it falling due or up to 30 June 2026 whichever is later with regular monitoring
- **System answer:** For an individual customer categorised as low-risk, the NBFC shall allow all transactions and ensure the updation of KYC within one year of its falling due for KYC or up to June 30, 2026, whichever is later. [S2] This relief also applies to low-risk individual customers for whom periodic updation of KYC has already fallen due, and such accounts shall be subject to regular monitoring. [S2]
- **Verdict:** correct
- **Reason:** The system answer includes all key facts: transactions may continue, KYC can be updated within one year of falling due or by 30 June 2026 whichever is later, and the accounts must be subject to regular monitoring. It also correctly notes that this applies to low-risk individual customers whose periodic updation has already fallen due.

### q009 (simple) - correct

- **Question:** What must the Key Facts Statement disclose additionally for digital loans?
- **Expected:** (i) The cooling-off/look-up period during which the borrower is not charged any penalty on prepayment of the loan; (ii) details of the LSP acting as recovery agent and authorised to approach the borrower.
- **System answer:** For digital loans, the Key Fact Statement may additionally furnish: cooling off / look-up period, in terms of the RE's board approved policy, during which borrower shall not be charged any penalty on prepayment of loan; and details of LSP acting as recovery agent authorized to approach the borrower. [S2]
- **Verdict:** correct
- **Reason:** The system answer includes both required additional disclosures for digital loans: the cooling-off/look-up period with no prepayment penalty, and the details of the LSP acting as recovery agent authorized to approach the borrower. It matches the expected answer and evidence in substance.

### q015 (simple) - correct

- **Question:** What type of entity must an LSP be to provide a DLG to an NBFC?
- **Expected:** A company incorporated under the Companies Act, 2013.
- **System answer:** The LSP providing DLG shall be incorporated as a company under the Companies Act, 2013. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the expected answer and the cited regulation: the LSP must be incorporated as a company under the Companies Act, 2013.

### q016 (simple) - correct

- **Question:** Can an NBFC automatically increase a digital borrower's credit limit?
- **Expected:** No. Only if the borrower explicitly requests it, and the request is evaluated and kept on record.
- **System answer:** No. An NBFC shall ensure that there is no automatic increase in credit limit unless an explicit request is received, evaluated and kept on record from the borrower for such increase. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the regulatory requirement: no automatic increase is allowed unless the borrower explicitly requests it and the request is evaluated and kept on record.

### q018 (simple) - correct

- **Question:** Can an NBFC or its LSP collect or store a digital borrower's biometric data?
- **Expected:** No, unless allowed under existing statutory guidelines.
- **System answer:** No. An NBFC shall ensure that no biometric data is stored / collected by the NBFC and LSP, unless allowed under extant statutory guidelines. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the expected answer and the cited regulation: biometric data cannot be collected or stored by the NBFC or its LSP unless existing statutory guidelines permit it.

### q035 (multi_part) - correct

- **Question:** How often must LSPs with DLG arrangements publish their DLG disclosures, and what is the deadline?
- **Expected:** Monthly, no later than 7 working days after the end of each month.
- **System answer:** LSPs with whom NBFCs have a DLG arrangement shall publish the disclosure on a monthly basis, and the disclosure for any given month must be provided no later than seven (7) working days following the conclusion of that month. [S1]
- **Verdict:** correct
- **Reason:** The system answer matches the expected answer exactly in substance: disclosures must be made monthly and no later than seven working days after the end of each month.

### q041 (change) - partial

- **Question:** Who decides the cooling-off period for digital loans, and did this change from the Digital Lending Directions 2025 to the NBFC Credit Facilities Directions 2025?
- **Expected:** Earlier the Board of the lender set it in the loan policy; now the NBFC sets it in its credit policy. The minimum of one day did not change.
- **System answer:** The cooling-off period is determined by the NBFC in terms of its credit policy, and it must not be less than one day. [S1] This does not state any change from the Digital Lending Directions 2025 to the NBFC Credit Facilities Directions 2025, because only the NBFC Credit Facilities Directions 2025 excerpt is provided here. [S1]
- **Verdict:** partial (missing: Earlier, under the Digital Lending Directions 2025, the cooling-off period was determined by the Board of the lender/RE as laid down in its loan policy.; There was a change in who decides it: from the Board in the loan policy to the NBFC in its credit policy.; The minimum period of one day did not change across the two directions.)
- **Reason:** The answer correctly states the current NBFC rule and the one-day minimum, but it does not convey the comparison to the earlier Digital Lending Directions 2025 that the expected answer requires.
