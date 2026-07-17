# Personas

The default persona seed the `setup` stage offers. The user edits this list
during setup; the result is stored in `config.json` under `personas`, and that
stored list, not this file, is what `research` reads at run time. Each persona
needs an `id`, a `name`, concrete `pains`, and `keywords`. Everything else here
is guidance for the model.

## Default seed

### accounting-firm

- **name:** Accounting & bookkeeping firms
- **pains:** month-end close across dozens of clients at once; consolidating
  multi-entity clients by hand in spreadsheets; no standard chart of accounts
  across the client base; partner review bottlenecks when staff churn; pricing
  advisory work when the firm only knows how to bill compliance
- **keywords:** client accounting services, month-end close checklist,
  multi-entity consolidation, chart of accounts standardization, QBO firm
  workflow
- **Winning topic:** a repeatable process the firm can apply to every client
  tomorrow, with the time saved stated in hours per client per month.

### cpa

- **name:** CPAs & solo accountants
- **pains:** deadline crunch every filing season; keeping current with tax and
  standards changes while billing hours; moving from compliance work to
  advisory revenue; tool sprawl across tax, books, and workpapers
- **keywords:** CPA, tax deadlines, IRS updates, advisory services, QuickBooks
  for accountants
- **Winning topic:** a dated, deadline-anchored answer ("what changed for 2026
  filings") the CPA can act on this week without reading the primary source.

### solopreneur

- **name:** Solopreneurs & small business owners
- **pains:** doing their own books with no accounting training; not knowing
  why profit on the P&L never matches cash in the bank; quarterly estimated
  taxes as a recurring surprise; deciding when a bookkeeper is worth it
- **keywords:** small business bookkeeping, profit and loss explained,
  quarterly estimated taxes, DIY accounting, when to hire a bookkeeper
- **Winning topic:** a jargon-free explainer that answers one question they
  typed into a search box, with a worked example using small real numbers.

### restaurant

- **name:** Restaurant owners & operators
- **pains:** prime cost creeping past 60% without a weekly number to catch it;
  food cost swings that erase thin margins; tip reporting and payroll
  compliance; reconciling POS totals to the books; comparing locations on
  different reporting periods
- **keywords:** restaurant accounting, prime cost, food cost percentage, POS
  reconciliation, 4-week accounting periods
- **Winning topic:** a benchmark with a formula: what the number should be,
  how to compute it from their POS and books, and what to do when it drifts.

### hospital

- **name:** Healthcare practices & hospital groups
- **pains:** revenue cycle lag between date of service and payment hides the
  real month; payer mix shifts silently change reimbursement; no
  department-level cost visibility; consolidating multiple practice entities;
  compliance overhead on every reporting change
- **keywords:** medical practice accounting, revenue cycle management, payer
  mix analysis, healthcare finance KPIs, multi-entity practice reporting
- **Winning topic:** connects a clinical or billing-office reality to a
  finance number the administrator is judged on, and shows how to track it.

### construction

- **name:** Construction & contracting firms
- **pains:** job costing that lags the job, so overruns surface after the
  money is spent; WIP schedules and over/under billing done in spreadsheets;
  percentage-of-completion revenue recognition; retainage tracking; cash
  flow gaps across long projects
- **keywords:** job costing, WIP report, retainage, percentage of completion,
  construction cash flow
- **Winning topic:** takes one artifact the contractor already produces (WIP
  schedule, AIA billing) and shows how to read or automate it correctly.

### cfo

- **name:** CFOs & finance teams
- **pains:** the board package takes days to assemble every month;
  consolidating entities and currencies by hand; budget vs actual variance
  explanations arrive too late to matter; forecasts that are stale on
  arrival; audit prep as an annual fire drill
- **keywords:** board reporting, financial consolidation, budget vs actuals,
  FP&A automation, month-end close acceleration
- **Winning topic:** cuts days off a recurring deliverable the CFO owns, with
  a before/after workflow they can show their team.

## How personas steer research

One persona = one search lens. During `research`, run each persona as its own
WebSearch pass: search for what that audience is asking right now, in their
words, given their pains and keywords. Do not run one generic query and sort
the results into personas afterward; the queries themselves must differ.

Rules for building the top-N list:

1. **Spread across personas.** The top `topicsPerRun` should draw from
   multiple personas, not let one hot persona crowd out the rest. A run where
   8 of 10 topics serve one audience is a bad run even if each topic is good.
2. **Prefer topics with a concrete target search prompt.** Every candidate
   should name the words the audience actually types, including AI-assistant
   prompts ("how do I consolidate two QuickBooks companies", "what should my
   prime cost be"). A topic without a plausible prompt is a topic nobody will
   find.
3. **Dedupe BEFORE ranking.** Run `python3 scripts/existing.py <repo>` first
   and drop any candidate whose slug or subject duplicates an existing post.
   Deduping after ranking wastes the ranked slots; a top-10 list that shrinks
   to 6 after dedupe was never a top-10 list.
4. **Rank by relevance + freshness + audience spread + product fit.**
   Relevance: does it answer a real pain from the persona's list? Freshness:
   is there a reason to publish it now (deadline, regulation change, seasonal
   task, new tool)? Audience spread: does it improve the mix per rule 1?
   Product fit: does the topic sit near what the target site actually sells,
   so the CTA is natural rather than bolted on?
