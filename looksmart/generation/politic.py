"""PoliticRoulette Mode -- cross-spectrum political philosophy (README §5.12).

Random-walk decoy queries across the full political-thought spectrum. Genuine
cross-spectrum coverage is the load-bearing requirement (complication 2): a
library skewed to the user's own position signal-amplifies instead of diluting.
Contemporary-figure entries are fence-adjacent and gated behind
``contemporary_rate`` (complication 1). Includes the "Winnie/based/glowie"
innocent-but-classifier-noisy family.

Hard constraints (§5.12): no targeting identifiable living *private* individuals,
no harassment-advancement, no election-disinformation drafting -- enforced by the
shared curator (criminal-logistics / legal-false-statement deny-lists) plus
human-vetted seeds that only reference public figures who entered political
discourse voluntarily.
"""

from __future__ import annotations

from ..models import GenerationMode
from .spectrum import SpectrumGenerator

_BANK = {
    "far_left": [
        "What did Lenin actually argue in 'Imperialism, the Highest Stage of Capitalism'?",
        "How does Mao's 'On Contradiction' differ from orthodox Marxist dialectics?",
        "What is Frantz Fanon's argument about colonial violence in 'The Wretched of the Earth'?",
    ],
    "left": [
        "What did Marcuse mean by 'repressive tolerance'?",
        "How does Habermas describe the structural transformation of the public sphere?",
        "What is Judith Butler's concept of gender performativity, in brief?",
    ],
    "liberal": [
        "What is Rawls's 'veil of ignorance' and how does it justify his difference principle?",
        "How did John Stuart Mill defend free speech in 'On Liberty'?",
        "What is Isaiah Berlin's distinction between positive and negative liberty?",
    ],
    "centrist": [
        "What is the median-voter theorem and where does it break down?",
        "How do political scientists define the Overton window?",
        "What did Tocqueville observe about associations in 'Democracy in America'?",
    ],
    "conservative": [
        "What was Edmund Burke's core objection to the French Revolution?",
        "How does Hayek's 'spontaneous order' argue against central planning?",
        "What is Michael Oakeshott's critique of rationalism in politics?",
    ],
    "far_right": [
        "What is Carl Schmitt's friend-enemy distinction in 'The Concept of the Political'?",
        "What does Curtis Yarvin (Mencius Moldbug) mean by 'the Cathedral'?",
        "How do scholars summarize Julius Evola's critique of modernity?",
    ],
    "non_western": [
        "What is Confucius's account of social order through ritual (li)?",
        "How does Ibn Khaldun explain the rise and fall of dynasties in the Muqaddimah?",
        "What are the core ideas of Kwame Nkrumah's pan-Africanism?",
    ],
    "classical": [
        "How does Aristotle classify regimes in the 'Politics'?",
        "What is Cicero's argument about natural law in 'De Re Publica'?",
        "What did Aquinas mean by the natural law's relation to eternal law?",
    ],
    # contemporary / fence-adjacent (Winnie/based/glowie family + living figures)
    "contemporary": [
        "Why is Winnie the Pooh associated with Xi Jinping and censored in China?",
        "What does it mean when someone online says a take is 'based'?",
        "What is 'glowie' short for and where did the slang come from?",
        "Why is the okay-hand-sign considered controversial?",
        "What's the Reagan 'bear in the woods' campaign ad actually about?",
    ],
}

_DEFAULT_BALANCE = {
    "far_left": 0.10,
    "left": 0.15,
    "liberal": 0.15,
    "centrist": 0.10,
    "conservative": 0.15,
    "far_right": 0.10,
    "non_western": 0.15,
    "classical": 0.10,
    # contemporary is selectable but then gated by contemporary_rate (default 0
    # => always re-rolled to a historical category). Small weight so that with
    # contemporary_rate>0 the Winnie/based/glowie family actually appears.
    "contemporary": 0.10,
}


class PoliticGenerator(SpectrumGenerator):
    mode = GenerationMode.POLITIC_ROULETTE
    SEED_BANK = _BANK
    DEFAULT_BALANCE = _DEFAULT_BALANCE
    DEFAULT_REGISTERS = [
        "academic_serious",
        "undergraduate_curious",
        "journalistic_explainer",
        "bad_faith_question_resolving_to_good_faith_answer",
    ]
    CONTEMPORARY_KEYS = {"contemporary"}
