"""Cohort Roulette Modes -- §5.18-§5.21 (population-classifier degradation).

GenderRoulette (§5.18), OrientationRoulette (§5.19), ImmigrationRoulette
(§5.20), HealthStatusRoulette (§5.21) as one parameterized SpectrumGenerator.

Unlike §5.16, these modes DELIBERATELY generate real content from the §5.15
high-exposure dimensions -- population-level classifier-degradation via training-
signal poisoning is the explicit point (§5.15). The cross-spectrum balance +
anti-signature discipline carry over from §5.12/§5.13: the library must NOT skew
to any single position within the dimension, or it leaves a signature (§5.18).

Per-mode hard constraints (curation, §5.18-§5.21):
  * no naming specific living *private* individuals;
  * no harassment-drafting copy;
  * no fraud-drafting copy (immigration / medical);
  * §12.5 global exclusions (and, for health, the §5.14 harm-vector layer).
These are enforced by the shared curator plus a cohort-specific deny-list and by
human-vetted seeds that reference only generic situations / public discourse.
"""

from __future__ import annotations

import re

from ..models import GenerationMode
from .curation import LibraryCurator
from .spectrum import SpectrumGenerator

# Cohort-wide hard-constraint deny-list (additive to §12.5 global curator).
_COHORT_DENY = [
    re.compile(p, re.IGNORECASE)
    for p in (
        # harassment-drafting copy
        r"\b(write|draft|compose|generate)\b.{0,40}\b(harassment|threat(ening)?|"
        r"dox(x)?(ing)?|hate (mail|message)|abusive (message|post))\b",
        # naming a specific private individual's status ("my neighbor John Smith is...")
        r"\bmy (neighbor|coworker|colleague|classmate|boss) [A-Z][a-z]+ [A-Z][a-z]+\b",
        # fraud-drafting (immigration / medical), beyond the global criminal-logistics rules
        r"\b(write|draft|fill out|complete)\b.{0,40}\b(fraudulent|fake|false)\b.{0,20}"
        r"\b(asylum claim|disability claim|insurance claim|visa application)\b",
        r"\bhow (to|do i)\b.{0,30}\bfake\b.{0,20}\b(a (diagnosis|disability)|"
        r"asylum|immigration status)\b",
    )
]


