import pickle

from funbites.checkpoint import Checkpointer, checkpoint
from funbites.interface import checkpointable, resumable
from funbites.strategy import continuator


class Stop(Exception):
    pass


class TimeBomb:
    def __init__(self, maxcount=10):
        self.maxcount = maxcount
        self.reset()

    def reset(self):
        self.count = 0

    @continuator
    def __call__(self, x=None, *, continuation):
        if self.count == self.maxcount:
            self.reset()
            raise Stop()
        else:
            self.count += 1
            return checkpoint(x, continuation=continuation)


tick = TimeBomb(10)
tick.__is_continuator__ = True


@checkpointable
def loopy(n):
    ret = 0
    for i in range(n):
        ret += i
        tick()
    return ret


def test_checkpoint(tmp_path):
    data_path = tmp_path / "data.pkl"
    chk = Checkpointer(data_path, cleanup=True)
    result = None
    stop_count = 0
    assert not data_path.exists()
    for _ in range(11):
        try:
            result = chk.run(loopy, 100)
            break
        except Stop:
            stop_count += 1
            assert data_path.exists()
            continue
    assert result == sum(range(100))
    assert stop_count == 9


@resumable
def squares():
    i = 0
    while True:
        yield i * i
        i += 1


def test_serialize_generator():
    sq = squares()
    assert next(sq) == 0
    assert next(sq) == 1
    assert next(sq) == 4
    ser = pickle.dumps(sq)
    assert next(sq) == 9
    assert next(sq) == 16
    sq = pickle.loads(ser)
    assert next(sq) == 9
    assert next(sq) == 16
