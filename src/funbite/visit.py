import ast
from dataclasses import dataclass
from typing import Callable

from ovld import Medley, recurse


class NodeVisitor(Medley):
    @classmethod
    def run(cls, node, *, context=None, **kwargs):
        inst = cls(**kwargs)
        return inst(node) if context is None else inst(node, context)

    def reduce(self, node, results, context):  # pragma: no cover
        return None

    def init_context(self):
        return None

    def __call__(self, node: object):
        return recurse(node, self.init_context())

    def __call__(self, node: object, context: object):
        return node

    def __call__(self, node: list, context: object):
        results = []
        for i, x in enumerate(node):
            value = recurse(x, context)
            if isinstance(value, list):
                results.extend([(i, v) for v in value])
            else:
                results.append((i, value))
        return self.reduce(node, results, context)

    def __call__(self, node: ast.AST, context: object):
        return self.reduce(
            node,
            [(field, recurse(value, context)) for field, value in ast.iter_fields(node)],
            context,
        )


@dataclass(kw_only=True)
class NodeReductor(NodeVisitor):
    reducer: Callable = None
    leaf: object = None

    def reduce(self, node, results, context):
        return self.reducer(x for _, x in results)

    def __call__(self, node: object, context: object):
        return self.leaf


class NodeConjunction(NodeReductor):
    def __post_init__(self):
        self.reducer = all
        self.leaf = True


class NodeDisjunction(NodeReductor):
    def __post_init__(self):
        self.reducer = any
        self.leaf = False


class NodeSummation(NodeReductor):
    def __post_init__(self):
        self.reducer = sum
        self.leaf = 0


def _merge_all(sets):
    rval = set()
    for s in sets:
        rval.update(s)
    return rval


class NodeUnion(NodeReductor):
    def __post_init__(self):
        self.reducer = _merge_all
        self.leaf = frozenset()


class NodeTransformer(NodeVisitor):
    def reduce(self, node: list, results, context):
        node[:] = [r for _, r in results]
        return node

    def reduce(self, node: ast.AST, results, context):
        for field, new_value in results:
            if new_value is not None:
                setattr(node, field, new_value)
        return node
