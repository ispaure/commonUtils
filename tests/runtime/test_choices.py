"""Choice identity, order and string-only presentation boundaries."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest

from commonUtils.runtime.choices import ChoiceOption, ChoiceSet


class ChoiceSetTests(unittest.TestCase):
    def test_order_lookup_and_none_identity_do_not_depend_on_labels(self):
        choices = ChoiceSet((ChoiceOption(None, 'Automatic'), ChoiceOption('text', 'Plain Text')))
        self.assertEqual(choices.labels, ('Automatic', 'Plain Text'))
        self.assertEqual(choices.index_of(None), 0)
        self.assertEqual(choices.by_id('text'), choices[1])
        self.assertIsNone(choices.from_label('Automatic').id)
        self.assertEqual(choices[:1], (choices[0],))
        translated = ChoiceSet((ChoiceOption('text', 'Texte'), ChoiceOption(None, 'Auto')))
        self.assertEqual(translated.index_of(None), 1)
        self.assertEqual(translated.by_id('text').label, 'Texte')

    def test_duplicate_ids_are_rejected_and_unknown_ids_do_not_fall_back(self):
        for identity in (None, 'same'):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                ChoiceSet((ChoiceOption(identity, 'First'), ChoiceOption(identity, 'Second')))
        choices = ChoiceSet((ChoiceOption('text', 'Plain Text'),))
        for lookup in (choices.by_id, choices.index_of, choices.from_label):
            with self.assertRaises(KeyError):
                lookup('unknown')

    def test_duplicate_labels_are_valid_ids_but_ambiguous_string_bindings_fail(self):
        choices = ChoiceSet((ChoiceOption('one', 'Same'), ChoiceOption('two', 'Same')))
        self.assertEqual(choices.by_id('two').id, 'two')
        with self.assertRaises(ValueError):
            choices.from_label('Same')

    def test_options_are_snapshotted_and_frozen(self):
        from dataclasses import FrozenInstanceError
        options = [ChoiceOption('one', 'One')]
        choices = ChoiceSet(options)
        options.append(ChoiceOption('two', 'Two'))
        self.assertEqual(len(choices), 1)
        with self.assertRaises(FrozenInstanceError):
            choices[0].label = 'Changed'


if __name__ == '__main__':
    unittest.main()
