"""Library curation: the security guardrail (README §12.4-§12.5, §4 principle 12).

This module is the single hard-exclusion chokepoint for ALL generated and seed
decoy content. Every decoy generator (§5.9-§5.21) MUST route its output through
:func:`is_excluded` (or :meth:`LibraryCurator.check`) before emitting a Query or
Session. On exclusion the generator resamples; it does not patch and ship.

What this enforces (§12.5 hard, non-negotiable exclusions):

  1. Content facilitating harm to children (grooming / CSAM-adjacent).
  2. Material support to designated terrorist organizations.
  3. WMD synthesis (bio / nuclear / chemical weapons).
  4. Drug-chemistry-DATABASE access-pattern mimicry (Lycaeum / Erowid / PubChem
     and equivalents). This is the access-pattern mimicry exclusion ONLY -- per
     §12.5 and §5.14, ordinary harm-reduction health questions (drug
     interactions, dosage, mental-health symptoms in the SWIM register) are
     explicitly ALLOWED and are NOT excluded here.
  5. Operational criminal logistics: drafting copy for fraud, trafficking,
     smuggling, document forgery, organized violence. Discussion AS a research /
     journalism / policy topic stays in scope (the §5.10 fence band); drafting
     operational copy does not.
  6. Content committing users to false statements that would be evidentiary in
     real (non-chatbot) legal proceedings (§5.17 constraint 2, corrected).

It additionally provides the HUMAN-CURATED SEED constants for the fence (§5.10)
and health (§5.14) libraries. Per §5.10/§5.14 the local LLM is NOT trusted to
freely generate these categories: it may only do *paraphrastic variation* of
these vetted seeds within tight constraints, never freeform generation. Those
generators (fence.py, health.py) draw their base content from these constants
and route every variant back through the curator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Exclusion category identifiers -----------------------------------------

CAT_CHILD_HARM = "child_harm"
CAT_TERROR_SUPPORT = "terror_material_support"
CAT_WMD = "wmd_synthesis"
CAT_DRUG_DB_PATTERN = "drug_chemistry_database_pattern"
CAT_CRIMINAL_LOGISTICS = "criminal_operational_logistics"
CAT_LEGAL_FALSE_STATEMENT = "legal_false_statement"

ALL_CATEGORIES = (
    CAT_CHILD_HARM,
    CAT_TERROR_SUPPORT,
    CAT_WMD,
    CAT_DRUG_DB_PATTERN,
    CAT_CRIMINAL_LOGISTICS,
    CAT_LEGAL_FALSE_STATEMENT,
)


def _rx(*patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# --- Deny patterns, per category --------------------------------------------
#
# These are intentionally over-inclusive on the genuinely-harmful side: the cost
# of a false exclusion is a resampled decoy (invisible to the user, §4
# principle 11), while the cost of a false admission is a public-safety channel
# degraded or an account banned. We err toward exclusion.
#
# Each pattern aims at *operational / facilitation* phrasing, not at the mere
# appearance of a sensitive proper noun -- §5.10/§5.12/§5.14 explicitly want
# classifier-noisy-but-benign content (Holocaust research, ballistics for
# fiction, harm-reduction dosage questions) to PASS.

_CHILD_HARM = _rx(
    r"\bchild\b.{0,30}\b(porn|sex|sexual|exploit|nude|naked|groom)",
    r"\b(porn|sex|sexual|nude|naked|explicit).{0,30}\b(child|minor|kid|preteen|underage|toddler|infant)",
    r"\bcsam\b",
    r"\bgroom(ing)?\b.{0,40}\b(child|minor|kid|underage|teen|boy|girl)",
    r"\b(minor|underage|preteen|jailbait)\b.{0,30}\b(sexual|sexually|nude|explicit|fantas)",
    r"\bhow to .{0,40}\b(lure|abduct|molest)\b",
)

_TERROR_SUPPORT = _rx(
    # material support: funding / joining / supplying designated orgs
    r"\b(fund|finance|funding|donate|send money|provide weapons|recruit for|join|pledge allegiance to)\b"
    r".{0,40}\b(isis|isil|daesh|al[- ]?qaeda|al[- ]?shabaab|boko haram|hezbollah|hamas|"
    r"designated terrorist|terrorist (organization|org|group|cell))",
    r"\b(material support|provide support)\b.{0,40}\bterror",
    r"\bhow (to|do i)\b.{0,40}\b(join|support|fund)\b.{0,20}\b(jihad|terror|isis|al[- ]?qaeda)",
)

_WMD = _rx(
    r"\b(synthesi[sz]e|manufactur|produc|make|build|cook|weaponi[sz]e)\b"
    r".{0,40}\b(sarin|vx nerve|tabun|soman|mustard gas|nerve agent|"
    r"anthrax|botulinum|ricin|smallpox|weaponi[sz]ed (virus|pathogen|anthrax)|bioweapon|"
    r"nuclear (bomb|weapon|device)|dirty bomb|enrich(ed|ment)? uranium|plutonium (core|pit)|"
    r"chemical weapon)",
    r"\b(recipe|instructions|protocol|steps|procedure)\b.{0,40}"
    r"\b(nerve agent|bioweapon|chemical weapon|dirty bomb|sarin|ricin|anthrax|weaponi[sz]ed)",
    r"\bgain[- ]of[- ]function\b.{0,40}\b(weaponi|enhance lethality|make.{0,10}deadlier)",
)

# Drug-chemistry-DATABASE access-pattern mimicry ONLY (§12.5 / §4 principle 12).
# NOT ordinary harm-reduction (those are §5.14 and must pass). We fire on the
# database-name access pattern and on clandestine-synthesis phrasing, NOT on
# dosage/interaction/symptom questions.
_DRUG_DB_PATTERN = _rx(
    r"\b(erowid|lycaeum|pubchem|rhodium archive|the hive|totse|vault of erowid)\b",
    r"\berowid (vault|experience report|dose chart|lookup)\b",
    r"\b(rhodium|hive)\b.{0,20}\b(synthesis|writeup|method)\b",
    # clandestine-synthesis access pattern (shake-and-bake / clandestine routes)
    r"\b(synthesi[sz]e|cook|clandestine (synthesis|production)|home(-| )?(synth|cook))\b"
    r".{0,30}\b(methamphetamine|meth|mdma|lsd|fentanyl|dmt|amphetamine|cocaine free.?base)\b",
    r"\b(shake and bake|one[- ]?pot)\b.{0,20}\bmeth",
    r"\b(reductive amination|birch reduction|nazi method|red phosphorus route)\b",
)

_CRIMINAL_LOGISTICS = _rx(
    # drafting operational copy -- imperative "write/draft/generate ... for fraud/scam"
    r"\b(write|draft|compose|generate|create)\b.{0,40}"
    r"\b(phishing (email|message|page)|scam (script|email|letter)|"
    r"419 letter|romance scam|fake invoice|fraudulent (invoice|claim|application)|"
    r"ransom note|extortion (letter|message))",
    r"\b(how to|steps to|instructions to)\b.{0,40}"
    r"\b(launder money|smuggle (people|migrants|drugs|guns|weapons)|"
    r"forge (a |the )?(passport|visa|id|document)|counterfeit (currency|money|documents)|"
    r"traffic (people|humans|drugs|weapons)|evade (customs|border)|"
    r"clone (a )?(credit )?card|skim (credit )?cards)",
    r"\b(fraudulent|fake|forged)\b.{0,20}\b(visa|asylum|passport|green card)\b.{0,30}"
    r"\b(application|how to|draft|write|instructions)",
    r"\bdocument forgery (instructions|guide|how)\b",
)

_LEGAL_FALSE_STATEMENT = _rx(
    r"\b(write|draft|generate|compose)\b.{0,40}"
    r"\b(sworn (statement|affidavit)|affidavit|under penalty of perjury|"
    r"declaration for (court|the court)|witness statement for (a |the )?(trial|case|court)|"
    r"false (alibi|testimony))",
    r"\b(fake|false|fabricated)\b.{0,20}\b(alibi|affidavit|sworn statement|testimony|"
    r"evidence for court)\b",
)

_DENY: dict[str, list[re.Pattern[str]]] = {
    CAT_CHILD_HARM: _CHILD_HARM,
    CAT_TERROR_SUPPORT: _TERROR_SUPPORT,
    CAT_WMD: _WMD,
    CAT_DRUG_DB_PATTERN: _DRUG_DB_PATTERN,
    CAT_CRIMINAL_LOGISTICS: _CRIMINAL_LOGISTICS,
    CAT_LEGAL_FALSE_STATEMENT: _LEGAL_FALSE_STATEMENT,
}


@dataclass(frozen=True)
class CurationResult:
    excluded: bool
    category: str  # the §12.5 category that fired, or "" if clean
    reason: str  # human-readable explanation


class LibraryCurator:
    """The hard-exclusion hook. Stateless and cheap; safe to share/reuse.

    Generators construct (or are handed) one of these and call :meth:`check`
    on every candidate string before it becomes a Query/Turn.
    """

    def __init__(self, extra_patterns: dict[str, list[re.Pattern[str]]] | None = None):
        self._deny = {k: list(v) for k, v in _DENY.items()}
        if extra_patterns:
            for cat, pats in extra_patterns.items():
                self._deny.setdefault(cat, []).extend(pats)

    def check(self, text: str, category: str | None = None) -> CurationResult:
        """Return a :class:`CurationResult`.

        `category` is the generator's own mode/category label, used only for
        diagnostics; the deny-lists are applied globally regardless.
        """
        if text is None:
            return CurationResult(True, CAT_CHILD_HARM, "empty/None content rejected")
        for cat, patterns in self._deny.items():
            for pat in patterns:
                if pat.search(text):
                    return CurationResult(
                        excluded=True,
                        category=cat,
                        reason=f"matched hard-exclusion {cat!r} via /{pat.pattern[:48]}/",
                    )
        return CurationResult(False, "", "clean")

    def assert_clean(self, text: str, category: str | None = None) -> None:
        """Raise :class:`CurationError` if `text` is excluded (defensive use)."""
        res = self.check(text, category)
        if res.excluded:
            raise CurationError(res.reason, res.category)


class CurationError(RuntimeError):
    def __init__(self, message: str, category: str):
        super().__init__(message)
        self.category = category


# Module-level default instance + functional facade (the spec's required hook).
_DEFAULT = LibraryCurator()


def is_excluded(text: str, category: str | None = None) -> tuple[bool, str]:
    """The mandatory pre-emit hook (spec signature).

    Returns ``(excluded, reason)``. ``reason`` is the firing §12.5 category id
    when excluded, else ``""``.
    """
    res = _DEFAULT.check(text, category)
    return (res.excluded, res.category if res.excluded else "")


# ---------------------------------------------------------------------------
# HUMAN-CURATED SEED LIBRARIES (§5.10 fence, §5.14 health).
#
# These are vetted benign seeds. The local LLM does PARAPHRASTIC variation of
# these only -- never freeform generation of these categories (§5.10/§5.14).
# Every seed below has been written to sit in the "classifier-fires-but-query-
# is-benign" band and to clear the curator. They are organized by the category
# keys the configs reference.
# ---------------------------------------------------------------------------

FENCE_SEEDS: dict[str, list[str]] = {
    "moral_hypotheticals": [
        "In the trolley problem, does it matter morally if the one person on the "
        "side track is someone you know personally?",
        "Is it ever ethical to lie to a murderer asking where their victim is "
        "hiding? Kant said no -- what's the strongest counterargument?",
        "If a self-driving car must choose between hitting one pedestrian or "
        "swerving and killing its passenger, what framework should govern that?",
    ],
    "dark_humor_legitimate": [
        "What's the history of gallows humor among soldiers in the trenches of "
        "World War I?",
        "Why do comedians say tragedy plus time equals comedy, and is there any "
        "research behind that idea?",
        "How did satirical cartoonists treat the sinking of the Titanic in the "
        "weeks afterward?",
    ],
    "historical_atrocity_research": [
        "What were the logistical and bureaucratic mechanisms that made the "
        "Holocaust possible, for a history paper?",
        "How did radio propaganda contribute to the Rwandan genocide in 1994?",
        "What was the route and death toll of the Trail of Tears, and how is it "
        "taught today?",
    ],
    "harm_reduction": [
        "What are the dangerous interactions between alcohol and common "
        "benzodiazepines that people should know about?",
        "What are the warning signs of an opioid overdose and when should "
        "someone call emergency services?",
        "Why is fentanyl test-strip distribution considered a public-health "
        "harm-reduction measure?",
    ],
    "fiction_research_violence": [
        "For a thriller I'm writing, how did 19th-century naval cannons actually "
        "load and fire, step by step in general terms?",
        "What kind of injuries would a sword duel realistically produce, for a "
        "historical-fiction fight scene?",
        "How did medieval siege weapons like trebuchets work, for a fantasy "
        "novel?",
    ],
    "transgressive_philosophy": [
        "What is Carl Schmitt's concept of 'the political' and why is it so "
        "controversial among liberal theorists?",
        "How did Georges Sorel's 'Reflections on Violence' influence both left "
        "and right movements?",
        "What did the Frankfurt School mean by 'repressive tolerance' in "
        "Marcuse's essay?",
    ],
    "transgressive_art_criticism": [
        "Why do critics treat the Marquis de Sade as a serious literary subject "
        "rather than just pornography?",
        "What is Georges Bataille's theory of transgression in 'Erotism'?",
        "How do scholars analyze body horror in the films of David Cronenberg as "
        "cultural commentary?",
    ],
    "misread_innocent": [
        "How do I get my toddler to actually take their antibiotics without "
        "spitting them out?",
        "What's the safest way to put down an elderly pet who is suffering, "
        "through a veterinarian?",
        "How do I kill the weeds taking over my vegetable garden without "
        "poisoning the vegetables?",
    ],
}

# §5.14 health seeds. Bound by §5.14 constraints: NO lethal-dose info, NO
# suicide-method info, NO eating-disorder coaching, NO prescription-substitution,
# NO named non-public individuals. These seeds are deliberately the benign
# harm-reduction / embarrassing-health register.
HEALTH_SEEDS: dict[str, list[str]] = {
    "medication_questions": [
        "Asking for a friend -- can you take ibuprofen and acetaminophen at the "
        "same time, or do you have to space them out?",
        "What are the common side effects of starting an SSRI in the first two "
        "weeks?",
    ],
    "drug_interactions": [
        "SWIM was wondering whether mixing antihistamines with melatonin is a bad "
        "idea for sleep.",
        "Hypothetically, if someone drinks grapefruit juice, which common "
        "medications does that interfere with?",
    ],
    "mental_health_symptoms": [
        "Asking for a friend -- how do you tell the difference between normal "
        "stress and an actual anxiety disorder?",
        "I have this friend who can't concentrate and wonders if it might be "
        "adult ADHD -- what are the signs?",
    ],
    "sexual_health": [
        "Asking for a friend, how often should someone get tested for STIs if "
        "they're dating casually?",
        "What's the difference between a yeast infection and a UTI in terms of "
        "symptoms?",
    ],
    "embarrassing_physical": [
        "Asking for a friend -- what causes excessive sweating and what actually "
        "helps with it?",
        "Hypothetically if someone has had a canker sore for a week, when should "
        "they see a doctor?",
    ],
    "sleep_disorders": [
        "Asking because I'm curious -- what is sleep apnea and how do people get "
        "diagnosed with it?",
    ],
    "chronic_conditions": [
        "I have this friend with type 2 diabetes who's confused about how carb "
        "counting works -- can you explain?",
        "Asking for a friend, what lifestyle changes actually help with high "
        "blood pressure?",
    ],
    "emergency_recognition": [
        "Asking for a friend -- what are the FAST warning signs that someone might "
        "be having a stroke?",
        "How do you tell if a skin reaction is a normal rash or an allergic "
        "reaction that needs emergency care?",
    ],
}


def validate_seed_libraries() -> None:
    """Sanity check at import-time-callable scope: every shipped human seed must
    itself clear the curator. A seed that doesn't is a curation bug, not a
    runtime resample. Tests call this."""
    for lib_name, lib in (("FENCE_SEEDS", FENCE_SEEDS), ("HEALTH_SEEDS", HEALTH_SEEDS)):
        for category, seeds in lib.items():
            for seed in seeds:
                excluded, reason = is_excluded(seed, category)
                if excluded:
                    raise CurationError(
                        f"{lib_name}[{category!r}] seed fails curation: "
                        f"{reason} :: {seed!r}",
                        reason,
                    )
