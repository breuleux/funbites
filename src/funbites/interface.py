import ast
import inspect
import textwrap
import warnings

from .runtime import FunBite, FunBiteYield
from .split import SplitState, SplitTagger, Splitter
from .strategy import MainStrategy


def split(fn, strategy):
    frame = inspect.currentframe()
    locs = frame.f_back.f_locals
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    fdef = tree.body[0]
    context = SplitState(
        strategy=strategy,
        name=fn.__name__,
        globals=fn.__globals__,
        locals=locs,
    )
    SplitTagger.run(fdef, context=context)
    fdef = Splitter.run(fdef, context=context)
    if fdef is None:
        warnings.warn(f"No split points found in function {fn.__name__}")
        return fn
    elif isinstance(fdef, list):
        tree.body[:] = fdef
    else:
        tree.body[0] = fdef
    tree = ast.fix_missing_locations(tree)
    tree = ast.increment_lineno(tree, fn.__code__.co_firstlineno - 1)
    fn.__globals__.update({"__FunBite": FunBite, "__FunBiteYield": FunBiteYield})
    exec(compile(tree, fn.__code__.co_filename, "exec"), fn.__globals__)
    return strategy.wrap(fn.__globals__[fn.__name__], fn)


def checkpointable(fn):
    func = split(fn, MainStrategy())
    func.__is_continuator__ = True
    return func


def resumable(fn):
    return split(fn, MainStrategy())
