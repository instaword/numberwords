"""Tests for compile_spec.py -- the compiler that turns
languages/mizo.yaml into the target package's _mizo.py.

These live in reference/'s suite rather than the package's own, so the
package's tests never need PyYAML (#20). The compiler is developer
tooling; it is not shipped.
"""

import ast
import importlib.util

import pytest

import compile_spec
from engine import _eval_condition, _positional_variables, load


@pytest.fixture(scope="module")
def spec():
    return load(compile_spec.SPEC_PATH)


@pytest.fixture(scope="module")
def artifact():
    """Imports the checked-in _mizo.py from its path. It belongs to the
    package, not to reference/, so it is not importable by name from here.
    """
    module_spec = importlib.util.spec_from_file_location(
        "_mizo", compile_spec.ARTIFACT_PATH
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_checked_in_artifact_is_up_to_date(spec, tmp_path):
    """The same drift problem the conformance vectors have: _mizo.py is a
    snapshot, so a spec edit that was never recompiled would go unnoticed.

    This compiles to a temp file rather than the real path. A failing test
    must not rewrite the artifact it is meant to be checking -- otherwise
    running the suite would quietly fix the very thing that should fail.
    """
    generated = tmp_path / "_mizo.py"
    compile_spec.write_module(spec, generated)
    assert generated.read_text(encoding="utf-8") == (
        compile_spec.ARTIFACT_PATH.read_text(encoding="utf-8")
    ), "_mizo.py is stale -- run `python compile_spec.py` and commit it"


def test_compiling_twice_gives_the_same_text(spec):
    """The drift test above is only meaningful if the compiler is
    deterministic. Anything that varied run to run (dictionary ordering,
    a timestamp) would make it fail at random.
    """
    assert compile_spec.render_module(spec) == compile_spec.render_module(spec)


def test_artifact_imports_nothing(artifact):
    """The point of compiling is that the package needs neither PyYAML nor
    ast at runtime (#20). An import appearing in the generated module would
    mean work leaked back into it.
    """
    tree = ast.parse(compile_spec.ARTIFACT_PATH.read_text(encoding="utf-8"))
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert imports == []


def test_compiled_conditions_match_the_engine(spec, artifact):
    """The compiled lambda and engine._eval_condition are two
    implementations of the same condition, which is the risk that made
    ast.unparse the right way to emit them. This checks they agree at every
    input in the supported range.
    """
    low, high = artifact.SUPPORTS
    for yaml_rule, compiled_rule in zip(spec.rules, artifact.RULES):
        assert yaml_rule["name"] == compiled_rule["name"]
        condition = yaml_rule.get("condition")
        if condition is None:
            assert compiled_rule["condition"] is None
            continue
        for n in range(low, high + 1):
            variables = _positional_variables(n)
            assert bool(compiled_rule["condition"](variables)) == bool(
                _eval_condition(condition, variables)
            ), f"rule {yaml_rule['name']} disagrees at n={n}"


def test_chained_comparison_keeps_python_semantics():
    """A chained comparison is the case an emitter that pasted strings
    together would get wrong: `0 < d < 5` means `0 < d and d < 5`, not
    `(0 < d) < 5`, which would evaluate a bool against 5 and be true for
    d = 0. No rule in mizo.yaml uses one today, so this guards the
    mechanism rather than the current data.
    """
    condition = eval(compile_spec._compile_condition("0 < ones_digit < 5"))
    results = [
        condition({"ones_digit": n, "tens_digit": 0}) for n in (0, 1, 4, 5)
    ]
    assert results == [False, True, True, False]


@pytest.mark.parametrize(
    "expression",
    [
        "ones_digit + 1 == 2",     # arithmetic
        "len(ones_digit) == 1",    # a call
        "ones_digit.real == 1",    # attribute access
        "not_a_variable == 1",     # a name the spec never defines
        "ones_digit == 'zero'",    # a constant that is not an integer
    ],
)
def test_validator_rejects_unsupported_conditions(expression):
    """The compiler only accepts what engine._eval_node accepts. Anything
    else raises here, at build time, instead of being written into the
    package as code.
    """
    with pytest.raises(ValueError):
        compile_spec._compile_condition(expression)


@pytest.mark.parametrize(
    "expression",
    [
        "ones_digit == 0",
        "ones_digit > 0",
        "ones_digit == 0 and tens_digit > 1",
        "ones_digit == 0 or ones_digit == 5",
    ],
)
def test_validator_accepts_the_shapes_the_engine_supports(expression):
    compile_spec._compile_condition(expression)
