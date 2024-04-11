type = 'StreamHelper'
obs_ws_url = 'ws://OBS_HOST:4455'
obs_ws_pwd = 'OBS_PWD'
detection_proc_cfg = dict(
    type='DetectionProcessor',
    verbose=False,
    input_queue_len=1,
    output_queue_len=1,
    detect_thread_cfg=dict(
        type='RTSPDetectionThread',
        rtsp_reader_backend='ffmpeg',
        rtsp_timeout=5,
        interval=1,
        verbose=False,
        cat_det_cfg=dict(type='YOLOv5CatDetection', device='cpu'),
    ))
obs_scenes = dict(
    balcony_lo=dict(
        media_source='Mate9',
        media_rotation=180,
        vote_key='b',
        state_label_source='state_label'),
    balcony_hi=dict(
        media_source='MeizuX', vote_key='a', state_label_source='state_label'),
    bed_hi=dict(
        media_source='MiMax', vote_key='c', state_label_source='state_label'),
    entry_lo=dict(
        media_source='Nokia6', vote_key='d', state_label_source='state_label'),
    kitchen_lo=dict(
        media_source='Redmi4',
        vote_key='e',
        media_rotation=180,
        state_label_source='state_label'),
    entry_hi=dict(
        media_source='Mi8SE', vote_key='f', state_label_source='state_label'),
)
interact_reader_cfg = None
detect_interval = 10
mainloop_interval = 5
vote_interval = 30
