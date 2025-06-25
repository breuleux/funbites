import ast
import dataclasses
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import count
from typing import Callable

from ovld import ovld

from .simplify import Simplify, TagIgnores
from .vars import VariableAnalysis, Variables
from .visit import NodeTransformer

ABSENT = object()


@dataclass(kw_only=True)
class SplitState:
    name: str = "_func"
    count: object = field(default_factory=count)
    continuation: ast.AST = None
    definitions: dict = field(default_factory=dict)
    variables: Variables = field(default_factory=Variables)
    strategy: Callable = None
    locals: dict = None
    globals: dict = None

    def gensym(self):
        return f"__{next(self.count)}"

    replace = dataclasses.replace


def _encapsulate(args, body, context, cont_name):
    assert cont_name not in context.definitions
    context.definitions[cont_name] = ast.FunctionDef(
        name=cont_name,
        args=args
        if isinstance(args, ast.arguments)
        else ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=var, annotation=None) for var in args],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=body,
        decorator_list=[],
    )
    return cont_name


@dataclass
class BodySplitter:
    queue: deque = field(default_factory=deque)
    acc: list = field(default_factory=list)
    prebody: list = field(default_factory=list)
    continuations: dict[str, ast.AST] = field(default_factory=dict)

    def create_continuation(self, current, context):
        match current:
            case ast.Continue():
                return self.continuations["continue"]
            case ast.Break():
                return self.continuations["break"]
        q = [*self.prebody, *self.queue]
        if isinstance(current, ast.Assign):
            name = current.targets[0].id
        else:
            name = context.gensym()
        upper_vars = VariableAnalysis.run(
            q, context=Variables(arg_defs=context.variables.arg_defs)
        )
        body = list(reversed(self.acc))
        acc_vars = VariableAnalysis.run(
            body, context=upper_vars.clone().replace(uses_local=set())
        )
        new_defs = acc_vars.local_defs - upper_vars.local_defs
        to_pass = list(acc_vars.uses_local - new_defs)
        to_pass.sort()
        args = [ast.Name(id=var, ctx=ast.Load()) for var in to_pass]
        to_pass.append(name)

        if try_model := self.continuations.get("try", None):
            try_model = deepcopy(try_model)
            try_model.body = body
            body = [try_model]

        cont_name = context.strategy.identify(name, q, body, context)
        cont_name = _encapsulate(to_pass, body, context, cont_name=cont_name)

        cont_struct = ast.Call(
            func=ast.Name(id="__FunBite", ctx=ast.Load()),
            args=[ast.Name(id=cont_name, ctx=ast.Load()), *args],
            keywords=[],
        )
        if current is not None:
            return context.strategy.transform(current.value, cont_struct, context)
        else:
            return context.strategy.default(cont_struct, context)

    @ovld
    def process(self, node: ast.If, context: SplitState):
        node.body = self.subsplit(node.body, context, prebody=self.queue)
        node.orelse = self.subsplit(node.orelse, context, prebody=self.queue)
        self.acc = [node]

    @ovld
    def process(self, node: ast.While, context: SplitState):
        stmt = ast.If(test=node.test, body=node.body, orelse=[context.continuation])
        self.acc = [stmt]
        wcont = self.create_continuation(None, context)
        wret = ast.Return(value=wcont)
        wret.no_transform = True
        stmt.body = self.subsplit(
            node.body,
            context.replace(continuation=wret),
            prebody=self.queue,
            continuations={
                **self.continuations,
                "continue": wcont,
                "break": context.continuation.value,
            },
        )
        self.acc = [wret]

    @ovld
    def process(self, node: ast.For, context: SplitState):
        make_iter = ast.Assign(
            targets=[ast.Name(id=node.target.id + "_iter", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="iter", ctx=ast.Load()),
                args=[node.iter],
                keywords=[],
            ),
        )
        nextvar = context.gensym()
        getnext = ast.NamedExpr(
            target=ast.Name(id=nextvar, ctx=ast.Store()),
            value=ast.Call(
                func=ast.Name(id="next", ctx=ast.Load()),
                args=[
                    ast.Name(id=node.target.id + "_iter", ctx=ast.Load()),
                    ast.Name(id="StopIteration", ctx=ast.Load()),
                ],
                keywords=[],
            ),
        )
        extractor = ast.Assign(
            targets=[node.target],
            value=ast.Name(id=nextvar, ctx=ast.Load()),
        )
        loop = ast.While(
            test=ast.Compare(
                left=getnext,
                ops=[ast.IsNot()],
                comparators=[ast.Name(id="StopIteration", ctx=ast.Load())],
            ),
            body=[
                extractor,
                *node.body,
            ],
        )
        self.queue.append(make_iter)
        self.process(loop, context)

    def split(self, body, context):
        if context.continuation:
            body = [*body, context.continuation]

        self.queue = deque(body)
        while self.queue:
            x = self.queue.pop()
            if not getattr(x, "ignore", True):
                match x:
                    case ast.Expr(value=focus):
                        pass
                    case ast.Assign(value=focus):
                        pass
                    case ast.Return(value=focus):
                        pass
                    case _:
                        focus = x

                if context.strategy.is_split(focus, context):
                    cont = self.create_continuation(x, context)
                    self.acc = [ast.Return(value=cont)]

                else:
                    cont = self.create_continuation(None, context)
                    ret = ast.Return(value=cont)
                    ctx = context.replace(continuation=ret)
                    self.process(x, ctx)

            else:
                match x:
                    case ast.Return(value=v):
                        if not getattr(x, "no_transform", False):
                            x = ast.Return(
                                value=ast.Call(
                                    func=self.continuations["return"],
                                    args=[v],
                                    keywords=[],
                                )
                            )
                self.acc.append(x)

        return list(reversed(self.acc))

    def subsplit(self, body, context, prebody=[], continuations={}):
        s = BodySplitter(
            prebody=prebody,
            continuations={**self.continuations, **continuations},
        )
        return s.split(body, context)

    def subcont(self, body, context, prebody=[], continuations={}):
        s = BodySplitter(
            prebody=prebody,
            continuations={**self.continuations, **continuations},
        )
        s.split(body, context)
        return s.create_continuation(None, context)


class Splitter(NodeTransformer):
    def __call__(self, node: ast.FunctionDef, context: SplitState):
        TagIgnores.run(node, context=context)
        Simplify.run(node, context=context)
        TagIgnores.run(node, context=context)

        node.args.kwonlyargs.append(ast.arg(arg="continuation", annotation=None))
        node.args.kw_defaults.append(ast.Constant(value=None))
        # We append an explicit return None so that the return transform can apply
        node.body.append(ast.Return(ast.Constant(value=None)))
        context = SplitState(
            name=context.name,
            variables=VariableAnalysis().inner(node, Variables()),
            strategy=context.strategy,
            globals=context.globals,
            locals=context.locals,
        )
        conts = {"return": ast.Name(id="continuation", ctx=ast.Load())}
        new_body = BodySplitter(prebody=[], continuations=conts).split(node.body, context)
        defns = context.definitions.values()
        if defns:
            _encapsulate(node.args, new_body, context, cont_name=node.name)
            return [*reversed(defns)]

        else:
            return None
