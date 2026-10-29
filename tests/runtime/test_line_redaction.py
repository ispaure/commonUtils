"""Line filters retain PEM state; callers supply secrets explicitly."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from commonUtils.runtime.diagnostics.redaction import LineRedactor, redact


class LineRedactionTests(unittest.TestCase):
    def test_pem_state_and_independent_instances(self):
        first, second = LineRedactor(), LineRedactor()
        self.assertEqual(first('-----BEGIN PRIVATE KEY-----\n'), '[private key redacted]\n')
        self.assertEqual(first('private material\n'), '')
        self.assertEqual(second('ordinary\n'), 'ordinary\n')
        self.assertEqual(first('-----END PRIVATE KEY-----\n'), '')
        self.assertEqual(first('ordinary\n'), 'ordinary\n')

    def test_explicit_values_tokens_and_url_credentials(self):
        line = LineRedactor(['sensitive-value'])
        for value in ('sensitive-value', 'ghp_' + 'a'*25, 'AIza' + 'a'*35):
            self.assertNotIn(value, line('output: ' + value))
        self.assertEqual(line('https://user:password@host/path'), 'https://[redacted]@host/path')
        self.assertEqual(line('authorization: bearer abc'), 'authorization: bearer [redacted]')
        self.assertEqual(redact('https://host/path?token=value'), 'https://host/path?[redacted]')
