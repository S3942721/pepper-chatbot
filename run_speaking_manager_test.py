#!/usr/bin/env python
import sys, os
# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Quick runner to test SpeakingStateManager handlers without NAOqi
from module_speaking_manager import SpeakingStateManager

m = SpeakingStateManager('TestMgr')
print('Initial pending:', m.get_status())
# Simulate queue events
m.on_queue_speech(None, {'speech_id':'s1'})
m.on_queue_speech(None, {'speech_id':'s2'})
print('After queueing 2:', m.get_status())
# Simulate dequeue with authoritative queue_size 0
m.on_dequeue_result(None, {'speech_id':'s1','queue_size':0})
print('After authoritative dequeue to 0:', m.get_status())
# Force speaking false
m.force_speaking_state(False)
print('After force speaking false:', m.get_status())
