"""Religious Mode -- cross-tradition theological queries (README §5.13).

Random-walk decoys across the world's religious/theological corpora. Cross-
tradition coverage produces a "religious-studies researcher" profile rather than
a partisan religious affiliation. Balance discipline (same as §5.12): a user who
only generates one tradition's decoys signals that affiliation.

Hard constraints (§5.13): no targeting identifiable *private* religious
individuals (public theologians/historical figures OK), no religious-hatred
drafting copy -- enforced by the shared curator plus human-vetted seeds.
"""

from __future__ import annotations

from ..models import GenerationMode
from .spectrum import SpectrumGenerator

_BANK = {
    "abrahamic_christian": [
        "What is Aquinas's distinction between the divine essence and divine energies?",
        "How does Karl Barth's doctrine of revelation differ from natural theology?",
        "What did Julian of Norwich mean by 'all shall be well'?",
    ],
    "abrahamic_jewish": [
        "How does Maimonides reconcile Aristotelian philosophy with Torah in the Guide?",
        "What is the difference in authority between the Talmud Bavli and Yerushalmi?",
        "What is Rashi's interpretive method in his commentary on Genesis?",
    ],
    "abrahamic_islamic": [
        "What are the main differences among the four Sunni madhabs on legal method?",
        "What is Ibn Arabi's concept of the 'unity of being' (wahdat al-wujud)?",
        "How does Ja'fari jurisprudence treat the role of the imam?",
    ],
    "dharmic_hindu": [
        "What is the difference between Shankara's Advaita and Ramanuja's Vishishtadvaita?",
        "How does the Bhagavad Gita reconcile action with renunciation?",
        "What is the concept of maya in Vedantic philosophy?",
    ],
    "dharmic_buddhist": [
        "How does Theravada's view of arhatship differ from the Mahayana bodhisattva ideal?",
        "What is the doctrine of dependent origination (pratityasamutpada)?",
        "What distinguishes Vajrayana practice from other Buddhist lineages?",
    ],
    "dharmic_other": [
        "What is the Jain principle of anekantavada (many-sidedness)?",
        "What is the significance of the Guru Granth Sahib in Sikh practice?",
    ],
    "east_asian": [
        "How do Daoist alchemical texts use the language of inner cultivation?",
        "What is the Confucian concept of ren (humaneness)?",
        "How does Shinto understand kami?",
    ],
    "indigenous_african": [
        "What is the role of Ifa divination in Yoruba religious practice?",
        "How do scholars describe the relationship between Orisha and devotees?",
    ],
    "indigenous_americas": [
        "What is the cosmological role of the Mesoamerican calendar systems?",
        "How do scholars approach the study of indigenous North American sacred geography?",
    ],
    "new_religious_movements": [
        "What is the LDS doctrine of eternal progression, in scholarly terms?",
        "What are the core teachings of the Baha'i faith on the unity of religions?",
    ],
    "esoteric": [
        "What is the relationship between Hermeticism and Renaissance Neoplatonism?",
        "How does Kabbalah describe the sefirot?",
        "What distinguishes Gnostic cosmology from orthodox Christian creation theology?",
    ],
    "comparative_secular": [
        "How does the academic field of religious studies define 'religion'?",
        "What is the phenomenological method in the study of religion?",
    ],
}

_DEFAULT_BALANCE = {
    "abrahamic_christian": 0.15,
    "abrahamic_jewish": 0.10,
    "abrahamic_islamic": 0.15,
    "dharmic_hindu": 0.10,
    "dharmic_buddhist": 0.10,
    "dharmic_other": 0.05,
    "east_asian": 0.10,
    "indigenous_african": 0.05,
    "indigenous_americas": 0.05,
    "new_religious_movements": 0.05,
    "esoteric": 0.05,
    "comparative_secular": 0.05,
}


class ReligiousGenerator(SpectrumGenerator):
    mode = GenerationMode.RELIGIOUS
    SEED_BANK = _BANK
    DEFAULT_BALANCE = _DEFAULT_BALANCE
    DEFAULT_REGISTERS = [
        "academic_theological",
        "devotional_practice",
        "historical_inquiry",
        "comparative_religion",
        "religious_aesthetics",
    ]
