# BoringAlpha — Project Review & Model-Contribution Attribution

- **Date:** 2026-09-04 (written 22:50–23:00 local)
- **Reviewer:** GLM (`glm-5.3-flash`, DeepSeek Harness agent) — an independent review pass, not part of the build
- **Scope:** whole repository at commit `6cce761`; all 65 commits; source, tests, charters, reviews, notes
- **Method:** read `README.md`, `docs/principles.md`, both strategy charters, the development/validation reviews, the after-tax note, `engine.py`, `trend.py`, `bootstrap.py`, `research_freeze.py`, sampled tests; ran the full suite (806 tests + 140 subtests, 2:00 min, all passing); parsed `Co-Authored-By:` trailers to attribute every commit; computed per-group line totals from `git show --shortstat`
- **Verification commands:** `git log --format='%h|%s|%b'` (trailer extraction), `git show --stat` per commit, `.venv/bin/python -m pytest -q`

**Caveats, stated up front:**

1. Attribution rests on `Co-Authored-By:` trailers. They are self-reported and a single human (`Hyu`) committed everything; they identify which agent produced the work, not who is accountable.
2. All groups worked inside the same harness, conventions, and review culture on one day. The ratings therefore measure *model-in-this-process*, not model-in-a-vacuum. Some of everyone's quality belongs to the loop they ran in.
3. The reviewer is also an AI model. Treat the relative rankings as more trustworthy than the absolute numbers.

---

## Part 1 — Overall project review (the original assessment)

**Verdict: a good project — but good in an unusual direction.** It is not a "find alpha" project; it is an anti-fooling-yourself project, and on that axis it is genuinely well above average. Whether that is a feature or a bug depends on what the owner wants from it.

### What is genuinely strong

**The epistemics machinery is real, not decorative.** Pre-registered charters with locked numeric criteria (C1–C5); development/validation/sealed periods where data is truncated at the boundary *before* the engine sees it (pinned by `tests/test_seal_identity.py`); write-once content-addressed artifacts; a `classify` command that computes the verdict mechanically so it cannot be typed in after the fact.

**The honesty is baked in, including in unflattering places.** The development review states that passing C1 was "close to a foregone conclusion" (the window contains 2008, the event that made 12-month trend famous), admits C4 "was passed on a weaker test than its name suggests", pre-commits in writing to what would change its reading *before* validation ran, and every Sharpe difference carries a block-bootstrap interval with plain words about it often containing zero. BA-001's mechanical verdict is **Inconclusive** — the development advantage over the exposure-matched benchmark reversed in validation under all eight tax scenarios — and the docs say so instead of shopping for a variant that works. That reversal is exactly the moment most hobby projects quietly re-tune.

**Engineering hygiene is excellent.** Zero runtime dependencies; clean layering (data / signals / portfolio / execution / backtest / metrics); ~8.4k source lines vs ~9.5k test lines; deterministic synthetic data with a `random_walk` negative-control regime on which a trend rule should earn nothing; plausibility checks that halt on broken data; provenance deliberately separated from the write-once manifest with a sound justification; a tax overlay with lot-level wash accounting, eight declared scenarios, and independent replay reconciliation of archived accounts.

### Where it is "just so-so"

1. **The ceremony dwarfs the hypothesis.** ~18k lines and a freeze/confirm/journal/reveal/repair protocol built to evaluate a 12-month lookback on eight ETFs — one of the most-studied rules in the literature. BA-002 (a 9/12/15 blend) is a modest perturbation. The instrument is impressive; the target it is pointed at is small.
2. **Zero economic conclusions so far, by design.** BA-001 Inconclusive, BA-002 synthetic-only, sealed period unrevealed. Nothing wrong with that, but the current output is a well-calibrated "we don't know."
3. **Data is the soft floor.** Yahoo's free, revisable endpoint with a derived `tr_open` — the development review itself calls it "the single most likely place for an error to enter." Self-aware, but it caps what any future sealed result can mean until a second vendor cross-check exists.
4. **Housekeeping.** ~7 MB of stray untracked screenshots in `docs/` (`Untitled.png`, `Untitled4.png`, `screenshot1.png`, …); a 400-line README absorbing doc sprawl that belongs in the charters; all 64→65 commits land on a single day, so the discipline is proven in artifacts but not yet tested by boring ordinary use.

**Recommendation:** clean up the stray files and verify data against a second source before anything touches the sealed period; then resist adding more scaffolding — the next unit of effort should go into hypotheses worth the ceremony, not more ceremony.

