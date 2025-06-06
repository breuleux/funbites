import ast
import inspect

from funbites.visit import (
    NodeConjunction,
    NodeDisjunction,
    NodeSummation,
    NodeTransformer,
    NodeUnion,
)


class HasSymbol(NodeDisjunction):
    name: str

    def __call__(self, node: ast.Name, context: object):
        return node.id == self.name


def test_run():
    code = "x = 1; z = 3"
    node = ast.parse(code)

    assert HasSymbol.run(node, name="x")
    assert not HasSymbol.run(node, name="y")


def test_has_symbol():
    code = "x = 1; z = 3"
    node = ast.parse(code)

    assert HasSymbol(name="x")(node)
    assert HasSymbol(name="z")(node)
    assert not HasSymbol(name="y")(node)


class HasNotSymbol(NodeConjunction):
    name: str

    def __call__(self, node: ast.Name, context: object):
        return node.id != self.name


def test_has_not_symbol():
    code = "x = 1; z = 3"
    node = ast.parse(code)

    assert HasNotSymbol(name="y")(node)
    assert not HasNotSymbol(name="x")(node)
    assert not HasNotSymbol(name="z")(node)


class SymbolCount(NodeSummation):
    name: str

    def __call__(self, node: ast.Name, context: object):
        return int(node.id == self.name)


def test_symbol_count():
    code = "x = 1; x += 2; y = 3"
    node = ast.parse(code)

    assert SymbolCount(name="x")(node) == 2
    assert SymbolCount(name="y")(node) == 1
    assert SymbolCount(name="z")(node) == 0


class CollectSymbols(NodeUnion):
    def __call__(self, node: ast.Name, context: object):
        return frozenset([node.id])


def test_node_union():
    code = "x = 1; y = 2; x = 3; z = 4"
    node = ast.parse(code)

    result = CollectSymbols()(node)
    assert result == {"x", "y", "z"}


def f(x):
    return x + one * two


class LiteralNumberNames(NodeTransformer):
    def __call__(self, node: ast.Name, context: object):
        number_map = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        if node.id in number_map:
            return ast.Constant(value=number_map[node.id])
        return node


def test_transform():
    source = inspect.getsource(f)
    tree = ast.parse(source)
    transformed = LiteralNumberNames()(tree)
    ast.fix_missing_locations(transformed)
    compiled = compile(transformed, filename="<ast>", mode="exec")
    exec(compiled, namespace := {})
    result = namespace["f"](10)
    assert result == 12  # 10 + 1 * 2


def f2(x):
    x += 1
    x *= 2
    return x


class DoubleAssign(NodeTransformer):
    def __call__(self, node: ast.AugAssign, context: object):
        return [node, node]


def test_expand():
    assert f2(10) == 22
    source = inspect.getsource(f2)
    tree = ast.parse(source)
    transformed = DoubleAssign()(tree)
    ast.fix_missing_locations(transformed)
    compiled = compile(transformed, filename="<ast>", mode="exec")
    exec(compiled, namespace := {})
    result = namespace["f2"](10)
    assert result == 48
