import ast
import inspect
import textwrap

from funbites.checkpoint import checkpoint
from funbites.debug import as_source, show
from funbites.simplify import GuaranteeReturn, Simplify, TagIgnores
from funbites.split import SplitState
from funbites.strategy import MainStrategy


def one():
    return 1


def two():
    return 2


def three():
    return 3


def f(*args):
    return


def simptest(fn):
    def test(file_regression):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        strategy = MainStrategy()
        context = SplitState(
            strategy=strategy,
            name=fn.__name__,
            globals=fn.__globals__,
            locals={},
        )
        TagIgnores.run(tree, context=context)
        Simplify.run(tree, context=context)
        GuaranteeReturn.run(tree, context=context)
        TagIgnores.run(tree, context=context)
        new_source = as_source(tree)
        show(tree)
        file_regression.check(new_source)

    return test


@simptest
def test_expr():
    return f(one(), checkpoint(), three())


@simptest
def test_expr_operators():
    return one() + checkpoint() + three()


@simptest
def test_expr_compare():
    return one() < checkpoint() < three()


@simptest
def test_for_transform():
    rval = 0
    for i in range(10):
        checkpoint()
        rval += i
    return rval


@simptest
def test_with_transform():
    with open("flafla", "r") as filou:
        checkpoint()
        filou.write("wow!\n")
    return True


@simptest
def test_add_return():
    print("hello")


@simptest
def test_add_return_to_if(x):
    if x > 0:
        print("hello")
    else:
        return True


@simptest
def test_add_return_to_if_2(x):
    if x > 0:
        print("hello")
    else:
        return True
    print("wow")


@simptest
def test_no_add_return(x):
    if x > 0:
        raise Exception("oh no")
    else:
        return True
