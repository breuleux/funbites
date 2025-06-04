import ast

from funbite.split import split


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

    def identify(self, above, body, name, context):
        return context.gensym()


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
