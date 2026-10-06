# Judge agreement with AI reference verdicts

Compared against: **reference verdicts graded by Claude (AI), NOT a human**. This checks the judge against an independent grader from another model family; it is not human ground truth.

15 of 15 gold answers graded. New judge: openai gpt-5.4-nano-2026-03-17, key facts, majority of 3 call(s). Step 5B judge: the holistic judge whose verdict is stored in the file.

| judge | agrees with the reference | exact agreement |
|---|---|---|
| new (key facts) | 14/15 | 93% |
| step 5B (holistic) | 14/15 | 93% |

## Confusion matrix, new judge (rows: reference)

| mine \ judge | correct | partial | incorrect |
|---|---|---|---|
| correct | 10 | 0 | 0 |
| partial | 1 | 2 | 0 |
| incorrect | 0 | 0 | 2 |

## Disagreements (new judge)

| id | type | reference | new judge | step 5B judge | judge detail | reference notes |
|---|---|---|---|---|---|---|
| q004 | change | partial | correct | correct | 3/3 facts present; present | present | present | [graded by Claude (AI), not a human] missing: entity that last uploaded/updated the record is responsible |
