import ast
import inspect
import textwrap

from funbite.vars import VariableAnalysis, Variables


def test_varanal_local_variables():
    code = textwrap.dedent("""
    x = 1
    y = x + 2
    z = y
    """)
    tree = ast.parse(code)
    results = VariableAnalysis.run(tree, context=Variables())

    assert results == Variables(
        local_defs={"x", "y", "z"},
        uses_local={"x", "y", "z"},
    )


def test_varanal_free_variables():
    code = "a = b + 1"
    tree = ast.parse(code)
    results = VariableAnalysis.run(tree, context=Variables())

    assert results == Variables(
        local_defs={"a"},
        uses_local={"a"},
        uses_free={"b"},
    )


def test_varanal_def():
    def f(x, y):
        z = x * y
        return z + a

    tree = ast.parse(textwrap.dedent(inspect.getsource(f)))
    results = VariableAnalysis.run(tree, context=Variables())

    assert results == Variables(
        local_defs={"f"},
        uses_free={"a"},
    )


def test_varanal_inner_def():
    def f(x, y):
        def g(z):
            return z + x + a

        return g(x * y * q)

    tree = ast.parse(textwrap.dedent(inspect.getsource(f)))
    inner_results = VariableAnalysis().inner(tree.body[0], context=Variables())
    assert inner_results == Variables(
        arg_defs={"x", "y"},
        local_defs={"g"},
        uses_local={"g", "x", "y"},
        uses_free={"q", "a"},
    )

    outer_results = VariableAnalysis.run(tree, context=Variables())
    assert outer_results == Variables(
        local_defs={"f"},
        uses_free={"q", "a"},
    )


def test_varanal_for():
    def f():
        z = 0
        for i, q in enumerate(range(4, 9)):
            z += q * i
        return z

    tree = ast.parse(textwrap.dedent(inspect.getsource(f)))
    results = VariableAnalysis.run(tree, context=Variables())

    assert results == Variables(
        local_defs={"f"},
        uses_free={"enumerate", "range"},
    )


def test_varanal_augass():
    code = "a += b"
    tree = ast.parse(code)
    results = VariableAnalysis.run(tree, context=Variables())

    assert results == Variables(
        local_defs={"a"},
        uses_local={"a"},
        uses_free={"b"},
    )


def test_varanal_nonlocal():
    code = "nonlocal x; x = 3;"
    tree = ast.parse(code)
    results = VariableAnalysis.run(tree, context=Variables())

    assert results == Variables(
        nonlocals={"x"},
        uses_free={"x"},
    )


def test_varanal_global():
    code = "global x; x = 3;"
    tree = ast.parse(code)
    results = VariableAnalysis.run(tree, context=Variables())

    assert results == Variables(
        globals={"x"},
        uses_free={"x"},
    )
