import ast
import dataclasses
from dataclasses import dataclass, field

from ovld import recurse

from .visit import NodeVisitor


@dataclass
class Variables:
    arg_defs: set[str] = field(default_factory=set)
    local_defs: set[str] = field(default_factory=set)
    uses_free: set[str] = field(default_factory=set)
    uses_local: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)
    globals: set[str] = field(default_factory=set)

    @property
    def defs(self):
        return self.arg_defs | self.local_defs

    def use(self, varname):
        if varname in self.defs:
            self.uses_local.add(varname)
        else:
            self.uses_free.add(varname)

    def define(self, varname):
        if varname in self.nonlocals or varname in self.globals or varname in self.arg_defs:
            return
        self.local_defs.add(varname)
        if varname in self.uses_free:
            self.uses_free.remove(varname)
            self.uses_local.add(varname)

    def define_argument(self, varname):
        if varname in self.nonlocals or varname in self.globals:
            return
        self.arg_defs.add(varname)
        if varname in self.uses_free:
            self.uses_free.remove(varname)
            self.uses_local.add(varname)

    def declare_nonlocal(self, varname):
        if varname in self.local_defs:
            self.local_defs.remove(varname)
        self.nonlocals.add(varname)
        if varname in self.uses_local:
            self.uses_local.remove(varname)
            self.uses_free.add(varname)

    def declare_global(self, varname):
        if varname in self.local_defs:
            self.local_defs.remove(varname)
        self.globals.add(varname)
        if varname in self.uses_local:
            self.uses_local.remove(varname)
            self.uses_free.add(varname)

    def clone(self):
        return type(self)(
            arg_defs=set(self.arg_defs),
            local_defs=set(self.local_defs),
            uses_free=set(self.uses_free),
            uses_local=set(self.uses_local),
            nonlocals=set(self.nonlocals),
            globals=set(self.globals),
        )

    replace = dataclasses.replace


class VariableAnalysis(NodeVisitor):
    def inner(self, node: ast.FunctionDef, context: Variables):
        for arg in node.args.args:
            context.define_argument(arg.arg)
        for arg in node.args.kwonlyargs:
            context.define_argument(arg.arg)
        if node.args.vararg:
            context.define_argument(node.args.vararg.arg)
        if node.args.kwarg:
            context.define_argument(node.args.kwarg.arg)
        self(node.body, context)
        return context

    def __call__(self, node: ast.Name, context: Variables):
        match node.ctx:
            case ast.Load():
                context.use(node.id)
            case ast.Store():
                context.define(node.id)
                context.use(node.id)
            case _:
                raise Exception(f"Unsupported context: {node.ctx}")
        return context

    def __call__(self, node: ast.Nonlocal, context: Variables):
        for name in node.names:
            context.declare_nonlocal(name)
        return context

    def __call__(self, node: ast.Global, context: Variables):
        for name in node.names:
            context.declare_global(name)
        return context

    def __call__(self, node: ast.FunctionDef, context: Variables):
        context.define(node.name)
        inner_context = self.inner(node, Variables())
        for expr in node.args.defaults:
            recurse(expr, context)
        for var in inner_context.uses_free:
            if var in inner_context.globals:
                context.uses_free.add(var)
            else:
                context.use(var)
        return context

    def reduce(self, node, results, context):
        return context
