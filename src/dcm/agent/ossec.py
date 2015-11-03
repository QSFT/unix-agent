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

from dcm.agent.messaging import persistence
from dcm.agent.messaging import alert_msg
from dcm.agent import config

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class OssecAlertParser(FileSystemEventHandler):

    def __init__(self, dir_to_watch="/opt/dcm-agent-extras/ossec/logs/alerts", w_file="alert.log"):
        super(FileSystemEventHandler, self).__init__()
        self.dir_to_watch = dir_to_watch
        self.w_file = w_file
        self.observer = Observer()
        config_files = config.get_config_files()
        conf = config.AgentConfig(config_files)
        self.db = persistence.SQLiteAgentDB(conf.storage_dbfile)
        self.alert_sender = alert_msg.AlertSender(self.db._db_conn, self.db)

    def start(self):
        """
        Start the watchdog observer
        """
        self.observer.schedule(OssecAlertParser(dir_to_watch=self.dir_to_watch, w_file=self.w_file),
                               path=self.dir_to_watch)
        self.observer.start()
        self.observer.join()

    def stop(self):
        """"
        Stop the watchdog observer
        """
        self.observer.stop()

    def on_modified(self, event):
        self.process(event)

    def on_created(self, event):
        self.process(event)

    def process(self, event):
        if event.is_directory:
            return

        if not self.w_file in event.src_path:
            return

        with open(event.src_path, "r", encoding='utf-8') as infile:
            data = infile.read().splitlines()
            if not data:
                return
            self._parse_data(data, time_to_seek=0)

    def _parse_data(self, data, time_to_seek):
        data_list = data[time_to_seek:]
        while data_list:
            alert_chunk = data_list[0:data_list.index('')+1] #alerts separated by blank lines
            for item in alert_chunk:
                if item.startswith('** Alert'):
                    linelist = item.split(' ')
                    alert_time = linelist[2].strip(':')
                if item.startswith('Rule:'):
                    linelist = item.split(' ')
                    level = linelist[3].strip(')')
                    rule = linelist[1]
                    subject = item[item.index('->')+3:]
                #based on the default format line that starts with 'Alert' is index 2 in alert_chunk
                #so we take the rest and concat as the message
                message = ''
                for mess in alert_chunk[3:]:
                    message += ' | ' + mess
                self.alert_sender.send_alert(alert_time, subject, level, rule, message)
            data_list = data_list[data_list.index('')+1:] # get rid of used chunk
