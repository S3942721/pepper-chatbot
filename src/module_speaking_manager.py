import threading
from naoqi import ALProxy, ALModule
import time
import logger

class SpeakingStateManager(ALModule):
    """
    Centralized manager for Speaking state to prevent race conditions
    and ensure consistent state across all modules
    """
    
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        
        self.memory = ALProxy("ALMemory")
        
        # Declare events that this module will manage
        # self.memory.declareEvent("StartSpeaking")
        # self.memory.declareEvent("StopSpeaking") 
        # self.memory.declareEvent("QueueSpeech")
        # self.memory.declareEvent("DequeueResult")
        
        # Central speaking state
        self._speaking = False
        self._speaking_lock = threading.Lock()
        
        # Queue management
        self._pending_speech_count = 0
        self._current_speech_id = None
        
        # Subscribe to events that affect speaking state
        self.memory.subscribeToEvent("StartSpeaking", self.getName(), "on_start_speaking")
        self.memory.subscribeToEvent("StopSpeaking", self.getName(), "on_stop_speaking")
        self.memory.subscribeToEvent("QueueSpeech", self.getName(), "on_queue_speech")
        self.memory.subscribeToEvent("DequeueResult", self.getName(), "on_dequeue_result")
        self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "on_speech_finished")
        
        logger.info("SpeakingStateManager initialized")

    def __del__(self):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
        try:
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribeToEvent("StartSpeaking", self.getName())
                    self.memory.unsubscribeToEvent("StopSpeaking", self.getName())
                    self.memory.unsubscribeToEvent("QueueSpeech", self.getName())
                    self.memory.unsubscribeToEvent("DequeueResult", self.getName())
                    self.memory.unsubscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from speaking manager events:", e)
                    
        except Exception as e:
            logger.error("Error during SpeakingStateManager cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def on_start_speaking(self, event_name, speech_id):
        """Handle request to start speaking"""
        with self._speaking_lock:
            was_speaking = self._speaking
            self._speaking = True
            self._current_speech_id = speech_id
            
            if not was_speaking:
                # Only raise Speaking event if we weren't already speaking
                self.memory.raiseEvent("Speaking", True)
                logger.info("Speaking state changed to True (speech_id:", speech_id, ")")
            else:
                logger.debug("Already speaking, continuing with new speech (speech_id:", speech_id, ")")

    def on_stop_speaking(self, event_name, speech_id):
        """Handle request to stop speaking"""
        with self._speaking_lock:
            # Only stop if this is the current speech or if no specific ID provided
            if speech_id is None or speech_id == self._current_speech_id:
                was_speaking = self._speaking
                self._speaking = False
                self._current_speech_id = None
                
                if was_speaking:
                    # Only raise Speaking False if we were actually speaking
                    self.memory.raiseEvent("Speaking", False)
                    logger.info("Speaking state changed to False (speech_id:", speech_id, ")")
            else:
                logger.debug("Ignoring stop request for different speech_id:", speech_id, "(current:", self._current_speech_id, ")")

    def on_queue_speech(self, event_name, queue_info):
        """Handle speech being added to queue"""
        with self._speaking_lock:
            self._pending_speech_count += 1
            logger.debug("Speech queued, pending count:", self._pending_speech_count)

    def on_dequeue_result(self, event_name, queue_info):
        """Handle speech being removed from queue"""
        with self._speaking_lock:
            if self._pending_speech_count > 0:
                self._pending_speech_count -= 1
                logger.info("Speech dequeued, pending count:", self._pending_speech_count)
                
                # If no more pending speech and we're not currently speaking, ensure Speaking is False
                if self._pending_speech_count == 0 and not self._speaking:
                    self.memory.raiseEvent("Speaking", False)
                    logger.info("Queue empty and not speaking, ensuring Speaking False")

    def on_speech_finished(self, event_name, value):
        """Handle end of animated speech"""
        with self._speaking_lock:
            # Check if there are pending messages in the queue
            if self._pending_speech_count > 0:
                logger.info("Speech finished but", self._pending_speech_count, "messages pending, keeping Speaking True")
                # Don't change speaking state - let queue worker handle the next message
            else:
                # No pending messages, safe to set Speaking to False
                was_speaking = self._speaking
                self._speaking = False
                self._current_speech_id = None
                
                if was_speaking:
                    self.memory.raiseEvent("Speaking", False)
                    logger.info("Speech finished and queue empty, Speaking state changed to False")

    def get_speaking_state(self):
        """Get current speaking state (thread-safe)"""
        with self._speaking_lock:
            return self._speaking

    def force_speaking_state(self, speaking, reason="manual"):
        """Force speaking state (for emergency situations)"""
        with self._speaking_lock:
            was_speaking = self._speaking
            self._speaking = speaking
            
            if was_speaking != speaking:
                self.memory.raiseEvent("Speaking", speaking)
                logger.info("Speaking state forced to", speaking, "reason:", reason)

    def get_status(self):
        """Get detailed status for debugging"""
        with self._speaking_lock:
            return {
                "speaking": self._speaking,
                "current_speech_id": self._current_speech_id,
                "pending_count": self._pending_speech_count
            }
