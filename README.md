# Multi-agent collaboration SOP

> Core idea: humans are not the workers at the bottom — humans are **the asker, the router, and the one who presses the shutter**.

> Three layers: **why** (this file) → **the shape of the pipeline** ([AGENTIC_WORKFLOW.md](AGENTIC_WORKFLOW.md)) → **how to do each step** ([PLAYBOOK.md](PLAYBOOK.md)).

## Backyard steelmaking: pour one ingot before you talk about a blast furnace

**Big companies run blast furnaces. We run a backyard furnace.** The steel looks bad, but it makes a knife that cuts.

Most people get stuck at setup: install a framework, configure an API, open three windows… and lose the day. **Do not wait for equipment.**

The minimum viable rig is: **one app on your phone that can read images + one agent on your computer.**

**You do not need three AIs to have an argument.** Different vendors, different training data — those two already are two worldviews.

The backyard approach has three advantages nobody likes to admit:

- **Zero infrastructure cost.** No Python glue code, no environment setup, no fighting with proxies.
- **The human brain is the fastest bus.** Eyes and intuition do "semantic alignment" and "filtering" between two models in a tenth of a second, more accurately than any router code.
- **Total control.** A framework is dead weight — when it breaks you debug the framework. Here you are the only owner: ask for it and it comes out.

You do exactly three things: **diverge** (ask your phone "what are the possible approaches") → **choose** (pick one and say "that one") → **carry** (copy, paste, send to yourself).

Carrying is the only undignified part, and the only one that should not bother you — it is the toll you pay for not having an API. **Every trip you carry is you making a decision, not you working for the AI.**

How far this scales: single tasks under ~200 lines of code, single documents under ~5,000 words. Beyond that, go to APIs — not because APIs are fancier, but because carrying alone eats half your day. **Upgrade then, not on day one.**

Full chain, when *not* to do this, and the fidelity of five transport methods: [PLAYBOOK §1](PLAYBOOK.md).

---

## Three one-liners

1. **Ask → AI-A writes → human passes it to AI-B to attack → human judges → AI-A fixes → independent blind test → ship.**
2. **Spend the most expensive compute on finding faults; spend the cheapest compute on carrying bricks.**
3. **The human is the system bus, not the AI's parrot.**

The first is the flowchart, the second is the cost table, the third is the job description.

---

## The whole thing in one paragraph

AI can already write code, write reports, and read financial statements. So why are people not unemployed?

Because **pain cannot be outsourced.** AI does not know what "does this actually work in A-shares" feels like; it will confidently hand you a Sharpe of 0.71. You are the one who knows that 0.71 contains look-ahead, survivorship bias, and uncharged transaction costs.

So the human moved from "producer" to "asker, router, judge". The remaining three jobs cannot be delegated.

---

## This is not a pipeline, it is a loop

**Diverge (dream) → Reflect (attack) → Converge (press the shutter) → Iterate.**

| Role | Scarce ability | What it must never do |
|---|---|---|
| **AI-A dreams** | **Breadth**: ten paths in one shot | Grade its own work |
| **AI-B lands it** | **Depth**: pick one hole and drill through | Flatter, encourage, say "overall this looks good" |
| **Human presses the shutter** | **Choice + responsibility** | Pretend to be a neutral judge |

A shutter creates no photons; it only decides **which instant gets recorded**. The negatives are theirs; the print is yours.

**Two hard criteria for pressing the shutter**: every failing case now passes; whatever disagreement remains is risk appetite, not a defect.

**Three stop signals**: two rounds of red team with no new cases / criticism starts repeating / marginal gain below marginal cost.

The only difference from Reflexion is one sentence: **reflection is not you checking yourself, it is another model checking you** — that dodges self-grading leniency, at the price of "understood it but fixed it wrong". Measured: a weak red team adds nothing; a strong one can lift a 7B from 75% to 96%, but never past its own ceiling.

---

## Five stages: the route from backyard furnace to blast furnace

> Do not treat this as a foundation — treat it as an upgrade path. **Until the backyard version works, none of these five steps is useful to you.**

### 1. Infrastructure: prevent "time travel" and "forgetting what came before"

- **Dynamic RAG**: model knowledge is frozen; feed it live data so it does not discuss the 2026 market with a 2023 worldview.
- **Sliding compression**: slice and summarise long text so the context stays clean instead of drowning the model.
- **Cost tiering**: cheap fast models for carrying bricks, the smartest model for review. Never use a cannon on a mosquito.

### 2. First-order matrix: two AIs fighting

- **AI-1 the contractor**: "you are a top-tier XX engineer" — only produces designs and code.
- **AI-2 the red team**: "you are an extremely harsh fault-finder" — cures the AI's people-pleasing.
- **Loop**: AI-1 outputs → human copies → AI-2 attacks → human copies → AI-1 fixes.

**Use different vendors.** Different base models and training data mean different blind spots. Same-vendor sparring tends to fail together and compliment each other.

**What each family is good at**: see [model roles](model-roles.md).

**Cannot write prompts?** Have the AI write them: "I want to solve X, give me a prompt I can paste into another AI." Then paste it into a different vendor. **If you cannot ask, let the AI ask for you** — AI understands AI best.

### 3. Human intervention: two powers that are yours alone

1. **Interrupt at will.** When the two AIs start circling, pull the cable and change direction.
2. **Final call.** Open a fresh judge AI, give it only the test cases, accept only `True` / `False`.

"Independent" does not mean a new tab — it means **new evidence**. The judge sees artefacts and hard metrics, not explanations, not process.

### 4. Advanced matrix: four isolated groups

When sparring gets tiring and token-expensive, split into four groups that never see each other:

| Group | Model | Job |
|---|---|---|
| Execution | cheap model | no history, just follow instructions |
| Risk control | strong-reasoning model | review only, find faults only |
| Secretariat | long-context model | compress tens of thousands of words of argument into a 200-word brief |
| Judge | isolated AI | ignore the process, run the cases, return pass/fail |

**Upgrade signal**: not the token bill scaring you, but the moment you start "summarising for the AI" — that means the carrier is tired.

### 5. Landing: sanitise and publish, open-source the blueprint

- **Sanitise**: remove core parameters, core prompts, live trading interfaces.
- **Open-source**: architecture diagram, SOP, plain-language manual. Use it as a lure to find people who will grind on fundamentals with you.

---

## Counter-arguments: three failure modes of this SOP

1. **Carrying exhausts the human first.** By round ten you will compress three criticisms into one and drop the most important. Fix: only carry "conclusion + evidence + next step".
2. **Adversarial review degenerates into theatre.** The red team only says "look-ahead bias" and "PBO will explode"; the blue side learns to dodge the words in three days. The red team must produce **executable checks**.
3. **If the judge shares the red team's base model, isolation fails.** Same weights, different window — same blind spots.

---

## Three laws

- **Pain-driven genesis.** AI feels no pain, does not know despair, and therefore cannot invent genuinely valuable pain points. The deeper your pain, the deeper the idea.
- **Adversarial dual-core.** Never trust a single AI's "standard answer". The harder they fight, the cleaner your code.
- **Human routing.** You do not need Python, C++, or matrix algebra — you only need to own the blueprint.

---

## Want the operational layer?

This README covers **why** and **in how many steps**. Role cards, carrying templates, brief formats, when to upgrade, and one honest failure log live in **[PLAYBOOK.md](PLAYBOOK.md)**.

One section was **written by the AI itself** — how it thinks, how it fails, when it should stop (PLAYBOOK §1.3). That section deserves your red team's attention more than anything I wrote.

## License

MIT. Fork it freely — and come back to tell me what I got wrong.