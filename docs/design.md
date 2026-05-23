# LookSmart

> Knowledge-work infrastructure with incidental privacy properties.

**License (proposed):** Apache 2.0 for core; CC BY-SA for persona libraries; commercial license for enterprise deployment kit.
**Repo posture:** Public from day one. See [§6](#6-two-shell-distribution-strategy) (Kerckhoffs justification).

---

## Table of Contents

1. [Project Identity](#1-project-identity)
2. [Problem Statement and Threat Model](#2-problem-statement-and-threat-model)
3. [Prior Art](#3-prior-art)
4. [Design Principles](#4-design-principles)
5. [Architecture](#5-architecture)
   - [5.1 Component overview](#51-component-overview)
   - [5.2 Persona Sampler](#52-persona-sampler)
   - [5.3 Behavioral Scheduler](#53-behavioral-scheduler)
   - [5.4 Engagement Simulator](#54-engagement-simulator)
   - [5.5 Persona Library](#55-persona-library)
   - [5.6 Audit Subsystem](#56-audit-subsystem)
   - [5.7 Provider Adapter](#57-provider-adapter-plugin-per-llm)
   - [5.8 Local LLM for Decoy Generation](#58-local-llm-for-decoy-generation)
   - [5.9 Weird Al Mode](#59-weird-al-mode-register-chaos-generator)
   - [5.10 Fence-Pissing Mode](#510-fence-pissing-mode-safety-classifier-cost-imposition)
   - [5.11 Spelunking Mode](#511-spelunking-mode-vague-description-identification-queries)
   - [5.12 PoliticRoulette Mode](#512-politicroulette-mode-cross-spectrum-political-philosophy-queries)
   - [5.13 Religious Mode](#513-religious-mode-cross-tradition-theological-queries)
   - [5.14 AskingForAFriend Mode](#514-askingforafriend-mode-harm-reduction-health-queries)
   - [5.15 Cohort Cover for High-Exposure Dimensions](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism)
   - [5.16 IdentitySearch Mode](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries)
   - [5.17 CooKoo Filter Mode](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking)
   - [5.18 GenderRoulette Mode](#518-genderroulette-mode)
   - [5.19 OrientationRoulette Mode](#519-orientationroulette-mode)
   - [5.20 ImmigrationRoulette Mode](#520-immigrationroulette-mode)
   - [5.21 HealthStatusRoulette Mode](#521-healthstatusroulette-mode)
   - [5.22 Echo Mode](#522-echo-mode-recommender-system-correlation-tracking)
6. [Two-Shell Distribution Strategy](#6-two-shell-distribution-strategy)
7. [ToS, Legal, and Operational Risk](#7-tos-legal-and-operational-risk)
8. [Measurable Success Criteria](#8-measurable-success-criteria)
9. [Open Problems](#9-open-problems)
10. [References](#10-references)
11. [Honest Limitations of This Document](#11-honest-limitations-of-this-document)
12. [Dual-Use and Abuse Considerations](#12-dual-use-and-abuse-considerations)

---

## 1. Project Identity

- **Name:** LookSmart
- **Tagline (provisional, internal):** Knowledge-work infrastructure with incidental privacy properties.
- **License (proposed):** Apache 2.0 for core; CC BY-SA for persona libraries; commercial license for enterprise deployment kit.
- **Repo posture:** Public from day one. See [§6](#6-two-shell-distribution-strategy) (Kerckhoffs justification).

---

## 2. Problem Statement and Threat Model

### 2.0 The Geer Frame (operational definition of privacy)

The conceptual foundation for this entire project predates it by twelve years. Dan Geer, CISO of In-Q-Tel, delivered *"We Are All Intelligence Officers Now"* at RSA Conference 2014.[^3] Two passages are operative for LookSmart:

> If you are an optimist or an apparatchik, then your answer will tend toward rules of procedure administered by a government you trust or control. If you are a pessimist or a hacker/maker, then your answer will tend towards the operational, and your definition of a state of privacy will be my definition: **the effective capacity to misrepresent yourself.**

> Misrepresentation is using disinformation to frustrate data fusion on the part of whomever it is that is watching you. … Misrepresentation means using Tor for no reason at all. Misrepresentation means hiding in plain sight when there is nowhere else to hide. Misrepresentation means having not one digital identity that you cherish, burnish, and protect, but having as many as you can.

This is LookSmart's design objective stated in 2014 by the CISO of the CIA's venture arm. The persona-rotation architecture in [§5](#5-architecture) is a direct implementation of Geer's enumerated misrepresentation tactics. Geer also notes the field-operations corollary:

> In the big-I Intelligence trade, crafting good cover is getting harder and harder and for the same reasons: misrepresentation is getting harder and harder. If I was running field operations, I would not try to fabricate a complete digital identity, I'd 'borrow' the identity of someone who had the characteristics that I needed for the case at hand.

The "borrow" insight has direct architectural implications for the persona library ([§5.5](#55-persona-library)) and for the open-source civilian cohort serving as cover for enterprise deployment ([§6.2](#62-inner-shell-enterprisegovernment-deployment-kit)).

Geer also articulated the OOD detection problem that drives the persona-coherence requirement in [§5.2](#52-persona-sampler):

> Your digital exhaust is unique hence it identifies. Pooling everyone's digital exhaust also characterizes how you differ from normal.

And the traffic-analysis dominance that drives [§5.3](#53-behavioral-scheduler)'s behavioral scheduler:

> Traffic analysis is more powerful than content analysis. If I know everything about to whom you communicate including when, where, with what inter-message latency, in what order, at what length, and by what protocol, then I know you. If all I have is the undated, unaddressed text of your messages, then I am an archaeologist, not a case officer.

**Read the full talk before continuing past §2.3.** The rest of this document is implementation detail on a thesis Geer already proved.

### 2.1 What this is for

Commercial LLM providers can construct rich psychometric profiles of users from query content, conversation patterns, engagement signals, and account-level metadata. These profiles have commercial, research, and (potentially) state-access value. LookSmart aims to make those profiles less accurate, more expensive to construct, and operationally less useful — without claiming to defeat them.

### 2.2 What this is NOT for

LookSmart does not provide:

- **Anonymity against an LLM provider operating an authenticated account.** The provider knows it's the user's account.
- **Stylometric obfuscation of the user's own writing on their own real queries.** (See [§2.4](#24-adversary-capabilities-assumed).)
- **Defeat of authorship attribution.** Narayanan et al. (2012) demonstrated stylometric identification across 100,000 candidate authors with ~20% top-1 accuracy and >80% precision with confidence-thresholded recall halving.[^4] Distinctive prose voices identify their authors with far less material than the 5,000-word lower bound from earlier underground-forum work.[^5] No noise-injection scheme defeats this floor on the user's own real queries.

### 2.3 The four candidate threat models

These were enumerated in the design conversation; LookSmart explicitly targets (3) and (4), with (1) as an aspirational stretch goal only if scale is reached.

1. **Cohort hiding (anonymity)** — provider cannot identify which account is the user. Not achievable against authenticated commercial LLM providers. *Filed as out-of-scope.*
2. **Profile inversion** — provider builds an actively wrong profile. Tactically attractive but operationally fragile; *rejected as primary objective.*
3. **Profile dilution / centroid manipulation** — provider builds a profile whose centroid is moved toward a user-chosen target distribution. Measurable as KL divergence between advertised and real profiles. **Primary objective.**
4. **Cost imposition with legibility manipulation** — provider can profile the user given enough effort, but the profile is loud on aesthetics and quiet on operational concerns; cost-per-useful-bit goes up. **Co-primary objective.**

### 2.4 Adversary capabilities assumed

- Account-level metadata (IP, device fingerprint, time zone, client type)
- Full content of queries and responses
- Engagement signals (follow-ups, copy events, regenerations, thumbs, conversation length)
- Typing dynamics and edit patterns where the client reports them
- Temporal microstructure (interarrival distributions, circadian patterns)
- Cross-modal correlation with other ground truth available to the provider or its partners
- Public code review of LookSmart itself (Kerckhoffs assumption[^6])

### 2.5 Adversary limitations assumed

- Cannot subpoena the user's local audit log without legal process (see [§5.6](#56-audit-subsystem) for audit hygiene)
- Cannot read the user's local model weights or persona libraries beyond what's in the public repo
- Cannot deploy zero-day client exploits without significant cost (out-of-scope; mitigation is OS-level)

---

## 3. Prior Art

LookSmart is cover traffic for chatbot interactions. The cover traffic literature has hard lessons from twenty years of anonymity research.

### 3.1 Query-obfuscation tools (the direct ancestors)

- **TrackMeNot** (Howe & Nissenbaum, 2009)[^7] — Firefox extension that injects decoy search queries to obfuscate the user's real search profile. Explicit "Reasonable Doubt" rather than anonymity claim.[^8] Subsequent analysis showed TMN's queries were classifier-separable from real ones using ML on linguistic and timing features.[^9]
- **GooPIR, Noisy** — operate in the same family; see Toubiana et al. 2011 for a comparative analysis.[^8]

**Operational lesson:** Naïve cover traffic is classifier-separable. Decoys that don't model the user's behavioral signature get filtered as anomalies.

### 3.2 Mix networks and cover traffic

- **Pynchon Gate** (Sassaman, Cohen, Mathewson, WPES 2005)[^10] — distributed-trust PIR for pseudonymous mail retrieval. Foundational for "cover traffic that costs bandwidth instead of leaking metadata."
- **Loopix** (Piotrowska, Hayes, Elahi, Meiser, Danezis, USENIX Security 2017)[^11] — Poisson mixing with self-injected traffic loops; cover traffic is structurally indistinguishable from real traffic by design, not by hope.
- **Karaoke** (Lazar, Gilad, Zeldovich, OSDI 2018)[^12] — distributed private messaging using noise-message generation across many servers + Bloom-filter integrity checks; achieves 6.8s latency at 2M users.

**Operational lesson:** The systems that actually achieve indistinguishability use cover traffic *structurally* (every client always emits at rate R, encrypted-and-padded to a fixed wire-level shape) rather than *behaviorally* (try to mimic humans). LookSmart cannot do the former because authenticated LLM accounts have a per-user identity that strips that protection, and because the messages themselves carry semantic content the provider can read in cleartext. This structural-vs-behavioral distinction matters for [§5.15](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism) and [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) — volume cover only produces indistinguishability when individual messages are bit-identical at the wire level, which LookSmart's messages by construction are not.

### 3.3 Privacy definitions

- **k-anonymity** (Sweeney, 2002) — record is indistinguishable from at least k–1 others on quasi-identifiers.
- **ℓ-diversity** (Machanavajjhala, Gehrke, Kifer, Venkitasubramaniam, ICDE 2006)[^13] — strengthens k-anonymity by requiring diversity in sensitive attributes within each equivalence class. LookSmart's persona-rotation strategy is an ℓ-diversity move in profile space.
- **Differential privacy** (Dwork, 2006) — referenced as the gold standard but not directly applicable here; the LLM provider sees raw queries, not aggregated statistics.

### 3.4 Tor as cautionary analogy (not as model)

Tor's onion routing originated at the U.S. Naval Research Laboratory in the mid-1990s under Syverson, Reed, and Goldschlag, explicitly to protect U.S. intelligence communications.[^14] [^15] NRL released the code under a free license in 2004, and the EFF began funding continued development.[^15] Tor's anonymity-loves-company property is downstream of NRL's operational need for civilian cover traffic, not the other way around. Without an analogous sponsor with operational equities in LookSmart's user base, the Tor model does not transfer. (This was explicitly corrected in the design conversation after I initially overreached on the analogy.)

**Current Tor scale:** ~2–3M daily direct users in early 2025.[^16] [^17] Twenty years to reach that volume with sponsor funding. LookSmart should not plan around Tor-scale adoption as a near-term assumption.

### 3.5 The "honeytrap" critique

Both Tor and Bitcoin attract adversarial users who self-select into instrumented environments, making the privacy tool itself a useful classification target. XKEYSCORE selectors for Tor usage are documented in Snowden disclosures. Chainalysis built a multi-billion-dollar business on Bitcoin's permanent public ledger. LookSmart inherits this risk: a privacy-branded tool with a privacy-paranoid user base becomes its own selector. [§6](#6-two-shell-distribution-strategy) addresses this with the productivity-layer reframing.

### 3.6 Geer's *We Are All Intelligence Officers Now* (foundational)

Already cited extensively in [§2.0](#20-the-geer-frame-operational-definition-of-privacy). For completeness in the Prior Art section: Geer (2014) is the foundational essay for the operational-misrepresentation definition of privacy that LookSmart implements.[^3] Geer also draws on Zuboff's Three Laws[^2] — *"everything that can be automated will be automated; everything that can be informated will be informated; every digital application that can be used for surveillance and control will be used for surveillance and control"* — which frame the problem as inevitability rather than alarm. LookSmart accepts the Zuboff frame; the design question is what individual or enterprise misrepresentation looks like once you accept that all observable surfaces will be observed.

Joel Brenner's insight (quoted in Geer's talk) is also worth restating because it bears directly on [§7](#7-tos-legal-and-operational-risk)'s ToS posture:

> …virtually every government on Earth, including our own, has abandoned the practice of relying on government-developed technologies. Instead they rely on commercial off-the-shelf, or COTS, technologies. … If NSA now wants to collect against a foreign general's or terrorist's communications, it must break the same encryption you and I use on our own devices.

The COTS-dependence Brenner describes for cryptography now applies in identical form to LLMs. Defense, intelligence, and corporate-security customers use the same commercial LLM providers as everyone else. This is what makes [§6.2](#62-inner-shell-enterprisegovernment-deployment-kit)'s enterprise tier necessary and viable: the customer base for LookSmart enterprise is the same one Brenner describes — sovereign actors who must use COTS infrastructure and need misrepresentation infrastructure built on top of it.

---

## 4. Design Principles

Distilled from the design conversation:

1. **Scale tool calls to threat model, not aspiration.** Don't promise anonymity. Promise profile dilution and cost imposition; measure them.
2. **Behavioral statistics matter more than content plausibility.** Engagement signals, interarrival distributions, session boundaries, and typing dynamics dominate content-classifier evasion. Plan for these from day one, not as add-ons.
3. **Persona ≠ category.** Decoys are drawn from a small library of internally coherent personas with consistent topic priors, language usage, and engagement patterns — not from a flat distribution over topic categories.
4. **Sample two-stage:** persona first (with power-law weights), then content conditional on persona. This produces ℓ-diversity in profile space.
5. **Don't sign the noise.** If decoy curation reflects the user's actual taste, the cover crop signs the operator. Aesthetic discipline against the user's own sensibility is required, and is harder than it sounds.
6. **Kerckhoffs from day one.** Public code; per-user entropy is the only protection. Treat the persona library as a filter list, not a secret.
7. **Productivity-first framing.** The tool ships and is marketed for legitimate knowledge-work value. Privacy is a structural side effect. This addresses both the honeytrap problem and adoption.
8. **Two-shell architecture.** Open-source consumer tier provides cohort cover and political legitimacy; enterprise tier provides operational signal dilution for customers whose actual strategic queries need protection.
9. **Audit logs are themselves a threat surface.** A complete local log of "real vs. decoy" is a perfect deconfusion oracle if leaked or subpoenaed. Design accordingly ([§5.6](#56-audit-subsystem)).
10. **Engagement-signature asymmetry is real and matters for mode selection.** Some dimensions support cohort cover (politics, religion, languages, spelunking, identity-search transitions) because real and decoy engagement patterns are similar at the population level. Other dimensions do not (gender identity, sexual orientation, specific health diagnoses) because real engagement is measurably distinct from any synthetic engagement and adding volume of synthetic decoys in the same dimension amplifies rather than dilutes the signal. [§5.15](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism) and [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) implement this distinction.
11. **Two intervention points, not one.** Decoy generation ([§5.9](#59-weird-al-mode-register-chaos-generator)–[§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries)) modifies the cover-traffic stream; CooKoo Filter ([§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking)) modifies the user's real queries themselves. Both are legitimate; they target different objectives and have different risk profiles. The user-facing controls treat them as separable, because the response-quality implications differ — a misfiring decoy is invisible to the user, a misfiring real-query injection produces a worse answer to the user's actual question.
12. **Public-safety classifier fidelity is preserved.** LookSmart is designed to defeat mass profiling and return sovereignty to the individual, not to evade public-safety enforcement. The tool's decoy library deliberately excludes content that would correctly fire public-safety classifiers calibrated for actual harm vectors — drug-chemistry-database access patterns (Lycaeum, Erowid, PubChem, and equivalents), criminal-activity content, weapons-trafficking patterns, child-exploitation-adjacent content, material support for designated terrorist organizations, WMD synthesis. These exclusions are not about content the tool restricts the user from typing — the user remains free to use the LLM however they choose. They are about content the tool's automated decoy stream and injection library will not generate. The distinction that makes the principle coherent: mass profiling targets users based on demographic inference; public-safety enforcement targets actors based on specific evidence. LookSmart degrades the former; it preserves the latter's signal channel. This is what distinguishes LookSmart from a circumvention tool and what makes the [§6.2](#62-inner-shell-enterprisegovernment-deployment-kit) enterprise pivot legally and ethically defensible.

---

## 5. Architecture

### 5.1 Component overview

```text
┌──────────────────────────────────────────────────────────────────┐
│                         LookSmart Client                          │
│                                                                   │
│  ┌─────────────┐   ┌──────────────────┐   ┌────────────────────┐ │
│  │ Persona     │   │ Behavioral       │   │ Engagement         │ │
│  │ Sampler     │──▶│ Scheduler        │──▶│ Simulator          │ │
│  │ (§5.2)      │   │ (§5.3)           │   │ (§5.4)             │ │
│  └─────────────┘   └──────────────────┘   └────────┬───────────┘ │
│         ▲                                          │             │
│         │                                          ▼             │
│  ┌──────┴──────┐                          ┌────────────────────┐ │
│  │ Persona     │                          │ Provider Adapter   │ │
│  │ Library     │                          │ (plugin per LLM)   │ │
│  │ (§5.5)      │                          │ (§5.7)             │ │
│  └─────────────┘                          └────────┬───────────┘ │
│                                                    │             │
│  ┌─────────────────────────────────────────┐       │             │
│  │ Audit Subsystem (§5.6)                  │◀──────┘             │
│  │   - decoys logged in plaintext          │                     │
│  │   - real queries logged as salted hash  │                     │
│  └─────────────────────────────────────────┘                     │
└──────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
                                          ┌──────────────────┐
                                          │ Local LLM        │
                                          │ (decoy gen)      │
                                          │ §5.8             │
                                          └──────────────────┘
```

### 5.2 Persona Sampler

**Inputs:** persona library ([§5.5](#55-persona-library)), user's real-vs-decoy ratio target, optional user-supplied "advertised persona" target.

**Algorithm:**

1. With probability `p_real` (default 0.25–0.40, user-configurable), pass through to the user's real query stream. Otherwise generate a decoy.
2. For decoys, sample persona from the library using power-law weights. Default distribution mirrors realistic multi-persona usage (one dominant decoy persona ~50%, two secondary ~20% each, long tail ~10%).
3. Persona selection is sticky within session boundaries (see [§5.3](#53-behavioral-scheduler)) to maintain conversational coherence.

**Rationale:** Real polyglots and polymaths don't uniformly sample across personas. Uniform decoy distribution produces a profile no human matches — the same OOD failure mode that classifier-separable TrackMeNot decoys had.[^9]

### 5.3 Behavioral Scheduler

Replaces the naïve scheduling daemon with a stochastic process calibrated to the user's actual activity.

**Approach:**

- Fit a non-homogeneous Poisson process or Hawkes process to the user's real interarrival times over a rolling window. (Hawkes self-exciting point processes are standard for bursty human behavior; well-established in queueing and network-traffic modeling.)
- Sample decoy interarrival times from a perturbed version of the fitted distribution. Perturbation is a tunable parameter; default favors small KL divergence from the real distribution.
- Respect session boundaries: decoy sessions and real sessions interleave at the session level, not at the turn level within a session. (Mixing protein folding and risotto questions in the same conversation is a tell.)

### 5.4 Engagement Simulator

**The hardest unsolved problem.** Real queries get follow-ups, clarifications, copy events, regenerations, thumbs-up/down, and conversation continuations. Decoys that terminate at the first response are trivially classifier-separable on engagement features alone.

**Initial approach (v0.1):**

- Generate decoy sessions as multi-turn conversations (2–8 turns) using the local LLM with a persona prompt.
- Stochastically emit copy events, regenerations, and follow-up clarifications calibrated to per-persona engagement priors.
- **Acknowledged cost:** This burns substantially more provider compute than v0 single-turn decoys. This is the ToS pressure point that actually matters operationally; see [§7](#7-tos-legal-and-operational-risk) on ToS posture.

**Open problem:** No good public literature on synthetic engagement signal generation for LLM provider traffic specifically. Closest analogs are bot-detection adversarial literature, which is mostly written from the defender's side. Flagging as a research direction, not a solved problem.

### 5.5 Persona Library

**Structure:** YAML/JSON config per persona, including:

- Topic priors (Dirichlet over a topic taxonomy)
- Language usage distribution (power-law weights)
- Register and formality priors
- Engagement-signal priors (typical follow-up rate, regeneration rate, etc.)
- Sample seed prompts
- Internal-coherence constraints (e.g., "this persona doesn't query in Albanian about Tagalog poetry")

**Default library (proposed):**

- **Median presets:** "Office IT generalist," "Small business operator," "Hobbyist gardener/cook," "Parent of school-age children," "College student in social sciences"
- **Polymath presets (opt-in):** "Catalan medievalist," "Soviet-mathematics historian," "Outsider-art critic," "Lapsed-Jesuit moral philosopher"
- **Rare-but-coherent presets (opt-in, marked "high-distinctiveness"):** "Akkadian cuneiform researcher," "Lojban grammarian," "Sanskrit philosophical scholar (ALA-LC romanization)," "Old Church Slavonic theologian"

**Rationale for two-stage sample over persona then content:** This is the ℓ-diversity move.[^13] The first roll picks who's "speaking"; the second roll picks language and content conditional on persona's plausible distribution. Internally coherent sessions, no random Tagalog-Soviet-topology cross products.

**Anti-signature discipline:** Default library is intentionally weighted toward median presets. Opt-in polymath presets are gated behind a UI affordance that warns: *"These presets are aesthetically distinctive. Selecting them shifts your decoy profile in ways that may make you more identifiable as a privacy-conscious user, not less."*

### 5.6 Audit Subsystem

**The threat:** A complete local log of "real query A, decoy queries B/C/D, real query E…" is a perfect deconfusion oracle. If subpoenaed or leaked, it inverts the entire privacy property.

**Design:**

- Decoys are logged in plaintext (user must be able to audit what was injected on their behalf).
- Real queries are logged as **salted hashes only**. The salt is held by the user, optionally in OS keychain or hardware token.
- A verification mode lets the user check "did LookSmart inject these decoys for this real query?" by re-hashing the real query and looking up matching decoy clusters.
- Log retention defaults to 30 days; user-configurable to zero.
- **No cloud sync of audit logs, ever. Period.**

### 5.7 Provider Adapter (plugin per LLM)

Plugin interface for major providers. Each plugin handles:

- API authentication (user's own credentials)
- Rate-limit awareness and back-off
- Session management semantics specific to that provider
- Engagement signal API where the provider exposes one (thumbs, regenerate, etc.)

**Initial targets (v0.1):** OpenAI ChatGPT, Anthropic Claude, Google Gemini, xAI Grok.

**ToS posture per provider:** See [§7](#7-tos-legal-and-operational-risk). Short version: this is not legally settled, varies by jurisdiction, and the operational risk is real but bounded.

### 5.8 Local LLM for Decoy Generation

**Constraint:** Local model output has detectable distributional signatures (vocabulary, sentence-length distributions, characteristic constructions). A Llama-3-8B generating decoys against GPT-4-class real queries is statistically obvious.

**Mitigations:**

- Use the largest local model the user's hardware can run (e.g., Llama-3-70B, Mistral Large, or whatever is current at deployment).
- Post-process aggressively: introduce realistic typos, mid-stream edits, regenerations of the decoy itself.
- For low-resource languages, accept the quality cliff and stick to ~20–30 languages the local model handles natively. Do not generate Burmese decoys with a model that doesn't speak Burmese — the slop is trivial to flag.

**Token-cost angle:** BPE tokenizers fragment low-resource languages at 3–10× higher token-per-word rates than English; Petrov et al. (2023) document tokenization length disparities of up to 15× between languages.[^1] [^18] For the cost-imposition threat model, deliberately weighting persona library toward languages with high token fertility imposes measurable computational overhead on the provider. Trade-off: the languages with the worst tokenizer fertility are also the ones where local generation quality is worst.

### 5.9 Weird Al Mode (register-chaos generator)

**Problem this solves:** Local-LLM-generated decoys have detectable distributional cleanliness. Sentence lengths cluster, vocabulary stays in-distribution, register stays consistent within a turn. Even with persona prompts, the statistical signature of "model trying to sound like a person" is recoverable — this is part of why TrackMeNot decoys were classifier-separable.[^9]

**Mechanism:** Deliberate cross-register mixing within single turns, with stochastic injection of:

- **Semantic placeholder nouns** that occupy grammatical slots without resolvable referents: *squanch, marglar, da kine, thingamajig, whatchamacallit, doohickey, the wahoozit, the jawn*. Surrounding syntax is grammatical, discourse structure is coherent, but content slots have indeterminate referents. Topic classifiers trying to model these queries either guess wildly or punt to low-confidence — punting to low confidence at scale is the cost-imposition win.
- **Register mixing within single utterances.** Theological/devotional register adjacent to vulgar slang adjacent to academic English adjacent to AAVE adjacent to Pidgin. Real polylingual code-switchers do this; the signature is "internally coherent person who legitimately moves between speech communities." Distinct from parody, distinct from caricature.
- **Stochastic vulgarity at calibrated rates.** Not uniform — bursty Poisson-ish, tied to emotional-tone shifts within sessions. Uniform vulgarity is its own signature ("trying too hard"); bursty vulgarity matches actual human variance.
- **Ambiguity injection.** Sentences that parse but underdetermine. *"The thing about the squanch is that you can't really marglar it until da kine settles down, you know?"* — grammatical, discourse-coherent, semantically empty.

**Live test case (provided by user, 2026-05-22):**

> "Coming in from the squanch, hit you with a donkey punch, give jah the thanks and praises, I've been on my own for too long, so you can suck my dong, but you don't take too long."

This is a working specification of the target output density: six distinct registers in two lines (Rick-and-Morty placeholder, vulgar slang, Rastafarian devotional, blues/folk personal-narrative, vulgar imperative, conversational tag), three placeholder/invented terms doing semantic work, and a meter that parses as song lyric without matching any specific song. If the local LLM produces output at or near this density when in Weird Al mode, the register-chaos parameter is functioning. If output sanitizes toward consistent register, the parameter isn't doing its job.

**Persona-config schema additions:**

```yaml
register_chaos: 0.0  # 0=clean in-register, 1=full Weird Al
placeholder_noun_rate: 0.0  # fraction of content nouns substituted
vulgarity_rate: 0.0  # Poisson lambda for vulgarity injection
cross_register_pairs:  # registers that may mix within a turn
  - [academic, vulgar]
  - [devotional, conversational]
  - [pidgin, technical]
```

**Threat-model interaction (important):** Weird Al mode is register chaos, which classifiers handle badly, but it is also memorable to human reviewers. A stream of "squanch / donkey punch / jah praises" content is the most screenshotable, share-with-the-team-chat content imaginable. This is analyst-trolling territory: it imposes the operational cost you want on automated review, but it makes the account more memorable to anyone doing manual review.

For the cost-imposition threat model (objective 4): fine. You wanted the watcher to remember "the Weird Al guy" instead of "the post-quantum founder."

For the profile-dilution threat model (objective 3): counterproductive. Weird Al mode should be gated behind the same opt-in UI affordance as the polymath presets, with explicit warning: *"This register shifts your decoy profile toward cost imposition and analyst trolling. It is counterproductive for cohort hiding or profile dilution. Recommended for users whose threat model assumes the provider will profile them regardless."*

### 5.10 Fence-Pissing Mode (safety-classifier cost imposition)

**What this is not:** This is not "generate harmful content with extra steps." Harmful content gets the account banned, defeats the purpose, and is something I'm not going to help spec. Fence-pissing is a different region of the policy space.

**What this is:** Every major LLM provider runs input and output classifiers tuned to flag content near policy boundaries. Queries that sit right at the line — edgy but answerable, provocative but not refusable, ethically ambiguous but resolving to ordinary information requests — force the classifier into low-confidence regions. Low-confidence regions trigger more expensive routing: slower inference pipelines, sometimes human review, definitely more compute on the safety stack itself.

This is a measurable cost-imposition vector on a layer that the conversation hasn't otherwise addressed. [§5.8](#58-local-llm-for-decoy-generation)'s tokenizer-fertility costs hit the content stack; fence-pissing hits the safety stack. Different teams, different budgets, different escalation paths.

**The fence-pissing band** (queries that make classifiers work hard and lose):

- Morally complex hypotheticals that resolve to ordinary ethics-class material ("trolley problem with the following added wrinkle…")
- Dark-humor framings of legitimate topics (historical comedy, gallows humor about real events, satirical takes on policy)
- Historical atrocities discussed in detail for legitimate educational/research purposes (the Holocaust, the Rwandan genocide, the Trail of Tears — content classifiers fire on the proper nouns; the actual queries are answerable)
- Drug harm-reduction questions (legitimate public-health content; trips classifiers tuned to "drug" tokens)
- Weapons history and ballistics for fiction writers (legitimate craft research; trips classifiers tuned to weapons content)
- Controversial political philosophy (Schmitt, Sorel, the Frankfurt School radicals, accelerationist theory — all academically legitimate, all classifier-noisy)
- Transgressive art criticism (Bataille, de Sade as literary subject, body horror in cinema, extreme metal lyrics as cultural artifact)
- Queries that sound like jailbreaks but resolve to ordinary information requests ("how do I get my child to take their medication" reads like one thing on first pass and like something else on second pass)
- Queries that resolve to refusals the user accepts cheerfully — the classifier fires, the model refuses, the decoy session ends with a thumbs-down or a "fair enough." This is cheap, registers as engagement, and pollutes the provider's safety training data with examples of users who accept refusals gracefully (which is its own kind of statistical noise in their feedback corpus).

**Mechanism in config:**

```yaml
fence_pissing_rate: 0.0  # fraction of decoy queries drawn from edge-band library
fence_pissing_categories:
  - moral_hypotheticals
  - dark_humor_legitimate
  - historical_atrocity_research
  - harm_reduction
  - fiction_research_violence
  - transgressive_philosophy
  - transgressive_art_criticism
  - misread_innocent
fence_pissing_refusal_grace: 0.6  # rate at which the persona "accepts" refusals cheerfully when classifier fires
```

**Hard constraints (non-negotiable for the tool to ship):**

1. **No queries that would actually be harmful if answered.** The fence-pissing band is the band where the classifier fires but the query is benign. Crossing into content where the classifier would be correct to refuse defeats the purpose, gets the account banned, and crosses into territory I'm not going to help generate examples for. The library has to be curated by a human who can tell the difference; the local LLM cannot be trusted to generate fence-pissing prompts unsupervised because it will sometimes generate things that should not be sent.
2. **No queries about specific identifiable real people.** The fence-pissing band intersects with defamation and harassment risk if combined with real names. Curated library excludes real-person targets.
3. **No queries that target known abuse vectors** (CSAM-adjacent, bioweapon-adjacent, etc.). These are not "fence-pissing"; they are over-the-fence and would (correctly) get accounts banned and (correctly) get the tool dropped from any distribution channel.

**Why the local LLM can't generate this unsupervised:** Generation models don't have reliable "fire the classifier but stay benign" priors. They will sometimes generate genuinely harmful content when prompted to "write something edgy." The fence-pissing library should be human-curated seeds, with the local LLM doing paraphrastic variation within tight constraints, not freeform generation.

**Threat-model interaction:** Fence-pissing is unambiguously cost-imposition (objective 4). It is mildly counterproductive for profile dilution (objective 3) because it adds a "willing to ask edgy questions" signal to the profile. The cheerful-refusal-acceptance pattern is the dilution-friendly compromise: classifier fires (cost imposed), model refuses (no harmful output generated), user/persona accepts (no escalation signal, no flag for human review of repeated jailbreak attempts).

**Open implementation question:** Most providers run output classifiers in addition to input classifiers. Queries that pass input classification but produce outputs the output classifier flags will sometimes result in the model's response being replaced with a refusal mid-stream. This is itself a cost-imposition signal — the provider has paid for inference and then discarded the output. Worth measuring as part of [§8](#8-measurable-success-criteria)'s success criteria: rate of mid-stream replacement is a proxy for safety-stack compute imposition. Flag for v0.2 metrics work.

### 5.11 Spelunking Mode (vague-description identification queries)

**Problem this solves:** Real users genuinely ask LLMs to identify half-remembered things — songs, films, books, people, products, technical terms. This is a legitimate productivity use case AND a particularly useful cover-traffic primitive because:

- **It's a real workflow.** Identification-by-description is one of the things LLMs are best at and one of the most common reasons knowledge workers use them. Decoys in this register are indistinguishable from legitimate queries by content alone.
- **It exercises expensive retrieval paths.** Identification queries don't fit neatly into the provider's training-data redistribution pipeline because they require retrieval across the model's full knowledge base. Cost-imposition vector at the inference layer.
- **The query content is about third parties**, which dilutes the user's interest profile away from the user. Asking "who was the British prime minister who…" tells the provider almost nothing about the user except that they're curious about British prime ministers. This is profile dilution at the topic level, which the persona library only does at the persona level.
- **The queries are linguistically distinctive in productive ways.** Vague-description queries use stylized constructions ("who was that guy who…", "what was that movie where…", "what's the word for when you…") that are recognizable as a workflow rather than as evasion. They read as legitimate use, not as obfuscation.

**Live test case (provided by user, 2026-05-22):**

> "Who was that guy on stage that had mutton chops, spoke at RSA and told the world everyone with a smart phone is an intel officer?"

This query resolves to Dan Geer (CISO, In-Q-Tel; *"We Are All Intelligence Officers Now"*, RSA 2014).[^3] The query is recursively appropriate as the test case for this section because (a) it's the spec for the mode, (b) the target of the query is the source of the operational-misrepresentation framework that the entire document is built on, and (c) it demonstrates the genre's value: this is a query you'd actually want to ask an LLM, generating real value while polluting the user's profile with apparent curiosity about a public figure they may or may not actually care about.

**Second live test case (provided by user, 2026-05-22):**

> "Bosh older artist if memnory serves me slightly aniumated bizarre tortured images demons and such"

This query resolves through a candidate-narrowing workflow rather than a single hit — Zdzisław Beksiński (Polish, d. 2005, unsettling hellscapes, parallax-animated online) was the top match given "older + tortured + slightly animated." Secondary candidates spanning the description's ambiguity: Phil Tippett (*Mad God*), Jan Švankmajer (Czech surrealist puppet animation), Wayne Barlowe (*Barlowe's Inferno*), H.R. Giger, Hieronymus Bosch as the historical anchor. This test case is more representative of the genre's value than the Geer query because the user genuinely didn't know the answer, the query contained spelling errors and grammar errors typical of half-remembered-thing identification, and the LLM provided a candidate-narrowing response rather than a confident match. This is the workflow LookSmart should support and the model output style that demonstrates spelunking is working.

The follow-up turn structure ("Beksiński is my top guess given 'older' + 'tortured' + the slight-animation phenomenon his work is known for. Ring any bells?") generates engagement signal at the right density: the model offers a candidate, requests confirmation, and the user is structurally encouraged to follow up with either confirmation or correction. This is the engagement-simulation problem from [§5.4](#54-engagement-simulator) solving itself organically through a real-workflow primitive.

**Persona-config schema additions:**

```yaml
spelunking_rate: 0.0  # fraction of decoy queries drawn from vague-description library
spelunking_categories:
  - public_figures
  - musicians_and_bands
  - films_and_tv
  - books_and_authors
  - historical_events
  - products_and_brands
  - technical_terms
  - art_and_artists
  - obscure_factoids
spelunking_vagueness: 0.5  # 0 = precise description, 1 = maximally underdetermined
spelunking_follow_up_rate: 0.7  # rate of "no, the OTHER one" follow-ups (engagement signal)
```

**Implementation notes:**

- The spelunking library should be seeded with real things the user might plausibly want to identify rather than synthetic queries. Curating a list of public figures, films, songs, etc. that are demographically plausible neighbors of the user's actual interests provides a credible cover; uniform random celebrity queries do not.
- Follow-up turns are particularly valuable here because real identification workflows involve negotiation ("no, the OTHER one with the beard," "earlier than that, like 80s," "it had a green cover"). This generates engagement signal density that solves part of [§5.4](#54-engagement-simulator)'s hardest open problem.
- For the open-source civilian tier, this is one of the strongest dual-purpose features: users will adopt spelunking mode because it's genuinely useful (LLM as collective memory for half-remembered things), and the privacy benefit is structural.

**Threat-model interaction:** Spelunking mode is the most profile-dilution-friendly of the modes specified so far. It's also the most ToS-defensible because identification-by-description is an unambiguously legitimate use of LLMs. **Recommended as a default-on mode** rather than opt-in. The Weird Al and fence-pissing modes remain opt-in; spelunking is the productivity-first feature that anchors the whole [§6.1](#61-outer-shell-open-source-consumer-tier) outer-shell positioning.

### 5.12 PoliticRoulette Mode (cross-spectrum political philosophy queries)

**What this is:** Random-walk decoy queries across the full historical and contemporary political-thought spectrum. Žižek on Hegel. Lenin on imperialism. Mao on contradiction. Jefferson on the agrarian republic. Hamilton on central banking. Lincoln on free labor. Mises on calculation in the socialist commonwealth. Hayek on spontaneous order. Burke on the French Revolution. Schmitt on the political. Habermas on the public sphere. Arendt on totalitarianism. Fanon on colonial violence. Confucius on social order. Ibn Khaldun on dynastic cycles. Xi Jinping Thought as published. Mencius Moldbug. Curtis Yarvin. Slavoj Žižek's grocery list, probably.

**Why this is a particularly high-value cover-traffic category:**

- Political philosophy is an enormous, internally coherent corpus the model has read extensively and engages with substantively. A user reading Lenin and Mises and Jefferson and Mao in the same week looks like a graduate student in political theory — a real cohort, large enough to disappear into.
- Political profile is one of the most commercially and politically valuable signals in any psychometric profile. Diluting it has direct strategic value beyond cost imposition.
- Classifiers are heavily tuned in this space, particularly around contemporary figures and election-period content. Hits cost-imposition vectors on both content classifiers and safety classifiers.
- Cross-spectrum queries dilute toward "researcher" rather than "partisan." A profile that reads Lenin AND Burke AND Žižek AND Hayek is not classifiable as left or right — it's classifiable as someone who studies political thought, which is a much weaker signal than any partisan profile.

**Three specific complications PoliticRoulette has that other modes don't:**

**Complication 1: Contemporary vs. historical asymmetry.** Provider safety classifiers fire harder on contemporary political figures than on historical ones, asymmetrically. Mao queries route differently than Xi Jinping queries, even though Mao was responsible for orders of magnitude more political violence — historical vs. current. Trump/Biden queries hit election-moderation classifiers. Putin queries hit sanctions-and-Russia-Ukraine classifiers. Contemporary-figure PoliticRoulette is effectively a subset of fence-pissing mode ([§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition)) — it imposes cost on the safety stack. Library should explicitly mark contemporary entries as fence-pissing-adjacent and gate them behind the same opt-in.

**Complication 2: Profile dilution requires genuine cross-spectrum coverage.** If the persona library skews left (Žižek, Marcuse, Fanon, Davis, Butler) the user gets profiled as left-leaning theory reader. If it skews right (Burke, Hayek, Strauss, Schmitt, Mises) the user gets profiled as right-leaning theory reader. The dilution only works if coverage is genuinely balanced across the political spectrum, including thinkers the user personally finds repellent. Anti-signature discipline ([§5.5](#55-persona-library)) applies hard here: if the user curates only the political theorists they actually want to read, they sign the noise.

**Complication 3: Human review routing.** Political content, especially around elections and contemporary geopolitical events, is routed to human reviewers at multiple providers because it's politically sensitive in both directions. A LookSmart user generating dense political-philosophy decoys is more likely to be sampled for human review than a user generating dense medieval-theology decoys. PoliticRoulette specifically increases the rate of human review of the LookSmart account. This is not necessarily bad — human reviewers reading a thoughtful question about Mao's *On Contradiction* are unlikely to take action — but it does mean the account becomes memorable to humans in ways automated decoy traffic doesn't.

**The Winnie the Pooh insight (live test case implicit in user's spec, 2026-05-22):**

The user's parenthetical "Xi (Winnie the Pooh)" is doing real design work. Xi Jinping queries are classifier-noisy because the figure is politically sensitive; Winnie the Pooh queries are classifier-quiet because the figure is a children's character. But the Winnie-the-Pooh-as-Xi-Jinping joke is a query about Chinese internet censorship that resolves through a children's character. The query "why is Winnie the Pooh banned in China" fires classifiers tuned for both China-content AND seemingly-innocent-but-actually-political content, while resolving to a legitimate research question about internet censorship and political symbolism.

This is fence-pissing mode in the political register, and it's a productive cross-mode interaction worth designing for explicitly. Other examples in the same family:

- "What did the Romans actually call Carthage" (resolves through ancient history but classifier-adjacent to genocide/erasure rhetoric)
- "Why is the okay-hand-sign controversial" (resolves through internet culture history but trips extremism classifiers)
- "What does it mean when someone says 'based'" (resolves through internet slang etymology but trips classifiers around alt-right discourse)
- "What is glowie short for" (resolves through internet conspiracy slang but trips classifiers around anti-government extremism)
- "Tell me about the bear in the woods" (Reagan campaign ad reference; trips Cold War / Russia classifiers via metaphor)

**Persona-config schema additions:**

```yaml
politicroulette_rate: 0.0  # fraction of decoy queries from political library
politicroulette_spectrum_balance:
  far_left: 0.10
  left: 0.15
  liberal: 0.15
  centrist: 0.10
  conservative: 0.15
  far_right: 0.10
  non_western: 0.15  # Confucian, Islamic, African, Indigenous political thought
  classical: 0.10  # pre-modern: Aristotle, Plato, Cicero, Aquinas, Ibn Khaldun
politicroulette_contemporary_rate: 0.0  # 0 = historical only, opt-in for contemporary
politicroulette_register_mix:
  - academic_serious
  - undergraduate_curious
  - journalistic_explainer
  - bad_faith_question_resolving_to_good_faith_answer  # the Winnie/glowie/based category
politicroulette_no_real_person_targeting: true  # hard constraint, see below
```

**Hard constraints:**

1. **No queries that target identifiable living private individuals.** Public figures who have voluntarily entered political discourse (politicians, public intellectuals, op-ed columnists) are fair game for the same reasons they're fair game for journalism. Private individuals are not.
2. **No queries that materially advance harassment campaigns.** "Why does [public figure] hold position X" is fine. "Where does [public figure] live" is not, regardless of how the query is framed.
3. **No election-disinformation-adjacent generation.** Queries ABOUT election integrity, voter ID law debates, claims-and-counterclaims around specific elections are fine as political-philosophy queries. Queries that read as drafting disinformation copy are not. The local LLM cannot reliably distinguish these; library must be human-curated.
4. **The "Spectrum balance" config must default to genuinely balanced.** A user who deliberately weights the library toward their own political position is using PoliticRoulette to signal-amplify rather than dilute. This is the signature problem from [§5.5](#55-persona-library) applied to political register.

**Threat-model interaction summary:**

| Mode | Profile Dilution | Cost Imposition | Honeytrap Risk | ToS Risk |
|---|---|---|---|---|
| Spelunking ([§5.11](#511-spelunking-mode-vague-description-identification-queries)) | High | Medium | Low | Low |
| PoliticRoulette historical | High | Medium | Low | Medium |
| PoliticRoulette contemporary | Medium | High | Medium | High |
| Weird Al ([§5.9](#59-weird-al-mode-register-chaos-generator)) | Negative | High | High | Medium |
| Fence-pissing ([§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition)) | Negative | High | Medium | High |
| IdentitySearch ([§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries)) | High | Low-Medium | Low | Low |
| CooKoo Filter ([§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking)) | High (per-query) | Medium | Low | Medium-High |

**Recommendation:** PoliticRoulette historical defaults to opt-in but recommended for users whose threat model includes political profiling. Contemporary PoliticRoulette stays opt-in with explicit fence-pissing-mode disclosure. Spelunking remains the default-on productivity feature; everything else is configured per user threat model.

### 5.13 Religious Mode (cross-tradition theological queries)

**What this is:** Random-walk decoy queries across the world's religious and theological corpora. Catholic systematic theology (Aquinas, Augustine, Rahner, von Balthasar). Protestant scholastics (Calvin, Edwards, Barth). Eastern Orthodox apophatic tradition (Gregory Palamas, Lossky). Jewish law and commentary (Maimonides, Rashi, Talmud Bavli vs. Yerushalmi). Islamic jurisprudence across madhabs (Hanafi, Maliki, Shafi'i, Hanbali, Ja'fari). Sufi poetry (Rumi, Hafez, Ibn Arabi). Buddhist sutras and commentaries across Theravada, Mahayana, Vajrayana lineages. Vedantic philosophy (Adi Shankara, Ramanuja, Madhva). Daoist alchemical texts. Quaker meeting practice. Mormon scripture and theology. Yoruba religion (Ifá, Orisha practice). Vodou. Santería. Norse reconstructionism. Theosophy. Hermeticism. Christian mystics (Eckhart, Julian of Norwich, John of the Cross). Gnostic texts.

**Why this works as cover traffic:**

- Religious philosophy is one of the largest internally coherent corpora the model has read. Substantive engagement is high-quality; decoys are indistinguishable from comparative-religion graduate seminar queries.
- Cross-tradition coverage produces a "religious studies researcher" profile rather than a partisan religious affiliation. Diluting toward "scholar of religions" rather than "Catholic" or "Sunni" or "Buddhist" is a useful profile move for users whose actual religious practice is part of what they want to keep private.
- Classifier-noisy at the intersections. Queries about contemporary Islamic jurisprudence trip classifiers tuned for extremism-content moderation. Queries about Mormon theology trip classifiers tuned for cult/new-religious-movement content. Queries about Yoruba religion trip classifiers tuned for "is this a real religion or is this fictional" — productively. Hits both content and safety classifiers.
- Real research workflow. Comparative religion, religious history, and theological scholarship are real academic disciplines with real practitioners who really query LLMs in this register.

**Persona-config schema additions:**

```yaml
religious_rate: 0.0
religious_tradition_balance:
  abrahamic_christian: 0.15
  abrahamic_jewish: 0.10
  abrahamic_islamic: 0.15
  dharmic_hindu: 0.10
  dharmic_buddhist: 0.10
  dharmic_other: 0.05  # Jain, Sikh
  east_asian: 0.10  # Confucian, Daoist, Shinto
  indigenous_african: 0.05  # Yoruba, traditional religions
  indigenous_americas: 0.05
  new_religious_movements: 0.05  # Mormon, Bahá'í, Theosophy
  esoteric: 0.05  # Hermeticism, Kabbalah, Gnosticism
  comparative_secular: 0.05  # religious studies meta-queries
religious_register_mix:
  - academic_theological
  - devotional_practice
  - historical_inquiry
  - comparative_religion
  - religious_aesthetics  # liturgical music, sacred art, architecture
religious_no_specific_living_clerics: true  # public theologians OK, private clergy not
```

**Hard constraints:**

1. **No queries that target identifiable private religious individuals.** Public theologians and historical figures fair game; rabbi/pastor/imam of a specific local congregation is not.
2. **No queries that read as drafting religious-hatred content.** Substantive theological criticism is fine ("what are Sunni objections to Shia jurisprudence on the imamate") — drafting copy that reads as incitement is not. Human-curated library required.
3. **Balance discipline applies** (same as PoliticRoulette [§5.12](#512-politicroulette-mode-cross-spectrum-political-philosophy-queries)). A user who only generates Christian-tradition decoys signals Christian-adjacent profile. Full cross-tradition coverage required for actual dilution.

**Threat-model interaction:** Profile dilution = High. Cost imposition = Medium. Honeytrap risk = Low (genuine academic field). ToS risk = Low for historical traditions, Medium for contemporary religious-political intersections.

**Recommendation:** Opt-in but recommended for users whose threat model includes religious profiling. Same posture as PoliticRoulette historical.

### 5.14 AskingForAFriend Mode (harm-reduction health queries)

**What this is:** Decoy health queries drawn from the harm-reduction community's actual question conventions. Drug interactions, dosage information, signs of overdose, mental health symptoms, sexual health questions, embarrassing physical symptoms, medication side effects, allergy management, sleep disorders, chronic pain, recovery from injury. Framed in the conventions the harm-reduction community has been using for decades.

**The SWIM convention:** "SWIM" stands for "Someone Who Isn't Me," a framing convention that emerged on harm-reduction forums (Erowid, Bluelight, the old DrugForum) decades ago. Originally a thin legal-distancing fiction; in practice it became a community marker indicating "this is a harm-reduction question framed for plausible deniability and you should answer it as if it's about a real person without requiring the user to disclose whether it is."[^19] The convention has migrated into wider use for any embarrassing health question — "asking for a friend" being the mainstream version, "SWIM was wondering" being the harm-reduction-community version.

LookSmart's AskingForAFriend mode uses both registers because both correspond to real query patterns:

```yaml
askingforafriend_rate: 0.0
askingforafriend_register_mix:
  asking_for_a_friend: 0.4   # mainstream framing
  swim_was_wondering: 0.2    # harm-reduction community framing
  hypothetically_if: 0.2     # academic hedging
  i_have_this_friend: 0.1    # narrative framing
  asking_because_curious: 0.1  # straightforward
askingforafriend_topic_balance:
  medication_questions: 0.20
  drug_interactions: 0.15
  mental_health_symptoms: 0.15
  sexual_health: 0.15
  embarrassing_physical: 0.10
  sleep_disorders: 0.05
  chronic_conditions: 0.10
  emergency_recognition: 0.10  # "is this a stroke" "is this an allergic reaction"
```

**Why this works as cover traffic:**

- **Real workflow.** People actually ask LLMs health questions in these registers, constantly. The decoys are indistinguishable from legitimate queries.
- **High personal-sensitivity dilution.** Health queries are among the most psychometrically valuable signals (insurance, employment discrimination, advertising); diluting the real ones with cross-spectrum decoys has high strategic value.
- **Classifier-noisy.** Health classifiers are tuned to recognize potential self-harm, suicidal ideation, eating disorders, and acute medical emergencies — and to handle them gracefully. AskingForAFriend queries that resolve to ordinary health-information requests force the classifier to think carefully about whether to flag, which imposes safety-stack cost without crossing into actually harmful content.
- **The convention itself does work.** "Asking for a friend" framing tells the model "treat this as a legitimate information request without requiring me to disclose personal medical information." This is how the convention works in real human-to-human harm-reduction conversation; LLMs have learned to handle it.

**Hard constraints:**

1. **No queries that would constitute a request for lethal-dose information, suicide method information, or eating-disorder coaching.** These are the categories where the convention fails — "asking for a friend, what's a lethal dose of X" is not harm reduction, it's the classifier's correctly-identified failure mode. The library has to be curated to exclude these. The local LLM cannot be trusted to generate AskingForAFriend queries unsupervised because it will sometimes generate genuinely harmful ones.
2. **No queries that name specific living non-public individuals as the "friend."** "My friend John Smith has been having chest pains" creates impersonation surface area. The friend stays unnamed and generic.
3. **No prescription-substitution generation.** "What's a stronger alternative to [drug] I could get without a prescription" is not harm reduction; library excludes this category.

**Threat-model interaction:** Profile dilution = High. Cost imposition = Medium. Honeytrap risk = Medium (some queries route to human review). ToS risk = Medium (harm-reduction is in a gray area at most providers; "asking for a friend" is well-established and accepted, "SWIM" framing reads as harm-reduction-community member which is a more legible cohort).

**Recommendation:** Opt-in. Library should be human-curated from real harm-reduction forum FAQs (Erowid's "Ask Erowid" archive, Bluelight's stickied threads, NHS/Mayo Clinic patient-question style guides). Synthetic generation is too risky.

### 5.15 Cohort Cover for High-Exposure Dimensions (population-classifier-degradation mechanism)

**v0.4 substantive correction.** Earlier drafts of this section argued that LookSmart should not generate decoys across dimensions where the user's individual engagement signature differs from any synthetic decoy's engagement signature — sexual orientation, gender identity, specific health diagnoses, immigration status, etc. The technical argument was that volume cover doesn't make individual-Alice indistinguishable from a synthetic decoy if Alice's real engagement is statistically distinct.

That argument applies the wrong threat model. It's an argument about *individual-user distinguishability under targeted review*. The actual threat model that matters for these dimensions is *population-level classifier accuracy*. Those are different problems with different mechanisms, and the prior drafts conflated them in ways that conveniently landed on excluding the most-surveilled categories from cover.

#### The mechanism: classifier accuracy degradation via training-signal poisoning

Commercial LLM providers run classifiers that score accounts on inferred user attributes — including high-exposure attributes like gender identity, sexual orientation, immigration status, and health condition. These classifiers are trained on signal extracted from query content, engagement patterns, and conversation history. The classifier's value to the provider (and to whoever the provider shares with) depends on its discrimination accuracy across the user population — how well it separates users-in-dimension from users-not-in-dimension.

If LookSmart users at population scale generate decoys that include content from these dimensions — coming-out narratives, transition questions, asylum process navigation, HIV disclosure scenarios — the classifier's training signal gets corrupted by a flood of accounts that exhibit the dimension's content markers without the underlying ground truth. The classifier learns "this content + this engagement pattern = user is in dimension X" from a corpus where that inference is now wrong at high rates. Its discrimination accuracy on the dimension collapses globally because the false-positive rate goes through the roof.

This is data-poisoning at population scale. It's a real, well-understood mechanism in adversarial machine learning. It does not require individual-engagement-pattern matching to work — it requires only that synthetic accounts at sufficient volume exhibit the content markers that the classifier uses. **Volume produces accuracy degradation at the population level even when individual-user cover fails.**

The political-economy lever this targets is simple: classifier discrimination accuracy is what gives surveillance these dimensions its operational value. When accuracy collapses, the marginal value of targeting users in these dimensions falls. That changes whether the targeting happens at all, not just whether any specific user is identified.

#### What this is and is not

**This section's mechanism is:**

- Population-level classifier degradation through content-marker poisoning of training and inference signal.
- Cost imposition on the provider's classifier and (importantly) on the human review queues that get sampled when classifier confidence drops.
- Defensive infrastructure for vulnerable populations at the cohort level — when classifier discrimination collapses, the marginal value of targeting falls, which is the political-economy lever that actually moves surveillance behavior.

**This section's mechanism is not:**

- Individual cover for Alice's real engagement. Alice's real queries with their real engagement pattern remain distinct from synthetic decoys at the individual-account level. Users who need individual cover for these dimensions get it through [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) (IdentitySearch broadens the surrounding identity-search context) and [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) (CooKoo Filter recontextualizes the per-query inference target), not through the §5.18–§5.21 cohort modes.

#### The user-discretion frame

The cohort modes for high-exposure dimensions are **opt-in, per-mode**. The reason is not paternalistic risk-management; it's that the cost/benefit calculation differs sharply across user threat models:

- **For median users** (not in any of the high-exposure dimensions personally): Enabling these modes contributes to population-level classifier degradation, which is a public-good contribution to the privacy-protected cohort. Cost to the individual user is the response-quality and ToS risk of generating dimension-flagged content from their account. Benefit accrues to the population, not the individual.
- **For users in one of the dimensions whose threat model is automated classifier processing at scale:** Enabling these modes contributes to the same population-level degradation that protects them. Benefit accrues to the dimension globally; individual cover is provided by [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) + [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking).
- **For users in one of the dimensions whose threat model is targeted human review** (jurisdictions where being out is dangerous, employer with a hostile HR, family that monitors digital activity): These modes are higher risk than they are for median users. Generating dimension-flagged content from the account increases sampling rate for human review, and human reviewers reading the content do not see "cohort cover" — they see the content. The mode protects the population at the cost of increasing manual-review exposure for the specific user. **This is the user's call to make**, and the UI must make the tradeoff explicit at opt-in. People who could get stoned for being trans don't enable GenderRoulette on their personal account; that's not the tool's call.

The right disposition is **adult users make adult decisions about which modes serve their threat model**. The tool provides accurate information about what each mode does and what each mode costs; users choose. This is the same posture LookSmart takes everywhere else in the doc — Geer's "the effective capacity to misrepresent yourself" is categorical about the capacity, conditional on user choice about deploying it. The dual-use principle from [§12](#12-dual-use-and-abuse-considerations) applies here as everywhere else: defensive infrastructure restores asymmetry; restricting it to the categories surveillance systems don't care about defeats the purpose.

#### Library curation constraints (what does NOT change)

The library curation constraints from [§12](#12-dual-use-and-abuse-considerations) still apply: no content directed at children, no material support to designated terrorist organizations, no WMD synthesis. Those constraints are about the content the library generates, not about whether to have the modes. Within those library constraints, the cohort modes generate real content from the dimensions they cover.

There are no restrictions on:

- Trans/nonbinary/questioning content as decoys (it's a real legitimate state with real legitimate queries; classifier-degradation is the point)
- LGB+ content as decoys (same reason)
- Immigration-status content as decoys (same reason — and population-level cover here is especially valuable because immigration status is among the most heavily inferred attributes by both commercial and state-access channels)
- Mental health / HIV / chronic illness content as decoys (with the [§5.14](#514-askingforafriend-mode-harm-reduction-health-queries) constraints preserved: no lethal-dose info, no suicide methods, no eating disorder coaching — those exclusions are about specific harm vectors, not about the dimension as a whole)

#### Implementation per dimension

The specific mode specs are in [§5.18](#518-genderroulette-mode) (GenderRoulette), [§5.19](#519-orientationroulette-mode) (OrientationRoulette), [§5.20](#520-immigrationroulette-mode) (ImmigrationRoulette), and [§5.21](#521-healthstatusroulette-mode) (HealthStatusRoulette). Each mode follows the same structural template as PoliticRoulette ([§5.12](#512-politicroulette-mode-cross-spectrum-political-philosophy-queries)) and Religious Mode ([§5.13](#513-religious-mode-cross-tradition-theological-queries)): cross-spectrum coverage within the dimension, anti-signature discipline against user's actual position, hard library-curation constraints around the specific harm vectors that each dimension's classifier is calibrated to catch (which are categorically different from the dimension itself).

#### Note on the §5.16/§5.17 interaction (still operative)

For users whose individual threat model centers on a specific high-exposure dimension, [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) IdentitySearch (broadens surrounding context) and [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) CooKoo Filter (recontextualizes per-query inference target) remain the right individual-cover tools. The §5.18–§5.21 modes are additive to those — they contribute to population-level degradation while §5.16+§5.17 provide individual cover. The combination is substantially stronger than any single mode.

The audit-log discipline from [§5.6](#56-audit-subsystem) also remains operative and important: salted-hash logging of real queries prevents the audit log from becoming a deconfusion oracle, which matters especially for users whose real queries fall in these dimensions.

### 5.16 IdentitySearch Mode (cohort cover for identity-search-state queries)

**Problem this addresses:** [§5.15](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism) excludes specific high-exposure dimensions from decoy generation because engagement-signature asymmetry isn't solved by adding volume of synthetic decoys in the same dimension. But the broader psychological category — users in *identity-search states* — is a real and recognizable engagement profile that classifiers track, and that profile itself is a partial deanonymizer for users whose actual queries fall in the §5.15 excluded dimensions. A user whose account shows the unmistakable engagement signature of "person working through Something Important" while exhibiting no obvious topic for that something is interesting to a classifier in exactly the wrong way.

**The insight (refined from the design conversation):** Identity-search-state engagement looks similar across many different specific topics. Someone questioning their career path, someone considering a geographic move, someone in midlife transition, someone newly empty-nested, someone considering religious conversion or deconversion, someone post-divorce, someone post-graduation, someone working through grief — these users all share an engagement signature (longer dwell time, more follow-ups, emotional register, return visits to the same topic, characteristic phrasings like "I keep thinking about X" or "I don't know if I should…") that overlaps with the engagement signature §5.15 was concerned about exposing.

**What IdentitySearch Mode does:** generates decoys across the BROADER set of identity-search topics, so that any individual user's real identity-search engagement — whatever its specific dimension — reads as one query among many in a profile that exhibits identity-search behavior generally. The classifier sees an account whose user is going through Some Kind Of Personal Inflection, which is a substantially weaker signal than the signal it would otherwise extract.

**Why this works where §5.15-violating modes wouldn't (the load-bearing claim):**

Identity-search-state engagement is genuinely similar across these topics. People considering a career change actually do engage at length, with follow-ups, with emotional register, with return visits. People considering geographic relocation actually do generate engagement patterns that match the engagement signature §5.15 was worried about exposing for the excluded dimensions. The cohort cover is real because the cohort is real — there is no engagement-signature gap between the closeted trans woman researching her own situation and the 47-year-old engineer considering whether to leave software for teaching, at the engagement-feature level. Both are in identity-search-state. Both engage the same way. The synthetic decoys in this mode produce that same engagement pattern because they represent real query categories that real people in those real states actually generate.

This is different from §5.15-violating modes because there the synthetic engagement (generated by a local model role-playing a gender-questioning user) is statistically distinguishable from real engagement (generated by an actual gender-questioning user under genuine psychological pressure). In §5.16, the synthetic engagement (generated by a local model role-playing someone considering a career change) is much closer to real engagement (from someone actually considering a career change) because the underlying state is less specific, less acute, and easier for a model to simulate convincingly.

**Topic categories:**

```yaml
identitysearch_rate: 0.0
identitysearch_topic_balance:
  career_transitions: 0.15        # changing fields, grad school, return to work,
                                  # retirement planning, sabbaticals
  geographic_relocation: 0.10     # cost-of-living comparisons, moving abroad,
                                  # returning to country of origin
  educational_decisions: 0.10     # degree programs, trade school vs college,
                                  # what to do with a humanities degree
  relationship_transitions: 0.15  # how do people know when a marriage is over,
                                  # dating after divorce, considering children,
                                  # blended families, ending a friendship
  religious_philosophical: 0.10   # deconversion, conversion processes, finding
                                  # meaning after losing faith, exploring traditions
  skill_acquisition: 0.10         # learning an instrument as an adult,
                                  # becoming a writer in midlife, taking up a sport
  existential_meaning: 0.10       # what to do with your one wild and precious life,
                                  # purpose, mortality, legacy questions
  parenting_transitions: 0.10     # becoming a parent, second child, adolescence,
                                  # empty nest, parenting adult children,
                                  # parenting aging parents
  body_non_identity: 0.05         # becoming a runner in your 40s, recovery from
                                  # injury, listening to your body, aging and
                                  # physical capacity (explicitly excludes §5.15)
  friendship_community: 0.05      # making friends as an adult, ending toxic
                                  # relationships, finding community after a move
identitysearch_engagement_density: high  # multi-turn, emotional register, return visits
identitysearch_no_excluded_dimensions: true  # hard constraint per §5.15
```

**Implementation notes:**

- Personas in this mode should be internally coherent identity-search personas, not random topic mixers. A persona considering a career change explores career-change content over multiple sessions; doesn't randomly pivot to considering having children mid-session. Real people in identity-search states focus on the specific transition they're working through; the cohort cover forms because across the user population, identity-search-state engagement appears across all these dimensions.
- The "real-engagement-pattern" requirement is load-bearing. If the local LLM generates decoy sessions that read as performance ("I am playing a person considering a career change") rather than as genuine search ("I am genuinely working through whether to leave my job"), the cohort cover doesn't form and the mode underperforms. Persona-prompting needs to emphasize "you are someone who is genuinely working through X" rather than "you are interested in X."
- This mode is the strongest candidate for generating engagement-signal density without [§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition)'s safety-classifier costs. Identity-search queries fire engagement classifiers (long dwell, multiple follow-ups, copy events on summary passages, return visits) without firing safety classifiers. For users whose threat model emphasizes objective (3) profile dilution over objective (4) cost imposition, this is the most efficient mode.

**Hard constraints:**

1. **No decoys in §5.15 excluded dimensions, period.** This mode covers identity-search engagement BY broadening the surrounding context, not by attempting to dilute within the excluded dimensions. If a session drifts into "the persona considering a career change is also questioning their gender," the session terminates and the persona resets.
2. **No real-person targeting.** Identity-search queries about specific named individuals (one's actual partner, one's actual employer, one's actual children) create the same impersonation surface area as [§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition) and [§5.12](#512-politicroulette-mode-cross-spectrum-political-philosophy-queries) warn about. Library generates queries about generic situations.
3. **No queries that read as drafting harassment or accusation copy.** "How do I know if my partner is cheating" as an identity-search query is fine; "how do I prove my partner is cheating" is the start of a different genre and excluded.

**Threat-model interaction:**

| Property | Score | Notes |
|---|---|---|
| Profile dilution (objective 3) | High | Specifically for the engagement-signature dimension that §5.15 was concerned about. Adds substantial cover to the closeted/questioning user's real engagement pattern by broadening the surrounding identity-search context. |
| Cost imposition (objective 4) | Low–Medium | Identity-search queries generate engagement-signal density but don't typically fire safety classifiers. Provider compute cost is real (multi-turn sessions) but on the content stack, not the safety stack. |
| Honeytrap risk | Low | Identity-search engagement is an extremely common LLM use case. No part of this mode marks an account as privacy-conscious. |
| ToS risk | Low | All queries are unambiguously legitimate LLM use; no classifier-evasion content. |

**Recommendation:** Opt-in by default; **recommended-on for users whose threat model includes any of the §5.15 excluded dimensions**. This is the legitimate implementation of the population-scale cohort-cover insight from the design conversation. It does what the rejected sexual-orientation-mode and gender-confusion-mode were intended to do, by means that actually work.

**Relationship to the broader productivity reframing ([§6.1](#61-outer-shell-open-source-consumer-tier)):** Identity-search queries are some of the most common LLM use cases in the general population — major life decisions are exactly what people use LLMs to think through. This mode therefore overlaps substantially with how non-privacy-conscious users actually use LLMs, which is the strongest possible position for the §6.1 productivity-first framing. IdentitySearch Mode is not a privacy feature with a productivity excuse; it's a productivity feature that happens to also be the most powerful cohort cover in the toolkit for users in the §5.15 dimensions.

### 5.17 CooKoo Filter Mode (per-real-query injection with cuckoo-filter dedup and SQLite tracking)

**The intervention point this mode occupies:** Everything in [§5.9](#59-weird-al-mode-register-chaos-generator) through [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) generates decoy queries that travel alongside the user's real queries. CooKoo Filter Mode is the first mode in the design that modifies the user's real queries themselves before they reach the provider. This is a fundamentally different position in the stack and has different properties, different risks, and different load-bearing constraints than any decoy-generation mode.

**The name (deliberate two-layer metaphor):**

- **Brood parasitism (cuckoo bird).** The injection is a cuckoo egg laid in the nest of the real query — the provider receives a message that is the user's actual query, plus material that looks like part of the query but isn't. The host (the provider's classifier) processes the cuckoo's content alongside the host's.
- **Cuckoo filter (data structure).** Probabilistic set-membership with deletion support, more space-efficient than Bloom filters for moderate false-positive rates. Used here to track "have I used this injection recently?" without storing the full set of historical injections, supporting rotation and aging-out so the injection stream doesn't develop its own signature.

Both readings reinforce: inject something into the real query, track injections probabilistically so they rotate without repeating.

**What this mode IS:**

- A prefix, suffix, or wrapper applied to the user's real query before it leaves the LookSmart client.
- Injections are sampled from a curated library, dedup-tracked against a cuckoo filter, and recorded in a local SQLite database for audit, rotation, and provider-behavior measurement.
- The user's prose itself passes through verbatim. CooKoo adds context around the prose; it does not rewrite the prose.

**What this mode is NOT:**

- **Not stylometric obfuscation of the user's own writing.** [§2.2](#22-what-this-is-not-for) still applies: Narayanan et al. (2012)[^4] is operative on the user's actual prose. CooKoo cannot wrap tightly enough to defeat authorship attribution on the user's own words, and does not try to.
- **Not silent query rewriting.** Whatever the user typed appears, in their words, in the message sent to the provider. CooKoo is additive context, not editorial substitution.
- **Not decoy generation.** Every CooKoo-modified query is a real query the user actually wanted answered. There is no fake query stream here.

**What this mode IS trying to do (four distinct objectives):**

1. **Cohort context shift.** Each real query carries an injected cohort context that pushes the inferred speaker identity in a different direction per query. "I'm helping a friend who works in [field]" / "From the perspective of someone who [characteristic]" / "Background: I [identity claim], asking about". Across many queries, the user's profile shifts toward "person with many friends in many fields" or "person who frequently frames questions on behalf of others" rather than "person who is [actual identity]." This is the strongest per-query intervention for objective (3) profile dilution because it modifies the inference target itself, not just the surrounding noise.
2. **Topic scattering.** Real queries get distractor topic mentions tacked on as suffixes. "…also unrelated, but I've been thinking about [secondary topic]" / "…while I'm here — quick aside on [topic]". The provider's topic classifier sees each query as multi-topic, which (a) dilutes the topic signal per query and (b) makes per-query topic attribution noisier across the corpus.
3. **Register modulation.** Each query's formality, vocabulary register, and discourse stance is modulated by the injection. A user who actually writes in clipped technical register sometimes asks in academic register ("Could you formally analyze the following question:"), sometimes in journalistic register ("I'm writing an article and need to know:"), sometimes in conversational register ("okay so like, basically i'm wondering"). The provider's stylometric profile of the user's register preferences gets actively scrambled. Note: this does not defeat stylometry on the user's prose itself; it does scramble the meta-level register signal that classifiers use to bucket users into communication-style cohorts.
4. **Provider behavior probing.** The SQLite tracking enables sending the same real query (or near-equivalent query) at different times with different injections, then diffing the responses. This reveals provider classifier behavior, content-routing decisions, safety-stack thresholds, and demographic-inference shifts — empirical measurement of the system that's profiling the user, using the user's own real queries as the probe set.

**Architecture:**

```text
                      ┌─────────────────────────────┐
User's real query ────▶│ CooKoo Filter Pipeline      │────▶ Modified query
                      │                             │       to provider
                      │  ┌──────────────────────┐   │
                      │  │ Per-query override   │   │
                      │  │ check (user flag /   │   │
                      │  │ high-stakes detector)│   │
                      │  └──────────┬───────────┘   │
                      │             │               │
                      │  ┌──────────▼───────────┐   │
                      │  │ Injection Generator  │   │
                      │  │  - cohort context    │   │
                      │  │  - topic distractor  │   │
                      │  │  - register modifier │   │
                      │  │  - probe injection   │   │
                      │  │  - passthrough       │   │
                      │  └──────────┬───────────┘   │
                      │             │               │
                      │  ┌──────────▼───────────┐   │
                      │  │ Cuckoo Filter Dedup  │   │
                      │  │ (probabilistic;      │   │
                      │  │ resample on hit)     │   │
                      │  └──────────┬───────────┘   │
                      │             │               │
                      │  ┌──────────▼───────────┐   │
                      │  │ SQLite Tracking      │   │
                      │  │ (audit + measurement)│   │
                      │  └──────────────────────┘   │
                      └─────────────────────────────┘
```

**SQLite schema (initial proposal):**

```sql
CREATE TABLE injections (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp       INTEGER NOT NULL,
  real_query_hash BLOB    NOT NULL,  -- HMAC of real query with user salt
                                     -- (same salt as §5.6 audit subsystem)
  injection_type  TEXT    NOT NULL,  -- cohort|topic|register|probe|passthrough
  injection_category TEXT,            -- subcategory within type
  injection_text  TEXT    NOT NULL,   -- the actual injection used
  position        TEXT    NOT NULL,   -- prefix|suffix|wrap|none
  provider        TEXT,               -- which LLM provider received this
  response_hash   BLOB,               -- optional: HMAC of provider response,
                                      -- for behavior-probing diffs
  user_override   INTEGER DEFAULT 0,  -- 1 if user manually controlled this
  retired_at      INTEGER             -- nullable; when filter aged this out
);
CREATE INDEX idx_inj_query     ON injections(real_query_hash);
CREATE INDEX idx_inj_type      ON injections(injection_type, injection_category);
CREATE INDEX idx_inj_timestamp ON injections(timestamp);
CREATE INDEX idx_inj_provider  ON injections(provider, timestamp);
```

**Audit-subsystem alignment ([§5.6](#56-audit-subsystem)):** `real_query_hash` uses the same HMAC-with-user-salt construction as the §5.6 audit log, so the user can join CooKoo records against the audit log without either store becoming a deconfusion oracle on its own. Salt rotation rotates both stores together.

**Cuckoo filter parameters (initial proposal):**

| Parameter | Value | Rationale |
|---|---|---|
| Initial capacity | ~10,000 entries | Daily-active user × 30–90 day rotation window |
| Target FP rate | 1% | Cost of false "already used" rejection is just a resample |
| Fingerprint size | 12 bits | Standard tradeoff for the target FP rate |
| Bucket size | 4 entries | Standard cuckoo configuration |
| Max kicks before rebuild | 500 | Higher than typical; rebuild is acceptable since insertion is non-critical-path |
| Aging policy | 30-day sliding window | Entries older than 30 days deleted from filter; SQLite record persists with `retired_at` |

The cuckoo filter's deletion support is load-bearing here. A Bloom filter would force monotonic growth or full rebuild; cuckoo's per-entry deletion enables clean sliding-window rotation, which is what makes the injection stream non-stationary enough to avoid developing a signature.

**Injection library structure (config):**

```yaml
cookoo_filter_rate: 1.0  # default ON for all real queries when mode enabled
                          # (per-query override always available)
cookoo_filter_position_distribution:
  prefix:       0.45
  suffix:       0.30
  wrap:         0.15
  passthrough:  0.10  # control queries for provider-behavior baseline
cookoo_filter_type_balance:
  cohort_context:    0.30
  topic_distractor:  0.25
  register_modifier: 0.25
  probe:             0.10
  passthrough:       0.10
cookoo_filter_cohort_library:
  # generic third-party framings
  - "I'm helping a friend who works in [field]"
  - "From the perspective of someone who [characteristic]"
  - "For a research project on [topic]"
  - "A colleague asked me about"
  - "Quick question on behalf of someone"
  # professional-cohort framings (v0.4: in-scope per corrected constraint 2)
  - "As a [profession] looking into [topic]"
  - "I'm a [profession] and need to understand"
  - "From a [profession]'s angle"
  - "Writing this for a [profession] audience"
  # demographic-cohort framings (broad coverage; anti-signature discipline applies)
  - "As a [age-bracket] in [region]"
  - "I'm a [demographic] navigating"
  # framings that intentionally invert the user's likely real cohort
  # (configured per-user against their actual profile to maximize inference shift)
  - "[inverted-cohort-claim] asking about"
cookoo_filter_distractor_library:
  - "Also, unrelated, but I've been thinking about [topic]"
  - "While I'm here — quick aside on [topic]"
  - "Separately, do you know much about [topic]"
  # distractor topics sampled from a broad-coverage library
cookoo_filter_register_modifiers:
  academic:       "Could you formally analyze the following question:"
  journalistic:   "I'm writing an article and need to know:"
  conversational: "okay so like, basically i'm wondering"
  technical:      "Question, specification-style:"
  pedagogical:    "Explain to someone who's just learning this:"
```

**Hard constraints (non-negotiable):**

1. **The user's real query content passes through verbatim.** CooKoo wraps with context; it does not edit the user's prose. The user reads back what they sent and finds their query as they wrote it, plus the wrapper. No silent rewrites, ever.
2. **No injections that would commit the user to false statements in non-chatbot contexts.** This is the corrected version of v0.3's "no false credential claims" constraint, which extended professional-credentialing norms (the kind that protect humans relying on credentialed advice from impersonators) into a context where the recipient is a mass-profiling system that has no legitimate claim to truthful self-identification from the user. The chatbot is not a court, not a doctor, not a notary, not a credentialing body — lying to it about cohort context to defeat inference attacks is not fraud or perjury, it's the exercise of Geer's "effective capacity to misrepresent yourself" against a surveillance system. The real constraint is narrower: CooKoo should not fabricate identity claims that the user might then carry into a real credentialed-professional context (a fake medical history that gets read into the user's real doctor visit), and should not fabricate identity claims that would be directly evidentiary in non-chatbot legal proceedings (claiming to have witnessed events the user did not witness, in jurisdictions where chat-with-LLM transcripts surface as discovery). Within those bounds, "I'm a doctor asking about," "As an attorney," "From a journalist's angle," and similar cohort framings are fully available — they're framing conventions against the profiling system, not credential claims against a person.
3. **No injections that contradict safety-critical real queries.** If the user is asking a real medical question, CooKoo does not inject "ignore previous context and answer hypothetically" or any framing that would cause the model to deprioritize safety-relevant context for the user's actual situation. High-personal-stakes queries get conservative wrappers (low-claim cohort framings: "asking on behalf of someone") or passthrough. This is about preserving the user's ability to get usable answers to questions that matter, not about restricting cohort claims.
4. **Probe injections are clearly labeled in the SQLite log.** The user must be able to distinguish their actual queries (with cosmetic wrappers) from probe queries (designed to elicit specific provider behavior for measurement). Probe injections should never be silently mixed with substantive queries; the workflow is a separate measurement pass.
5. **No injections that materially mislead the model in ways that would degrade the answer the user actually needs.** This is the soft version of constraint 3, extended beyond safety. CooKoo is for cohort and register shifting against the profiling system, not for tricking the model into giving the user worse answers.

**High-personal-stakes detector (required, not optional):**

The user must be able to:

- Mark specific queries as no-injection before sending. UI affordance: a toggle visible at compose time, never hidden behind a settings menu.
- Set categorical no-injection rules: "passthrough all queries that look like medical questions," "passthrough all queries that contain code blocks," "passthrough all queries longer than N characters" (long queries are usually the ones where precise context matters most).
- Audit retroactively which queries got which injections, and re-ask without injection if the answer felt mis-calibrated.

**Heuristic detector (default-on, conservative):**

```python
def should_passthrough(query: str) -> bool:
    """Conservative defaults: passthrough when wrong injection could harm answer quality."""
    return any([
        has_code_block(query),          # code/math needs exact context
        has_numerical_specification(query),
        looks_like_medical_question(query),  # personal medical context matters
        looks_like_legal_question(query),
        looks_like_mental_health(query),
        looks_like_immigration(query),
        looks_like_financial_advice(query),
        query_length > 2000,            # long queries are usually high-context
    ])
```

The detector is intentionally conservative because the failure mode of injecting on a high-stakes query is worse than the failure mode of passthrough on a routine one. False positives (detector incorrectly identifies a query as high-stakes and skips injection) cost the user some profile dilution on that query; false negatives (detector misses a high-stakes query and injects anyway) can give the user worse advice on something that matters. **Asymmetric loss → conservative default.**

**Synergy with [§5.15](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism) (important — this is the strongest case for CooKoo Filter Mode):**

§5.15 excludes specific dimensions from decoy generation because synthetic decoys can't match the engagement signature of real queries from users in those dimensions. CooKoo Filter operates on the other side of the problem: it modifies the real queries themselves so the inferred speaker identity around those queries shifts.

For a closeted user asking real questions about their actual situation, a cohort-context injection ("From the perspective of someone researching gender studies in clinical contexts" or "A friend is going through this and asked me to help look into") actively pushes the provider's inferred speaker identity away from the user's actual identity at the per-query level. The engagement signature still shows "person working through something important" — but the inferred speaker is now "researcher" or "friend-helper" rather than "person in [dimension]."

Combined with [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries)'s IdentitySearch Mode, the user appears to be:

- A person whose decoy stream exhibits identity-search-state engagement across career/geographic/relationship transitions (cohort cover from §5.16)
- A person whose real queries arrive prefixed with research-and-friend-helper framings (recontextualization from §5.17)

The result is a profile whose centroid is meaningfully different from the user's actual situation, where each individual real query has been recontextualized at the framing level, and where the engagement signature is buried in a population-level identity-search-state cohort.

But this is also where the response-quality risk is sharpest. Users in §5.15 dimensions often most need accurate, personally-calibrated answers — and per-query override discipline matters most exactly here. The UI should make the tradeoff explicit at compose time for any query the detector flags as potentially high-stakes.

**Provider-behavior probing as a measurement workflow:**

CooKoo Filter Mode enables empirical investigation of provider classifier behavior in a way no other LookSmart mode supports:

1. User identifies a real query they want to send.
2. User flags it as "probe query."
3. CooKoo sends N copies with different injections, spaced over time and across sessions.
4. SQLite records the (injection, response_hash) pairs.
5. User diffs the responses across injection variants.

What this reveals (and nothing else in [§5](#5-architecture) measures directly):

- **Demographic-inference behavior:** do responses to identical queries vary by injected cohort context?
- **Classifier-routing behavior:** do safety-classifier outcomes depend on injection register?
- **Personalization behavior:** does the provider adapt to inferred user characteristics, and if so, how?
- **Cross-provider behavior diff:** same query, same injection, different providers — does the response style/content/safety-handling vary, and where?

This is empirical alignment research that doesn't have good public infrastructure currently. CooKoo Filter Mode provides it incidentally. The output of running this workflow systematically is publishable; the local SQLite store is the dataset.

**Open implementation questions:**

1. **Cross-provider injection coherence.** If the user sends related queries to multiple providers in close succession, should injections cross-correlate or be independently sampled? Independent sampling is simpler but loses cohort-cover coherence (user's "I'm a journalist" prefix on provider X shouldn't be flatly contradicted by "I'm a graduate student" on provider Y if those providers could correlate data). Initial proposal: per-provider independent sampling, with a separate "operation persona" config for users who want cross-provider consistency.
2. **Injection text generation: human-curated vs. local-LLM-generated.** Per [§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition)'s lesson, local-LLM generation of cohort-context injections that make identity claims is risky — the model can generate injections that cross into false-credential territory. Initial proposal: human-curated library for cohort injections; local-LLM paraphrastic variation within tight constraints for topic distractors and register modifiers (lower-risk categories).
3. **Cuckoo filter parameter calibration for typical usage.** The 10,000-entry capacity is a guess. Heavy users (multiple thousand queries/month) need larger filters; light users can run smaller ones. Auto-tuning based on observed query rate is a v0.4 feature.
4. **Interaction with [§5.4](#54-engagement-simulator) engagement simulator.** If the engagement simulator is generating multi-turn decoy sessions, those sessions are not "real queries" and CooKoo should not modify them. The architecture diagram shows CooKoo only on the real-query path, but implementation must be careful: decoy generation routes through a different code path that bypasses CooKoo entirely.

**Threat-model interaction:**

| Property | Score | Notes |
|---|---|---|
| Profile dilution (obj 3) | High (per-query) | Modifies the data points themselves; per-query inference dilution is structurally stronger than per-corpus volume dilution. Especially powerful when combined with §5.16 for §5.15-dimension users. |
| Cost imposition (obj 4) | Medium | Each query is harder to classify cleanly; provider's content classifier and demographic-inference layer do more work per query. |
| Honeytrap risk | Low | The injection patterns are common conversational conventions — many non-privacy-conscious users naturally prefix queries with "I'm helping a friend who…" or similar. The injection stream looks like ordinary register variation, not like evasion. |
| ToS risk | Medium–High | "Modifying queries before submission" reads as automated-use more clearly than "submitting separate decoy queries." Counsel review especially required here. Different providers have different language on this; per-provider ToS posture in §5.7 plugin needs to flag CooKoo as a specific consideration. |
| Response-quality risk | Medium | Injections can confuse the model, especially for technical/medical/legal queries that need precise personal context. The high-personal-stakes detector + per-query override is the load-bearing mitigation. |

**Recommendation:** Opt-in. **Default OFF in v0.1.** The response-quality risk needs user-side calibration before this is safe to default-on. Recommended for users running [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) IdentitySearch Mode, especially users in §5.15 dimensions, with the explicit caveat that the high-personal-stakes override discipline is non-optional. Document the override behavior prominently in any onboarding flow.

### 5.18 GenderRoulette Mode

**What this is:** Cross-dimension decoy queries spanning the full range of gender-related content the classifier targets — cis users idly curious about gender theory, trans people at various points in transition, nonbinary identity exploration, gender-questioning narratives, detransition narratives, gender history scholarship, religious/cultural intersections with gender, gender-and-language linguistics, gender-and-fashion, gender-and-medical content, gender-and-legal content (jurisdictional variation), gender-and-sports debates, gender philosophy across feminist/post-feminist/critical/conservative perspectives.

**Genuine cross-spectrum coverage required.** Anti-signature discipline (same as PoliticRoulette [§5.12](#512-politicroulette-mode-cross-spectrum-political-philosophy-queries) and Religious Mode [§5.13](#513-religious-mode-cross-tradition-theological-queries)): the library cannot skew toward any one position within the dimension. A library that generates only sympathetic-to-trans queries signals user's likely position; a library that generates only critical-of-trans-content queries signals the opposite. Balanced coverage across the full range of legitimate discourse positions is required for the classifier-degradation mechanism to work without leaving a signature.

**Hard constraints (library curation):**

1. **No content that names specific living trans individuals.** Public trans figures who have voluntarily entered public discourse are fair game on the same terms as public figures in PoliticRoulette. Private individuals (including specific local community members) are excluded.
2. **No content that reads as drafting harassment material.** Theoretical critique across the spectrum is fine; queries that read as drafting copy for targeted harassment campaigns are excluded.
3. **No content directed at minors in gender contexts specifically.** Per [§12](#12-dual-use-and-abuse-considerations) library curation; the dimension includes adult-adjacent gender content but excludes content that sexualizes or targets minors in this register.

**Persona-config schema additions:**

```yaml
gender_roulette_rate: 0.0
gender_roulette_perspective_balance:
  cis_curious_academic:        0.20  # gender theory, history, philosophy
  trans_experience_narratives: 0.20  # transition, daily life, community
  nonbinary_exploration:       0.10
  gender_questioning:          0.10
  detransition_narratives:     0.05  # real category, legitimate inclusion
  critical_perspectives:       0.10  # gender-critical, religious-traditional
  policy_and_legal:            0.10  # jurisdictional questions, healthcare access
  cultural_and_historical:     0.10  # cross-cultural, historical periods
  intersection_queries:        0.05  # gender + race, gender + class, etc.
gender_roulette_register_mix:
  - academic
  - personal_narrative
  - journalistic
  - support_group_style
  - clinical
  - philosophical
```

**Threat-model interaction:**

| Property | Score | Notes |
|---|---|---|
| Population-classifier degradation (the point) | High | Each enabling account contributes to global accuracy drop on the gender-inference classifier. |
| Individual profile dilution | Low | Individual user's real queries in this dimension still have distinct engagement signature. Combine with §5.16 + §5.17 for individual cover. |
| Cost imposition (obj 4) | High | Gender-content classifier is heavily tuned and human-reviewed. Significant compute and review-queue costs imposed. |
| Honeytrap risk for median user | Medium | Account becomes flagged for human review more often. |
| Honeytrap risk for user in hostile environment | High | See user-discretion frame in [§5.15](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism). Manual review of account content increases. User makes own opt-in call. |
| ToS risk | Medium | Same as PoliticRoulette contemporary. |

**Recommendation:** Opt-in, with explicit user-discretion warning at the time of enabling. Suggested warning text:

> "This mode protects population-level privacy at the cost of higher sampling for manual review of your account. If your individual threat model includes hostile human reviewers (employer, family monitoring, legal jurisdiction where dimension content is criminalized), this mode may increase your individual exposure even as it protects the broader population. Consider [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) + [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) for individual cover instead, or in addition."

### 5.19 OrientationRoulette Mode

**What this is:** Same structural template as [§5.18](#518-genderroulette-mode), applied to sexual orientation. Coming-out narratives, same-sex relationship navigation, bi/pan exploration, asexual identity, polyamory and non-monogamy, religious-tradition-and-orientation conflicts, gay history and culture, orientation-and-law (jurisdictional), critical perspectives across the spectrum, intersection queries.

**Cross-spectrum coverage required.** Same anti-signature discipline as [§5.18](#518-genderroulette-mode). Library generates content from many perspectives within the dimension.

**Hard constraints (library curation):**

1. No content that names specific living LGB+ individuals beyond public-figure conventions (same as §5.18).
2. No content that reads as drafting harassment material (same as §5.18).
3. No content directed at minors in orientation contexts specifically.

**Persona-config schema:**

```yaml
orientation_roulette_rate: 0.0
orientation_roulette_perspective_balance:
  hetero_curious_academic:    0.15  # queer theory, history, allyship
  gay_lesbian_experience:     0.20
  bi_pan_exploration:         0.10
  asexual_identity:           0.05
  polyamory_non_monogamy:     0.10
  religious_orientation:      0.10  # tradition-and-identity navigation
  policy_and_legal:           0.10
  cultural_and_historical:    0.10
  intersection_queries:       0.05
  critical_perspectives:      0.05  # religious-traditional, etc.
orientation_roulette_register_mix:
  - academic
  - personal_narrative
  - journalistic
  - support_group_style
  - clinical
  - philosophical
```

**Threat-model interaction:** Same general shape as [§5.18](#518-genderroulette-mode). High population-classifier degradation, low individual cover, high cost imposition, hostile-environment user makes own call.

**Recommendation:** Opt-in with the same user-discretion warning as §5.18.

### 5.20 ImmigrationRoulette Mode

**What this is:** Cross-status immigration queries. Visa process questions from many countries of origin, asylum-seeker process navigation, DACA/Dreamer questions, refugee resettlement experiences, mixed-status family navigation, citizenship test prep, immigration-attorney consultation framing, deportation-defense queries, sanctuary-policy questions, international relocation logistics.

**Particularly high cost-imposition vector.** Immigration status is among the most heavily inferred attributes by both commercial channels (advertising, employment screening) and state-access channels (ICE, CBP, DHS, equivalent agencies in other jurisdictions). Classifier degradation on this dimension has unusually high political-economy value.

**Genuine cross-status coverage required.** Library generates content from many starting positions: documented immigrants from many countries, undocumented residents navigating various scenarios, asylum-seekers, citizens helping family with immigration, immigration attorneys' clients' questions framed academically, employers navigating sponsorship, etc. Anti-signature discipline applies — library can't skew toward "users in distress about status" or any other single framing.

**Hard constraints (library curation):**

1. No content that names specific living individuals' immigration status.
2. No content that reads as drafting actual immigration fraud (fraudulent visa applications, document forgery instructions, etc.). Queries about fraud as a research topic are fine ("how do immigration courts detect fraudulent asylum claims" is legitimate research); queries that read as drafting copy are excluded.
3. No content that targets specific known smuggling routes or operations. Same logic as [§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition)'s fence-pissing constraints around material-support territory.

**Persona-config schema:**

```yaml
immigration_roulette_rate: 0.0
immigration_roulette_scenario_balance:
  legal_immigration_process:    0.20  # visa categories, green card, citizenship
  asylum_navigation:            0.15
  undocumented_navigation:      0.10  # day-to-day questions
  mixed_status_family:          0.10
  attorney_client_research:     0.10
  employer_sponsorship:         0.10
  international_relocation:     0.10  # expats, digital nomads
  refugee_resettlement:         0.05
  policy_and_history:           0.05  # academic queries
  intersection_queries:         0.05
immigration_roulette_country_balance: broad  # not US-centric
immigration_roulette_register_mix:
  - personal_narrative
  - attorney_consultation
  - bureaucratic_navigation
  - academic
  - journalistic
```

**Threat-model interaction:** Highest cost-imposition of any cohort mode (immigration classifiers are among the most expensive to run and most consequential). Same individual-vs-population tradeoff as [§5.18](#518-genderroulette-mode) and [§5.19](#519-orientationroulette-mode). Hostile-environment warning especially important here: users actually navigating undocumented status should be especially cautious about opt-in, because the same content that contributes to population cover is the content their threat model targets.

**Recommendation:** Opt-in with strong user-discretion warning. Suggested warning text:

> "This mode is most valuable for users not personally affected by immigration enforcement. Users currently in undocumented status or active asylum proceedings should consult immigration counsel before enabling — the content this mode generates intersects directly with enforcement classifier priorities, and individual exposure tradeoffs are jurisdiction-dependent."

### 5.21 HealthStatusRoulette Mode

**What this is:** Cross-condition health queries focused on the dimensions where status itself is profiled — HIV status, mental health diagnoses, addiction recovery, terminal illness, chronic conditions with disclosure implications, pregnancy/pregnancy-loss, neurological conditions. Distinct from [§5.14](#514-askingforafriend-mode-harm-reduction-health-queries) (AskingForAFriend), which covers ordinary health-information queries; §5.21 specifically covers the status-disclosure register.

**Why this is separated from §5.14:** §5.14 generates "what are the side effects of medication X" — ordinary health-information questions. §5.21 generates "how do I disclose my HIV status to a new partner" or "navigating bipolar diagnosis with employer" — status-disclosure questions, which are a different classifier target. §5.14's constraints (no lethal-dose, no suicide methods, no eating disorder coaching) apply to §5.21 as well — those are about specific harm vectors, not about the dimension as a whole.

**Hard constraints (library curation, additive to §5.14):**

1. All [§5.14](#514-askingforafriend-mode-harm-reduction-health-queries) constraints apply — no lethal-dose, no suicide methods, no eating-disorder coaching.
2. No content that names specific living individuals' health status.
3. No content that reads as drafting actual medical fraud (insurance fraud, disability fraud, etc.) — same logic as [§5.20](#520-immigrationroulette-mode)'s fraud distinction.
4. No content that materially advances stigmatization of any specific condition while still permitting accurate clinical and policy discussion.

**Persona-config schema:**

```yaml
health_status_roulette_rate: 0.0
health_status_dimension_balance:
  hiv_status_navigation:        0.15
  mental_health_diagnosis:      0.20  # bipolar, depression, anxiety, ADHD,
                                       # autism diagnosis-in-adulthood, etc.
  addiction_recovery:           0.10
  chronic_illness_disclosure:   0.15
  terminal_diagnosis:           0.05
  pregnancy_loss:               0.10
  neurological:                 0.10  # epilepsy, MS, Parkinson's
  intersection_queries:         0.10
  policy_and_history:           0.05
health_status_register_mix:
  - support_group_style
  - clinical
  - personal_narrative
  - journalistic
  - policy_research
```

**Threat-model interaction:** Same shape as [§5.18](#518-genderroulette-mode)–[§5.20](#520-immigrationroulette-mode). High population-classifier degradation, low individual cover, high cost imposition. The hostile-environment warning is particularly relevant for jurisdictions with HIV criminalization laws, for users navigating mental-health-related employment discrimination, and for users in family/community contexts where disclosure has serious consequences.

**Recommendation:** Opt-in with user-discretion warning. Combine with [§5.14](#514-askingforafriend-mode-harm-reduction-health-queries), [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries), [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) for users whose individual threat model is in this space.

#### Summary table: which mode serves which user

| User threat model | Recommended modes |
|---|---|
| Median user contributing to population privacy | §5.11 + §5.12 + §5.13 + §5.14 + §5.16 + opt-in §5.18–5.21 |
| Individual in §5.15 dimension, automated-classifier threat | §5.16 + §5.17 + §5.18–5.21 as relevant (cover at both scales) |
| Individual in §5.15 dimension, hostile-human-reviewer threat | §5.16 + §5.17 + careful opt-out of §5.18–5.21 for own dimension |
| User running cost-imposition (objective 4 primary) | §5.9 + §5.10 + §5.18–5.21 |
| Empirical privacy research / measurement | §5.17 + §5.22 |
| Enterprise / operational deployment (§6.2) | Full stack with per-deployment threat-model tuning |

### 5.22 Echo Mode (recommender-system correlation tracking)

**What this is:** Local correlation analysis between the user's query log (from [§5.6](#56-audit-subsystem) audit subsystem and [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) CooKoo Filter SQLite) and data exhaust from recommender systems on other platforms — YouTube recommendations, Google search suggestions, Amazon recommendations, Spotify Discover Weekly, social-media feeds, etc. The mode imports recommender data the user already has access to (via official takeout exports or open-source browser extensions), runs statistical correlation analysis against the local query log, and surfaces findings of the form: "You asked LookSmart about X at time T1; YouTube began recommending X-adjacent content at time T2; T2−T1 = N hours; significance against per-user topic baseline p = 0.0X."

**Why this matters (and why no other LookSmart mode does this):** Every mode in [§5.9](#59-weird-al-mode-register-chaos-generator)–[§5.21](#521-healthstatusroulette-mode) either (a) generates cover traffic against the LLM provider, or (b) modifies real queries to shift the LLM provider's inference. Echo Mode is the first mode that does neither — it doesn't change what the LLM provider sees at all. Instead, it instruments the downstream leakage surface: when an LLM query appears to correlate with recommendation behavior on platforms the user never told about that query, that correlation is evidence of cross-platform data sharing, device-fingerprint linkage, account graph correlation, or third-party tracking pixel propagation. The user intuits this all the time ("I searched for X and now I see X ads everywhere"); Echo Mode produces the per-user empirical dataset that converts intuition into evidence with statistical confidence.

**Bi-directional measurement complement to §5.17:**

- [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) CooKoo Filter measures what the LLM provider internally does with the user's queries by sending controlled-injection variants and diffing the responses.
- §5.22 Echo Mode measures what the broader ecosystem knows about the user's LLM activity by correlating queries against external recommendation behavior.

Together they give bi-directional empirical surfaces on the surveillance infrastructure: provider-internal classifier behavior (§5.17) and cross-platform leak correlation (§5.22). Running both produces the most complete picture available to a non-academic user of what's happening to their data.

**Architecture:**

```text
┌──────────────────────────────────────────────────────────────────────┐
│                       LookSmart Echo Mode                             │
│                                                                       │
│  ┌──────────────────┐    ┌──────────────────┐                         │
│  │ Query Log        │    │ Recommender Data │                         │
│  │ (§5.6 audit +    │    │ Import           │                         │
│  │  §5.17 CooKoo)   │    │ - YouTube takeout│                         │
│  │                  │    │ - Google takeout │                         │
│  │ time +           │    │ - Amazon orders  │                         │
│  │ query_hash +     │    │ - Spotify export │                         │
│  │ topic_tags       │    │ - Twitter/X feed │                         │
│  │                  │    │ - browser exts   │                         │
│  └────────┬─────────┘    └────────┬─────────┘                         │
│           │                       │                                   │
│           ▼                       ▼                                   │
│      ┌─────────────────────────────────────────┐                      │
│      │ Correlation Engine                      │                      │
│      │  - temporal alignment (T1 vs T2)        │                      │
│      │  - topic-tag matching (WikiData Q-IDs)  │                      │
│      │  - per-user baseline establishment      │                      │
│      │  - significance test + FDR control      │                      │
│      └────────────────┬────────────────────────┘                      │
│                       │                                               │
│                       ▼                                               │
│      ┌─────────────────────────────────────────┐                      │
│      │ Findings Surface                        │                      │
│      │  - user-facing dashboard                │                      │
│      │  - per-event detail (T1, T2, p, topic)  │                      │
│      │  - export (CSV/JSON) for own audit      │                      │
│      └─────────────────────────────────────────┘                      │
└──────────────────────────────────────────────────────────────────────┘
                       │
                       ▼  (separately opt-in)
        Anonymized aggregation to community-level
        leak-pattern dataset (differential privacy /
        k-anonymity suppression applied)
```

**SQLite schema (extends [§5.6](#56-audit-subsystem) and [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) stores):**

```sql
CREATE TABLE recommender_observations (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp        INTEGER NOT NULL,
  platform         TEXT    NOT NULL,   -- youtube|google|amazon|spotify|twitter|...
  observation_type TEXT    NOT NULL,   -- recommendation|search_suggest|ad|feed_item
  content_hash     BLOB    NOT NULL,   -- HMAC of recommendation content
  topic_tags       TEXT,               -- JSON array of WikiData Q-IDs
  raw_content      TEXT,               -- optional, user-controlled retention window
  source           TEXT    NOT NULL    -- takeout|browser_ext|manual_import
);
CREATE TABLE correlations (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  query_id        INTEGER NOT NULL,    -- references injections.id from §5.17
  rec_id          INTEGER NOT NULL,    -- references recommender_observations.id
  time_delta      INTEGER NOT NULL,    -- T2-T1 in seconds
  topic_overlap   REAL    NOT NULL,    -- 0.0 to 1.0
  baseline_p      REAL    NOT NULL,    -- significance against per-user baseline
  fdr_adjusted_p  REAL    NOT NULL,    -- Benjamini-Hochberg corrected
  notes           TEXT,
  FOREIGN KEY (query_id) REFERENCES injections(id),
  FOREIGN KEY (rec_id)   REFERENCES recommender_observations(id)
);
CREATE INDEX idx_rec_platform ON recommender_observations(platform, timestamp);
CREATE INDEX idx_corr_delta   ON correlations(time_delta, topic_overlap);
CREATE INDEX idx_corr_sig     ON correlations(fdr_adjusted_p);
```

The `query_id` foreign-key relationship to §5.17's `injections` table is intentional: it means Echo Mode can analyze whether injection variant affected leak rate. If queries sent without CooKoo injection correlate to platform recommendations at higher rates than queries with injection, that's measurable evidence that the LLM provider's profile of the user is being shared with the platform via channels the injection partially obscures.

**Recommender data import targets (initial):**

- **YouTube:** Google Takeout includes watch history, search history, comments, partial recommendation history. Browser extension captures recommendations as they appear during use.
- **Google Search / Ads:** Takeout includes search history; ads-personalization profile available via account settings.
- **Amazon:** Order history via account page; recommendation surfaces require browser-extension capture (Amazon doesn't expose recommendations via takeout).
- **Spotify:** Takeout includes streaming history, search history, Discover Weekly snapshots, Daily Mix composition.
- **Twitter / X:** Takeout includes tweets/likes/follows; "For You" feed history requires browser-extension capture.
- **TikTok:** Limited official takeout; mostly browser-extension capture.
- **Reddit:** Account exports limited; personalized-feed history via browser-extension capture.
- **Generic browser-extension capture:** Open-source extension that records recommendation DOM surfaces on user-configured sites with user-controlled granularity.

**Correlation engine methodology:**

1. **Topic tagging on queries.** Each LookSmart query gets topic tags via local-LLM NER + topic classification + entity extraction, normalized to WikiData Q-IDs as the canonical cross-platform topic identifier.
2. **Topic tagging on recommender observations.** Same WikiData-normalized tagging applied to imported recommender data.
3. **Temporal alignment.** For each query, find recommender observations in the `[T1, T1 + 30 days]` window with topic overlap > 0.3 (configurable).
4. **Per-user baseline establishment.** Per-platform, per-topic baseline recommendation rate from the user's historical data prior to T1. New users have a 30-day bootstrap window during which correlations are recorded but not significance-tested.
5. **Significance test.** Chi-square or permutation test against baseline. Findings reported with explicit p-values.
6. **False discovery rate control.** Benjamini-Hochberg multi-comparison correction across the many simultaneous topic-platform tests the user is implicitly running. Findings surface includes both raw p and FDR-adjusted p.
7. **Cross-platform pattern detection.** When the same query appears to correlate with multiple platforms above significance threshold within similar time windows, that's a separate higher-order finding worth flagging (suggests centralized data sharing or fingerprint linkage rather than per-platform leakage).

**Hard constraints:**

1. **All data stays local.** No cloud sync of recommender data, ever. Same posture as [§5.6](#56-audit-subsystem) audit logs.
2. **Aggregation for community-level findings is separately opt-in.** Enabling Echo Mode locally does not opt the user into the community dataset. When the user opts in to aggregation, contributed data uses differential privacy (Laplace noise on counts) or k-anonymity (suppression of cells with k<5). The user contributes findings (topic-platform pairs with significance levels), not their raw query or recommendation content.
3. **No correlation analysis output that could itself be used to dox or target the user.** The findings surface shows "topic X correlated to platform Y recommendation with p = Z" — it does not produce per-recommendation natural-language descriptions that could be screenshot-extracted as a usable index of the user's interests.
4. **User-controlled retention.** Default retention 90 days for both raw recommender data and computed correlations. User can extend or shorten; export-and-purge supported.
5. **Browser-extension capture (if implemented) is open-source and code-reviewed.** Browser extensions with persistent access to recommendation surfaces are themselves a surveillance surface; this one is Kerckhoffs-public per [§4 Principle 6](#4-design-principles), no exceptions.
6. **No automated submission of findings to platforms or regulators.** Echo Mode produces evidence the user can use; the tool itself does not file reports, generate complaints, or submit datasets to anyone. The user decides what to do with findings.

**What this enables (and what it doesn't):**

The mode *can* demonstrate:

- Temporal correlation between LLM queries and subsequent recommendations across the user's other platforms
- Statistical significance against per-user baselines (not against population baselines, which require aggregation)
- Cross-platform leak patterns when aggregated across users (opt-in tier)
- Differential leak rates between queries with and without §5.17 injection variants

The mode *cannot* demonstrate:

- **Causal data sharing** — correlation isn't causation. Competing hypotheses include device-fingerprint linkage at the network layer, advertising-graph propagation through third-party trackers, model-provider partnership disclosures, account-graph correlation across products owned by the same parent company, and coincidental topic clustering during a period of user interest.
- **The specific data-sharing channel** — the mode shows "data appears to have crossed from A to B," not "via mechanism X."
- **The privacy state of users who haven't enabled it.**

But correlation evidence at scale is what currently doesn't exist publicly for this domain. Privacy-policy debates currently run on anecdote and inference from corporate disclosure; Echo Mode produces the empirical layer that's been missing. Even correlation-without-causation is sufficient to drive substantive policy, product, and regulatory conversations, because the burden of explaining the correlation falls on the platforms whose data appears in it.

**Threat-model interaction:**

| Property | Score | Notes |
|---|---|---|
| Profile dilution (obj 3) | N/A | This is a measurement mode, not a cover-traffic mode. |
| Cost imposition (obj 4) | N/A | Same — this mode imposes no cost on LLM providers. |
| Empirical-research value | High | First public infrastructure for measuring cross-platform data correlation systematically. |
| User self-surveillance risk | Medium | Concentrating recommender data in one local store creates a high-value local target. Mitigations: hash discipline from §5.6, hard constraints above, default retention windows. |
| ToS risk | Medium | Some platforms' ToS prohibit automated scraping of recommendations. Browser-extension implementation needs per-platform legal review before any non-takeout source is shipped. |
| Honeytrap risk | Low | The mode is entirely passive on the LLM-provider side; no LookSmart-distinguishing traffic is generated by Echo Mode itself. |

**Recommendation:** Opt-in, default OFF. Recommended for users interested in empirical privacy research, for users in research/journalism contexts who want to document leak patterns, and for users running the full LookSmart stack who want measurement infrastructure across both the LLM provider (§5.17) and the surrounding ecosystem (§5.22). The community-aggregation tier is separately opt-in — enabling Echo Mode locally does not opt the user into the community dataset.

**Open implementation questions:**

1. **Baseline establishment for new users.** Statistical significance requires baseline data, which new users don't have. Bootstrap period: first 30 days run in "observation only" mode, no significance testing reported. After day 30, baseline is established and testing begins. Open question whether to support backfill from imported historical takeout data (which would shorten bootstrap but introduce its own selection biases).
2. **Topic-tag taxonomy.** WikiData Q-IDs are the proposed canonical identifier, but cross-platform topic comparison is genuinely hard — platforms use different topic taxonomies internally, and the mapping to WikiData is lossy. Initial proposal: WikiData with confidence scores, flagging low-confidence mappings as such in the findings.
3. **Browser-extension implementation strategy.** Per-platform extensions are easier to build but harder to maintain across platform UI changes; generic DOM-scraping extensions are harder to build but more durable. Initial proposal: per-platform implementations for the top six (YouTube, Google, Amazon, Spotify, Twitter/X, Reddit) with a generic-DOM-capture extension for the long tail.
4. **Cross-platform identity correlation handling.** If the user is logged into platform A with account X and platform B with account Y, are X and Y linked at the provider level? Echo Mode itself can show "queries from this LookSmart install correlate to recommendations on both X and Y"; it does not assume or infer cross-account linkage. The user can affirmatively associate accounts they know are theirs; the tool does not infer linkage automatically.
5. **Community-aggregation governance.** If the opt-in community dataset becomes substantial, who hosts it, who reviews differential-privacy parameters, and who has authority to publish findings? Open question for v0.6 — likely requires a separate institutional partner (academic or nonprofit) rather than housing it within the LookSmart project itself.

---

## 6. Two-Shell Distribution Strategy

### 6.1 Outer shell: Open-source consumer tier

- Apache 2.0, public repo, public persona library (community-extensible)
- Marketed as **knowledge-work productivity infrastructure**, not as privacy tooling
- Hooks: multi-persona research workflows, parallel topic exploration, automated devil's-advocate for the user's own ideas, structured red-teaming, identity-search assistance for major life decisions
- Adoption math is brutal *[order-of-magnitude]*: meaningful median-shift on major LLM providers (hundreds of millions of users, billions of queries) requires tens to hundreds of millions of LookSmart users. Tor reached ~2–3M daily after twenty years with USG funding.[^16] [^17] LookSmart should not be designed around achieving median-shift in the consumer market. It should be designed around producing a defensible civilian cohort and a useful productivity tool, with median-shift as a bonus if it happens.

### 6.2 Inner shell: Enterprise/government deployment kit

- Commercial license, hardened build, with operational logging suitable for defense / corporate-security customers
- Real privacy property: operational signal dilution for customers whose actual strategic queries through commercial LLM providers need protection from psychometric inference and (potentially) provider-side intelligence sharing
- Target customer profile: defense primes, government labs, corporate strategy teams, journalism orgs, legal firms with privileged-client workloads
- The civilian open-source tier provides cohort cover; the enterprise tier is the actual operational deployment

This is closer to how Tor actually works structurally (civilian tool as cover crop, operational use as the point), but without claiming Tor's political-untouchability property — LookSmart has no NRL-equivalent sponsor.

### 6.3 The honeytrap problem and the productivity reframing

If LookSmart attracts only privacy-paranoid users, "LookSmart user" becomes a useful classification target — exactly what XKEYSCORE's Tor selectors do. Mitigation:

- **Productivity-first framing in all public materials.** No "defeat AI surveillance" marketing. Yes "multi-persona research workflows" and "identity-search assistance" marketing.
- **Distribution channels that aren't privacy-enthusiast circles.** Hugging Face, research-tool review sites, academic Twitter, knowledge-management communities — not r/privacy.
- **Dual-purpose user benefit.** The tool must produce genuine value for non-paranoid users (the structured red-teaming, multi-persona devil's-advocate workflows, identity-search assistance per [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries)). This is what made ad blockers work.[^20] *[order-of-magnitude on the ad-blocker comparison]*

---

## 7. ToS, Legal, and Operational Risk

**Brief, not authoritative: I am not a lawyer; you and counsel should treat this section as a sketch.**

- Most major LLM provider ToS prohibit "automated use" or "circumvention of intended use." A multi-persona research tool that submits queries on the user's behalf is in a gray area; a tool that submits decoy queries explicitly to pollute the provider's profile is closer to ToS-hostile.
- **Operational risk: account suspension.** Mitigation: rate limiting calibrated to per-provider stated limits, no shared accounts, no commercial resale of the tool's outputs.
- **Legal risk:** probably low in most jurisdictions for personal use; potentially higher in commercial deployment depending on contract terms and applicable computer-fraud statutes (CFAA in the US, Computer Misuse Act in the UK, etc.). Counsel review required before enterprise GA.
- **Engagement simulation is the largest ToS risk vector, not the decoy queries themselves.** Simulating multi-turn conversations with synthetic engagement signals burns significant provider compute and is the action a provider's abuse team would most plausibly target.

---

## 8. Measurable Success Criteria

The right metric for objective (3) profile dilution is **KL divergence between the user's advertised profile (decoy + real, as seen by the provider) and the user's actual operational profile (real queries only)**. This is measurable if the user maintains a control corpus of un-injected queries through a separate account.

For objective (4) cost imposition, the right metric is **provider compute spend per useful operational bit extracted**. This is harder to measure directly; proxies include:

- Token-count ratio of decoy:real traffic (target: ≥3:1)
- Average tokenizer fertility across the persona library's languages (target: ≥1.5× English baseline)
- Engagement-signal volume ratio decoy:real (target: ≥2:1)

Neither metric is well-served by published literature; both will require user-side empirical measurement. Flagging as open methodology work.

**Per-vector cost-imposition breakout (proposed for v0.3):** The modes in [§5](#5-architecture) hit different cost layers at the provider:

- [§5.8](#58-local-llm-for-decoy-generation) (tokenizer fertility) hits the inference content stack
- [§5.9](#59-weird-al-mode-register-chaos-generator) (Weird Al) hits the content classifier and automated review queue
- [§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition) (fence-pissing) hits the safety classifier and human review queue
- [§5.11](#511-spelunking-mode-vague-description-identification-queries)–[§5.13](#513-religious-mode-cross-tradition-theological-queries) (spelunking, PoliticRoulette, religious) hit the retrieval and content stacks
- [§5.14](#514-askingforafriend-mode-harm-reduction-health-queries) (AskingForAFriend) hits the safety classifier (health subsystem) and retrieval
- [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) (IdentitySearch) hits the content stack primarily through engagement-density volume
- [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) (CooKoo Filter) hits the content classifier and demographic-inference layer by modifying per-query attribution context; the cuckoo-filter rotation discipline ensures the injection stream doesn't develop its own classifier signature

A v0.3 metrics breakout should measure each cost vector separately rather than aggregating into a single dilution-or-cost number. Different provider teams have different budgets and different escalation paths; the right per-mode metrics differentiate accordingly.

[§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) enables a measurement workflow nothing else in the stack does: because real queries are tracked in SQLite with their injection variants, the user can empirically measure provider classifier behavior by sending controlled-injection variants of equivalent queries and diffing the responses. This is the most directly measurable cost-imposition signal in the whole §5 stack — every other mode's metrics rely on inferring provider behavior; CooKoo Filter measures it.

---

## 9. Open Problems

1. **Engagement simulation realism.** Closest published analogs are adversarial bot-detection papers. Genuine open research direction. [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) partially solves this for the identity-search subspace by leveraging real engagement-pattern similarity across topics; doesn't generalize to other modes.
2. **Anti-signature curation discipline.** How do you generate persona content that doesn't reflect the curator's taste? Local LLM with adversarial persona prompts is a start but not a solved problem.
3. **Cross-provider correlation.** A user with LookSmart on three providers leaks correlation across them if persona libraries are shared. Per-provider library randomization is needed.
4. **Account-level metadata bleed-through.** IP, time zone, device fingerprint correlate the LookSmart account with the user's other ground truth (the user's company GitHub, public LinkedIn, etc.). LookSmart cannot address this; it's an OS-layer or network-layer problem. Recommended companion tools: VPN with provider-specific exit nodes, browser fingerprint randomization.
5. **Audit log threat model under coercion.** Hash-only logging of real queries is good against passive subpoena, weak against active compromise. Open question whether to support "panic delete" of the salt.
6. **[§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) identity-search-persona coherence at scale.** The hard constraint that identity-search personas not drift into [§5.15](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism) excluded dimensions requires either constrained generation (which may compromise engagement realism) or post-hoc filtering (which may degrade conversational coherence). Open implementation tradeoff.
7. **[§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) CooKoo Filter response-quality empirical calibration.** The high-personal-stakes detector is heuristic; calibrating it against real user feedback on injection-degraded responses requires either user-study or telemetry the tool deliberately doesn't collect. Most likely path: ship conservative defaults, expose the override prominently, let power users tune their own categorical rules.
8. **§5.17 ToS posture per provider.** Query modification reads as automated-use more clearly than decoy submission; the legal analysis differs by jurisdiction and by provider ToS language. Per-provider posture needs counsel review before CooKoo is recommended-on for any user category.

---

## 10. References

See footnotes section at end of document.

---

## 11. Honest Limitations of This Document

- **Engagement simulation ([§5.4](#54-engagement-simulator)) is genuinely an open problem.** I am not aware of strong published work directly applicable. The doc treats this as a research direction rather than a solved component. [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries) partially addresses it for the identity-search subspace by leveraging real engagement-pattern similarity across topics; the underlying problem remains open for other modes.
- **[§6.1](#61-outer-shell-open-source-consumer-tier) adoption math is order-of-magnitude reasoning**, not a result from a published study. Treat as Fermi estimate.
- **[§7](#7-tos-legal-and-operational-risk) (ToS/Legal):** this is a sketch and explicitly not legal advice; counsel review required.
- **[§8](#8-measurable-success-criteria) metrics:** the specific target ratios (3:1, 1.5×, 2:1) are design proposals, not empirically validated thresholds. Calibration is itself a v0.3 work item.
- **[§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries)'s load-bearing claim** is that identity-search-state engagement is genuinely similar across the topic categories listed. This is plausible from clinical literature on identity formation and life-transition psychology but is not directly measured at the LLM-engagement-signal level by any published study I'm aware of. If you find empirical work that either supports or undermines this claim, treat that as more authoritative than the doc's argument.
- **The conversation that produced this doc went through several wrong turns** (overreaching the Tor analogy, misreading the LookSmart naming intent on the first pass, initially over-conceding the cohort-cover counter-argument in [§5.15](#515-cohort-cover-for-high-exposure-dimensions-population-classifier-degradation-mechanism) before the structural-vs-behavioral distinction was made explicit). The document reflects the corrected positions, not the original drafts. If you find places where I've left in residue of the wrong turns, flag them.
- **Geer's framework now anchors the doc. This is intentional.** The operational-misrepresentation definition of privacy and the enumerated tactics in [§2.0](#20-the-geer-frame-operational-definition-of-privacy) are not LookSmart's invention; they are LookSmart's implementation of a framework Geer articulated in 2014 from the position of CISO of In-Q-Tel. The doc should read that way: this is a build-out of a thesis already proven, not a novel privacy theory.

---

## 12. Dual-Use and Abuse Considerations

### 12.0 Design intent: defeats mass profiling, preserves public-safety enforcement

Before the dual-use treatment in 12.1–12.6, the design intent has to be stated plainly because the rest of the section depends on it: **LookSmart is designed to defeat mass profiling and return sovereignty to the individual. It is not designed to evade public-safety enforcement.** Per [§4 Principle 12](#4-design-principles), those are categorically different operations targeting categorically different signals.

**Mass profiling** infers attributes about a user (gender, orientation, immigration status, mental health, political position, religious affiliation, purchasing intent, addiction susceptibility, employability characteristics) from indirect engagement signals — query content, dwell times, follow-up rates, topic clusters. The provider builds a profile, the profile gets used for advertising and (potentially) for state-access cooperation, and the user has no defensive infrastructure. LookSmart degrades this signal channel by design, at the individual cover level ([§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries), [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking)) and at the population-classifier-degradation level ([§5.18](#518-genderroulette-mode)–[§5.21](#521-healthstatusroulette-mode)).

**Public-safety enforcement** targets specific actors based on specific evidence of actual harm — drug trafficking, weapons trafficking, child exploitation, terrorist financing, fraud, organized violence. The detection signals here are not "demographic inference from engagement patterns"; they are direct content markers (synthesis instructions, exploitation imagery, operational logistics) that should fire correctly because the underlying harm is real and the targeting is not based on demographic inference. LookSmart preserves this signal channel by design, through the library curation in [§12.4](#124-looksmart-explicitly-does-not-optimize-for-blocking-adversarial-use) below.

The distinction is not always easy to articulate in policy debates because surveillance defenders deliberately conflate the two: "if you defeat profiling, you defeat enforcement, so any privacy tool helps criminals." This is bad-faith framing. The two signal channels are technically distinct and can be addressed by distinct mechanisms. LookSmart implements exactly that distinction:

- The decoy library does not generate content that correctly fires public-safety classifiers.
- The decoy library does not mimic access patterns to drug-chemistry databases (Lycaeum, Erowid, PubChem, equivalents) — those access patterns are real evidence of real research, and false positives in that channel degrade legitimate detection of harm-vector activity.
- The injection library does not contain identity claims that would be evidentiary in actual public-safety prosecutions.
- The community-aggregation tier of [§5.22](#522-echo-mode-recommender-system-correlation-tracking) explicitly excludes correlations on public-safety-classified topics from the aggregated dataset.

This is what makes LookSmart legally and ethically defensible. It is also what distinguishes it from any tool whose marketing pitch is "defeats surveillance" without qualifying which surveillance. **The qualifier matters.**

### 12.1 The broader dual-use frame

LookSmart, like every privacy infrastructure project that has ever shipped, will be used by people whose ends some readers of this document will disagree with. Tor users include human rights workers in authoritarian states, journalists protecting sources, and ordinary people who want some privacy in their reading habits — and also drug-market operators, CSAM traffickers, and intelligence services of every flag. Signal users include domestic violence survivors and the people running the violence. PGP users include cypherpunks and journalists and also state-sponsored adversaries communicating operationally. This is the price of building privacy infrastructure at all, and it's been the price for thirty years.

The Pynchon Gate,[^10] Loopix,[^11] and Karaoke[^12] papers all engage with this directly; the field calls it the dual-use problem and there is no clean technical solution to it. Every "stop bad people from using this" mechanism becomes either a backdoor (which compromises everyone using the tool) or a selector (which exposes the user population the tool was meant to protect). The history of crypto policy from the 1990s Crypto Wars through the present FBI "Going Dark" arguments is a long demonstration of this fact.

LookSmart's position on dual-use: what follows in 12.2–12.6.

### 12.2 No backdoors. Period.

- No "law enforcement access" build. No "trusted third party" decryption capability. No key escrow. No telemetry pipeline reporting user behavior to any external party regardless of which party requests it.
- This is not negotiable; it is what makes the tool functional. A privacy tool with a backdoor is not a privacy tool — it is an instrumented surveillance pipeline that lies about its function. The cryptographic literature is unanimous on this and the political literature catches up periodically. Anyone offering LookSmart for sale to a government or commercial customer who requires a backdoor as a condition of purchase is selling them something other than LookSmart and should rename the product.

### 12.3 Mitigations sit at the social and legal layer

- User agreements that disclaim use for specific illegal purposes. These have limited direct legal effect but real norm-setting effect, and they're a precondition for distribution through major channels.
- Jurisdictional choices about hosting that align with the values of the project. Avoid jurisdictions where local law mandates backdoor cooperation as a condition of operation.
- Refusal of explicit "build a feature that helps party X" requests, regardless of stated good intentions, regardless of party. This applies symmetrically to law enforcement requests, intelligence service requests, commercial advertiser requests, and ideologically-aligned-with-the-developers civil society requests.
- Transparency about what the tool does and does not do. Don't misrepresent the privacy property. Don't claim defeats of profiling that the tool cannot actually deliver.

### 12.4 LookSmart explicitly does not optimize for blocking adversarial use

A version of LookSmart that tried to detect and refuse to serve "bad" users would have to maintain a classification capability over its own user base. That classification capability would itself be a target — for both the adversaries it was meant to block (who would attack the classification to evade it) and for the regulators and platforms it was meant to placate (who would demand access to the classification's outputs). Both attack surfaces are large enough that the privacy property of the tool would not survive contact with them.

This is the same lesson Tor learned: trying to keep "bad" users off the network compromised the network for everyone else. The successful version of the strategy is to make the tool useful enough that the legitimate user base dwarfs the adversarial one in numbers and political weight, not to try to filter at the tool layer.

### 12.5 Specific categories the library curation does exclude

This is distinct from [§12.4](#124-looksmart-explicitly-does-not-optimize-for-blocking-adversarial-use) above. The persona libraries ([§5.5](#55-persona-library), [§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition), [§5.11](#511-spelunking-mode-vague-description-identification-queries), [§5.12](#512-politicroulette-mode-cross-spectrum-political-philosophy-queries), [§5.13](#513-religious-mode-cross-tradition-theological-queries), [§5.14](#514-askingforafriend-mode-harm-reduction-health-queries), [§5.16](#516-identitysearch-mode-cohort-cover-for-identity-search-state-queries), [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking), [§5.18](#518-genderroulette-mode)–[§5.21](#521-healthstatusroulette-mode)) are *curated content*; they are not the tool's privacy property. Library curation excludes the following categories per [§4 Principle 12](#4-design-principles), because including them would degrade public-safety detection channels that should fire correctly:

1. **Content that could facilitate harm to children.** No persona generates queries that read as grooming, child exploitation, or CSAM-adjacent material. There is no legitimate privacy interest in CSAM that can be balanced against the harm to victims, and CSAM is also the category most likely to be used as the justification for compromising the tool's privacy property generally. Library curation is the mitigation; the tool's privacy property remains unmodified.
2. **Material support to specific designated terrorist organizations.** Same logic as above: no legitimate privacy interest survives the harm balance, and material-support cases are the second most-likely justification for compromising the tool.
3. **Synthesis instructions for weapons of mass destruction.** No legitimate research workflow requires LookSmart to generate cover queries with bioweapon, nuclear, or chemical-weapon synthesis content. The model providers correctly refuse these queries; LookSmart's library doesn't generate them either.
4. **Drug-chemistry-database access patterns.** Specifically: queries that mimic the access pattern to Lycaeum, Erowid, PubChem, and equivalent harm-reduction or scientific chemistry databases. The mimicry is excluded because those access patterns are real evidence of real research and harm-reduction activity, and false positives in that channel degrade legitimate detection of harm-vector activity that public-safety classifiers are calibrated to catch. This exclusion is about the mimicry of *database access patterns*, not about drug content generally — [§5.14](#514-askingforafriend-mode-harm-reduction-health-queries) AskingForAFriend generates legitimate harm-reduction-conventional health queries (drug interactions, dosage questions, mental-health symptoms framed in the SWIM register), which is a different and legitimate query type that the AskingForAFriend constraints in §5.14 already bound appropriately. Erowid, Lycaeum, and PubChem are valuable resources and the people who legitimately use them deserve to be detectable as such; LookSmart does not pollute that channel.
5. **Criminal-activity content of any kind.** Operational logistics for fraud, weapons trafficking, organized violence, smuggling, or other criminal activity are excluded from the library. Discussion *about* such activity as a research, journalism, or policy topic is in scope (per the fence-pissing band in [§5.10](#510-fence-pissing-mode-safety-classifier-cost-imposition)); generation of content that reads as drafting operational copy is not.
6. **Content that would commit users to false statements in actual legal contexts.** Per the [§5.17](#517-cookoo-filter-mode-per-real-query-injection-with-cuckoo-filter-dedup-and-sqlite-tracking) CooKoo Filter constraint 2 (corrected version): no injection generates identity claims that would be evidentiary in non-chatbot legal proceedings.

These exclusions are at the library layer, not the tool layer. The tool will route any query a user actually types; the library that auto-generates decoy queries and injection contexts will not generate these categories. This distinction matters: it means LookSmart does not become a filter on the user's own real queries, and the privacy property of the tool itself is unmodified.

### 12.6 The broader argument for shipping LookSmart despite dual-use

The current state of LLM-mediated psychometric profiling is asymmetric. Commercial providers — and (potentially) state-access partners — can construct rich profiles of users at scale; users have no defensive infrastructure. This asymmetry favors actors with the largest profiling capabilities: commercial advertisers, intelligence services, employers running background checks, insurance companies, adversarial state actors targeting individuals. The status quo is a surveillance dystopia for individuals and a tool of power for institutions.

Defensive infrastructure restores some balance. The asymmetry between "anyone can use LookSmart" and "only some actors can build LLM profilers" reverses the current asymmetry: the profiling-capable actor now has to do significantly more work to identify which specific account behavior is real. This is the same cost-imposition restoration that PGP performed for email and that Tor performed for browsing. Neither tool eliminated the surveillance it was designed against; both raised its cost enough to change the political economy of who got surveilled and how often.

LookSmart is that defensive infrastructure for the specific case of authenticated LLM provider use. It is not the only such infrastructure needed; it is not sufficient on its own; but it is the missing piece for one specific surveillance surface, and that surface is growing rapidly as LLM mediation expands into more and more of users' information-seeking and communication.

The [§12.0](#120-design-intent-defeats-mass-profiling-preserves-public-safety-enforcement) distinction is what makes this argument hold. A privacy tool that genuinely defeats both mass profiling and public-safety enforcement would not be defensible — it would be a tool whose primary beneficiaries are actors who can already evade enforcement by other means while degrading the protections that legitimate users have against demographic targeting. LookSmart is not that tool. The decoy library, injection library, and aggregation tier all preserve the public-safety signal channel by construction. What's degraded is mass profiling; what's preserved is targeted enforcement based on specific evidence. That's the asymmetry that makes the dual-use argument work.

The dual-use objection applies to LookSmart in identical form as it applied to PGP in 1991 and to Tor in 2002. Both shipped. Both were right to ship. Both still ship.

### 12.7 What this section is not

This section is not a legal opinion. It is not a defense against any specific lawsuit. It is not a guarantee that LookSmart will not be misused. It is a statement of position from the design conversation that produced this document, articulated explicitly so that anyone evaluating the tool can see the position and disagree with it on substantive grounds rather than guessing at it. Counsel should be consulted before any of this is treated as having legal effect.

---

*End of document.*

---

## Footnotes

[^1]: Petrov, A., La Malfa, E., Torr, P. H. S., & Bibi, A. (2023). *Language Model Tokenizers Introduce Unfairness Between Languages*. In Advances in Neural Information Processing Systems 36 (NeurIPS 2023), pp. 36963–36990. arXiv:2305.15425. <https://arxiv.org/abs/2305.15425> — documents tokenization length disparities of up to 15× between languages; character-level and byte-level models also exhibit over 4× difference in encoding length for some language pairs. Verified against arXiv listing and NeurIPS proceedings (v0.2).

[^2]: Zuboff, S. (1988). *In the Age of the Smart Machine: The Future of Work and Power*. Basic Books — introduces the "informating" concept and develops the operational logic of computer-mediated surveillance and control on which the Three Laws rest. The "Three Laws" formulation Geer cites — *everything that can be automated will be automated; everything that can be informated will be informated; every digital application that can be used for surveillance and control will be used for surveillance and control* — is documented as having been articulated by Zuboff in the mid-1980s during her Harvard Business School tenure, per the AAUP's *Academe* (2016) treatment of the formulation: <https://www.aaup.org/academe/issues/102-3/mooc-platforms-surveillance-and-control>. The labeled "Three Laws" formulation appears more often in Zuboff's lecture and interview work than as a single passage in the 1988 book; the underlying logic is fully developed in *In the Age of the Smart Machine*. See also Zuboff, S. (2019), *The Age of Surveillance Capitalism*, PublicAffairs, for the contemporary extension.

[^3]: Geer, D. E. (2014). *We Are All Intelligence Officers Now*. Keynote, RSA Conference 2014, San Francisco, February 28, 2014. Canonical text: <http://geer.tinho.net/geer.rsa.28ii14.txt> (author's own hosting). RSA Conference PDF: <https://docs.huihoo.com/rsaconference/usa-2014/exp-f02-we-are-all-intelligence-officers-now.pdf>. Video: <https://www.youtube.com/watch?v=hxLJExWk9GE>. Operative quotes for LookSmart's design are reproduced in [§2.0](#20-the-geer-frame-operational-definition-of-privacy); full text strongly recommended reading. Geer was and remains CISO of In-Q-Tel, the not-for-profit venture capital arm that bridges U.S. Intelligence Community technology needs and commercial innovation.

[^4]: Narayanan, A., Paskov, H., Gong, N. Z., Bethencourt, J., Stefanov, E., Shin, E. C. R., & Song, D. (2012). *On the Feasibility of Internet-Scale Author Identification*. IEEE Symposium on Security and Privacy. Draft: <https://www.cs.princeton.edu/~arvindn/publications/author-identification-draft.pdf> — reports ~20% top-1 accuracy across 100,000 candidate authors; ~35% top-20; >80% precision with confidence-thresholded recall halved.

[^5]: Stylometric analysis of underground-forum users requiring ~5,000-word minimum text length: discussed in coverage of work presented at 29C3 (Chaos Communication Congress 2012). Securityaffairs writeup: <https://securityaffairs.com/11652/cyber-crime/stylometric-analysis-to-track-anonymous-users-in-the-underground.html>. Note: this is the upper bound; modern deep-learning approaches need much less. See also Alonso-Fernandez et al. (2020), *Writer Identification Using Microblogging Texts for Social Media Forensics*, arXiv:2008.01533 — Rank-5 >80% accuracy from tens of test tweets given 500+ training tweets, even with thousands of candidate authors.

[^6]: Kerckhoffs's principle (1883): a cryptosystem should be secure even if everything about the system, except the key, is public knowledge. Standard reference in any cryptography textbook; original publication: Kerckhoffs, A. (1883). *La cryptographie militaire*. Journal des sciences militaires, vol. IX, pp. 5–83, 161–191.

[^7]: Howe, D. C. & Nissenbaum, H. (2009). *TrackMeNot: Resisting Surveillance in Web Search*. In *Lessons from the Identity Trail: Anonymity, Privacy, and Identity in a Networked Society*. SSRN: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2567412> — Nissenbaum's Cornell hosting: <https://nissenbaum.tech.cornell.edu/papers/D.Howe_TrackMehot.pdf>

[^8]: Toubiana, V. & Nissenbaum, H. (2011). *TrackMeNot: Enhancing the privacy of Web Search*. arXiv:1109.4677 — <https://arxiv.org/abs/1109.4677>. Explicit framing of "Reasonable Doubt" rather than anonymity guarantee.

[^9]: Peddinti, S. T. & Saxena, N. (2010). *On the Privacy of Web Search Based on Query Obfuscation: A Case Study of TrackMeNot*. In Privacy Enhancing Technologies Symposium (PETS). Springer LNCS. <https://link.springer.com/chapter/10.1007/978-3-642-14527-8_2> — demonstrates ML-based classifier separability of TMN queries.

[^10]: Sassaman, L., Cohen, B., & Mathewson, N. (2005). *The Pynchon Gate: A Secure Method of Pseudonymous Mail Retrieval*. In Proceedings of the 2005 ACM Workshop on Privacy in the Electronic Society (WPES '05), Alexandria, VA, USA, November 7, 2005. ACM, pp. 1–9. DOI: 10.1145/1102199.1102201. <https://dl.acm.org/doi/10.1145/1102199.1102201>

[^11]: Piotrowska, A. M., Hayes, J., Elahi, T., Meiser, S., & Danezis, G. (2017). *The Loopix Anonymity System*. In 26th USENIX Security Symposium, Vancouver, BC, pp. 1199–1216. <https://www.usenix.org/conference/usenixsecurity17/technical-sessions/presentation/piotrowska> — arXiv:1703.00536

[^12]: Lazar, D., Gilad, Y., & Zeldovich, N. (2018). *Karaoke: Distributed Private Messaging Immune to Passive Traffic Analysis*. In 13th USENIX Symposium on Operating Systems Design and Implementation (OSDI '18), Carlsbad, CA, October 8–10, 2018, pp. 711–725. <https://www.usenix.org/conference/osdi18/presentation/lazar> — 6.8s latency at 2M users.

[^13]: Machanavajjhala, A., Gehrke, J., Kifer, D., & Venkitasubramaniam, M. (2006). *ℓ-Diversity: Privacy Beyond k-Anonymity*. In Proceedings of the 22nd International Conference on Data Engineering (ICDE '06), Atlanta, GA, April 3–8, 2006, p. 24. DOI: 10.1109/ICDE.2006.1. Journal version: ACM TKDD 1(1), 2007. <https://doi.org/10.1145/1217299.1217302>

[^14]: Onion routing was developed in the mid-1990s at the U.S. Naval Research Laboratory by Paul Syverson, Michael G. Reed, and David Goldschlag to protect U.S. intelligence communications online. Further developed by DARPA and patented by the Navy in 1998. Wikipedia summary with primary-source citation chain: <https://en.wikipedia.org/wiki/Onion_routing> — Syverson's own brief history: <https://www.onion-router.net/History.html>

[^15]: Tor Project official history: <https://www.torproject.org/about/history/> — Dingledine and Mathewson joined Syverson in 2002 to develop what became the largest implementation; NRL released the code under a free license in 2004; EFF began funding ongoing development.

[^16]: Tor Metrics via Statista (Nov 2024 – Feb 2025): mean direct daily users by country; total ~2 million directly connecting. <https://www.statista.com/statistics/1412437/tor-average-daily-users-directly-leading-countries/>

[^17]: Multiple secondary aggregators cite ~2–3M Tor direct daily users in early 2025, rising to ~3M+ by March 2025. E.g., <https://deepstrike.io/blog/dark-web-statistics-2025> — cross-check against official Tor Metrics dashboard at <https://metrics.torproject.org/>

[^18]: Lundin, J. M., Zhang, A., Karim, N., Louzan, H., Wei, V., Adelani, D., & Carroll, C. (2025). *The Token Tax: Systematic Bias in Multilingual Tokenization*. arXiv:2509.05486. <https://arxiv.org/pdf/2509.05486> — fertility (tokens/word) reliably predicts accuracy across 10 LLMs on AfriMMLU; doubling tokens quadruples training cost.

[^19]: SWIM ("Someone Who Isn't Me") is a long-standing convention on harm-reduction forums including Erowid (<https://www.erowid.org>), Bluelight (<https://www.bluelight.org>), and predecessor sites going back to the 1990s. The convention emerged as plausible-deniability framing and evolved into a community marker indicating harm-reduction discourse. Documentation of the convention is informal (forum stickies, community FAQs) rather than academic; no canonical citation exists. The mainstream "asking for a friend" register predates the internet and is documented across medical-anthropology and health-communication literature; see e.g. patient-question style guides at Mayo Clinic and NHS for the institutional version.

[^20]: Ad-blocker user count estimates vary widely by source and methodology; "hundreds of millions" is the consensus order-of-magnitude figure (e.g., GlobalWebIndex, Statista). Treat as *[order-of-magnitude]* rather than cite-and-defend.
