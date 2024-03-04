type = 'StreamHelper'
obs_ws_url = 'ws://192.168.111.111:4455'
obs_ws_pwd = 'qqdIciF8FPNfzrqX'
cat_det_cfg = dict(type='YOLOv5CatDetection', device='cpu')
rtsp_reader_backend = 'ffmpeg'
obs_scenes = dict(
    balcony=dict(default=True, media_source='MeizuX'),
    kitchen_lo=dict(media_source='Mi8SE'),
    kitchen_hi=dict(media_source='Redmi4'),
    entry=dict(media_source='Nokia6'))
detect_interval = 10
missing_tolerance = 3
