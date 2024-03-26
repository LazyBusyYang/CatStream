import asyncio
import logging
import simpleobsws
from typing import Union


class ObsClient:

    def __init__(self,
                 ws_url: str,
                 ws_pwd: str,
                 logger: Union[None, str, logging.Logger] = None) -> None:
        """A client for controlling the live scene in OBS.

        Args:
            ws_url (str):
                The url of the OBS websocket.
            ws_pwd (str):
                The password of the OBS websocket.
            logger (Union[None, str, logging.Logger], optional):
                Logger for logging. If None, root logger will be selected.
                Defaults to None.
        """
        if logger is None:
            logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            logger = logging.getLogger(logger)
        self.logger = logger
        self.ws_url = ws_url
        self.ws_pwd = ws_pwd
        # Create an IdentificationParameters object (optional for connecting)
        identification_parameters = simpleobsws.IdentificationParameters(
            ignoreNonFatalRequestChecks=False)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self.loop = loop

        # connect to obs
        self.ws = simpleobsws.WebSocketClient(
            url=ws_url,
            password=ws_pwd,
            identification_parameters=identification_parameters,
        )

    @property
    def server_valid(self) -> bool:
        try:
            self.loop.run_until_complete(self.ws.connect())
            self.loop.run_until_complete(self.ws.wait_until_identified())
        except Exception as e:
            self.logger.error(e)
            return False
        self.loop.run_until_complete(self.ws.disconnect())
        return True

    def __del__(self) -> None:
        self.loop.close()

    def set_current_scene(self, scene_name: str) -> None:
        """Switch to a scene by its name.

        Args:
            scene_name (str):
                The name of the scene.
        """
        self.loop.run_until_complete(
            set_current_scene(self.ws, scene_name, self.logger))

    def get_source_settings(self, source_name: str) -> dict:
        """Get settings of a source.

        Args:
            source_name (str):
                The name of the source.
        Returns:
            dict: The settings of the source.
        """
        return self.loop.run_until_complete(
            get_source_settings(self.ws, source_name, self.logger))

    def get_current_scene_name(self) -> str:
        """Get name of the current scene.

        Returns:
            str:
                The name of the current scene.
        """
        return self.loop.run_until_complete(
            get_current_scene_name(self.ws, self.logger))

    def set_source_text(self, source_name: str, text: str) -> None:
        """Set text for a source.

        Args:
            source_name (str):
                The name of the source.
            text (str):
                The text to be set.
        """
        self.loop.run_until_complete(
            set_source_text(self.ws, source_name, text, self.logger))


async def set_current_scene(
    ws: simpleobsws.WebSocketClient,
    scene_name: str,
    logger: logging.Logger,
) -> None:
    """Set the current scene by scene name.

    Args:
        ws (simpleobsws.WebSocketClient):
            The websocket client.
        scene_name (str):
            The name of the scene.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.
    Raises:
        RuntimeError:
            If the request failed.
    """
    # connect and authenticate
    await ws.connect()
    await ws.wait_until_identified()
    request = simpleobsws.Request(
        requestType='SetCurrentProgramScene',
        requestData=dict(sceneName=scene_name))
    ret = await ws.call(request)
    if not ret.ok():
        logger.error('Failed to set the current visible scene.\n' +
                     f'Error code: {ret.requestStatus.code}\n' +
                     f'Error message: {ret.requestStatus.comment}')
        raise RuntimeError(ret.requestStatus.comment)
    await ws.disconnect()
    return


async def get_current_scene_name(ws: simpleobsws.WebSocketClient,
                                 logger: logging.Logger) -> str:
    """Get name of the current scene.

    Args:
        ws (simpleobsws.WebSocketClient):
            The websocket client.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.
    Returns:
        str:
            The name of the current scene.
    Raises:
        RuntimeError:
            If the request failed.
    """
    # connect and authenticate
    await ws.connect()
    await ws.wait_until_identified()
    request = simpleobsws.Request(requestType='GetCurrentProgramScene')
    ret = await ws.call(request)
    if ret.ok():
        scene_name = ret.responseData['currentProgramSceneName']
    else:
        logger.error('Failed to get name of the current scene.\n' +
                     f'Error code: {ret.requestStatus.code}\n' +
                     f'Error message: {ret.requestStatus.comment}')
        raise RuntimeError(ret.requestStatus.comment)
    await ws.disconnect()
    return scene_name


async def get_source_settings(
    ws: simpleobsws.WebSocketClient,
    source_name: str,
    logger: logging.Logger,
) -> dict:
    """Get settings of a source.

    Args:
        ws (simpleobsws.WebSocketClient):
            The websocket client.
        source_name (str):
            The name of the source.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.
    Returns:
        dict: The settings of the source.
    Raises:
        RuntimeError:
            If the request failed.
    """
    # connect and authenticate
    await ws.connect()
    await ws.wait_until_identified()
    request = simpleobsws.Request(
        requestType='GetInputSettings',
        requestData=dict(inputName=source_name))
    ret = await ws.call(request)
    if ret.ok():
        type_setting_dict = ret.responseData
    else:
        logger.error(f'Failed to get source settings of {source_name}.\n' +
                     f'Error code: {ret.requestStatus.code}\n' +
                     f'Error message: {ret.requestStatus.comment}')
        raise RuntimeError(ret.requestStatus.comment)
    await ws.disconnect()
    return type_setting_dict


async def set_source_text(
    ws: simpleobsws.WebSocketClient,
    source_name: str,
    text: str,
    logger: logging.Logger,
) -> None:
    """Set the current scene by scene name.

    Args:
        ws (simpleobsws.WebSocketClient):
            The websocket client.
        source_name (str):
            The name of the source.
        input_settings (dict):
            The settings of the source.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.
    Raises:
        RuntimeError:
            If the request failed.
    """
    # connect and authenticate
    await ws.connect()
    await ws.wait_until_identified()
    request = simpleobsws.Request(
        requestType='SetInputSettings',
        requestData=dict(inputName=source_name, inputSettings=dict(text=text)))
    ret = await ws.call(request)
    if not ret.ok():
        logger.error('Failed to set text for source.\n' +
                     f'Error code: {ret.requestStatus.code}\n' +
                     f'Error message: {ret.requestStatus.comment}')
        raise RuntimeError(ret.requestStatus.comment)
    await ws.disconnect()
    return
