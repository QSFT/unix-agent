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
import calendar
import datetime
import hashlib
import threading
import time
import uuid

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


class AlertSender(object):

    def __init__(self, conn, db, poll_interval=5.0):
        self._conn = conn
        self._db = db
        self._alerts = {}
        self._stopping = None
        self._thread = None
        self._cond = threading.Condition()
        self._poll_interval = poll_interval
        self._last_processed = time.time()

    def send_alert(self, alert_time, subject, level, rule, message):
        request_id = str(uuid.uuid4())
        doc = {
            'type': 'ALERT',
            'request_id': request_id,
            'current_timestamp': calendar.timegm(datetime.time.gmtime()) * 1000,
            'alert_timestamp': int(alert_time * 1000),
            'level': level,
            'rule': rule,
            'message': message,
            'subject': subject
        }
        alert_msg = AlertAckMsg(doc, self._conn)
        self._alerts[request_id] = alert_msg
        alert_msg.send()

    def incoming_message(self, incoming_doc):
        request_id = incoming_doc['request_id']
        alert = self._out_standing_alerts[request_id]
        alert.incoming_message()

        h = hashlib.sha256()
        h.update(str(alert.doc['alert_timestamp']))
        h.update(alert.doc['subject'])
        h.update(alert.doc['message'])
        alert_hash = h.hexdigest()
        self._db.add_alert(alert.doc['alert_timestamp'],
                           alert.doc['current_timestamp'],
                           alert_hash,
                           alert.doc['level'],
                           alert.doc['rule'],
                           alert.doc['subject'],
                           alert.doc['message'])
        del self._out_standing_alerts[request_id]

    def stop(self):
        self._cond.acquire()
        try:
            self._stopping.set()
            self.cond.notify()
        finally:
            self._cond.release()

    def start(self):
        if self._thread is not None:
            raise Exception("The alert object has already been started.")
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def signal_alert(self):
        self._cond.acquire()
        try:
            self.cond.notify()
        finally:
            self._cond.release()

    def _run(self):
        timeout = self._poll_interval
        self._cond.acquire()
        try:
            while not self._stopping.is_set():
                # do work here
                self.cond.wait(timeout=timeout)
                time_now = time.time()
                time_diff = time_now - self._last_processed
                if  time_diff < self._poll_interval:
                    timeout = self._poll_interval - time_diff
                else:
                    self._last_processed = time_now
                    timeout = None
                    # ... parse out the file here.
        finally:
            self._cond.release()