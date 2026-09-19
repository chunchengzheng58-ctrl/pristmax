"""Local-filesystem durability and cooperating-process exclusion."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import uuid


def sync_file(path):
    with Path(path).open('r+b' if os.name == 'nt' else 'rb') as stream:
        os.fsync(stream.fileno())


def sync_directory(path):
    # Windows has no portable directory fsync; do not claim power-loss immunity.
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_json(path, value):
    path = Path(path)
    temp = path.parent / ('.state-' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        sync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def exclusive_lock(path):
    # Keep the lock inode stable. OS releases the lock on close or process exit.
    with Path(path).open('a+b') as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('保管区正被其他操作使用，请稍后重试') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
