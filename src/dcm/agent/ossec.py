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
import calendar
import hashlib
import os
import threading
import time
import uuid

import dcm.agent.messaging.alert_msg as alert_msg

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class OssecAlertParser(object):

    def __init__(self, alert_sender, dir_to_watch, w_file):
        self.dir_to_watch = dir_to_watch
        self.w_file = w_file
        self.alert_sender = alert_sender

    def process(self, src_path, latest_processed_time):
        with open(src_path, "r", encoding='utf-8') as infile:
            data = infile.read().splitlines()
            if not data:
                return
            self._parse_data(data, time_to_seek=latest_processed_time)

    def _parse_data(self, data, time_to_seek):
        data_list = data[time_to_seek:]
        alert_time = -1
        subject = ''
        level = -1
        rule = -1
        message = ''
        while data_list:
            try:
                alert_chunk = data_list[0:data_list.index('')+1] #alerts separated by blank lines
            except ValueError:
                alert_chunk = data_list[0:]
            #based on the default format line that starts with 'Alert' is index 2 in alert_chunk
            #so we take the rest and concat as the message
            for mess in alert_chunk[3:]:
                message += ' | ' + mess
            for item in alert_chunk:
                if item.startswith('** Alert'):
                    linelist = item.split(' ')
                    alert_time = linelist[2].strip(':')
                if item.startswith('Rule:'):
                    linelist = item.split(' ')
                    level = linelist[3].strip(')')
                    rule = linelist[1]
                    subject = item[item.index('->')+3:]

            self.alert_sender.send_alert(alert_time, subject, level, rule, message)
            message=''
            try:
                data_list = data_list[data_list.index('')+1:] # get rid of used chunk
            except ValueError:
                data_list = []


class AlertSender(FileSystemEventHandler):

    def __init__(self, conn, db, poll_interval=5.0, dir_to_watch="/opt/dcm-agent-extras/ossec/logs/alerts", w_file="alerts.log"):
        super(FileSystemEventHandler, self).__init__()
        self._conn = conn
        self._db = db
        self._alerts = {}
        self._stopping = None
        self._thread = None
        self._cond = threading.Condition()
        self._poll_interval = poll_interval
        self._last_processed = time.time()
        self.dir_to_watch = dir_to_watch
        self.w_file = w_file
        self.observer = Observer()
        self.parser = OssecAlertParser(self, dir_to_watch, w_file)

    def send_alert(self, alert_time, subject, level, rule, message):
        request_id = str(uuid.uuid4())
        doc = {
            'type': 'ALERT',
            'request_id': request_id,
            'current_timestamp': calendar.timegm(time.gmtime()) * 1000,
            'alert_timestamp': int(float(alert_time) * 1000),
            'level': level,
            'rule': rule,
            'message': message,
            'subject': subject
        }
        alert = alert_msg.AlertAckMsg(doc, self._conn)
        self._alerts[request_id] = alert
        alert.send()

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
        self.observer.stop()
        self.observer.join()
        self._thread.join()

    def start(self):
        if self._thread is not None:
            raise Exception("The alert object has already been started.")
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run)
        self._thread.start()
        self.observer.schedule(AlertSender(dir_to_watch=self.dir_to_watch,
                                                w_file=self.w_file),
                               path=self.dir_to_watch)
        self.observer.start()

    def on_modified(self, event):
        self._process(event)

    def on_created(self, event):
        self._process(event)

    def _process(self, event):
        if event.is_directory:
            return

        if not self.w_file in event.src_path:
            return

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
                    latest_processed_time = self._db.get_latest_alert_time()
                    # ... parse out the file here.
                    self.parser.process(os.path.join(
                        self.dir_to_watch, self.w_file), latest_processed_time)
        finally:
            self._cond.release()
