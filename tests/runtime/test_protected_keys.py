"""Key adapters keep host namespaces explicit and native imports lazy."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import importlib.abc
import subprocess
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from commonUtils.runtime.protected_keys import AndroidKeys


class ProtectedKeyTests(unittest.TestCase):
    def test_android_aliases_are_namespaced_by_the_caller(self):
        store = SimpleNamespace(load=lambda *args: None)
        java = SimpleNamespace(jclass=lambda name: SimpleNamespace(getInstance=lambda kind: store))
        with patch.dict('sys.modules', java=java):
            first = AndroidKeys(alias_prefix='consumer.one.', aad_prefix='consumer one v1:')
            second = AndroidKeys(alias_prefix='consumer.two.', aad_prefix='consumer two v1:')
        self.assertEqual(first.alias('identity'), 'consumer.one.identity')
        self.assertEqual(second.alias('identity'), 'consumer.two.identity')
        self.assertEqual(first.aad_prefix, 'consumer one v1:')

    def test_module_import_does_not_load_platform_bridges_or_consumer(self):
        script = '''
import importlib.abc, sys
class Reject(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'java', 'rubicon', 'ctypes', 'toga', 'logisticsmobile'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Reject())
import commonUtils.runtime.protected_keys
'''
        subprocess.run([sys.executable, '-c', script], check=True)
