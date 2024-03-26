import asyncio
import hashlib
import hmac
import json
import logging
import random
import requests
import struct
import time
import websockets
from hashlib import sha256
from queue import Full, Queue
from typing import Union


class BiliClient:

    def __init__(self,
                 id_code: str,
                 app_id: str,
                 key: str,
                 secret: str,
                 host: str,
                 interact_queue: Union[None, Queue] = None,
                 queue_put_timeout: int = 10,
                 verbose: bool = False,
                 logger: Union[None, str, logging.Logger] = None):
        self.id_code = id_code
        self.app_id = app_id
        self.key = key
        self.secret = secret
        self.host = host
        self.game_id = ''
        self.interact_queue = interact_queue
        self.queue_put_timeout = queue_put_timeout
        self.verbose = verbose
        if logger is None:
            self.logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger

    def run(self):
        # loop = asyncio.get_event_loop()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        websocket = loop.run_until_complete(self.connect())
        tasks = [
            asyncio.ensure_future(self.recv_loop(websocket)),
            asyncio.ensure_future(self.send_heartbeat(websocket)),
            asyncio.ensure_future(self.app_send_heartbeat()),
        ]
        loop.run_until_complete(asyncio.gather(*tasks))

    def sign(self, params):
        """Sign the http request."""
        key = self.key
        secret = self.secret
        md5 = hashlib.md5()
        md5.update(params.encode())
        ts = time.time()
        nonce = random.randint(1, 100000) + time.time()
        md5data = md5.hexdigest()
        headerMap = {
            'x-bili-timestamp': str(int(ts)),
            'x-bili-signature-method': 'HMAC-SHA256',
            'x-bili-signature-nonce': str(nonce),
            'x-bili-accesskeyid': key,
            'x-bili-signature-version': '1.0',
            'x-bili-content-md5': md5data,
        }

        headerList = sorted(headerMap)
        headerStr = ''

        for key in headerList:
            headerStr = headerStr + key + ':' + str(headerMap[key]) + '\n'
        headerStr = headerStr.rstrip('\n')

        appsecret = secret.encode()
        data = headerStr.encode()
        signature = hmac.new(appsecret, data, digestmod=sha256).hexdigest()
        headerMap['Authorization'] = signature
        headerMap['Content-Type'] = 'application/json'
        headerMap['Accept'] = 'application/json'
        return headerMap

    def get_websocket_info(self):
        # 开启应用
        postUrl = '%s/v2/app/start' % self.host
        params = '{"code":"%s","app_id":%d}' % (self.id_code, self.app_id)
        headerMap = self.sign(params)
        retry_count = 0
        retry_max = 5
        retry_interval = 1
        _game_id = None
        while retry_count < retry_max:
            r = requests.post(
                url=postUrl, headers=headerMap, data=params, verify=True)
            data = json.loads(r.content)
            _data = data['data']
            try:
                _game_info = _data['game_info']
                _game_id = _game_info['game_id']
                break
            except TypeError:
                retry_count += 1
                time.sleep(retry_interval)
                continue
        if _game_id is None:
            raise ValueError(
                f'Failed to get game_id within {retry_count} retries.')
        self.game_id = str(_game_id)
        self.logger.info('[BiliClient] get_websocket_info success. ' +
                         f'data={data}')
        # 获取长连地址和鉴权体
        return str(data['data']['websocket_info']['wss_link'][0]), str(
            data['data']['websocket_info']['auth_body'])

    # 发送游戏心跳
    async def app_send_heartbeat(self):
        while True:
            await asyncio.ensure_future(asyncio.sleep(20))
            postUrl = '%s/v2/app/heartbeat' % self.host
            params = '{"game_id":"%s"}' % (self.game_id)
            headerMap = self.sign(params)
            r = requests.post(
                url=postUrl, headers=headerMap, data=params, verify=True)
            if r.status_code != 200:
                self.logger.error('[BiliClient] app_send_heartbeat failed')
                r.raise_for_status()
            else:
                data = json.loads(r.content)
                self.logger.debug('[BiliClient] app_send_heartbeat success. ' +
                                  f'data={data}')

    # 发送鉴权信息
    async def auth(self, websocket, authBody):
        req = _BliveProto()
        req.body = authBody
        req.op = 7
        await websocket.send(req.pack())
        buf = await websocket.recv()
        resp = _BliveProto()
        resp.unpack(buf)
        respBody = json.loads(resp.body)
        if respBody['code'] != 0:
            self.logger.info('[BiliClient] Auth failed.')
        else:
            self.logger.info('[BiliClient] Auth success.')

    # 发送心跳
    async def send_heartbeat(self, websocket):
        while True:
            await asyncio.ensure_future(asyncio.sleep(20))
            req = _BliveProto()
            req.op = 2
            await websocket.send(req.pack())
            self.logger.debug('[BiliClient] send_heartbeat success')

    # 读取信息
    async def recv_loop(self, websocket):
        self.logger.debug('[BiliClient] recv_loop start')
        while True:
            recvBuf = await websocket.recv()
            resp = _BliveProto()
            resp.unpack(recvBuf)
            op_type = resp.get_operation_type()
            if op_type == 'OP_SEND_SMS_REPLY':
                body_str = resp.body
                body_dict = json.loads(body_str)
                if 'cmd' in body_dict and \
                        body_dict['cmd'] == 'LIVE_OPEN_PLATFORM_DM':
                    uid = body_dict['data']['uid']
                    uname = body_dict['data']['uname']
                    msg = body_dict['data']['msg']
                    # put danmu into queue
                    clean_data = dict(uid=uid, uname=uname, msg=msg)
                    if self.verbose:
                        self.logger.info(clean_data)
                    if self.interact_queue is not None:
                        try:
                            self.interact_queue.put(
                                clean_data, timeout=self.queue_put_timeout)
                        except Full:
                            self.logger.error(
                                '[BiliClient] interact_queue is full, ' +
                                f' drop danmu message={clean_data}.')
                else:
                    # Not a danmu message
                    # TODOL record gifts
                    pass
            else:
                # Not a reply message
                pass

    # 建立连接
    async def connect(self):
        addr, authBody = self.get_websocket_info()
        self.logger.debug('[BiliClient] connect success. ' +
                          f'addr={addr}, authBody={authBody}')
        websocket = await websockets.connect(addr)
        # 鉴权
        await self.auth(websocket, authBody)
        return websocket

    def __enter__(self):
        pass

    def __exit__(self, type, value, trace):
        # 关闭应用
        postUrl = '%s/v2/app/end' % self.host
        params = '{"game_id":"%s","app_id":%d}' % (self.game_id, self.app_id)
        headerMap = self.sign(params)
        r = requests.post(
            url=postUrl, headers=headerMap, data=params, verify=True)
        if r.status_code != 200:
            self.logger.error(f'[BiliClient] end app failed, params={params}')
        else:
            self.logger.debug(f'[BiliClient] end app success, params={params}')


