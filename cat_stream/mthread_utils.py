from queue import Empty, Queue
from typing import Any


def force_put(queue: Queue, data: Any) -> None:
    """Force put data into a queue, if the queue is full, consume the last
    input.

    Args:
        queue (Queue): A queue to put data into.
        data (Any): Data to put into the queue.
    """
    if queue.full():
        try:
            # clear the queue
            queue.get_nowait()
        except Empty:
            # last input is consumed
            pass
    queue.put(data)
