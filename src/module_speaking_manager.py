import threading
from naoqi import ALProxy, ALModule
import logger


class SpeakingStateManager(ALModule):
    """
    Keep a single authoritative Speaking state.

    This intentionally follows the simple pattern used in the
    HakuHandler_WhenIGrowUp repo: rely on ALTextToSpeech events
    (TextStarted/TextDone/TextInterrupted) and only emit Speaking when
    the state actually changes.
    """

    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")

        self.memory = ALProxy("ALMemory")
        self._speaking_lock = threading.Lock()
        self._speaking = False
        self._current_speech_id = None
        self._naoqi_task_id = None

        self.memory.subscribeToEvent("StartSpeaking", self.getName(), "on_start_speaking")
        self.memory.subscribeToEvent("StopSpeaking", self.getName(), "on_stop_speaking")
        self.memory.subscribeToEvent("StopAction", self.getName(), "on_force_stop")
        self.memory.subscribeToEvent("ClearQueue", self.getName(), "on_force_stop")

        self.memory.subscribeToEvent("ALTextToSpeech/TextStarted", self.getName(), "on_text_started")
        self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "on_speech_finished")
        self.memory.subscribeToEvent("ALTextToSpeech/TextInterrupted", self.getName(), "on_text_interrupted")

        logger.info("SpeakingStateManager initialized")

    def __del__(self):
        logger.info("cleaning everything")

        try:
            if hasattr(self, "memory"):
                try:
                    self.memory.unsubscribeToEvent("StartSpeaking", self.getName())
                    self.memory.unsubscribeToEvent("StopSpeaking", self.getName())
                    self.memory.unsubscribeToEvent("StopAction", self.getName())
                    self.memory.unsubscribeToEvent("ClearQueue", self.getName())
                    self.memory.unsubscribeToEvent("ALTextToSpeech/TextStarted", self.getName())
                    self.memory.unsubscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName())
                    self.memory.unsubscribeToEvent("ALTextToSpeech/TextInterrupted", self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from speaking manager events:", e)

        except Exception as e:
            logger.error("Error during SpeakingStateManager cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def _set_speaking(self, speaking, reason=""):
        with self._speaking_lock:
            if self._speaking == speaking:
                return

            self._speaking = speaking
            self.memory.raiseEvent("Speaking", speaking)
            if speaking:
                logger.info("Speaking state changed to True", reason)
            else:
                logger.info("Speaking state changed to False", reason)

    def _normalise_payload(self, payload):
        if isinstance(payload, dict):
            return payload.get("speech_id"), payload.get("naoqi_task_id")
        return payload, None

    def on_start_speaking(self, event_name, payload):
        speech_id, naoqi_task_id = self._normalise_payload(payload)

        with self._speaking_lock:
            self._current_speech_id = speech_id
            self._naoqi_task_id = naoqi_task_id

        logger.info("StartSpeaking received - speech_id:", speech_id, "naoqi_task_id:", naoqi_task_id)
        self._set_speaking(True, "(StartSpeaking)")

    def on_stop_speaking(self, event_name, payload):
        speech_id, _ = self._normalise_payload(payload)

        with self._speaking_lock:
            current_speech_id = self._current_speech_id

        if speech_id is not None and current_speech_id is not None and speech_id != current_speech_id:
            logger.debug("Ignoring StopSpeaking for different speech_id:", speech_id, "(current:", current_speech_id, ")")
            return

        with self._speaking_lock:
            self._current_speech_id = None
            self._naoqi_task_id = None

        logger.info("StopSpeaking received - speech_id:", speech_id)
        self._set_speaking(False, "(StopSpeaking)")

    def on_text_started(self, event_name, value):
        # Mirror the simple Haku behavior exactly.
        # Some NAOqi setups emit complementary True/False transitions.
        if value:
            self._set_speaking(True, "(TextStarted=True)")
        else:
            self._set_speaking(False, "(TextStarted=False)")

    def on_speech_finished(self, event_name, value):
        # ALAnimatedSpeech/EndOfAnimatedSpeech fires when speech AND animations complete.
        # This is the authoritative signal that the entire utterance is done.
        # (Compare to TextDone which only indicates speech completion; animations may still run.)
        with self._speaking_lock:
            self._current_speech_id = None
            self._naoqi_task_id = None

        self._set_speaking(False, "(EndOfAnimatedSpeech)")

    def on_text_interrupted(self, event_name, value):
        # Mirror Haku behavior: interruption True => speaking ended.
        if value:
            with self._speaking_lock:
                self._current_speech_id = None
                self._naoqi_task_id = None
            self._set_speaking(False, "(TextInterrupted=True)")

    def on_force_stop(self, event_name, value):
        with self._speaking_lock:
            self._current_speech_id = None
            self._naoqi_task_id = None

        self._set_speaking(False, "(" + str(event_name) + ")")

    def get_speaking_state(self):
        with self._speaking_lock:
            return self._speaking

    def force_speaking_state(self, speaking, reason="manual"):
        self._set_speaking(speaking, "(forced: " + str(reason) + ")")

    def get_status(self):
        with self._speaking_lock:
            return {
                "speaking": self._speaking,
                "current_speech_id": self._current_speech_id,
                "naoqi_task_id": self._naoqi_task_id,
            }