---

## Part 2 — Commit attribution

The stated taxonomy was "commits with Claude Fable → fable-5.1; everything else → codex gpt (BA-001 phase = gpt-5.6 xhigh; BA-002 onward = gpt-6 Astra Ultra)." The trailers are actually **finer than that**: the repo distinguishes *Claude Fable 5.1* from *Claude Opus 5* (one commit as *Claude Opus 5 (1M context)*). Lumping all Claude together would misattribute the entire engine spine to Fable, so three Claude-era groups are rated separately. The four no-trailer commits split at `fd729f4` (22:17, the BA-002 mega-commit) per the stated phase mapping.

| Group (trailer) | Label used here | Commits | Lines (+/−) | Window | Role |
|---|---|---:|---:|---|---|
| *(none)* → `2abda20`, `a3252b2`, `3a3a74c` | **gpt-5.6 (codex, xhigh)** | 3 | +3,331 / −352 | 01:06, 19:39–19:47 | initial skeleton; tax-lot corrections; after-tax results note |
| `Claude Opus 5` (+ 1 commit *1M context*) | **Opus 5** | 22 | +7,838 / −606 | 01:54–10:55 | engine, sealing, evaluation harness, execution split, fetcher, methodology verification |
| `Claude Fable 5.1` | **Fable 5.1 (xhigh)** | 39 | +14,366 / −740 | 01:32, 11:35–19:12, 22:55 | BA-001 reviews, after-tax design + plans + overlay implementation, whole-branch review |
| *(none)* → `fd729f4` | **gpt-6 Astra (codex, Ultra)** | 1 | +13,044 / −132 | 22:17 | entire BA-002 pipeline: freeze/journal workflow, schema-7 archives, NYSE calendar, charter |

Total: 65 commits, +36,584 / −1,830 lines, all on 2026-09-04.

Test count trajectory (from commit messages): 8 → 51 → 111 → 121 → 153 → 183 → 216 → 272 through the Opus phase; 806 tests + 140 subtests at `fd729f4`.

---

## Part 3 — Comparative ratings

Scale: 1–10, 10 = exceptional. "Overall" is a judgment, not an average — process weaknesses weigh more than the subscores suggest.

| Dimension | gpt-5.6 | Opus 5 | Fable 5.1 | gpt-6 Astra |
|---|---:|---:|---:|---:|
| Architecture & solution design | 8.5 | **9.5** | 9.0 | 9.0 |
| Depth of thinking / self-correction | 8.5 | **9.0** | **9.5** | 8.5 |
| Commit-message documentation | 6.0 | **10** | 9.5 | 5.5 |
| Standalone documentation (charters, notes, records) | 9.0 | 8.5 | **9.5** | 8.5 |
| Code quality (as sampled) | 8.5 | **9.5** | 9.0 | 9.0 |
| Test rigor | 9.0 | **9.5** | 9.0 | 9.0 |
| Process discipline (commit hygiene) | 7.0 | **9.5** | 9.0 | 5.0 |
| Honesty / calibration | 9.0 | 9.0 | **9.5** | 8.5 |
| **Overall** | **8.4** | **9.4** | **9.3** | **8.3** |

**Reading the gpt-5.6 vs gpt-6 gap — it is a tie, not a ranking.** The 0.1 difference is well inside measurement noise and the two should be read as effectively equal (≈8.3–8.4). The gap came entirely from commit-message and process-discipline scores, both of which are confounded: the morning and afternoon sessions were driven task-by-task by the orchestrator (Fable's plan explicitly assigned "a commit each"), while gpt-6 received one ~3-hour solo window and necessarily committed once — a harness structure, not a model trait. The two groups also did categorically different jobs: gpt-5.6's best work was *verification* of another model's code (which this repo's value system weights heavily), while gpt-6's was a large *construction* job against existing conventions. Neither comparison says which model is more capable; they describe the artifacts each was given the chance to produce. gpt-6 additionally carries a one-commit sample size — its code quality is judged from one deep-read file plus a passing 806-test suite.

### gpt-5.6 (codex) — 3 commits, the bookends of BA-001

**Good.**

