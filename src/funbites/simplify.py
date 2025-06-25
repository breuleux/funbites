import ast

from ovld import call_next, ovld, recurse

from .visit import NodeVisitor


class TagIgnores(NodeVisitor):
    def reduce(self, node, results, context):
        return any(x for _, x in results)

    @ovld(priority=1)
    def __call__(self, node: ast.AST, context: object):
        matches = call_next(node, context) or context.strategy.is_split(node, context)
        node.ignore = not matches
        return matches

    def __call__(self, node: ast.Expr, context: object):
        return recurse(node.value, context)

    def __call__(self, node: object, context: object):
        return False


class Simplify(NodeVisitor):
    def collapse(self, node, hoist, recurse, context):
        stmts = []
        for fld in hoist:
            value = getattr(node, fld)
            new_stmts, new_value = self(value, context)
            assert value is None or new_value is not None
            stmts.extend(new_stmts)
            setattr(node, fld, new_value)

        for fld in recurse:
            if not hasattr(node, fld):
                continue
            value = getattr(node, fld)
            substmts, rval = self(value, context)
            assert not any(rval)
            setattr(node, fld, substmts)

        if isinstance(node, ast.stmt):
            rval = None
            add = node
        else:
            newsym = context.gensym()
            rval = ast.Name(id=newsym, ctx=ast.Load())
            add = ast.Assign(
                targets=[ast.Name(id=newsym, ctx=ast.Store())],
                value=node,
            )
            # add.ignore = node.ignore
        # add.collapsed = True
        stmts.append(add)
        return stmts, rval

    @ovld(priority=1)
    def __call__(self, node: ast.stmt, context):
        if node.ignore:
            return [node], None
        else:
            return call_next(node, context)

    @ovld(priority=1)
    def __call__(self, node: ast.expr, context):
        if node.ignore:
            return [], node
        else:
            print(ast.unparse(node))
            return call_next(node, context)

    def __call__(self, node: ast.AST, context):
        usually_recurse = {"body", "orelse", "cases"}
        usually_keep = set()
        no_hoist = {*usually_recurse, *usually_keep}
        all_fields = [f for f, _ in ast.iter_fields(node)]
        hoist = [f for f in all_fields if f not in no_hoist]
        return self.collapse(node, hoist, usually_recurse, context)

    def __call__(self, node: ast.While, context):
        return self.collapse(node, hoist=[], recurse=["body", "orelse"], context=context)

    def __call__(self, node: ast.Try, context):
        return self.collapse(
            node,
            hoist=[],
            recurse=["body", "handlers", "orelse", "finalbody"],
            context=context,
        )

    # def __call__(self, node: ast.With, context):
    #     return self.collapse(node, hoist=[], context=context)

    def __call__(self, node: ast.Compare, context):
        return self.collapse(node, hoist={"comparators"}, recurse=[], context=context)

    def __call__(self, node: ast.FunctionDef, context):
        return self.collapse(node, hoist=[], recurse=["body"], context=context)

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
