"""Offline language decisions with real profiles and installed-voice constraints."""
import unittest
from commonUtils.runtime.speech_language import passage_language, matching_locale


class SpeechLanguageTests(unittest.TestCase):
    def test_real_multilingual_passages(self):
        samples = {
            'fr': "Le petit garçon ouvre la porte de la maison. Il regarde le jardin et cherche son livre sur la table.",
            'es': "La niña abrió la puerta de la casa y miró hacia el jardín. Quería encontrar el libro que había dejado sobre la mesa.",
            'de': "Der kleine Junge öffnete die Tür des Hauses. Er schaute in den Garten und suchte das Buch auf dem Tisch.",
            'it': "La ragazza aprì la porta della casa e guardò il giardino. Cercava il libro che aveva lasciato sul tavolo.",
            'ja': "少年は家の扉を開けて庭を見ました。テーブルの上に置いた本を探していました。今日はとても良い天気です。",
            'en': "The little boy opened the door of the house. He looked into the garden and searched for the book on the table.",
        }
        for language, text in samples.items():
            with self.subTest(language=language):
                self.assertEqual(passage_language(text, 'en'), language)
                self.assertEqual(passage_language(text), language)

    def test_short_or_nonlinguistic_text_uses_metadata(self):
        self.assertEqual(passage_language('12345 ...'), '')
        self.assertEqual(passage_language('Bonjour', 'fr_CA'), 'fr-ca')
        self.assertEqual(passage_language('', 'fra'), 'fr')

    def test_matching_uses_language_boundaries_and_dialects(self):
        offered = ['en-US', 'fr-FR', 'fr-CA', 'es-ES']
        self.assertEqual(matching_locale('fr', offered, 'fr-CA'), 'fr-CA')
        self.assertEqual(matching_locale('fr-FR', offered, 'fr-CA'), 'fr-FR')
        self.assertEqual(matching_locale('de', offered, 'en-US'), '')
        self.assertEqual(matching_locale('', offered), '')
        self.assertEqual(matching_locale('zh-tw', ['zh-CN', 'zh-TW']), 'zh-TW')
        self.assertEqual(matching_locale('no', ['nb-NO']), 'nb-NO')
