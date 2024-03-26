import logging
from queue import Queue
from threading import Thread
from typing import List, Union

from .bili_client import BiliClient


class BiliInteractReader:

    def __init__(self,
                 id_code: str,
                 app_id: str,
                 key: str,
                 secret: str,
                 host: str,
                 super_users: List[str],
                 verbose: bool = False,
                 interact_queue_len: int = 100,
                 logger: Union[None, str, logging.Logger] = None) -> None:
        if logger is None:
            self.logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger
        self.interact_queue_len = interact_queue_len
        self.interact_queue = Queue(maxsize=interact_queue_len)
        self.bili_client = BiliClient(
            id_code=id_code,
            app_id=app_id,
            key=key,
            secret=secret,
            host=host,
            interact_queue=self.interact_queue,
            verbose=verbose,
            logger=logger)
        self.super_users = super_users
        # init vote cache
        self.votes = dict()
        # call self.bili_client.run() in a new thread
        self.client_thread = Thread(target=self.bili_client.run)
        self.client_thread.start()

    def reset(self) -> None:
        self.votes = dict()

    def _load_new_msg(self) -> None:
        n_data = self.interact_queue.qsize()
        for _ in range(n_data):
            inter_data = self.interact_queue.get()
            danmu_msg = inter_data['msg']
            clean_msg = danmu_msg.strip().lower()
            # check if clean_msg is a single letter
            if len(clean_msg) == 1 and clean_msg.isalpha():
                if clean_msg not in self.votes:
                    self.votes[clean_msg] = set()
                self.votes[clean_msg].add(inter_data['uid'])

    def get_vote_results(self) -> dict:
        self._load_new_msg()
        ret_dict = dict()
        for k, v in self.votes.items():
            ret_dict[k] = 0
            for uid in v:
                uid = str(uid)
                if uid in self.super_users:
                    ret_dict[k] += 10
                else:
                    ret_dict[k] += 1
        return ret_dict

    def get_lock_queue(self) -> dict:
        raise NotImplementedError
