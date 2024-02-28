import argparse
from cat_stream.config_reader import file2dict
from cat_stream.stream_helper import StreamHelper
import logging

def main(args):
    # init logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('CatSream')
    # load cfg
    cfg = file2dict(args.config_path)
    cfg['logger'] = logger
    if args.obs_ws_pwd is not None:
        cfg['obs_ws_pwd'] = args.obs_ws_pwd
    # create a StreamHelper
    cfg.pop('type', None)
    stream_helper = StreamHelper(**cfg)
    # start the main loop
    stream_helper.start()

def setup_parser():
    parser = argparse.ArgumentParser('Start the cat stream helper.')
    # server args
    parser.add_argument(
        '--config_path',
        help='Path to the configuration file.',
        type=str,
        default='configs/yolov5_ffmpeg.py')
    parser.add_argument(
        '--obs_ws_pwd',
        help='Password of the OBS websocket.',
        required=False
    )
    return parser.parse_args()

if __name__ == '__main__':
    args = setup_parser()
    main(args)