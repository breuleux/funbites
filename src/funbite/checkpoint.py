import pickle
from contextvars import ContextVar
from pathlib import Path

from .runtime import FunBite
from .strategy import continuator, returns

checkpointer = ContextVar("checkpointer", default=None)


class Checkpointer:
    def __init__(self, filename, save_function=None, load_function=None, cleanup=False):
        self.file = Path(filename)
        if (save_function is None) ^ (load_function is None):
            raise TypeError(
                "Please provide *both* save_function and load_function, or neither to use the defaults."
            )
        if save_function is None:
            save_function = pickle.dump
            load_function = pickle.load
        self.save = save_function
        self.load = load_function
        self.cleanup = cleanup
        self._token = None

    def run(self, func, *args, **kwargs):
        with self:
            if self.file.exists():
                cont = self.load(self.file.open("rb"))
                rval = cont.execute()
            else:
                rval = func(*args, **kwargs)
        if self.cleanup:
            if self.file.exists():
                self.file.unlink()
        else:
            self.save(FunBite(returns, rval), self.file.open("wb"))
        return rval

    def __enter__(self):
        assert self._token is None
        self._token = checkpointer.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        checkpointer.reset(self._token)
        self._token = None


@continuator
def checkpoint(x=None, *, continuation):
    assert continuation is not None
    cont = continuation(x)
    if (chk := checkpointer.get()) is not None:
        chk.save(cont, chk.file.open("wb"))
    return cont