class _BliveProto:

    def __init__(self):
        self.packetLen = 0
        self.headerLen = 16
        self.ver = 0
        self.op = 0
        self.seq = 0
        self.body = ''
        self.maxBody = 2048

    def pack(self):
        self.packetLen = len(self.body) + self.headerLen
        buf = struct.pack('>i', self.packetLen)
        buf += struct.pack('>h', self.headerLen)
        buf += struct.pack('>h', self.ver)
        buf += struct.pack('>i', self.op)
        buf += struct.pack('>i', self.seq)
        buf += self.body.encode()
        return buf

    def unpack(self, buf):
        if len(buf) < self.headerLen:
            print('包头不够')
            return
        self.packetLen = struct.unpack('>i', buf[0:4])[0]
        self.headerLen = struct.unpack('>h', buf[4:6])[0]
        self.ver = struct.unpack('>h', buf[6:8])[0]
        self.op = struct.unpack('>i', buf[8:12])[0]
        self.seq = struct.unpack('>i', buf[12:16])[0]
        if self.packetLen < 0 or self.packetLen > self.maxBody:
            print('包体长不对', 'self.packetLen:', self.packetLen, ' self.maxBody:',
                  self.maxBody)
            return
        if self.headerLen != self.headerLen:
            print('包头长度不对')
            return
        bodyLen = self.packetLen - self.headerLen
        self.body = buf[16:self.packetLen]
        if bodyLen <= 0:
            return
        if self.ver == 0:
            return
        else:
            return

    def get_operation_type(self) -> str:
        if self.op == 2:
            return 'OP_HEARTBEAT'
        elif self.op == 3:
            return 'OP_HEARTBEAT_REPLY'
        elif self.op == 5:
            return 'OP_SEND_SMS_REPLY'
        elif self.op == 7:
            return 'OP_AUTH'
        elif self.op == 8:
            return 'OP_AUTH_REPLY'
        else:
            return 'OP_UNKNOWN'
