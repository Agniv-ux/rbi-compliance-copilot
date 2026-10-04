# Answer eval summary

Questions: eval/questions.csv (50). System called as a user would: k=5, active documents only. Judge: gpt-5.4 (reasoning effort none, temperature 0, strict JSON schema).

Notes: partial and incorrect answers are both "non-correct" and get a diagnosis. Change/status questions whose expected source is a repealed or superseded document cannot retrieve it with active-only search, so they show up as retrieval_miss by design. Citation accuracy excludes rows whose expected source is not a paragraph (q007: metadata.csv).

## mini vs nano

| metric | gpt-5.4-mini | gpt-5.4-nano |
|---|---|---|
| correct (all) | 84.0% (42/50) | 76.0% (38/50) |
| partial (all) | 10.0% (5/50) | 10.0% (5/50) |
| incorrect (all) | 6.0% (3/50) | 14.0% (7/50) |
| correct (answerable) | 82.2% (37/45) | 75.6% (34/45) |
| citation accuracy | 90.9% (40/44) | 84.1% (37/44) |
| faithfulness: supported | 92.9% (39/42) | 92.9% (39/42) |
| refusal accuracy | 100.0% (5/5) | 80.0% (4/5) |
| false-refusal rate | 6.7% (3/45) | 8.9% (4/45) |
| retrieval_miss / generation_error | 3 / 5 | 4 / 8 |
| answer tokens in / out (total) | 84,999 / 2,660 | 84,999 / 2,852 |
| answering cost: total / per question | $0.0757 / $0.00151 | $0.0206 / $0.00041 |
| judging cost: total / per question | $0.2132 / $0.00426 | $0.2132 / $0.00426 |
| avg answer latency | 1.53s | 1.52s |

## gpt-5.4-mini

Correctness (all 50): correct 84.0% (42/50), partial 10.0% (5/50), incorrect 6.0% (3/50)

| type | n | correct | partial | incorrect |
|---|---|---|---|---|
| simple | 20 | 95.0% (19/20) | 0.0% (0/20) | 5.0% (1/20) |
| multi_part | 15 | 100.0% (15/15) | 0.0% (0/15) | 0.0% (0/15) |
| change | 7 | 42.9% (3/7) | 57.1% (4/7) | 0.0% (0/7) |
| status | 3 | 0.0% (0/3) | 33.3% (1/3) | 66.7% (2/3) |
| unanswerable | 5 | 100.0% (5/5) | 0.0% (0/5) | 0.0% (0/5) |

- Citation accuracy (answerable, expected paragraph known): 90.9% (40/44)
- Faithfulness (answers that make claims): supported 92.9% (39/42), partially supported 7.1% (3/42), unsupported 0.0% (0/42)
- Refusal accuracy (unanswerable): 100.0% (5/5)
- False-refusal rate (answerable): 6.7% (3/45)
- Non-correct answers: retrieval_miss 3, generation_error 5
- Cost: answering $0.0757 total ($0.00151/question); judging $0.2132 total ($0.00426/question)

Non-correct answers:

| id | type | verdict | diagnosis | judge reason |
|---|---|---|---|---|
| q004 | change | partial | generation_error | The system answer correctly states that re-verification is not required if the CKYCR record is current and compliant with the PML Act/Rules. However, it omits the expected fact that responsibility for verification lies with the entity that last uploaded or updated the record. |
| q006 | status | partial | generation_error | The system correctly identifies the RBI (Non-Banking Financial Companies – Credit Facilities) Directions 2025, but it does not state the key location detail that these rules are in Chapter III (Digital Lending). The added paragraph references are not contradictory. |
| q007 | status | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q020 | simple | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q041 | change | partial | generation_error | The system answer correctly states the current rule that the NBFC sets the cooling-off period in its credit policy with a minimum of one day. However, it does not acknowledge the earlier position or the change between the two directions, which are key parts of the expected answer. |
| q042 | change | partial | generation_error | The system answer correctly states the new rule now points asset classification/provisioning to the NBFC IRACP Directions, but it omits the prior rule and the effective-date/substitution aspect of the change. |
| q043 | status | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q044 | change | partial | generation_error | The system answer correctly gives the implementation deadline as 1 January 2026, but it does not convey the expected fact that this deadline remained unchanged from the June 2025 amendment. |

## gpt-5.4-nano

Correctness (all 50): correct 76.0% (38/50), partial 10.0% (5/50), incorrect 14.0% (7/50)

| type | n | correct | partial | incorrect |
|---|---|---|---|---|
| simple | 20 | 85.0% (17/20) | 5.0% (1/20) | 10.0% (2/20) |
| multi_part | 15 | 93.3% (14/15) | 0.0% (0/15) | 6.7% (1/15) |
| change | 7 | 42.9% (3/7) | 42.9% (3/7) | 14.3% (1/7) |
| status | 3 | 0.0% (0/3) | 33.3% (1/3) | 66.7% (2/3) |
| unanswerable | 5 | 80.0% (4/5) | 0.0% (0/5) | 20.0% (1/5) |

