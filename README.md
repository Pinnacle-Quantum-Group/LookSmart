# LookSmart

> *"Your definition of a state of privacy will be my definition: the effective capacity to misrepresent yourself."*
> — Dan Geer, CISO of In-Q-Tel, RSA Conference 2014

**Knowledge-work infrastructure with incidental privacy properties.**
**Status:** Design v0.5 · Pre-implementation · Public from day one
**License:** Apache 2.0 (core) · CC BY-SA (persona libraries) · Commercial (enterprise deployment kit)

---

## What this is

LookSmart is cover traffic and per-query injection infrastructure for authenticated commercial LLM use. It is the implementation of [Dan Geer's 2014 RSA framework](http://geer.tinho.net/geer.rsa.28ii14.txt) as software for the surface that's now eating the world: psychometric profiling by LLM providers.

Every major commercial LLM provider (OpenAI, Anthropic, Google, xAI, Meta, the Chinese majors) can construct rich profiles of every authenticated user from query content, conversation patterns, engagement signals, and account metadata. These profiles have commercial value, research value, and potentially state-access value. Users have no defensive infrastructure.

LookSmart is that defensive infrastructure.

It descends from a thirty-year academic lineage: TrackMeNot (Howe & Nissenbaum, NYU, 2009), Pynchon Gate (Sassaman/Cohen/Mathewson, WPES 2005), Loopix (Piotrowska et al., USENIX Security 2017), Karaoke (Lazar/Gilad/Zeldovich, OSDI 2018), grounded in ℓ-diversity (Machanavajjhala et al., ICDE 2006) and operating under the Kerckhoffs assumption.

## What this is not

- **Not an anonymity tool.** Authenticated LLM accounts have per-user identity by construction. LookSmart cannot defeat that and does not pretend to.
- **Not stylometric obfuscation.** Narayanan et al. (2012) is operative on the user's actual prose; no injection scheme defeats authorship attribution on the user's own words.
- **Not a circumvention tool for public-safety enforcement.** Mass profiling targets users by demographic inference. Public-safety enforcement targets actors by specific evidence. LookSmart degrades the first; preserves the second by design. The persona libraries explicitly exclude CSAM-adjacent content, material support to designated terrorist organizations, WMD synthesis, mimicry of drug-chemistry-database access patterns (Erowid, Lycaeum, PubChem and equivalents), and criminal operational logistics. See [DESIGN.md §12](docs/DESIGN.md) for the full dual-use treatment.

## Threat model

LookSmart targets two of the four classical cover-traffic objectives:

| Objective | Status | Mechanism |
|---|---|---|
| 1. Cohort hiding (anonymity) | Out of scope | Not achievable against authenticated providers |
| 2. Profile inversion | Rejected | Operationally fragile |
| 3. **Profile dilution** | **Primary** | KL divergence between advertised and real profiles |
| 4. **Cost imposition** | **Co-primary** | Per-provider-layer compute and review-queue overhead |

Full threat-model enumeration in [DESIGN.md §2](docs/DESIGN.md).

## Architecture (one-screen summary)

Five subsystems. See [DESIGN.md §5](docs/DESIGN.md) for the full spec.

- **Persona Sampler** — Two-stage sample (persona, then content) with ℓ-diversity discipline and power-law weights.
- **Behavioral Scheduler** — Non-homogeneous Poisson / Hawkes process fit to the user's actual interarrival distribution.
- **Engagement Simulator** — Multi-turn decoy sessions with calibrated copy events, regenerations, follow-ups. **(Hardest unsolved problem; see [Contributing](#contributing).)**
- **CooKoo Filter Mode** — Per-real-query wrapping (cohort context / topic distractor / register modulation / provider-behavior probing) with cuckoo-filter dedup and SQLite tracking. User's prose passes through verbatim.
- **Echo Mode** — Local correlation engine joining the query log against recommender data from other platforms (YouTube, Google, Amazon, Spotify, Twitter/X). First public infrastructure for per-user empirical measurement of cross-platform data leakage.

Plus a salted-hash audit subsystem that prevents the local log from becoming a deconfusion oracle if subpoenaed.

## Current status

This repository is the **design phase**. The v0.5 design document is complete and is published in full at [docs/DESIGN.md](docs/DESIGN.md). Implementation has not started; this is a pre-launch artifact and a contributor recruitment surface.

The design doc went through five major iterations including a substantive correction in v0.4 around cohort cover for high-exposure dimensions (see [DESIGN.md §5.15](docs/DESIGN.md)). Read the doc before opening issues that touch threat-model assumptions or any of the §5.15–§5.21 cohort modes — the corrections matter.

## Contributing

This is a serious-contributor recruitment. Specific asks:

- **Engagement-simulation research.** The hardest unsolved problem in §5.4. Closest published analogs are bot-detection adversarial literature, mostly written from the defender side. If you've worked in synthetic interaction modeling, behavioral biometrics adversarial ML, or queueing-theory traffic synthesis, open an issue tagged `engagement-simulation`.

- **Adversarial ML measurement.** Help calibrate the §5.18–§5.21 population-classifier-degradation mechanism against real provider classifier behavior. Issue tag: `adversarial-ml`.

- **Persona-library curation** across underrepresented dimensions: non-Western political philosophy, cross-tradition theological corpora, identity-search-state real-life narratives, immigration-process content across many starting jurisdictions, harm-reduction-conventional health queries in the conventions the community actually uses. **Anti-signature discipline is the constraint** — curators whose curation reflects population reality rather than personal taste. Issue tag: `persona-library`.

- **Browser-extension developers** for Echo Mode recommender-data capture (YouTube, Google, Amazon, Spotify, Twitter/X, Reddit, plus generic DOM capture for the long tail). Issue tag: `echo-mode`.

- **Per-provider ToS legal review** across major commercial LLM providers and major jurisdictions. CooKoo Filter Mode (§5.17) and engagement simulation (§5.4) are the two largest ToS-pressure vectors and need counsel review before recommended-on status. Issue tag: `tos-review`.

- **Empirical privacy research** for the differential-privacy / k-anonymity discipline on the opt-in Echo Mode community-aggregation tier. Issue tag: `community-aggregation`.

Read [docs/DESIGN.md](docs/DESIGN.md) before opening substantive issues. Read [Geer's 2014 RSA talk](http://geer.tinho.net/geer.rsa.28ii14.txt) before reading the design doc. The rest is implementation detail on a thesis Geer already proved.

### What I am asking for less of

Privacy-tribal performance, anti-AI signaling, accelerationist framing, anything that would make this tool a useful classification target rather than useful infrastructure. The honeytrap problem is real and LookSmart is designed structurally to avoid it: productivity-first framing, distribution through knowledge-work channels rather than privacy-enthusiast circles, dual-purpose user benefit by construction.

## License

- **Core implementation:** Apache 2.0
- **Persona libraries:** CC BY-SA — derivative libraries must be share-alike, which is load-bearing for the anti-signature discipline (curated libraries that fork private don't help the cohort)
- **Enterprise deployment kit:** Commercial license. Message [@Pinnacle-Quantum-Group](https://github.com/Pinnacle-Quantum-Group) if your operational privacy needs require the hardened build.

## Prior art (anchor citations)

- Geer, D. E. (2014). *We Are All Intelligence Officers Now.* RSA Conference keynote. [Canonical text](http://geer.tinho.net/geer.rsa.28ii14.txt)
- Howe, D. C. & Nissenbaum, H. (2009). *TrackMeNot: Resisting Surveillance in Web Search.*
- Sassaman, L., Cohen, B., & Mathewson, N. (2005). *The Pynchon Gate.* WPES.
- Piotrowska, A. M., et al. (2017). *The Loopix Anonymity System.* USENIX Security.
- Lazar, D., Gilad, Y., & Zeldovich, N. (2018). *Karaoke: Distributed Private Messaging Immune to Passive Traffic Analysis.* OSDI.
- Machanavajjhala, A., et al. (2006). *ℓ-Diversity: Privacy Beyond k-Anonymity.* ICDE.
- Narayanan, A., et al. (2012). *On the Feasibility of Internet-Scale Author Identification.* IEEE S&P.

Full reference list with verification notes in [docs/DESIGN.md §10](docs/DESIGN.md).

## Honest limitations

This document and this project make claims they can be embarrassed by. The most important ones are documented in [DESIGN.md §11](docs/DESIGN.md). Read it. The engagement-simulation problem is unsolved. The adoption math for population-scale classifier degradation is unforgiving. The ToS posture is jurisdiction- and provider-dependent. None of this is hidden.

## Maintainer

[Michael A. Doran Jr.](https://www.linkedin.com/in/michaeldoranjr/) · Pinnacle Quantum Group

*Ad Majorem Dei Gloriam.*
