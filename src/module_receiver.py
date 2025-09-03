import re
from naoqi import ALModule, ALProxy
import time
import json
import threading
import random
import Queue  # Python 2.7 queue module
import logger

class BaseSpeechReceiverModule(ALModule):
    """
    Speech processing module that handles incoming text messages,
    sanitizes them with behaviours/expressions, and speaks them via TTS.
    Acts as a speech box - no LLM or speech recognition functionality.
    """

    def __init__( 
            self, strModuleName, strNaoIp, port, 
            server_url=None, base_route=None, api_key=None, 
            model_name=None, save_csv=False, system_prompt='', behaviours_file='behaviours_described.json', sounds_file='sounds_described.json',
            expressions=None, early_speaking_finish=True
        ):
        
        ALModule.__init__(self, strModuleName )
        self.BIND_PYTHON( self.getName(),"callback" )

        # Add shutdown flag
        self.shutting_down = False

        self.SAY_SIGNAL = "Say"
        self.JSON_SAY_SIGNAL = "JSONSay"

        self.port = port
        self.strNaoIp = strNaoIp
        
        self.expressions = expressions
        self.early_speaking_finish = early_speaking_finish

        # Message queue system initialisation
        self.message_queue = Queue.Queue()
        self.queue_worker_thread = None
        self.queue_running = False
        self.queue_lock = threading.Lock()
        self.speech_counter = 0  # Counter for unique speech IDs
        
        # Speaking state management
        self.is_currently_speaking = False
        self.speech_finished_event = threading.Event()

        self.speech = ALProxy('ALAnimatedSpeech')
        self.led_service = ALProxy('ALLeds')
        self.memory = ALProxy("ALMemory", self.strNaoIp, self.port)
        self.memory.subscribeToEvent("Speaking", self.getName(), "handle_speaking")
        self.memory.subscribeToEvent("StopSpeech", self.getName(), "stop_speech")
        self.memory.subscribeToEvent("StopAction", self.getName(), "stop_all")
        self.memory.subscribeToEvent("StopBehaviour", self.getName(), "stop_behaviour")
        self.memory.subscribeToEvent("StopAudio", self.getName(), "stop_audio")
        self.memory.subscribeToEvent("ALAnimatedSpeech/EndOfAnimatedSpeech", self.getName(), "finished_speaking")

        # Simple conversation state tracking (optional)
        self.conversation_ongoing = False

        logger.debug("Speech processing module initialized")

        # Start the queue worker thread
        self.start_queue_worker()

    # __init__ - end
    def __del__( self ):
        """Enhanced destructor that handles all cleanup gracefully"""
        logger.info("cleaning everything")
        
        # Set shutdown flag to prevent new message processing
        self.shutting_down = True
        
        try:
            # Stop the queue worker first
            if hasattr(self, 'queue_running'):
                self.queue_running = False
                if hasattr(self, 'queue_worker_thread') and self.queue_worker_thread and self.queue_worker_thread.is_alive():
                    try:
                        # Add stop signal to wake up the queue
                        if hasattr(self, 'message_queue'):
                            self.message_queue.put({"type": "STOP_WORKER"})
                        self.queue_worker_thread.join(timeout=3)
                    except:
                        pass
            
            # Unsubscribe from events if memory is still available
            if hasattr(self, 'memory'):
                try:
                    self.memory.unsubscribe('Say', self.getName())
                    self.memory.unsubscribe('JSONSay', self.getName())
                    self.memory.unsubscribe('SayChunk', self.getName())
                    self.memory.unsubscribe('Speaking', self.getName())
                    self.memory.unsubscribe('StopAction', self.getName())
                    self.memory.unsubscribe('StopSpeech', self.getName())
                    self.memory.unsubscribe('StopBehaviour', self.getName())
                    self.memory.unsubscribe('StopAudio', self.getName())
                    self.memory.unsubscribe('ALAnimatedSpeech/EndOfAnimatedSpeech', self.getName())
                except Exception as e:
                    logger.warning("Could not unsubscribe from receiver events:", e)
                    
        except Exception as e:
            logger.error("Error during ReceiverModule cleanup:", e)
        finally:
            logger.info("cleaned up!")

    def finished_speaking(self, _, value):
        logger.debug("Speech finished event received")
        
        # Signal that speech has finished
        self.is_currently_speaking = False
        self.speech_finished_event.set()

        # Don't raise Speaking events directly - let speaking manager handle it
        logger.debug("Speech finished, letting speaking manager handle Speaking state")

    def stop_speech(self, _, value):
        logger.debug("Stop speech event received")
        threading.Thread(target=self._stop_speech, args=(_, value)).start()

    def _stop_speech(self, _, value):
        tts = ALProxy("ALTextToSpeech")
        tts.stopAll()

    def stop_behaviour(self, _, value):
        logger.debug("Stop behaviour event received")
        threading.Thread(target=self._stop_behaviour, args=(_, value)).start()

    def _stop_behaviour(self, _, value):
        self.memory.raiseEvent("RunningBehaviour", False)
        bhv_manager = ALProxy("ALBehaviorManager")
        bhv_manager.stopAllBehaviors()

    def stop_audio(self, _, value):
        logger.debug("Stop audio event received")
        threading.Thread(target=self._stop_audio, args=(_, value)).start()

    def _stop_audio(self, _, value):
        self.memory.raiseEvent("RunningBehaviour", False)
        audio_player = ALProxy("ALAudioPlayer")
        audio_player.stopAll()

    def stop_all(self, _, value):
        """Stop current speech/behaviours but do NOT clear pending queued messages."""
        logger.debug("Stop all event received - stopping speech and behaviours (queue preserved)")

        # Stop current speech only (allow pending queued messages to be processed)
        self.stop_current_speech()

        # Original stop all functionality (stop display/behaviours/audio)
        self.finished_speaking(_, value)
        self.stop_speech(_, value)
        self.stop_behaviour(_, value)
        self.stop_audio(_, value)

    def start( self ):
        self.memory.subscribeToEvent("Say", self.getName(), "processRemote")
        self.memory.subscribeToEvent("JSONSay", self.getName(), "processRemote")
        self.memory.subscribeToEvent("SayChunk", self.getName(), "processRemote")
        logger.info("started!")

    def stop( self ):
        """Enhanced stop to shutdown queue worker"""
        logger.info("stopping...")
        try:
            # Stop the queue worker
            self.stop_queue_worker()
            
            # Original stop functionality
            self.memory.unsubscribe('Say', self.getName())
            self.memory.unsubscribe('JSONSay', self.getName())
            self.memory.unsubscribe('SayChunk', self.getName())
        finally:
            logger.info("stopped!")

    def handle_speaking(self, _, speaking):
        # Handle speaking state changes from centralized speaking manager
        logger.debug("Speaking event received:", speaking)

    def start_queue_worker(self):
        """Start the message queue worker thread"""
        if not self.queue_running:
            self.queue_running = True
            self.queue_worker_thread = threading.Thread(target=self.process_message_queue)
            self.queue_worker_thread.daemon = True
            self.queue_worker_thread.start()
            logger.debug("Message queue worker started")

    def stop_queue_worker(self):
        """Stop the message queue worker thread"""
        self.queue_running = False
        if self.queue_worker_thread and self.queue_worker_thread.is_alive():
            # Add a special stop message to wake up the queue
            self.message_queue.put({"type": "STOP_WORKER"})
            self.queue_worker_thread.join(timeout=5)
            logger.debug("Message queue worker stopped")

    def process_message_queue(self):
        """Worker thread to process messages from the queue"""
        logger.debug("Queue worker thread started")
        
        while self.queue_running:
            try:
                # Get message from queue with timeout
                message_item = self.message_queue.get(timeout=1)
                
                # Check for stop signal
                if message_item.get("type") == "STOP_WORKER":
                    break
                
                # Process the message
                self.process_queued_message(message_item)
                
                # Mark task as done
                self.message_queue.task_done()
                
            except Queue.Empty:
                # Timeout occurred, continue loop
                continue
            except Exception as e:
                logger.error("Queue worker error:", e)
                
        logger.debug("Queue worker thread ended")

    def process_queued_message(self, message_item):
        """Process a single message from the queue"""
        try:
            signal_name = message_item["signal"]
            message_text = message_item["message_text"]
            speech_id = message_item["speech_id"]
            
            logger.debug("Processing queued message - Signal:", signal_name, "Speech ID:", speech_id)
            
            # Notify speaking manager about queue activity
            self.memory.raiseEvent("DequeueResult", {"speech_id": speech_id})
            
            # Stop any current speech before starting new one
            if self.is_currently_speaking:
                logger.debug("Stopping current speech for new message")
                self.stop_current_speech()
            
            # Process the text message
            self.process_text_message(message_text, speech_id)
                
        except Exception as e:
            logger.error("Error processing queued message:", e)

    def stop_current_speech(self):
        """Stop current speech without triggering global StopAction (preserve queue)."""
        try:
            if self.is_currently_speaking:
                # Stop animated speech / tts directly
                try:
                    tts = ALProxy("ALTextToSpeech")
                    tts.stopAll()
                except Exception:
                    pass
                try:
                    self.speech.stopAll()
                except Exception:
                    pass

                # Signal running behaviour stopped
                try:
                    self.memory.raiseEvent("RunningBehaviour", False)
                except Exception:
                    pass

                # Wait for ALAnimatedSpeech end event (with timeout)
                self.speech_finished_event.wait(timeout=2)
                self.speech_finished_event.clear()

                # Update state
                self.is_currently_speaking = False
                logger.debug("Current speech stopped (direct stop)")
        except Exception as e:
            logger.error("Error stopping current speech:", e)

    def extract_text_from_message(self, signal_name, raw_message):
        """Extract plain text from various message formats"""
        if raw_message is None:
            return ""
        
        # Convert to string
        message_str = str(raw_message).strip()
        
        if not message_str:
            return ""
        
        # Handle JSONSay format - extract chat_response from JSON
        if signal_name == self.JSON_SAY_SIGNAL:
            try:
                # Try to parse as JSON
                if message_str.startswith('{') and message_str.endswith('}'):
                    message_dict = json.loads(message_str)
                    text = message_dict.get('chat_response', message_str)
                    logger.debug("Extracted text from JSON:", text)
                    return text
                else:
                    # Not valid JSON, treat as plain text
                    logger.debug("JSONSay message not valid JSON, treating as plain text")
                    return message_str
            except (ValueError, json.JSONDecodeError) as e:
                logger.debug("Failed to parse JSONSay as JSON:", e, "treating as plain text")
                return message_str
        
        # For Say and SayChunk, return as-is
        return message_str

    def processRemote(self, signalName, message):
        """Add messages to queue for processing"""
        # Don't process new messages during shutdown
        if getattr(self, 'shutting_down', False):
            return

        logger.debug("Received from:", signalName)
        logger.debug("Received message:", message)

        if message is None:
            logger.debug("Received message is None. Ignoring.")
            return

        # Extract plain text from the message
        message_text = self.extract_text_from_message(signalName, message)
        
        if not message_text:
            logger.debug("No text content found in message. Ignoring.")
            return

        # Pre-sanitise the text if expressions module is available
        if self.expressions:
            try:
                sanitised_text, behaviour_triggered, spoken_response = self.expressions.sanitise_request(message_text)
                logger.debug("Pre-sanitised message from", message_text, "to", sanitised_text)
                message_text = sanitised_text
            except Exception as e:
                logger.warning("Failed to pre-sanitise message:", e, "using original text")

        # Check for message aggregation opportunity
        with self.queue_lock:
            queue_size = self.message_queue.qsize()
            
            # If there are 2 or more messages in queue, aggregate with the last message
            if queue_size >= 2:
                # Convert queue to list to access items
                queue_items = []
                
                # Extract all items from queue safely
                while not self.message_queue.empty():
                    try:
                        item = self.message_queue.get_nowait()
                        self.message_queue.task_done()  # Mark as done since we're removing it
                        queue_items.append(item)
                    except Queue.Empty:
                        break
                
                # Aggregate with the last item (most recent in queue)
                if queue_items:
                    last_item = queue_items[-1]
                    
                    # Check if the last message needs punctuation
                    last_text = last_item["message_text"].strip()
                    needs_punctuation = last_text and not last_text.endswith(('.', '!', '?', ';', ':'))
                    
                    # Combine the message text with proper punctuation
                    if needs_punctuation:
                        combined_text = last_item["message_text"] + ". " + message_text
                    else:
                        combined_text = last_item["message_text"] + " " + message_text
                    
                    last_item["message_text"] = combined_text
                    logger.info("Aggregated message: '{}' + '{}' -> '{}'".format(
                        last_text, 
                        message_text, 
                        combined_text
                    ))
                
                # Put all items back in queue
                for item in queue_items:
                    self.message_queue.put(item)
                
                # Don't add the new message as it's been aggregated
                # Don't notify speaking manager since we didn't add a new message
                logger.debug("Message aggregated, not adding to queue")
                return

        # No aggregation - proceed with normal message queuing
        # Generate unique speech ID
        self.speech_counter += 1
        speech_id = "speech_{}".format(self.speech_counter)
        
        # Create message item for queue
        message_item = {
            "signal": signalName,
            "message_text": message_text,
            "speech_id": speech_id,
            "timestamp": time.time()
        }
        
        # Notify speaking manager about queue activity
        self.memory.raiseEvent("QueueSpeech", {"speech_id": speech_id})
        
        # Add to queue
        try:
            self.message_queue.put(message_item, timeout=1)
            logger.debug("Message added to queue - Speech ID:", speech_id, "Queue size:", self.message_queue.qsize())
        except Queue.Full:
            logger.error("Message queue is full, dropping message")

    def process_text_message(self, message_text, speech_id):
        """Process a text message for speech output"""
        try:
            # Check if early speaking finish is enabled and if this message has a trailing ^run
            if self.early_speaking_finish and speech_id:
                # Check if there are any pending messages in the queue (this should be the last one)
                with self.queue_lock:
                    queue_empty = self.message_queue.empty()
                
                if queue_empty:
                    # This is the final message, check for trailing ^run behavior
                    message_text = self.add_early_speaking_finish(message_text, speech_id)

            # Strip brace segments (e.g. { ... }) from what will be spoken
            cleaned_text = self._strip_brace_segments(message_text)
            
            if not cleaned_text.strip():
                logger.debug("Response empty after cleaning. Skipping speech.")
                return
            
            logger.info("Speech Output:\n================================\n", cleaned_text, "\n================================\n")
            
            # Mark speaking state and notify speaking manager BEFORE speaking
            if not self.is_currently_speaking:
                self.is_currently_speaking = True
                
                # Notify speaking manager
                self.memory.raiseEvent("StartSpeaking", speech_id)
                logger.debug("Notified speaking manager to start speaking")
            else:
                logger.debug("Already speaking, not toggling Speaking event")

            # Set running behaviour flag
            self.memory.raiseEvent("RunningBehaviour", True)

            # Execute the speech
            self.speech.say(cleaned_text)

        except Exception as e:
            logger.error("Error processing text message:", e)
            # Ensure we notify speaking manager on error
            if speech_id:
                self.memory.raiseEvent("StopSpeaking", speech_id)

    def add_early_speaking_finish(self, message_text, speech_id):
        """Add $StopSpeaking event before trailing ^run(...) behaviors"""
        try:
            # Pattern to match trailing ^run(...) at the end of the message
            # This regex looks for ^run(...) that appears at the end, possibly followed by whitespace and braces
            import re
            
            # Match ^run(...) followed only by optional whitespace and brace segments
            trailing_run_pattern = r'(\^run\([^)]+\))(\s*\{[^}]*\})*\s*$'
            
            match = re.search(trailing_run_pattern, message_text)
            
            if match:
                # Found a trailing ^run behavior
                run_behavior = match.group(0)  # The entire matched trailing section
                
                # Find the position where the trailing ^run starts
                run_start = match.start()
                
                # Split the message into before and after the trailing ^run
                before_run = message_text[:run_start]
                
                # Insert $StopSpeaking event before the trailing ^run
                stop_speaking_event = "$StopSpeaking={}".format(speech_id)
                
                # Reconstruct the message with the event inserted
                modified_message = before_run + " " + stop_speaking_event + " " + run_behavior
                
                logger.info("Added early speaking finish event before trailing ^run behavior")
                logger.debug("Original:", message_text)
                logger.debug("Modified:", modified_message)
                
                return modified_message
            
            # No trailing ^run found, return original message
            return message_text
            
        except Exception as e:
            logger.error("Error adding early speaking finish:", e)
            return message_text

    def _strip_brace_segments(self, text):
        """Remove any { ... } segments (and leading whitespace before them), then collapse extra spaces"""
        cleaned = re.sub(r'\s*\{[^}]*\}', '', text)
        cleaned = re.sub(r' +', ' ', cleaned).strip()
        return cleaned

    def clear_message_queue(self):
        """Clear all pending messages from the queue"""
        with self.queue_lock:
            # Clear the queue and mark all tasks as done
            while not self.message_queue.empty():
                try:
                    self.message_queue.get_nowait()
                    self.message_queue.task_done()
                except Queue.Empty:
                    break

            logger.debug("Message queue cleared")
