from naoqi import ALProxy, ALModule
import time
import json
import logger


class HealthyCheckModule(ALModule):
    def __init__(self, name, webview_url = None):
        ALModule.__init__(self, name)
        self.BIND_PYTHON( self.getName(),"callback" )

        self.got_pong = False
        self.webview_url = webview_url
        
        self.memory = ALProxy("ALMemory")
        self.tablet_service = ALProxy("ALTabletService")
        self.tablet_service.reloadPage(False)
        self.memory.subscribeToEvent("HealthyCheck", name, "pong")
        self.memory.subscribeToEvent("ControlRecording", name, "update_recording")
        self.memory.subscribeToEvent("Speaking", name, "update_speaking")
        self.memory.subscribeToEvent("SyncMessages", name, "update_chat_history")
        self.memory.subscribeToEvent("LoadHTML", name, "update_html_url")

        self.is_allowed_recording = False
        self.is_speaking = None
        self.chat_history = ''
    
    def ping(self):
        if not self.webview_url: return
        self.memory.raiseEvent("HealthyCheck", "ping")
        self.got_pong = False
        self.got_pong = self.tablet_service.loadUrl(self.webview_url)
        logger.debug("Getting pong")
        time.sleep(10)
        logger.debug("Got pong:", self.got_pong)
        if not self.got_pong:
            logger.warning("No pong from tablet, reloading webview")
            self.tablet_service.loadUrl(self.webview_url)
            self.tablet_service.showWebview(self.webview_url)
            time.sleep(2)
            self.sync()

    def pong(self, event_name, value):
        if value == 'pong':
            self.got_pong = True

    def sync(self):
        self.memory.raiseEvent("Sync", json.dumps({
            "speaking": self.is_speaking,
            "allowed_recording": self.is_allowed_recording,
            "history": self.chat_history
        }))

    def update_recording(self, event_name, value):
        self.is_allowed_recording = value
        if not value: self.memory.raiseEvent("Listening", False)

    def update_speaking(self, event_name, value):
        # Receive speaking state updates from centralized speaking manager
        self.is_speaking = value
        logger.debug("Healthy check received speaking state:", value)

    def update_chat_history(self, event_name, value):
        self.chat_history = value

    def update_html_url(self, event_name, value):
        logger.info("Loading HTML:", value)
        self.webview_url = value
        self.tablet_service.showWebview(self.webview_url)
        self.tablet_service.reloadPage(0)
        self.sync()
