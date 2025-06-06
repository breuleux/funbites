import importlib

ABSENT = object()


class Loop:
    def __init__(self, start, args, kwargs, is_generator):
        self.is_generator = is_generator
        self.state = start(*args, **kwargs)

    def step(self):
        yields = ABSENT
        self.state = self.state.step()
        if isinstance(self.state, FunBiteYield):
            yields = self.state.value
            self.state = self.state.continuation(self.state.value)
        return yields, self.state

    def run(self):
        while True:
            if not isinstance(self.state, FunBite):
                return self.state
            self.step()

    def __iter__(self):
        if not self.is_generator:
            raise TypeError(f"{self.start} is not a generator")
        return self

    def __next__(self):
        while True:
            if not isinstance(self.state, FunBite):
                raise StopIteration(self.state)
            yields, _ = self.step()
            if yields is not ABSENT:
                return yields


def loop(start, args, kwargs):
    result = start(*args, **kwargs)
    while isinstance(result, FunBite):
        result = result.step()
    return result


class FunBite:
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        return FunBite(
            self.func,
            *self.args,
            *args,
            **self.kwargs,
            **kwargs,
        )

    def step(self, *args, **kwargs):
        return self.func(
            *self.args,
            *args,
            **self.kwargs,
            **kwargs,
        )

    def execute(self, *args, **kwargs):
        return loop(self, args, kwargs)


class FunBiteYield:
    def __init__(self, value, continuation=None):
        self.value = value
        self.continuation = continuation
