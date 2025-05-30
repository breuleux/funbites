import ast
import inspect
import textwrap

from funbite.tools import VariableAnalysis, Variables, split


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


class SplittingStrategy:
    def __init__(self, globals):
        self.globals = globals

    def is_split(self, node, context):
        match node:
            case ast.Call(func=ast.Name(x)):
                if self.globals.get(x, None) is checkpoint:
                    return True
        return False

    def transform(self, node: ast.Call, cont, context):
        return ast.Call(
            func=node.func,
            args=node.args,
            keywords=[*node.keywords, ast.keyword("continuation", cont)],
        )

    def default(self, cont, context):
        return ast.Call(
            func=cont,
            args=[ast.Constant(None)],
        )

    def wrap(self, entry):
        return entry


def checkpoint(x=None, continuation=None):
    assert continuation is not None
    return continuation(x)


def test_splitter():
    @split(SplittingStrategy)
    def f(x, y):
        print("hello", y * y)

        checkpoint(x)

        print("middle")
        z = x * x

        checkpoint(y)

        print("bye", x * z)
        return z

    result = f(5, 3)
    assert result == 25


def test_splitter_in_expr():
    @split(SplittingStrategy)
    def f(x):
        w = 1 + checkpoint(x) + 2
        z = w * w
        return z

    result = f(4)
    assert result == 49


def test_splitter_in_expr_2():
    @split(SplittingStrategy)
    def f(x):
        z = x * x
        w = 1 + checkpoint(z) + 2
        return w

    result = f(4)
    assert result == 19


def test_splitter_in_if():
    @split(SplittingStrategy)
    def f(x, y):
        print("hello", y * y)

        if x:
            x = 0
            checkpoint()
            print("inif")

        print("middle")
        z = x * x

        checkpoint()

        print("bye", x * z)
        return x * z

    result = f(5, 3)
    assert result == 0


def test_splitter_in_while():
    @split(SplittingStrategy)
    def f(xs):
        val = 0

        while xs:
            checkpoint()
            val = val + xs.pop()

        return val

    result = f([1, 2, 3, 4])
    assert result == 10


def test_splitter_in_for():
    @split(SplittingStrategy)
    def f(xs):
        val = 0

        for x in xs:
            checkpoint()
            val = val + x

        return val

    result = f([1, 2, 3, 4])
    assert result == 10
