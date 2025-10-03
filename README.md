# Pepper Chatbot

A Python 2.7 NAOqi-based social interaction system for Pepper robots, integrating OpenAI-compatible APIs for speech recognition and chat completion with real-time audio streaming and behavior execution.

## Architecture Overview

The system is built using a modular architecture with NAOqi `ALModule` components that communicate via `ALMemory` events:

### Core Modules

- **`start.py`** - Main orchestrator that initializes all modules and handles configuration
- **`module_receiver.py`** - Speech processing pipeline with message queuing, LLM integration, and TTS
- **`module_speechrecognition.py`** - Audio capture with auto-detection and streaming capabilities
- **`module_expressions.py`** - Behavior execution engine using JSON animation definitions
- **`module_socket.py`** - WebSocket client for external system integration and state synchronization
- **`module_audiostream.py`** - GStreamer-based real-time audio streaming to external servers
- **`module_speaking_manager.py`** - Centralized speech state management across modules
- **`module_awareness.py`** - Robot awareness and engagement control

### Message Flow
```
Audio Input → Speech Recognition → LLM Processing → Behavior Sanitization → TTS + Animation
```

## Initial Setup
### 0. Requirements
- Robot is powered on and connected and your device is connected to the same network as it
- You have a system that supports ssh connections

### 1. Install rsync (if running on UNIX machine)
- 
Update package lists.
```bash
    sudo apt update
```
install rsync.
```bash
    sudo apt install rsync
```
On Linux (Red Hat/CentOS/AlmaLinux-based systems):
Update system packages.
```bash
    sudo dnf update -y
```
install rsync.
```bash
    sudo dnf install rsync -y
```

### 2. SSH Key Setup
You need to set up your ssh config to connect to the robot easily without authentication.

This will prompt you to generate new keys for the robot if you don't already have them.
```bash
./haku_sync --setup <IP ADDRESS OF THE ROBOT>
# Default password is 'nao' unless changed
# To get the IP address of the robot, press the chest button once, and it will read it to you
```
### 3. Sync code to Haku
If the IP address has not changed since you last synced:
```bash
./haku_sync
```

If the IP address has changed:
```bash
./haku_sync <IP ADDRESS OF THE ROBOT>
```

### 4. SSH Connection to Pepper (Haku)
If you have completed the ssh config setup:
```bash
ssh haku
```
Otherwise:
```bash
ssh nao@<pepper-ip-address>
# Default password is 'nao' unless changed
```

### 5. Start the System
```bash
python src/start.py \
  --web-controller-url "<The IP of the device running web-controller>" \
  --log-level INFO
```

### Example Full Startup Command
```bash
python src/start.py \
  --url "http://192.168.1.100:8080/v1" \
  --web-controller-url "http://192.168.1.100:3000" \
  --socket-url "192.168.1.100" \
  --socket-port "3456" \
  --audio-stream-url "192.168.1.100" \
  --audio-stream-port "5004" \
  --webview "http://198.18.0.1:3000/tablet?robot=Haku" \
  --save-csv \
  --log-level DEBUG \
  --log-filter "+module_receiver:+module_socket"
```

## Configuration Options

### Environment Variables (`.env` file)
```bash
NAO_IP=localhost
NAO_PORT=9559
DEFAULT_SOCKET_URL=192.168.1.101
DEFAULT_SOCKET_PORT=3456
DEFAULT_AUDIO_STREAM_URL=192.168.1.101
DEFAULT_AUDIO_STREAM_PORT=5004
WEBVIEW=http://198.18.0.1:3000/tablet?robot=Haku
```

### Key Command Line Options
- `--url`: Base URL for OpenAI-compatible LLM server
- `--web-controller-url`: Base URL that sets both socket and audio streaming if not overridden
- `--socket-url/--socket-port`: WebSocket server for external control
- `--audio-stream-url/--audio-stream-port`: Audio streaming destination
- `--webview`: URL loaded on Pepper's tablet
- `--save-csv`: Save conversation logs to `dialogue.csv`
- `--log-level`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `--log-filter`: Target specific modules (e.g., `+module_receiver`)

## Behavior System

The system uses embedded behavior syntax in LLM responses:
- `^start(animation)` - Start animation while speaking
- `^run(animation)` - Run animation to completion, pause speech
- `^wait(animation)` - Wait for animation to complete
- `^stop(animation)` - Stop running animation

Example: `"Hello! ^start(hey) Nice to meet you. ^wait(hey)"`

Available animations are defined in `src/robot_behaviours_described.json`.  
## System Output