- Citation accuracy (answerable, expected paragraph known): 84.1% (37/44)
- Faithfulness (answers that make claims): supported 92.9% (39/42), partially supported 7.1% (3/42), unsupported 0.0% (0/42)
- Refusal accuracy (unanswerable): 80.0% (4/5)
- False-refusal rate (answerable): 8.9% (4/45)
- Non-correct answers: retrieval_miss 4, generation_error 8
- Cost: answering $0.0206 total ($0.00041/question); judging $0.2132 total ($0.00426/question)

Non-correct answers:

| id | type | verdict | diagnosis | judge reason |
|---|---|---|---|---|
| q005 | simple | partial | generation_error | The system answer correctly states the minimum period of not less than one day, but it omits that the NBFC sets the exact cooling-off period under its credit policy. |
| q006 | status | partial | generation_error | The answer correctly identifies the 2025 RBI Directions but omits the specific location within them: Chapter III titled Digital Lending. The extra section examples do not contradict the expected answer. |
| q007 | status | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q008 | change | partial | retrieval_miss | The system answer correctly states that transactions may continue and that KYC can be updated within one year of falling due or by 30 June 2026, whichever is later. However, it omits the condition that such accounts must be subject to regular monitoring. |
| q009 | simple | incorrect | generation_error | The evidence explicitly lists two additional KFS disclosures for digital loans, but the system answer denies that the documents cover them and omits both required facts. |
| q020 | simple | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q034 | multi_part | incorrect | generation_error | The system answer includes all required facts about certification and contents, but it adds a requirement about past default rates that is not supported by the evidence and changes the stated regulatory requirement. |
| q041 | change | partial | generation_error | The system correctly states the current rule that the NBFC sets the cooling-off period in its credit policy with a minimum of one day. However, it fails to identify the earlier rule and the fact that the minimum one-day requirement remained unchanged, and it incorrectly claims the comparison is not covered. |
| q042 | change | incorrect | generation_error | false refusal: the question is answerable from the documents |
| q043 | status | incorrect | retrieval_miss | false refusal: the question is answerable from the documents |
| q044 | change | partial | generation_error | The system answer correctly states the implementation deadline of 1 January 2026. However, it does not convey the expected fact that this deadline remained unchanged from the June 2025 amendment, instead saying the change cannot be determined. |
| q049 | unanswerable | incorrect | generation_error | should have refused (exact refusal sentence) |

## 10 random judge verdicts (gpt-5.4-mini, seed 42)

### q002 (simple) - correct

- **Question:** How often must periodic KYC updation be done for medium-risk and low-risk customers?
- **Expected:** At least once every eight years for medium-risk and once every ten years for low-risk customers
- **System answer:** Periodic KYC updation must be done at least once in every eight years for medium-risk customers and at least once in every 10 years for low-risk customers from the date of opening of the account / last KYC updation. [S1]
- **Verdict:** correct
- **Reason:** The system answer includes both required frequencies: at least once every eight years for medium-risk customers and at least once every ten years for low-risk customers. The added detail about counting from account opening or last KYC updation does not contradict the expected answer.

### q006 (status) - partial

- **Question:** Where are the digital lending rules for NBFCs located now?
- **Expected:** In Chapter III (Digital Lending) of the RBI (Non-Banking Financial Companies – Credit Facilities) Directions 2025
- **System answer:** The digital lending rules for NBFCs are located in the Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities) Directions 2025, especially paras 5, 6, 7, 9, and 16. [S1][S2][S3][S4][S5]
- **Verdict:** partial (missing: The rules are specifically located in Chapter III, titled 'Digital Lending'.)
- **Reason:** The system correctly identifies the RBI (Non-Banking Financial Companies – Credit Facilities) Directions 2025, but it does not state the key location detail that these rules are in Chapter III (Digital Lending). The added paragraph references are not contradictory.

### q007 (status) - incorrect

