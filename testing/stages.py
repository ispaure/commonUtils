"""Execution scope and source-only classification for unittest/native checks."""
import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import io
import tokenize


class TestStage(str, Enum):
    SMOKE = 'smoke'
    REGRESSION = 'regression'
    EXTENDED = 'extended'


STAGE_ORDER = tuple(TestStage)
PROFILES = {
    'smoke': (TestStage.SMOKE,),
    'daily': (TestStage.SMOKE, TestStage.REGRESSION),
    'full': STAGE_ORDER,
}


def stage(value):
    """Override a module's default on a unittest class or test method."""
    if not isinstance(value, TestStage):
        raise TypeError('Use a TestStage enum member')
    def decorate(target):
        target.__test_stage__ = value
        return target
    return decorate


@dataclass(frozen=True)
class Classification:
    path: Path
    default: TestStage
    overrides: dict
    cases: tuple

    def resolve(self, case):
        """Resolve runtime unittest cases, including inherited test methods."""
        method = getattr(type(case), getattr(case, '_testMethodName', ''), None)
        return (getattr(method, '__test_stage__', None)
                or getattr(type(case), '__test_stage__', None) or self.default)

    def inventory(self):
        return [dict(case=name, stage=value.value, origin=origin)
                for name, value, origin in self.cases]


def classify(path):
    """Reject missing/ambiguous labels before imports, fixture setup or execution.

    Python uses TEST_STAGE = TestStage.MEMBER. Standalone runtime drivers and
    other languages may use the same declaration in a source comment. Class and
    method overrides use @stage(TestStage.MEMBER), never free-form strings.
    """
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'{path}: linked test sources are not accepted')
    source = path.read_text(encoding='utf-8')
    def member(node):
        if (not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name)
                or node.value.id != 'TestStage' or node.attr not in TestStage.__members__):
            raise ValueError(f'{path}:{getattr(node, "lineno", 1)}: expected TestStage.SMOKE, REGRESSION or EXTENDED')
        return TestStage[node.attr]

    if path.suffix == '.py':
        tree = ast.parse(source, filename=str(path))
        comments = '\n'.join(t.string for t in tokenize.generate_tokens(io.StringIO(source).readline)
                             if t.type == tokenize.COMMENT and t.start[1] == 0)
    else:
        comments = source
    declarations = re.findall(r'^(?:#|//)\s*TEST_STAGE\s*=\s*TestStage\.(\w+)\s*$', comments, re.M)
    defaults, overrides, cases = [], {}, []
    for name in declarations:
        if name not in TestStage.__members__:
            raise ValueError(f'{path}: invalid TestStage member {name}')
        defaults.append(TestStage[name])
    if path.suffix == '.py':
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id == 'TEST_STAGE' for t in targets):
                defaults.append(member(node.value))
        def override(node):
            if any(isinstance(d, ast.Name) and d.id == 'stage' for d in node.decorator_list):
                raise ValueError(f'{path}:{node.lineno}: use @stage(TestStage.MEMBER)')
            labels = [d for d in node.decorator_list
                      if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == 'stage']
            if len(labels) > 1:
                raise ValueError(f'{path}:{node.lineno}: duplicate stage override')
            if labels:
                if len(labels[0].args) != 1 or labels[0].keywords:
                    raise ValueError(f'{path}:{node.lineno}: stage requires one TestStage member')
                return member(labels[0].args[0])
            return None
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        def methods(node, seen=()):
            if node.name in seen:
                raise ValueError(f'{path}:{node.lineno}: cyclic local test inheritance')
            found = {}
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id in classes:
                    for name, method in methods(classes[base.id], (*seen, node.name)).items():
                        found.setdefault(name, method)
            found.update((method.name, method) for method in node.body
                         if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)))
            return found
        def class_stage(node, seen=()):
            if node.name in seen:
                raise ValueError(f'{path}:{node.lineno}: cyclic local test inheritance')
            value = override(node)
            if value:
                return value
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id in classes:
                    value = class_stage(classes[base.id], (*seen, node.name))
                    if value:
                        return value
            return None
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                value = class_stage(node)
                if value:
                    overrides[node.name] = value
                for method in methods(node).values():
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith('test_'):
                        specific = override(method)
                        name = node.name + '.' + method.name
                        if specific:
                            overrides[name] = specific
                        cases.append((name, specific or value, 'method' if specific else 'class' if value else 'module'))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
                value = override(node)
                cases.append((node.name, value, 'method' if value else 'module'))
    if len(defaults) != 1:
        raise ValueError(f'{path}: declare exactly one TEST_STAGE = TestStage member (found {len(defaults)})')
    return Classification(path, defaults[0], overrides,
                          tuple((name, value or defaults[0], origin) for name, value, origin in cases))


def validate(paths):
    """Return all classifications or report every source issue together."""
    rows, issues = [], []
    for path in sorted(set(map(Path, paths))):
        try:
            rows.append(classify(path))
        except (OSError, SyntaxError, ValueError) as error:
            issues.append(str(error))
    if issues:
        raise ValueError('Invalid test structure:\n' + '\n'.join(issues))
    return rows
