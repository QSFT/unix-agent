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

from collections import namedtuple
import json
import time
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

OssecAlert = namedtuple('OssecAlert', 'alert_time alert_hash level rule message')

class OssecAlertParser(FileSystemEventHandler):

    def __init__(self, dir_to_watch="/opt/dcm-agent-extras/ossec/logs/alerts"):
        super(FileSystemEventHandler, self).__init__()
        self.dir_to_watch = dir_to_watch

    def start(self):
        """
        Start the watchdog observer
        """
        observer = Observer()
        observer.schedule(OssecAlertParser(dir_to_watch=self.dir_to_watch), path=self.dir_to_watch)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    def stop(self):
        """"
        Stop the watchdog observer
        """

    def process(self, event):
        if event.is_directory:
            return

        if not "alert.log" in event.src_path:
            return
        with open(event.src_path, "r") as infile:
            data = infile.read()
            if not data:
                return
            return self._parse_data(data)

    def on_modified(self, event):
        self.process(event)

    def on_created(self, event):
        self.process(event)

    def _build_response(self, d):
        alert_time = d['message']
        m = hashlib.md5()
        m.update(d)
        alert_hash = m.digest()
        level = d['crit']
        rule = d['classification']
        message = d['message']
        return alert_time, alert_hash, level, rule, message

    def _parse_data(self, data):
        start = data.find("{")
        while start >= 0:
            end = data.find("}")
            jdoc = data[start, end+1]
            d = json.loads(jdoc)
            alert_res = self._build_response(d)
            alert_tuple = OssecAlert(alert_res[0],
                                     alert_res[1],
                                     alert_res[2],
                                     alert_res[3],
                                     alert_res[4])
            return alert_tuple