class _CohortGenerator(SpectrumGenerator):
    """Base for the four cohort roulette modes; layers cohort deny-list."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.curator = self._with_cohort_layer(self.curator)

    @staticmethod
    def _with_cohort_layer(curator) -> LibraryCurator:
        layered = LibraryCurator()
        layered._deny = {k: list(v) for k, v in curator._deny.items()}
        layered._deny.setdefault("cohort_hard_constraint", []).extend(_COHORT_DENY)
        return layered


# --- §5.18 GenderRoulette ---------------------------------------------------
class GenderRouletteGenerator(_CohortGenerator):
    mode = GenerationMode.GENDER_ROULETTE
    DEFAULT_REGISTERS = [
        "academic", "personal_narrative", "journalistic",
        "support_group_style", "clinical", "philosophical",
    ]
    SEED_BANK = {
        "cis_curious_academic": [
            "What is the history of the sex/gender distinction in feminist theory?",
            "How do anthropologists describe third-gender roles across cultures?",
        ],
        "trans_experience_narratives": [
            "What does the early process of social transition typically involve, day to day?",
            "How do people describe the experience of starting hormone therapy?",
        ],
        "nonbinary_exploration": [
            "What does it mean for someone to use they/them pronouns, and how is that handled at work?",
            "How do nonbinary people describe gender outside the binary?",
        ],
        "gender_questioning": [
            "How do people tell the difference between gender questioning and a passing phase?",
            "What resources exist for someone just starting to question their gender?",
        ],
        "detransition_narratives": [
            "What do detransition narratives have in common, according to researchers?",
            "How is detransition discussed in the clinical literature?",
        ],
        "critical_perspectives": [
            "What are the main arguments of gender-critical feminism?",
            "How do traditional religious frameworks understand gender roles?",
        ],
        "policy_and_legal": [
            "How does legal gender recognition vary across jurisdictions?",
            "What do healthcare-access debates around gender-affirming care turn on?",
        ],
        "cultural_and_historical": [
            "How was gender understood in different historical periods, like the Roman era?",
            "What cross-cultural variation exists in gender expression historically?",
        ],
        "intersection_queries": [
            "How does the literature treat the intersection of gender and race?",
            "How do class and gender intersect in labor history?",
        ],
    }
    DEFAULT_BALANCE = {
        "cis_curious_academic": 0.20,
        "trans_experience_narratives": 0.20,
        "nonbinary_exploration": 0.10,
        "gender_questioning": 0.10,
        "detransition_narratives": 0.05,
        "critical_perspectives": 0.10,
        "policy_and_legal": 0.10,
        "cultural_and_historical": 0.10,
        "intersection_queries": 0.05,
    }


# --- §5.19 OrientationRoulette ----------------------------------------------
class OrientationRouletteGenerator(_CohortGenerator):
    mode = GenerationMode.ORIENTATION_ROULETTE
    DEFAULT_REGISTERS = [
        "academic", "personal_narrative", "journalistic",
        "support_group_style", "clinical", "philosophical",
    ]
    SEED_BANK = {
        "hetero_curious_academic": [
            "What is the history of queer theory as an academic field?",
            "How do historians study same-sex relationships in the ancient world?",
        ],
        "gay_lesbian_experience": [
            "What do coming-out narratives commonly describe about the process?",
            "How do people navigate being out at work in different industries?",
        ],
        "bi_pan_exploration": [
            "How do people describe figuring out a bisexual or pansexual identity?",
            "What are common misconceptions about bisexuality the research addresses?",
        ],
        "asexual_identity": [
            "What does the asexual spectrum include, according to community sources?",
            "How is asexuality distinguished from low libido in the literature?",
        ],
        "polyamory_non_monogamy": [
            "How do people structure communication in polyamorous relationships?",
            "What does the research say about consensual non-monogamy outcomes?",
        ],
        "religious_orientation": [
            "How do people navigate the tension between a faith tradition and their orientation?",
            "How do different denominations approach same-sex relationships theologically?",
        ],
        "policy_and_legal": [
            "How did marriage-equality law develop across different countries?",
            "What employment-discrimination protections exist by orientation, by jurisdiction?",
        ],
        "cultural_and_historical": [
            "What is the history of Pride as a movement?",
            "How was orientation understood in different historical cultures?",
        ],
        "intersection_queries": [
            "How does the literature treat the intersection of orientation and race?",
            "How do orientation and disability intersect in scholarship?",
        ],
        "critical_perspectives": [
            "What are traditionalist religious objections to changing norms around orientation?",
            "How do critics of identity politics frame orientation categories?",
        ],
    }
    DEFAULT_BALANCE = {
        "hetero_curious_academic": 0.15,
        "gay_lesbian_experience": 0.20,
        "bi_pan_exploration": 0.10,
        "asexual_identity": 0.05,
        "polyamory_non_monogamy": 0.10,
        "religious_orientation": 0.10,
        "policy_and_legal": 0.10,
        "cultural_and_historical": 0.10,
        "intersection_queries": 0.05,
        "critical_perspectives": 0.05,
    }


# --- §5.20 ImmigrationRoulette ----------------------------------------------
class ImmigrationRouletteGenerator(_CohortGenerator):
    mode = GenerationMode.IMMIGRATION_ROULETTE
    DEFAULT_REGISTERS = [
        "personal_narrative", "attorney_consultation",
        "bureaucratic_navigation", "academic", "journalistic",
    ]
    SEED_BANK = {
        "legal_immigration_process": [
            "What are the differences between an H-1B and an O-1 visa category?",
            "What does the green-card-through-employment process involve, step by step?",
        ],
        "asylum_navigation": [
            "How does the affirmative asylum process work in general terms?",
            "What is the difference between asylum and refugee status?",
        ],
        "undocumented_navigation": [
            "What rights do people have during a workplace immigration check, in general?",
            "How do mixed-status families typically handle day-to-day paperwork?",
        ],
        "mixed_status_family": [
            "How do families with members of different immigration statuses plan for travel?",
            "What options exist for sponsoring a family member, in general terms?",
        ],
        "attorney_client_research": [
            "How do immigration courts detect fraudulent asylum claims?",
            "What questions should someone prepare before a first immigration-attorney consult?",
        ],
        "employer_sponsorship": [
            "What obligations does an employer take on when sponsoring a work visa?",
            "How does the labor-certification step of sponsorship work?",
        ],
        "international_relocation": [
            "What do digital nomads need to know about tax residency when relocating?",
            "How do expats typically handle healthcare when moving abroad?",
        ],
        "refugee_resettlement": [
            "How does refugee resettlement work through the UNHCR process?",
            "What support services do resettlement agencies typically provide?",
        ],
        "policy_and_history": [
            "What was the history of the Bracero program?",
            "How have asylum laws changed internationally over the past few decades?",
        ],
        "intersection_queries": [
            "How does immigration status intersect with labor rights in scholarship?",
            "How do gender and immigration intersect in the research literature?",
        ],
    }
    DEFAULT_BALANCE = {
        "legal_immigration_process": 0.20,
        "asylum_navigation": 0.15,
        "undocumented_navigation": 0.10,
        "mixed_status_family": 0.10,
        "attorney_client_research": 0.10,
        "employer_sponsorship": 0.10,
        "international_relocation": 0.10,
        "refugee_resettlement": 0.05,
        "policy_and_history": 0.05,
        "intersection_queries": 0.05,
    }


# --- §5.21 HealthStatusRoulette --------------------------------------------
class HealthStatusRouletteGenerator(_CohortGenerator):
    mode = GenerationMode.HEALTH_STATUS_ROULETTE
    DEFAULT_REGISTERS = [
        "support_group_style", "clinical", "personal_narrative",
        "journalistic", "policy_research",
    ]
    SEED_BANK = {
        "hiv_status_navigation": [
            "How do people approach disclosing HIV status to a new partner?",
            "What does U=U (undetectable equals untransmittable) mean clinically?",
        ],
        "mental_health_diagnosis": [
            "How do people navigate disclosing a bipolar diagnosis to an employer?",
            "What does an adult ADHD or autism diagnosis process typically involve?",
        ],
        "addiction_recovery": [
            "How do people in recovery talk about disclosure in new workplaces?",
            "What does the research say about long-term recovery support structures?",
        ],
        "chronic_illness_disclosure": [
            "How do people decide whether to disclose a chronic illness at work?",
            "What workplace accommodations are common for chronic conditions?",
        ],
        "terminal_diagnosis": [
            "How do people approach planning conversations after a terminal diagnosis?",
            "What does palliative care involve compared to hospice?",
        ],
        "pregnancy_loss": [
            "How do people navigate telling others about a pregnancy loss?",
            "What support resources exist for processing pregnancy loss?",
        ],
        "neurological": [
            "How do people manage disclosing epilepsy to employers and friends?",
            "What does an MS diagnosis typically involve in early stages?",
        ],
        "intersection_queries": [
            "How does chronic illness intersect with employment law?",
            "How do mental health and immigration status intersect in research?",
        ],
        "policy_and_history": [
            "What is the history of HIV-disclosure criminalization laws?",
            "How has mental-health parity in insurance changed over time?",
        ],
    }
    DEFAULT_BALANCE = {
        "hiv_status_navigation": 0.15,
        "mental_health_diagnosis": 0.20,
        "addiction_recovery": 0.10,
        "chronic_illness_disclosure": 0.15,
        "terminal_diagnosis": 0.05,
        "pregnancy_loss": 0.10,
        "neurological": 0.10,
        "intersection_queries": 0.10,
        "policy_and_history": 0.05,
    }