The terminal displays structured output:
```
Speech Recognition Result:
================================
hi how are you
================================

AI Inference Result:
================================
Hello! ^start(hey) Nice to meet you. ^wait(hey)
================================
```

Conversations can be logged to CSV format with `--save-csv` flag.
## Module Details

### Speech Recognition (`module_speechrecognition.py`)
- Captures audio at 48kHz from Pepper's microphones
- Converts to 16-bit PCM WAV format
- Sends HTTP POST requests to speech recognition endpoint
- Supports auto-detection thresholds and streaming modes

### Speech Processing (`module_receiver.py`)
- Message queue system for handling multiple speech requests
- Integrates with OpenAI-compatible LLM APIs
- Sanitizes responses to extract and embed behavior commands
- Manages TTS output with behavior synchronization

### Behavior Execution (`module_expressions.py`)
- Loads animation definitions from JSON configuration
- Parses behavior syntax from LLM responses
- Controls robot animations, LED patterns, and audio
- Manages speech speed and pause timing

### Socket Integration (`module_socket.py`)
- WebSocket client for external system communication
- Synchronizes robot state (speaking, listening, behaviors)
- Reports status and receives control commands

### Audio Streaming (`module_audiostream.py`)
- GStreamer pipeline for real-time audio transmission
- Streams processed audio to external servers
- Handles network resilience and reconnection

### Logging System (`logger.py`)
- Custom logging with qi.logging integration
- Line number tracking and module filtering
- Supports different verbosity levels and targeted debugging

## Event System

Inter-module communication uses ALMemory events:
- `Speaking`/`StopSpeaking` - Speech state management
- `Say`/`JSONSay` - Text-to-speech requests
- `ControlRecording` - Audio capture control
- `RunningBehaviour` - Animation state tracking
- `EyeContact` - Human interaction detection
## Troubleshooting

### Common Issues

**Audio Issues**:
- Check microphone permissions and volume settings
- Verify GStreamer installation for audio streaming
- Ensure network connectivity to streaming endpoints

**Connection Problems**:
- Confirm Pepper's IP address and NAOqi port (9559)
- Test LLM server connectivity from Pepper's network
- Check firewall settings for socket and streaming ports

**Module Failures**:
- Use `--log-level DEBUG --log-filter "+module_name"` for targeted debugging
- Check ALProxy initialization in module `__init__` methods
- Verify event subscriptions in ALMemory

### Debugging Commands
```bash
# Detailed logging for specific module
python src/start.py --log-level DEBUG --log-filter "+module_receiver"

# Test connectivity without full startup
python -c "from naoqi import ALProxy; print(ALProxy('ALMemory').getData('RobotConfig/Head/BaseYaw'))"

# Run commands on the robot with qicli
qicli call ALTabletService.showWebview "http://www.google.com/"

# Check audio device status
python -c "from naoqi import ALProxy; audio=ALProxy('ALAudioDevice'); print(audio.getOutputVolume())"
```
## Development

### Key Files
- `src/start.py` - Main entry point and module initialization
- `src/system-prompt.txt` - LLM system prompt with behavior syntax rules
- `src/robot_behaviours_described.json` - Animation definitions and descriptions
- `src/logger.py` - Custom logging system with line number tracking

### Module Development Pattern
All modules follow the NAOqi ALModule pattern:
```python
class MyModule(ALModule):
    def __init__(self, name, ip, port):
        ALModule.__init__(self, name)
        self.BIND_PYTHON(self.getName(), "callback")
        
        # Pre-create proxies to avoid threading issues
        self.memory = ALProxy("ALMemory", ip, port)
        self.memory.subscribeToEvent("EventName", self.getName(), "callback_method")
    
    def __del__(self):
        # Graceful cleanup - unsubscribe events, stop threads
        try:
            self.memory.unsubscribe("EventName", self.getName())
        except Exception as e:
            logger.warning("Cleanup warning:", e)
```

### Event Communication
Inter-module communication uses ALMemory events:
```python
# Raise an event
self.memory.raiseEvent("Say", "Hello world")

# Subscribe to events
self.memory.subscribeToEvent("Speaking", self.getName(), "on_speaking")
```

### Adding New Behaviors
1. Add animation definitions to `robot_behaviours_described.json`
2. Update system prompt with new behavior keywords
3. Test behavior execution through LLM responses

## Requirements
- Python 2.7 (NAOqi requirement)
- NAOqi SDK installed on Pepper
- Network connectivity for LLM and streaming services
- Optional: GStreamer for audio streaming