from dataclasses import dataclass

from funbite.interface import checkpointable
from funbite.strategy import MainStrategy, continuator

strategy = MainStrategy()


@dataclass
class ImmediateReturn:
    value: object


@continuator
def checkpoint(x=None, continuation=None):
    assert continuation is not None
    if isinstance(x, ImmediateReturn):
        return x.value
    else:
        return continuation(x)


def test_split():
    @checkpointable
    def f(x, y):
        checkpoint()
        a = x * x
        checkpoint(a)
        b = y * y
        checkpoint(b)
        return a + b

    result = f(3, 4)
    assert result == 25


def test_split_in_expr():
    @checkpointable
    def f(x):
        w = 1 + checkpoint(x) + 2
        z = w * w
        return z

    result = f(4)
    assert result == 49
    assert f(ImmediateReturn(666)) == 666


def test_splitter_in_expr_2():
    @checkpointable
    def f(x):
        z = x * x
        w = 1 + checkpoint(z) + 2
        return w

    result = f(4)
    assert result == 19


def test_splitter_in_if():
    @checkpointable
    def f(x):
        if x < 0:
            checkpoint(ImmediateReturn(False))
        return True

    assert f(12) is True
    assert f(-12) is False


def test_splitter_in_while():
    @checkpointable
    def f(xs):
        val = 0

        while xs:
            checkpoint()
            val = val + xs.pop()

        return val

    assert f([1, 2, 3, 4]) == 10


def test_splitter_in_for():
    @checkpointable
    def f(xs):
        val = 0

        for x in xs:
            checkpoint(x)
            val = val + x

        return val

    assert f([1, 2, 3, 4]) == 10
    assert f([1, 2, ImmediateReturn("boom!"), 4]) == "boom!"


@continuator
def mult_result(x, *, continuation):
    val = continuation.execute(x)
    return val * x


def test_mult_result():
    @checkpointable
    def f(x):
        mult_result(2)
        return x * x

    assert f(5) == 50


def test_mult_result_2():
    @checkpointable
    def f(xs):
        for x in xs:
            mult_result(x)
        return 2

    assert f([2, 3, 4]) == 48
    assert f([2, 3, 4, 5]) == 240
