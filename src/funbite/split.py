import ast
import dataclasses
from collections import deque
from dataclasses import dataclass, field
from itertools import count
from typing import Callable

from ovld import call_next, ovld, recurse

from .vars import VariableAnalysis, Variables
from .visit import NodeTransformer, NodeVisitor


class SplitTagger(NodeVisitor):
    def reduce(self, node, results, context):
        for _, x in results:
            match x:
                case "match":
                    return "inner"
                case "inner":
                    return "inner"
        return "normal"

    @ovld(priority=1)
    def __call__(self, node: ast.AST, context: object):
        if context.strategy.is_split(node, context):
            result = "match"
        else:
            result = call_next(node, context)
        node.split_tag = result
        return result

    def __call__(self, node: ast.Expr, context: object):
        return recurse(node.value, context)

    def __call__(self, node: object, context: object):
        return "normal"


class Collapse(NodeVisitor):
    def collapse(self, node, hoist, context):
        stmts = []
        for fld in hoist:
            value = getattr(node, fld)
            new_stmts, new_value = self(value, context)
            assert value is None or new_value is not None
            stmts.extend(new_stmts)
            setattr(node, fld, new_value)

        if isinstance(node, ast.stmt):
            rval = None
            add = node
            SplitTagger.run(add, context=context)
        else:
            newsym = context.gensym()
            rval = ast.Name(id=newsym, ctx=ast.Load())
            add = ast.Assign(
                targets=[ast.Name(id=newsym, ctx=ast.Store())],
                value=node,
            )
            if getattr(node, "split_tag", None) == "match":
                add.split_tag = "match"

        add.collapsed = True
        stmts.append(add)
        return stmts, rval

    def __call__(self, node: ast.AST, context):
        usually_keep = {"body", "orelse", "cases"}
        all_fields = [f for f, _ in ast.iter_fields(node)]
        hoist = [f for f in all_fields if f not in usually_keep]
        return self.collapse(node, hoist, context)

    def __call__(self, node: ast.While, context):
        return self.collapse(node, hoist=[], context=context)

    def __call__(self, node: ast.Compare, context):
        return self.collapse(node, hoist={"comparators"}, context=context)

    def __call__(self, node: list, context):
        stmts = []
        rval = []
        for x in node:
            new_stmts, x = self(x, context)
            rval.append(x)
            stmts.extend(new_stmts)
        return stmts, rval

    def __call__(self, node: ast.Name, context):
        return [], node

    def __call__(self, node: ast.Constant, context):
        return [], node

    def __call__(self, node: ast.operator, context):
        return [], node

    def __call__(self, node: object, context):
        return [], node


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

    def create_continuation(self, current, context):
        q = [*self.prebody, *self.queue]
        if isinstance(current, ast.Assign):
            name = current.targets[0].id
        else:
            name = context.gensym()
        upper_vars = VariableAnalysis.run(
            q, context=Variables(arg_defs=context.variables.arg_defs)
        )
        self.acc.reverse()
        acc_vars = VariableAnalysis.run(
            self.acc, context=upper_vars.clone().replace(uses_local=set())
        )
        new_defs = acc_vars.local_defs - upper_vars.local_defs
        to_pass = list(acc_vars.uses_local - new_defs)
        to_pass.sort()
        args = [ast.Name(id=var, ctx=ast.Load()) for var in to_pass]
        to_pass.append(name)

        cont_name = context.strategy.identify(name, q, self.acc, context)
        cont_name = _encapsulate(to_pass, self.acc, context, cont_name=cont_name)

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
        node.body = split_body(node.body, context, prebody=self.queue)
        node.orelse = split_body(node.orelse, context)
        self.acc = [node]

    @ovld
    def process(self, node: ast.While, context: SplitState):
        stmt = ast.If(test=node.test, body=node.body, orelse=[context.continuation])
        self.acc = [stmt]
        wcont = self.create_continuation(None, context)
        wret = ast.Return(value=wcont)
        wret.no_transform = True
        stmt.body = split_body(
            node.body, context.replace(continuation=wret), prebody=self.queue
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
            split_tag = getattr(x, "split_tag", "normal")
            collapsed = getattr(x, "collapsed", False)

            if split_tag == "inner" and collapsed:
                cont = self.create_continuation(None, context)
                ret = ast.Return(value=cont)
                ctx = context.replace(continuation=ret)
                self.process(x, ctx)

            elif split_tag == "inner":
                stmts, expr = Collapse.run(x, context=context)
                assert expr is None
                self.queue.extend(stmts)

            elif split_tag == "match":
                cont = self.create_continuation(x, context)
                self.acc = [ast.Return(value=cont)]

            else:
                match x:
                    case ast.Return(value=v):
                        if not getattr(x, "no_transform", False):
                            x = ast.Return(
                                value=ast.Call(
                                    func=ast.Name(id="continuation", ctx=ast.Load()),
                                    args=[v],
                                    keywords=[],
                                )
                            )
                self.acc.append(x)

        self.acc.reverse()
        return self.acc


def split_body(body, context, prebody=[]):
    return BodySplitter(prebody=prebody).split(body, context)


class Splitter(NodeTransformer):
    def __call__(self, node: ast.FunctionDef, context: SplitState):
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
        new_body = split_body(node.body, context)
        defns = context.definitions.values()
        if defns:
            _encapsulate(node.args, new_body, context, cont_name=node.name)
            return [*reversed(defns)]

        else:
            return None