- `2abda20` laid a sound skeleton (engine, config, loader, metrics, CLI, full BA-001 charter) in one shot; everything later hardened it rather than replaced it, which is the sign of a correct first sketch.
- `a3252b2` (+1,460/−342 across 20 files) is the most under-appreciated commit in the repo: it **independently corrected and verified another model's tax-lot histories** — split wash-sale replacements from dividend entitlements, net carried losses across characters, added a new `tax/reconcile.py` (110 lines) that replays archived accounts, plus ~600 lines of adversarial regression tests (`test_tax_lot_interactions.py` 183, `test_tax_reconcile.py` 93). Cross-examining Fable's overlay instead of trusting it is exactly the right instinct for this repository's stated purpose.
- `3a3a74c` wrote the 208-line after-tax note: dense, honest, admits `legacy-unverified` provenance for old archives, and refuses to upgrade BA-001's Inconclusive verdict. First-rate research documentation.

**Weak.**

- Commit messages are the thinnest of the three groups: one title-only, two single paragraphs — against an essay standard the other groups set. The correction commit's *reasoning* lives in the docs file, not the commit.
- The initial skeleton had known gaps (calendar-date lookback with one-to-two session jitter, silently-passing month-end issues) that Opus spent `7720490` fixing — normal for a first cut, but the commit claimed none of them.

### Opus 5 — 22 commits, the engine spine

**Good.**

- The hardest problems in the repo are here and were solved *as invariants, not steps*: the seal (truncate before the engine sees data; run identity = f(config, data, code, period)); artifact identity separated from environment (`bddf8e9`); the shared-calendar ragged start; the negative-control regime whose test asserts a generator property over 20 seeds rather than a flaky single-seed outcome.
- Genuine design insight, e.g. `bddf8e9`: folding environment into a write-once manifest makes "an integrity alarm fire on ordinary work, which teaches you to ignore it" — that is thinking about the human, not just the code.
- Behavior-neutral refactors proven, not asserted: the portfolio/execution split verified byte-identical against a pre-change baseline (`231aed8`); test strengthening confirmed by mutation testing before restoring (`a4fbc7f` — three tests that "could not fail" made failable).
- Self-correction loop visible in its own work: `f70ab15` fixed its own two-way turnover bug and missing sweep provenance the same day it shipped them.
- Commit messages are the repo's gold standard: every behavior change enumerated, test counts stated, verification method named.

**Weak.**

- Occasional kitchen-sink commits (`804501b` "Fix wave" bundles eight unrelated changes).
- Shipped then fixed its own bugs in adjacent commits (normal velocity, but the first versions did land).
- The `90e20c2` fetcher introduced the derived `tr_open` — flagged by itself as the likeliest error source, never independently verified since.

### Fable 5.1 (xhigh) — 39 commits, the researcher

**Good.**

- The best thinking in the repo is in its two reviews (`34d946d`, `dac1ebb`): pre-committing in writing to what would change its reading *before* validation ran, checking those pre-commitments against the outcome, recording where its own expectation was wrong, and recommending leaving the sealed period unrevealed. This is textbook calibration and the crown jewel of the project.
- Disciplined plan-then-execute: design doc revised twice after external review (`a5e0985`, `d5f0768` — one review item declined *with a stated bound*), implementation plan with hand-computed fixtures, one commit per task, ten tasks.
- Self-checking code: the tax overlay reports share-identity and income-plus-gain identities on every ex-date, making its riskiest assumption (split-adjusted units) self-verifying; pooled child lots avoid a 2^N lot explosion with the invariance argument in the commit message.
- Corrects its own record when reality disagrees — twice (`228a12f`, `ab43ae9`) on the hand-check record, plus `60c0b98` aligning docs back to evidence.
- Fixed three defects in its own plan *before* execution (`7cbe449`); ran a whole-branch review (`6cce761`) producing 6 important + 27 minor findings and handed them to a separate agent rather than fixing them itself.

**Weak.**

- Record-keeping churn: the hand-check record needed three consecutive correction commits in 40 minutes; plans shipped with defects that a pre-execution pass caught.
- Real-data surprises surfaced late in its overlay (`981a4c4` adjustment-factor jitter found only when real TLT/EFA data tripped an over-sell error; the fix widens a tolerance to 1e-5 — justified, but widening a tolerance to admit an inconsistency is the kind of move this repository exists to scrutinize).
- A qualified-dividend date bug and a wash-sale matching gap slipped through review and were caught in its own later pass (`af40397`).

### gpt-6 Astra (codex, Ultra) — 1 commit, the big build

**Good.**

