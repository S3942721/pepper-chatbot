# Pepper Chatbot AI Instructions

This is a Python 2.7 NAOqi-based application for Pepper robot social interaction, using OpenAI-compatible APIs for speech recognition and chat completion.

## Architecture Overview

**Core Module Pattern**: All functionality is implemented as NAOqi `ALModule` subclasses with standardized lifecycle:
- `__init__()`: Setup with `ALModule.__init__()`, `BIND_PYTHON()`, create proxies, subscribe to events
- `__del__()`: Graceful cleanup - unsubscribe events, stop threads, handle proxy cleanup failures
- Event-driven communication via `ALMemory` events between modules

**Key Components**:
- `start.py`: Main orchestrator, initializes all modules and handles command-line configuration
- `module_receiver.py`: Speech processing pipeline with message queuing and sanitization
- `module_speechrecognition.py`: Audio capture with auto-detection and streaming capabilities  
- `module_expressions.py`: Behavior execution engine using JSON behavior definitions
- `module_socket.py`: WebSocket client for external system integration
- `module_audiostream.py`: GStreamer-based real-time audio streaming

## Critical Patterns

**Message Flow**: Socket Input → Sanitization → TTS with behavior triggers
```python
# Behavior embedding in responses using ^start(), ^run(), ^wait() syntax
message = "Hello! ^start(hey) Nice to meet you. ^wait(hey)"
```

**Event System**: All inter-module communication uses ALMemory events. Key events:
- `Speaking`/`StopSpeaking`: Speech state management
- `Say`/`JSONSay`: Text-to-speech requests  
- `ControlRecording`: Enable/disable audio capture
- `RunningBehaviour`: Animation state tracking

**Proxy Management**: Pre-create ALProxy instances in `__init__()` to avoid thread spawn issues during cleanup:
```python
self.tts_proxy = ALProxy("ALTextToSpeech", self.strNaoIp, self.port)
```

## Development Workflow

**Running**: `python src/start.py --url "http://server/v1" --save-csv`

**Key Files**:
- `src/robot_behaviours_described.json`: Animation definitions with descriptions
- `src/system-prompt.txt`: LLM system prompt with behavior syntax and conversation rules
- `src/logger.py`: Custom logging with qi.logging integration and line number tracking

**Behavior System**: JSON-defined animations triggered by keywords in LLM responses. Use `sanitise_request()` to process text and extract behaviors.

**Audio Pipeline**: 48kHz capture → 16-bit PCM → WAV conversion → HTTP POST to speech recognition endpoint

## Configuration

Environment variables in `.env` or command-line flags control:
- `NAO_IP`/`NAO_PORT`: Robot connection
- `URL`: OpenAI-compatible server base URL
- `API_KEY`: Authentication for external services
- Volume, recording thresholds, socket endpoints

**Logging**: Use `--log-level DEBUG` and `--log-filter "+module_name"` for targeted debugging.

## Common Patterns

**Thread Safety**: Use threading for HTTP calls, but avoid concurrent ALProxy creation. Always handle exceptions in worker threads.

**Error Handling**: Graceful degradation - modules continue operating even if dependencies fail. Use try/except around all ALProxy calls.

**State Management**: Track robot state (speaking, listening, awareness) across modules using shared ALMemory events.