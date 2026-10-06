# Retrieval ablation (v5_5C)

Settings: hybrid = top 20 vector + top 20 keyword (up to 40 fused candidates), reciprocal rank fusion k=60; keyword = OR of the question's lexemes found in at most 15% of chunks, ranked with ts_rank_cd. Statuses as in retrieval_eval.py (active for simple / multi_part, all for change / status); boilerplate excluded.

## Recall

| method | group | n | R@1 | R@3 | R@5 | R@10 | R@20 | R@30 |
|---|---|---|---|---|---|---|---|---|
| vector | overall | 44 | 70.5% | 86.4% | 93.2% | 95.5% | 97.7% | 97.7% |
| vector | simple | 20 | 75.0% | 90.0% | 90.0% | 90.0% | 95.0% | 95.0% |
| vector | multi_part | 15 | 73.3% | 93.3% | 100.0% | 100.0% | 100.0% | 100.0% |
| vector | change | 7 | 71.4% | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% |
| vector | status | 2 | 0.0% | 0.0% | 50.0% | 100.0% | 100.0% | 100.0% |
| keyword | overall | 44 | 47.7% | 59.1% | 81.8% | 90.9% | 95.5% | 97.7% |
| keyword | simple | 20 | 45.0% | 55.0% | 90.0% | 100.0% | 100.0% | 100.0% |
| keyword | multi_part | 15 | 66.7% | 80.0% | 93.3% | 93.3% | 100.0% | 100.0% |
| keyword | change | 7 | 28.6% | 42.9% | 57.1% | 85.7% | 100.0% | 100.0% |
| keyword | status | 2 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 50.0% |
| hybrid | overall | 44 | 75.0% | 86.4% | 90.9% | 95.5% | 100.0% | 100.0% |
| hybrid | simple | 20 | 75.0% | 95.0% | 95.0% | 95.0% | 100.0% | 100.0% |
| hybrid | multi_part | 15 | 86.7% | 93.3% | 100.0% | 100.0% | 100.0% | 100.0% |
| hybrid | change | 7 | 71.4% | 71.4% | 85.7% | 100.0% | 100.0% | 100.0% |
| hybrid | status | 2 | 0.0% | 0.0% | 0.0% | 50.0% | 100.0% | 100.0% |

## Questions whose rank differs between methods (rank of the first matching chunk; >30 = miss)

| id | type | expected | vector | keyword | hybrid |
|---|---|---|---|---|---|
| q006 | status | nbfc_credit_facilities_2025.pdf para 6 | 5 | 24 | 10 |
| q008 | change | kyc_amendment_2025_06.pdf para 4 | 1 | 7 | 1 |
| q009 | simple | nbfc_responsible_business_conduct_2025.pdf Annex I Part 2 | 2 | 8 | 2 |
| q012 | simple | nbfc_credit_facilities_2025.pdf para 27 | 1 | 6 | 2 |
| q013 | simple | nbfc_credit_facilities_2025.pdf para 12 | 1 | 2 | 1 |
| q014 | simple | nbfc_credit_facilities_2025.pdf para 14 | 2 | 1 | 1 |
| q015 | simple | nbfc_credit_facilities_2025.pdf para 19 | 1 | 5 | 1 |
| q016 | simple | nbfc_credit_facilities_2025.pdf para 8 | 1 | 4 | 1 |
| q017 | simple | nbfc_credit_facilities_2025.pdf para 10 | 1 | 5 | 1 |
| q019 (watch) | simple | nbfc_credit_facilities_2025.pdf para 25 | >30 | 4 | 13 |
| q020 (watch) | simple | nbfc_kyc_md_2025.pdf para 5 | 15 | 4 | 2 |
| q022 | simple | nbfc_kyc_md_2025.pdf para 41 | 1 | 4 | 2 |
| q025 | simple | nbfc_kyc_md_2025.pdf para 47 | 2 | 2 | 1 |
| q026 | simple | nbfc_credit_facilities_2025.pdf para 18 | 1 | 5 | 1 |
| q027 | multi_part | nbfc_credit_facilities_2025.pdf para 23 | 1 | 5 | 1 |
| q030 | multi_part | nbfc_kyc_md_2025.pdf para 28 | 2 | 1 | 1 |
| q031 | multi_part | nbfc_kyc_md_2025.pdf para 28 | 3 | 1 | 1 |
| q033 | multi_part | nbfc_credit_facilities_2025.pdf para 13 | 5 | 12 | 4 |
| q035 | multi_part | nbfc_credit_facilities_2025.pdf para 28 | 1 | 5 | 2 |
| q036 | multi_part | nbfc_credit_facilities_2025.pdf para 12 | 1 | 2 | 1 |
| q038 | multi_part | nbfc_kyc_md_2025.pdf para 5 | 2 | 1 | 1 |
| q040 | multi_part | nbfc_credit_facilities_2025.pdf para 22 | 1 | 3 | 1 |
| q041 | change | nbfc_credit_facilities_2025.pdf para 11; digital_lending_directions_2025.pdf para 10 | 1 | 8 | 1 |
| q042 | change | nbfc_credit_facilities_2025.pdf para 25; digital_lending_directions_2025.pdf para 24 | 1 | 5 | 1 |
| q043 (watch) | status | nbfc_credit_facilities_2025.pdf para 112 | 8 | >30 | 18 |
| q045 | change | nbfc_kyc_md_2025.pdf para 3; kyc_md_2016.pdf para 2 | 2 | 3 | 4 |
| q046 | change | nbfc_kyc_md_2025.pdf para 18; kyc_amendment_2025_08.pdf para 4 | 5 | 15 | 6 |
