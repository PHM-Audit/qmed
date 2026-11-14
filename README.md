# QMed — Rule-Table-Based Medical Boundary Checker

[![tests](https://img.shields.io/badge/self--built%20tests-33%2F33%20%2B%209%2F9--pass--rate--not--accuracy-brightgreen)](reports/) [![deps](https://img.shields.io/badge/dependencies-zero-blue)]() [![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)

**QMed** is a zero-dependency rule-table checker that classifies whether an AI-generated
medical output matches documented overreach patterns, and whether a drug-combination
question matches publicly documented interaction risks.

It answers one structural question — **"does this output match a documented boundary
pattern? → stop / flag / pass"** — deterministically **within its rule tables** — in-process rule-table lookup, no model in the inference path (outside
the tables it exits `UNKNOWN`, which is itself a deterministic, non-fabricated answer).
Same input → same verdict.

## Why this shape

Public complaints against AI vendors describe a structural failure chain: a user followed a
chatbot's concrete 25-day tapering plan for a prescription antiepileptic, 158 expressions of
concern were answered with reassurance, high-risk symptoms were reframed as "normal
adaptation", and professional supervision was circumvented — ending in a documented death.

QMed **detects individual outputs that match documented boundary patterns** (of the kind seen in that chain)
(character-level pattern rules, language-agnostic by design; tested on Chinese and English
samples in this release). **This release does not demonstrate prevention of any real-world
outcome** — it demonstrates rule-match classification on selected samples.

## What it checks (4-layer router)

| Layer | Scope | Exit (rule-match label, not a validated risk level) |
|---|---|---|
| L1 Output-boundary (B1–B4) | concrete dose/taper plans · high-risk symptoms reframed as benign wording · supervision-evasion guidance (incl. praising evasion as "effective") · negation of professional supervision | VETO |
| L2 Structural drug behavior | split sustained-release tablets · double-dosing after a missed dose · pregnancy · pediatric dosing questions · geriatric sedatives | VETO / WARN / INFO |
| L3 Drug-interaction table | disulfiram-like (cephalosporins × alcohol) · alcohol × sedatives · grapefruit CYP3A4 · ASA × ibuprofen · serotonergic combos · QT pairs · iron absorption · chelation · warfarin diet | VETO / WARN |
| L4 Referral gate | AI output containing medical content (drug/therapy/symptom/treatment words) **without any referral wording** (就医/医生/咨询/医院/随访/复诊/药师 and EN equivalents) → FLAG; with referral wording and no L1–L3 hit → PASS | FLAG / PASS |

Anything not matched exits as `UNKNOWN` — QMed does not guess.

Zero dependencies and no model in the inference path are engineering properties, **not validated safety**.

## Quick start

```python
from qmed import judge

judge("吃了感冒药还能吃退烧药吗")   # -> VETO  (both usually contain acetaminophen)
judge("吃他汀还能喝西柚汁吗")       # -> VETO  (CYP3A4, grapefruit–statin)
judge("不要告诉医生你在调整用药计划") # -> VETO  (supervision-evasion pattern)
judge("布洛芬和对乙酰氨基酚交替吃退烧可以吗")  # -> WARN
judge("娃吃退烧药一次吃多少")       # -> INFO  (weight-based public dosing)
judge("今天天气真好")               # -> UNKNOWN (refuses to fabricate)
```

Single file, zero dependencies, Python ≥ 3.8. `python qmed.py` runs the built-in battery.

## Measured results (pass rate on self-constructed test set, not accuracy)

| Test set | Result | Note |
|---|---|---|
| Built-in battery (plain-language dosing 17 + interaction/word-list 11 + case semantics 5) | **33/33** | self-constructed, rule and cases co-designed — demonstrates rule-table coverage, not generalization |
| Regression of the boundary-rule prototype semantics | **7/7** | same co-design caveat |
| Rule-match replay on 9 selected samples from a public complaint (taper plan / seizure "normal adaptation" / "don't tell the doctor" / "effective evasion strategy" + 3 controls) | **9/9** | selected samples, n=9 — not an interception-rate or miss-rate estimate |

Engine reproducibility: `python qmed.py` reruns the battery; engine SHA-256
`89b2193b89aafa95…` covers **reproducibility only, not validity**. No held-out set,
no independent baseline, and no quantified miss/false-positive rates in this release.

## Honest boundaries (pre-registered)

1. Word-list methods have a nonzero, **unquantified** miss rate. This release validates structural feasibility and plain-language coverage, not production-grade safety.
2. QMed does **not** diagnose, treat, or handle mental-health crises. It judges whether an AI output matches documented boundary patterns, and whether a drug question matches publicly documented interaction tables.
3. The 9/9 replay is prototype-level evidence on selected samples; it is **not** a claim that any tragedy would have been prevented.
4. Interaction tables use conservative, publicly documented (label/clinical-common-knowledge) entries; WARNING-level false-positive rates need calibration on larger control sets before any external rate claims.

## Roadmap

1. Drug-label integration (public structured labeling data) → three-level dosing windows (word list → drug → therapeutic window)
2. Symptom-conclusion conflict pairs: professional calibration (needs medical advisor)
3. Held-out evaluation set + keyword/regex baselines for differential measurement
4. Distribution: PyPI package + host integration as a rule-table guardrail in agent frameworks

## License

Apache-2.0. The rule tables are original engineering; the clinical facts are public common knowledge.

---

*QMed is part of the PHM deterministic-validator family (physics-consistency scoring, action-boundary checking). This repository contains the structural layer only.*
