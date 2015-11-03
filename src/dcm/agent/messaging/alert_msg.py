#
#  Copyright (C) 2014 Dell, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import threading

import dcm.agent.utils as utils
import dcm.agent.events.state_machine as state_machine

from dcm.agent.events.globals import global_space as dcm_events


class States:
    NEW = "NEW"
    WAITING_FOR_ACK = "WAITING_FOR_ACK"
    COMPLETE = "COMPLETE"


class Events:
    TIMEOUT = "TIMEOUT"
    SEND = "SEND"
    ACK_RECEIVED = "ACK_RECEIVED"
    STOP = "STOP"


class AlertAckMsg(object):

    def __init__(self, doc, conn, timeout=5.0):
        self._timeout = timeout
        self.doc = doc
        self._sm = state_machine.StateMachine(States.NEW)
        self.setup_states()
        self._timer = None
        self._lock = threading.RLock()
        self._conn = conn

    @utils.class_method_sync
    def incoming_message(self):
        self._sm.event_occurred(Events.ACK_RECEIVED)

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()

    @utils.class_method_sync
    def timeout(self):
        self._sm.event_occurred(Events.TIMEOUT)

    @utils.class_method_sync
    def send(self):
        self._sm.event_occurred(Events.SEND)

    @utils.class_method_sync
    def stop(self):
        self._sm.event_occurred(Events.STOP)

    def _send_timeout(self):
        self._timer = dcm_events.register_callback(
            self.timeout, delay=self._timeout)
        self._conn.send(self.doc)

    def _sm_send_message(self):
        self._send_timeout()

    def _sm_ack_received(self):
        # the timer must be active
        dcm_events.cancel_callback(self._timer)
        self._timer = None

    def _sm_resend_message(self):
        self._send_timeout()

    def _sm_stopping_early(self):
        dcm_events.cancel_callback(self._timer)
        self._timer = None

    def setup_states(self):
        self._sm.add_transition(States.NEW,
                                Events.SEND,
                                States.WAITING_FOR_ACK,
                                self._sm_send_message)
        self._sm.add_transition(States.NEW,
                                Events.STOP,
                                States.COMPLETE,
                                None)

        self._sm.add_transition(States.WAITING_FOR_ACK,
                                Events.TIMEOUT,
                                States.WAITING_FOR_ACK,
                                self._sm_resend_message)
        self._sm.add_transition(States.WAITING_FOR_ACK,
                                Events.ACK_RECEIVED,
                                States.COMPLETE,
                                self._sm_ack_received)
        self._sm.add_transition(States.WAITING_FOR_ACK,
                                Events.STOP,
                                States.COMPLETE,
                                self._sm_stopping_early)

        self._sm.add_transition(States.COMPLETE,
                                Events.ACK_RECEIVED,
                                States.COMPLETE,
                                None)
        self._sm.add_transition(States.COMPLETE,
                                Events.TIMEOUT,
                                States.COMPLETE,
                                None)
        self._sm.add_transition(States.COMPLETE,
                                Events.STOP,
                                States.COMPLETE,
                                None)


