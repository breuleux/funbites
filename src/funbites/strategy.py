import ast
import hashlib
import inspect

from ovld import ovld, recurse

from .runtime import Loop


def continuator(fn):
    fn.__is_continuator__ = True
    return fn


@ovld
def _hashexpr(xs: list | tuple):
    return tuple(recurse(x) for x in xs)


@ovld
def _hashexpr(node: ast.AST):
    return tuple((f, recurse(x)) for f, x in ast.iter_fields(node))


@ovld
def _hashexpr(x: str | int):
    return x


@ovld
def _hashexpr(x: object):
    return hash(x)


class Strategy:
    def is_split(self, node, context):
        """Determine if the excution should be split at this point.

        Args:
            node: The AST node to check
            context: The current split context

        Returns:
            bool: True if this is a splitting boundary, False otherwise
        """
        raise NotImplementedError()

    def transform(self, node: ast.Call, cont, context):
        """Transform a boundary node into a continuation call

        Args:
            node: An AST node for which is_split is True
            cont: The continuation
            context: The current split context

        Returns:
            ast.AST: The transformed node
        """
        raise NotImplementedError()

    def default(self, cont, context):
        """Called for additional boundaries created by the splitting algorithm

        Args:
            cont: The continuation
            context: The current split context

        Returns:
            ast.AST: The default continuation node
        """
        raise NotImplementedError()

    def identify(self, name, above, body, context):
        """Generate a unique identifier for a continuation.

        Args:
            name: A unique name for the continuation
            above: The AST nodes above the split point
            body: The AST nodes in the continuation body
            context: The current split context

        Returns:
            str: A unique identifier for the continuation
        """
        raise NotImplementedError()

    def wrap(self, entry):
        """Wrap the entry point function.

        Args:
            entry: The entry point function to wrap

        Returns:
            callable: The wrapped function
        """
        raise NotImplementedError()


def returns(x):
    return x


class MainStrategy(Strategy):
    def is_split(self, node, context):
        match node:
            case ast.Call(func=ast.Name(x)):
                ref = (
                    context.locals[x] if x in context.locals else context.globals.get(x, None)
                )
                if getattr(ref, "__is_continuator__", False):
                    return True
            case ast.Yield():
                return True
        return False

    def transform(self, node, cont, context):
        match node:
            case ast.Call(func, args, keywords):
                return ast.Call(
                    func=ast.Name(id="__FunBite", ctx=ast.Load()),
                    args=[func, *args],
                    keywords=[*keywords, ast.keyword("continuation", cont)],
                )
            case ast.Yield(value):
                return ast.Call(
                    func=ast.Name(id="__FunBiteYield", ctx=ast.Load()),
                    args=[value],
                    keywords=[ast.keyword("continuation", cont)],
                )

    def default(self, cont, context):
        return ast.Call(
            func=cont.func,
            args=[*cont.args, ast.Constant(None)],
            keywords=cont.keywords,
        )

    def identify(self, above, body, name, context):
        hsh = hashlib.blake2b(
            str(_hashexpr([name, *above])).encode(), digest_size=8
        ).hexdigest()
        return f"{context.name}__{hsh}"

    def wrap(self, entry, original):
        is_generator = inspect.isgeneratorfunction(original)
        is_async = inspect.iscoroutinefunction(original)
        return Fun(entry, is_generator=is_generator, is_async=is_async)


class Fun:
    def __init__(self, entry, is_generator=False, is_async=False):
        self.entry = entry
        self.is_generator = is_generator
        self.is_async = is_async

    def __call__(self, *args, continuation=None, **kwargs):
        if continuation is not None:
            assert not self.is_generator
            assert not self.is_async
            return self.entry(*args, **kwargs, continuation=continuation)

        loop = Loop(
            self.entry,
            args,
            {"continuation": returns, **kwargs},
            is_generator=self.is_generator,
        )

        if self.is_generator:
            return loop
        elif self.is_async:
            raise NotImplementedError()
        else:
            return loop.run()
