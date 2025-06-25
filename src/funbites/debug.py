import ast


def as_source(node):
    ast.fix_missing_locations(node)
    return ast.unparse(node)


def show(node):
    print(as_source(node))
