from functools import partial


class FunBites:
    def __init__(self, start, definitions):
        self.start = start
        self.definitions = definitions

    def __call__(self, *args, **kwargs):
        result = self.definitions[self.start](*args, **kwargs)
        while isinstance(result, Bite):
            result = result()
        return result


class Bite(partial):
    pass
