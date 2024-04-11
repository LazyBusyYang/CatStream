import logging
from queue import Queue
from threading import Event, Thread
from typing import List, Union

from .bili_client import BiliClient


class BiliInteractReader:
    """A class to read and process the interaction data from Bilibili."""

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
        """
        Args:
            id_code (str):
                ID code.
            app_id (str):
                App ID on in https://open-live.bilibili.com/open-manage.
            key (str):
                Access key.
            secret (str):
                Secret key.
            host (str):
                Host URL of bilibili open api,
                typically it is https://live-open.biliapi.com.
            super_users (List[str]):
                A list of super users' uid.
                Super users have more voting power.
            verbose (bool, optional):
                Whether to print verbose log messages.
                Defaults to False.
            interact_queue_len (int, optional):
                Length of the interaction queue.
                Defaults to 100.
            logger (Union[None, str, logging.Logger], optional):
                Logger for logging. If None, a logger
                named __name__ will be selected.
                Defaults to None.

        Raises:
            ValueError:
                The first item from the interact queue is not "Ready".
        """
        if logger is None:
            self.logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger
        self.interact_queue_len = interact_queue_len
        self.interact_queue = Queue(maxsize=interact_queue_len)
        self.exit_signal = Event()
        self.verbose = verbose
        self.bili_client = BiliClient(
            id_code=id_code,
            app_id=app_id,
            key=key,
            secret=secret,
            host=host,
            interact_queue=self.interact_queue,
            exit_signal=self.exit_signal,
            verbose=verbose,
            logger=logger)
        self.super_users = super_users
        # init vote cache
        self.reset()
        # call self.bili_client.run() in a new thread
        self.client_thread = Thread(target=self.bili_client.run)
        self.client_thread.start()
        first_item = self.interact_queue.get(block=True)
        if not first_item == 'Ready':
            msg = '[BiliInteractReader] The first item ' +\
                'from the interact queue should be "Ready".'
            self.logger.error(msg)
            raise ValueError(msg)

    def reset(self) -> None:
        """Reset the vote cache."""
        self.votes = dict()
        self.voted_users = set()

    def _load_new_msg(self) -> None:
        """Load new messages from the interact queue and update the vote
        cache."""
        n_data = self.interact_queue.qsize()
        for _ in range(n_data):
            inter_data = self.interact_queue.get()
            danmu_msg = inter_data['msg']
            clean_msg = danmu_msg.strip().lower()
            # check if clean_msg is a single letter
            if len(clean_msg) == 1 and clean_msg.isalpha():
                if clean_msg not in self.votes:
                    self.votes[clean_msg] = 0
                uid = str(inter_data['uid'])
                # skip if the user has voted
                if uid in self.voted_users:
                    continue
                self.voted_users.add(uid)
                n_votes = 1
                medal_name = inter_data['medal_name']
                if medal_name == '小菜雞':
                    medal_bonus = int(inter_data['medal_level'])
                    n_votes += medal_bonus
                if uid in self.super_users:
                    super_bonus = 10
                    n_votes += super_bonus
                self.votes[clean_msg] += n_votes

    def get_vote_results(self) -> dict:
        """Get the vote results.

        Returns:
            dict: The vote results.
        """
        self._load_new_msg()
        return self.votes

    def stop_thread(self) -> None:
        """Stop the client thread."""
        self.exit_signal.set()
        if self.verbose:
            self.logger.info('[BiliInteractReader] Stop signal is sent to ' +
                             'the client thread.')
        self.client_thread.join()
        self.logger.info('[BiliInteractReader] Reader and its client thread ' +
                         'have been stopped.')