- **Question:** Is the Master Direction on KYC 2016 still in force?
- **Expected:** No. Per RBI's Master Directions list (recorded in data/metadata.csv), it was repealed on 28 November 2025 and replaced by entity-wise KYC directions; for NBFCs it is the RBI (NBFC – KYC) Directions 2025.
- **System answer:** Not covered in the provided RBI documents.
- **Verdict:** incorrect (missing: No. Per RBI's Master Directions list (recorded in data/metadata.csv), it was repealed on 28 November 2025 and replaced by entity-wise KYC directions; for NBFCs it is the RBI (NBFC – KYC) Directions 2025.)
- **Reason:** false refusal: the question is answerable from the documents

### q008 (change) - correct

- **Question:** What relief did the June 2025 KYC amendment give to low-risk individual customers?
- **Expected:** Allowed transactions to continue and KYC updation within one year of it falling due or up to 30 June 2026 whichever is later with regular monitoring
- **System answer:** In respect of an individual customer who is categorised as low-risk, the NBFC shall allow all transactions and ensure the updation of KYC within one year of its falling due for KYC or up to June 30, 2026, whichever is later. [S2] The NBFC shall subject accounts of such customers to regular monitoring, and this also applies to low-risk individual customers for whom periodic updation of KYC has already fallen due. [S2]
- **Verdict:** correct
- **Reason:** The system answer includes all key facts: low-risk individual customers may continue transactions, KYC can be updated within one year of falling due or by 30 June 2026 whichever is later, and the accounts must be subject to regular monitoring.

### q009 (simple) - correct

- **Question:** What must the Key Facts Statement disclose additionally for digital loans?
- **Expected:** (i) The cooling-off/look-up period during which the borrower is not charged any penalty on prepayment of the loan; (ii) details of the LSP acting as recovery agent and authorised to approach the borrower.
- **System answer:** For digital loans, the additional specific disclosures may include the cooling off / look-up period, in terms of the RE’s board approved policy, during which borrower shall not be charged any penalty on prepayment of loan, and the details of LSP acting as recovery authorized to approach the borrower agent. [S2]
- **Verdict:** correct
- **Reason:** The system answer includes both required additional disclosures for digital loans: the cooling-off/look-up period with no prepayment penalty, and the details of the LSP acting as recovery agent authorized to approach the borrower. There is no contradiction with the expected answer or evidence.

### q015 (simple) - correct

- **Question:** What type of entity must an LSP be to provide a DLG to an NBFC?
- **Expected:** A company incorporated under the Companies Act, 2013.
- **System answer:** The LSP providing DLG shall be incorporated as a company under the Companies Act, 2013. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the expected answer and includes the required entity type and legal basis.

### q016 (simple) - correct

- **Question:** Can an NBFC automatically increase a digital borrower's credit limit?
- **Expected:** No. Only if the borrower explicitly requests it, and the request is evaluated and kept on record.
- **System answer:** No. An NBFC shall ensure that there is no automatic increase in credit limit unless an explicit request is received, evaluated and kept on record from the borrower for such increase. [S1]
- **Verdict:** correct
- **Reason:** The system answer matches the expected answer exactly: no automatic increase is allowed unless the borrower explicitly requests it, and the request is evaluated and kept on record.

### q018 (simple) - correct

- **Question:** Can an NBFC or its LSP collect or store a digital borrower's biometric data?
- **Expected:** No, unless allowed under existing statutory guidelines.
- **System answer:** An NBFC shall ensure that no biometric data is stored / collected by the NBFC and LSP, unless allowed under extant statutory guidelines. [S1]
- **Verdict:** correct
- **Reason:** The system answer exactly matches the regulatory requirement: biometric data cannot be collected or stored by the NBFC or its LSP unless existing statutory guidelines permit it.

### q035 (multi_part) - correct

- **Question:** How often must LSPs with DLG arrangements publish their DLG disclosures, and what is the deadline?
- **Expected:** Monthly, no later than 7 working days after the end of each month.
- **System answer:** LSPs with DLG arrangements must publish the disclosure on a monthly basis. [S1] The disclosure for any given month must be provided no later than seven (7) working days following the conclusion of that month. [S1]
- **Verdict:** correct
- **Reason:** The system answer includes both key facts exactly: the disclosures must be made monthly, and each month's disclosure is due no later than 7 working days after that month ends.

### q041 (change) - partial

- **Question:** Who decides the cooling-off period for digital loans, and did this change from the Digital Lending Directions 2025 to the NBFC Credit Facilities Directions 2025?
- **Expected:** Earlier the Board of the lender set it in the loan policy; now the NBFC sets it in its credit policy. The minimum of one day did not change.
- **System answer:** The cooling-off period for a digital loan is determined by the NBFC in terms of its credit policy, subject to the period so determined not being less than one day. [S1] The provided documents do not include the Digital Lending Directions 2025 text, so any change from that version to the NBFC Credit Facilities Directions 2025 is not covered in the provided RBI documents.
- **Verdict:** partial (missing: Earlier, the Board of the lender/RE determined the cooling-off period in the loan policy.; This changed from Board of the lender/RE in the earlier Digital Lending Directions 2025 to NBFC in its credit policy under the NBFC Credit Facilities Directions 2025.; The minimum of one day did not change across the two versions.)
- **Reason:** The system answer correctly states the current rule that the NBFC sets the cooling-off period in its credit policy with a minimum of one day. However, it does not acknowledge the earlier position or the change between the two directions, which are key parts of the expected answer.
