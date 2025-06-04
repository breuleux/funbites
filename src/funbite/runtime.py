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
