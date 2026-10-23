"""Toolkit-independent editor language choices and automatic/manual selection."""
from ..runtime.choices import ChoiceOption, ChoiceSet
from .code_syntax import LANGUAGES, detect_language


AUTOMATIC = ChoiceOption(None, 'Automatic')
LANGUAGE_CHOICES = ChoiceSet((AUTOMATIC, *(ChoiceOption(code, name) for name, code in LANGUAGES)))
_LABELS = {choice.id: choice.label for choice in LANGUAGE_CHOICES}


def language_choices(*, extended=False):
    """Curated native choices, optionally expanded for the desktop chooser."""
    if not extended:
        return LANGUAGE_CHOICES
    from pygments.lexers import get_all_lexers
    choices = {choice.id: choice for choice in LANGUAGE_CHOICES[1:]}
    for name, aliases, _, _ in get_all_lexers():
        if aliases:
            choices.setdefault(aliases[0], ChoiceOption(aliases[0], name))
    plain = choices.pop('text')
    return ChoiceSet((AUTOMATIC, plain, *sorted(choices.values(), key=lambda choice: choice.label)))


def language_label(identity):
    """Curated display name, falling back to an extended/unknown language ID."""
    return _LABELS.get(identity, identity)


class LanguageSelection:
    """A per-document choice; None means Automatic, 'text' means manual Plain Text.

    Detection stays current even during a manual override, so returning to
    Automatic uses the current name/content. No widget, document or persistence
    owner is retained here.
    """
    def __init__(self):
        self.selected_id = None
        self.detected_id = 'text'
        self._source = None

    @property
    def automatic(self):
        return self.selected_id is None

    @property
    def language_id(self):
        return self.detected_id if self.automatic else self.selected_id

    def select(self, language_id):
        if language_id is not None and (
                not isinstance(language_id, str) or not language_id.strip() or len(language_id) > 100):
            raise ValueError('Invalid syntax language ID.')
        self.selected_id = language_id

    def update(self, path, text=''):
        """Return whether the effective language changed; only inspect a prefix."""
        source = (str(path) if path else '', text[:256])
        previous = self.language_id
        if source != self._source:
            self.detected_id = detect_language(*source)
            self._source = source
        return self.language_id != previous
