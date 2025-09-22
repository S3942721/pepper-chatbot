from naoqi import ALProxy, ALModule
import time
import json
import logger
import threading


class HealthyCheckModule(ALModule):
    def __init__(self, name, nao_ip=None, nao_port=None, webview_url=None):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        # Basic state
        self.got_pong = False
        self.webview_url = webview_url
        self.nao_ip = nao_ip
        self.nao_port = nao_port

        # Reload/heartbeat tracking (legacy)
        self.last_reload_time = 0
        self.stale_strikes = 0
        self.min_reload_interval = 20  # seconds between reloads to avoid thrashing

        # Services via ALProxy (no qi.Session)
        self.tablet_service = ALProxy("ALTabletService")
        self.memory = ALProxy("ALMemory")
        try:
            self.tablet_service.reloadPage(False)
        except Exception as e:
            logger.warning("HealthyCheck: reloadPage failed:", e)
        
        # Subscriptions for existing health/state sync
        self.memory.subscribeToEvent("HealthyCheck", name, "pong")
        self.memory.subscribeToEvent("ControlRecording", name, "update_recording")
        self.memory.subscribeToEvent("Speaking", name, "update_speaking")
        self.memory.subscribeToEvent("SyncMessages", name, "update_chat_history")
        self.memory.subscribeToEvent("LoadHTML", name, "update_html_url")
        
        # Listen for external reload command from web controller (via socket bridge)
        self.memory.subscribeToEvent("ReloadTablet", name, "reload_tablet")

        self.is_allowed_recording = False
        self.is_speaking = None
        self.chat_history = ''

        # Legacy heartbeat monitoring state (disabled)
        self.last_heartbeat = time.time()
        self.heartbeat_timeout = 25  # seconds
        self.monitoring = False
        self.monitor_thread = None

        # Load initial page if URL provided
        if self.webview_url:
            self.show_page()
    
    def __del__(self):
        """Cleanup event subscriptions"""
        logger.info("HealthyCheck: cleaning up")
        try:
            # Unsubscribe events
            try:
                self.memory.unsubscribeToEvent("HealthyCheck", self.getName())
                self.memory.unsubscribeToEvent("ControlRecording", self.getName())
                self.memory.unsubscribeToEvent("Speaking", self.getName())
                self.memory.unsubscribeToEvent("SyncMessages", self.getName())
                self.memory.unsubscribeToEvent("LoadHTML", self.getName())
                self.memory.unsubscribeToEvent("ReloadTablet", self.getName())
            except Exception as e:
                logger.warning("HealthyCheck: Unsubscribe failed:", e)
        except Exception as e:
            logger.error("HealthyCheck: cleanup error:", e)
        finally:
            logger.info("HealthyCheck: cleaned up!")
    
    def ping(self):
        # Legacy helper retained for compatibility; simply show page
        if not self.webview_url: return
        self.memory.raiseEvent("HealthyCheck", "ping")
        self.got_pong = False
        try:
            self.show_page()
        except Exception as e:
            logger.warning("HealthyCheck: ping load error:", e)
        logger.debug("Getting pong")
        time.sleep(2)
        logger.debug("Got pong:", self.got_pong)
        if not self.got_pong:
            logger.warning("No pong from tablet, reloading webview")
            try:
                self.show_page()
            except Exception as e:
                logger.warning("HealthyCheck: reload after no pong failed:", e)
            time.sleep(1)
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
        # Just (re)load the page when URL changes
        self.show_page()
        self.sync()

    def reload_tablet(self, event_name, value):
        """External trigger to reload the tablet webview"""
        logger.info("HealthyCheck: ReloadTablet received - reloading webview")
        self.show_page()

    def show_page(self):
        """Display the configured webview URL without injecting JS"""
        if not self.webview_url:
            return
        try:
            self.tablet_service.showWebview(self.webview_url)

            self.last_reload_time = time.time()
            logger.info("HealthyCheck: Webview shown:", self.webview_url)
        except Exception as e:
            logger.warning("HealthyCheck: showWebview failed:", e)

    # Legacy heartbeat handlers removed (no JS injection, no monitoring)
    # def on_webview_heartbeat(self, event_name, value): pass
    # def monitor_heartbeat(self): pass

    def stop_webview_monitoring(self):
        try:
            self.monitoring = False
        except Exception as e:
            logger.warning("HealthyCheck: stop_webview_monitoring error:", e)
