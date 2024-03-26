type = 'StreamHelper'
obs_ws_url = 'ws://192.168.111.111:4455'
obs_ws_pwd = 'qqdIciF8FPNfzrqX'
cat_det_cfg = dict(type='YOLOv5CatDetection', device='cpu')
rtsp_reader_backend = 'ffmpeg'
obs_scenes = dict(
    balcony=dict(
        default=True,
        media_source='MeizuX',
        vote_key='a',
        state_label_source='state_label'),
    kitchen_lo=dict(
        media_source='Mi8SE', vote_key='d', state_label_source='state_label'),
    kitchen_hi=dict(
        media_source='Redmi4', vote_key='e', state_label_source='state_label'),
    entry_hi=dict(
        media_source='MiMax', vote_key='b', state_label_source='state_label'),
    entry_lo=dict(
        media_source='Nokia6', vote_key='c', state_label_source='state_label'))
interact_reader_cfg = dict(
    type='BiliInteractReader',
    id_code='DE05WFEOKJK07',
    app_id=1712207820649,
    key='C30iYiXWexZWYMIDLN9SAPfy',
    secret='gXdR89EkRmJ6BOH2FLRoIpl7NiXldJ',
    host='https://live-open.biliapi.com',
    super_users=['4378037'],
    verbose=True,
    interact_queue_len=100)
detect_interval = 10
mainloop_interval = 1
vote_interval = 10
missing_tolerance = 6
