"""Source classification is complete, strict and independent of test imports."""
from commonUtils.testing.stages import TestStage, stage, classify, validate

TEST_STAGE = TestStage.SMOKE

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class ExecutionStageTests(unittest.TestCase):
    def source(self, root, text, name='test_sample.py'):
        path = Path(root) / name
        path.write_text(text)
        return path

    def test_class_and_method_overrides_have_explicit_inheritance(self):
        with TemporaryDirectory() as root:
            path = self.source(root, '''TEST_STAGE = TestStage.REGRESSION
@stage(TestStage.EXTENDED)
class Example:
    def test_default(self): pass
    @stage(TestStage.SMOKE)
    def test_smoke(self): pass
''')
            result = classify(path)
            self.assertEqual([(n, s, o) for n, s, o in result.cases], [
                ('Example.test_default', TestStage.EXTENDED, 'class'),
                ('Example.test_smoke', TestStage.SMOKE, 'method')])
        @stage(TestStage.EXTENDED)
        class Base(unittest.TestCase):
            @stage(TestStage.SMOKE)
            def test_sample(self): pass
        self.assertIs(result.resolve(Base('test_sample')), TestStage.SMOKE)

    def test_every_invalid_source_is_reported_before_execution(self):
        with TemporaryDirectory() as root:
            first = self.source(root, 'raise RuntimeError("must not import")\n', 'test_a.py')
            second = self.source(root, 'TEST_STAGE = "smoke"\n', 'test_b.py')
            with self.assertRaises(ValueError) as caught:
                validate([first, second])
            self.assertIn('test_a.py', str(caught.exception))
            self.assertIn('test_b.py', str(caught.exception))

    def test_inherited_methods_use_subclass_stage_and_keep_method_overrides(self):
        with TemporaryDirectory() as root:
            result = classify(self.source(root, '''TEST_STAGE = TestStage.REGRESSION
class Base:
    def test_default(self): pass
    @stage(TestStage.SMOKE)
    def test_smoke(self): pass
@stage(TestStage.EXTENDED)
class Derived(Base): pass
'''))
            cases = {name: value for name, value, _ in result.cases}
            self.assertIs(cases['Derived.test_default'], TestStage.EXTENDED)
            self.assertIs(cases['Derived.test_smoke'], TestStage.SMOKE)

    def test_duplicates_unknown_members_and_invalid_overrides_are_rejected(self):
        sources = ['TEST_STAGE = TestStage.UNKNOWN',
                   'TEST_STAGE = TestStage.SMOKE\nTEST_STAGE = TestStage.REGRESSION',
                   'TEST_STAGE = TestStage.SMOKE\n@stage("smoke")\nclass Example: pass']
        with TemporaryDirectory() as root:
            for source in sources:
                with self.subTest(source=source), self.assertRaises(ValueError):
                    classify(self.source(root, source))
        with self.assertRaises(TypeError):
            stage('smoke')

    def test_standalone_and_foreign_comments_resolve_to_the_same_enum(self):
        with TemporaryDirectory() as root:
            for name, marker in [('test.py', '#'), ('sample_test.go', '//'), ('SampleTests.swift', '//')]:
                result = classify(self.source(root, marker + ' TEST_STAGE = TestStage.SMOKE\n', name))
                self.assertIs(result.default, TestStage.SMOKE)