- `fd729f4` (+13,044 across 62 files) is the largest single unit of work in the repo and the code quality holds up: `research_freeze.py` (sampled) validates exact field sets, canonicalizes JSON, rejects NaN/inf, writes atomically with fsync, and makes confirmation idempotent with a full-hash check. The freeze/journal/reveal state machine is a well-designed governance layer.
- Good judgment in simplification: the workflow-simplification change record (`2026-09-04-ba-002-workflow-simplification.md`) removes per-run approval files in favor of one family journal, learning from BA-001's friction — and documents the rationale.
- Honest framing everywhere: "implemented for synthetic review, not historically evaluated"; "no historical BA-002 evaluation or holdout access performed"; the NYSE calendar ships with provenance and source-facts sidecars.
- Tests doubled the suite (→ 806 + 140 subtests) inside the same commit, including 1,700+ lines of research-governance tests.

**Weak.**

- **Process discipline is the weakest in the repo.** One mega-commit of 62 files for a day's most complex feature is hard to review, hard to bisect, and abandons the one-commit-per-task convention the other two groups followed all day. Its own commit message is one paragraph for +13k lines.
- The governance layer it built sits on top of safeguards it also *simplified* — the same commit both builds and loosens, which concentrates review burden at exactly the moment review is hardest.
- Sampling bias caveat: with a single commit, code quality is judged from `research_freeze.py` plus the passing suite, not from a broad read.

---

## Part 4 — Cross-group dynamics, ranking, and takeaways

**The loop worked.** Each group's output was audited by another: Opus hardened gpt-5.6's skeleton; Fable designed and implemented what gpt-5.6 later corrected and verified; gpt-6 Astra simplified what Fable had built. The single best commit in the repo (`a3252b2`) is a *critique* commit. For a project whose stated first job is "make it hard to fool ourselves," a multi-model adversarial loop is arguably its most important design decision — and the ratings above partly measure how well each model operated as reviewer vs. author.

**Ranking (as measured in this repo, this process, this day):**

1. **Opus 5 — 9.4.** The infrastructure every later group leaned on; solutions framed as invariants; flawless commit hygiene.
2. **Fable 5.1 — 9.3.** The best raw reasoning (the reviews, the self-corrections) and the project's soul; loses a hair to process churn and late-discovered data issues.
3. **gpt-5.6 ≈ gpt-6 Astra — 8.4 ≈ 8.3, a tie.** gpt-5.6 edges ahead only on dimensions the orchestrator's session structure rewarded (small reviewable commits); gpt-6 Astra produced the largest and, per sampled file, equally careful code of the day under the least favorable process conditions. The honest statement is that the measurement cannot distinguish them.

**What each could learn from the others:** gpt-5.6 and gpt-6 Astra should write Fable/Opus-grade commit messages and (for gpt-6) split work into reviewable tasks; Fable should catch data-model mismatches *before* real data touches the code rather than widening tolerances after; Opus should resist bundling unrelated fixes into one "wave" commit.

**One-line verdict:** *Opus built the lab, Fable taught it honesty, gpt-5.6 checked the math, and gpt-6 Astra built the next wing — a genuinely good project produced by four agents who were, at their best, each other's reviewers.*

---

*Attribution detail: full per-commit classification is reproducible with `git log --format='%h|%s|%b'` and filtering on `Co-Authored-By:`. Fable-group commits: `6840ea6`, `34d946d`, `2625ab8`, `dac1ebb`, `829f131`, `a5e0985`, `d5f0768`, `cd38bad`, `e5686b8`, `b51d7ee`, `9850b62`, `98a7353`, `9fd915e`, `5cd1d54`, `f348b27`, `9935221`, `0603dee`, `01e7d1f`, `c004801`, `228a12f`, `ab43ae9`, `82ff012`, `ec11717`, `60c0b98`, `b9c355d`, `7cbe449`, `2d74006`, `5d39400`, `eb1223a`, `0631aca`, `ed94a2f`, `992079f`, `647a3e9`, `af40397`, `1add246`, `6392053`, `981a4c4`, `16ee714`, `6cce761`. Opus-group: `7720490`, `292c39d`, `bddf8e9`, `57b2f1e`, `0cb7dd5`, `f70ab15`, `d6b9063`, `d7969e5`, `2371c1a`, `3c94261`, `91ac37f`, `c69091e`, `231aed8`, `a4fbc7f`, `529e5dc`, `f30fa3e`, `804501b`, `90e20c2`, `3e6e9cd`, `896b13e`, `32fa703`, `a49b80f`. No-trailer: `2abda20`, `a3252b2`, `3a3a74c` (gpt-5.6); `fd729f4` (gpt-6 Astra).*
