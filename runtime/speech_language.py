"""Offline passage language detection and installed-locale matching.

Only the detector's language profiles are retained; document text is never cached.
Consumers install langdetect when automatic detection is wanted.
"""
from functools import lru_cache
import re


def language_tag(value):
    tag = str(value or '').strip().replace('_', '-').lower()
    aliases = {'eng': 'en', 'fra': 'fr', 'fre': 'fr', 'deu': 'de', 'ger': 'de',
               'spa': 'es', 'ita': 'it', 'por': 'pt', 'zho': 'zh', 'chi': 'zh',
               'jpn': 'ja', 'kor': 'ko', 'rus': 'ru', 'ara': 'ar', 'nob': 'nb',
               'nor': 'no', 'iw': 'he', 'in': 'id', 'fil': 'tl'}
    parts = tag.split('-')
    parts[0] = aliases.get(parts[0], parts[0])
    return '-'.join(parts) if re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]{2,8})*', '-'.join(parts)) else ''


@lru_cache(maxsize=1)
def _factory():
    from langdetect.detector_factory import DetectorFactory, PROFILES_DIRECTORY
    factory = DetectorFactory()
    factory.seed = 0
    factory.load_profile(PROFILES_DIRECTORY)
    return factory


def passage_language(text, hint=''):
    """Detect a bounded sample, falling back to metadata for ambiguous passages."""
    sample = text[:6000]
    if sum(char.isalpha() for char in sample) >= 20:
        try:
            from langdetect.lang_detect_exception import LangDetectException
        except ImportError:
            return language_tag(hint)
        try:
            detector = _factory().create()
            detector.append(sample)
            results = detector.get_probabilities()
            if results and results[0].prob >= .85:
                return language_tag(results[0].lang)
        except LangDetectException:
            pass
    return language_tag(hint)


def matching_locale(language, locales, preferred=''):
    """Return an offered locale tag, preserving a preferred matching dialect."""
    language = language_tag(language)
    if not language:
        return ''
    offered = list(locales)
    def compatible(tag):
        base = language_tag(tag).split('-')[0]
        target = language.split('-')[0]
        return base == target or {base, target} <= {'no', 'nb', 'nn'}
    matches = [tag for tag in offered if compatible(tag)]
    return next((tag for tag in matches if language_tag(tag) == language),
                preferred if preferred in matches else next(iter(matches), ''))
