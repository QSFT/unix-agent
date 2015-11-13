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
import datetime
import json
import logging
import os
import sqlite3
import threading

import dcm.agent.exceptions as exceptions
import dcm.agent.messaging.states as messaging_states
import dcm.agent.utils as agent_utils


_g_logger = logging.getLogger(__name__)


_g_sqllite_ddl = """
create table if not exists requests (
    request_id        TEXT primary key not null,
    creation_time     date,
    request_doc       text,
    reply_doc         text,
    state             string,
    agent_id          string,
    last_update_time  date
);

create table if not exists users (
    username          string not null,
    added_time        date,
    ssh_public_key    text,
    owner             integer,
    agent_id          string,
    administrator     integer,
    PRIMARY KEY (username, agent_id)
);

create table if not exists alerts (
    alert_time        integer not null,
    added_time        integer,
    alert_hash        string not null,
    level             integer,
    rule              integer,
    message           text,
    subject           text,
    PRIMARY KEY (alert_hash)
);
"""


def fail_started_state(db_record):
    db_record.state = messaging_states.ReplyStates.REPLY
    r = {
        'Exception': "The job was executed but the state of the execution "
                     "was lost.",
        'return_code': 1}
    db_record.reply_doc = json.dumps(r)
    db_record.last_update_time = datetime.datetime.now()


class RequestDBObject(object):

    def __init__(self, request_id, incoming_document, agent_id, state,
                 reply_doc=None):
        self.request_doc = incoming_document
        self.reply_doc = reply_doc
        self.request_id = request_id
        self.state = state
        self.last_update_time = datetime.datetime.now()
        self.agent_id = agent_id


class RequestObject(object):

    # this is the disconnected object
    def __init__(self, connected_obj):
        self.request_doc = connected_obj.request_doc
        self.reply_doc = connected_obj.reply_doc
        self.request_id = connected_obj.request_id
        self.state = connected_obj.state
        self.last_update_time = datetime.datetime.now()
        self.agent_id = connected_obj.agent_id


def _get_column_order():
    return ["request_id", "creation_time", "request_doc",
            "reply_doc", "state", "agent_id", "last_update_time"]


class SQLiteRequestObject(object):

    # this is the disconnected object
    def __init__(self, row):
        if row is None:
            raise exceptions.PersistenceException("The row is none")
        column_order = _get_column_order()
        i = 0
        for attr in column_order:
            setattr(self, attr, row[i])
            i += 1


class SQLiteAgentDB(object):
    _lock = threading.RLock()

    def __init__(self, db_file):
        self._db_file = db_file

        try:
            self._db_conn = sqlite3.connect(
                self._db_file, check_same_thread=False)
            try:
                self._db_conn.executescript(_g_sqllite_ddl)
                self._db_conn.commit()
            except Exception as ex:
                _g_logger.exception(
                    "Could not open " + db_file + " " + str(ex))
                self._db_conn.rollback()
                raise
        except Exception as ex:
            _g_logger.exception(
                "Could not connect to the DB " + db_file + " " + str(ex))
            raise

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()

    def _log_db_info(self):
        if os.path.exists(self._db_file):
            st = os.stat(self._db_file)
            msg = "DB: " + self._db_file + os.linesep + str(st)
        else:
            msg = "DB: " + self._db_file + " does not exist."
        _g_logger.warn(msg)

    def _execute(self, func):
        try:
            cursor = self._db_conn.cursor()
            try:
                rc = func(cursor)
                self._db_conn.commit()
                return rc
            except Exception as ex:
                _g_logger.exception(
                    "Could not access " + self._db_file + " " + str(ex))
                self._db_conn.rollback()
                raise
            finally:
                cursor.close()
        except Exception as ex:
            _g_logger.exception(
                "Failed to access the DB " + self._db_file + " " + str(ex))
            self._log_db_info()
            raise

    @agent_utils.class_method_sync
    def starting_agent(self):
        r = {
            'Exception':
            "The job was executed but the state of the execution was lost.",
            'return_code': 1}
        reply_doc = json.dumps(r)

        stmt = ("UPDATE requests SET state=?, reply_doc=? WHERE state=?")

        def do_it(cursor):
            cursor.execute(stmt,
                           (messaging_states.ReplyStates.REPLY,
                            reply_doc,
                            messaging_states.ReplyStates.ACKED))
        self._execute(do_it)

    @agent_utils.class_method_sync
    def check_agent_id(self, agent_id):
        stmt = 'DELETE FROM requests where agent_id <> ?'

        def do_it(cursor):
            cursor.execute(stmt, (agent_id,))
        self._execute(do_it)

    def _get_all_state(self, state):
        stmt = ("SELECT " + ", ".join(_get_column_order()) +
                " FROM requests WHERE state=\"" + state + '"')

        def do_it(cursor):
            cursor.execute(stmt)
            rows = cursor.fetchall()
            if not rows:
                return []
            return [SQLiteRequestObject(i) for i in rows]
        return self._execute(do_it)

    @agent_utils.class_method_sync
    def get_all_complete(self):
        return self._get_all_state(messaging_states.ReplyStates.REPLY_ACKED)

    @agent_utils.class_method_sync
    def get_all_rejected(self, session=None):
        return self._get_all_state(messaging_states.ReplyStates.NACKED)

    @agent_utils.class_method_sync
    def get_all_reply_nacked(self, session=None):
        return self._get_all_state(messaging_states.ReplyStates.REPLY_NACKED)

    @agent_utils.class_method_sync
    def get_all_ack(self):
        return self._get_all_state(messaging_states.ReplyStates.ACKED)

    @agent_utils.class_method_sync
    def get_all_reply(self):
        return self._get_all_state(messaging_states.ReplyStates.REPLY)

    @agent_utils.class_method_sync
    def lookup_req(self, request_id):
        stmt = ("SELECT " + ", ".join(_get_column_order()) + " FROM "
                'requests where request_id=?')

        def do_it(cursor):
            cursor.execute(stmt, [request_id])
            row = cursor.fetchone()
            if not row:
                return
            return SQLiteRequestObject(row)
        return self._execute(do_it)

    @agent_utils.class_method_sync
    def new_record(self, request_id, request_doc, reply_doc, state,
                   agent_id):
        stmt = ("INSERT INTO requests(request_id, creation_time, request_doc, "
                "reply_doc, state, agent_id, last_update_time) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)")

        if request_id != request_doc['request_id']:
            raise exceptions.PersistenceException("The request_id must match "
                                                  "the request_doc")

        if request_doc is not None:
            request_doc = json.dumps(request_doc)
        if reply_doc is not None:
            reply_doc = json.dumps(reply_doc)

        def do_it(cursor):
            nw = datetime.datetime.now()
            parms = (request_id, nw, request_doc,
                     reply_doc, state, agent_id, nw)
            cursor.execute(stmt, parms)
        self._execute(do_it)

    @agent_utils.class_method_sync
    def update_record(self, request_id, state, reply_doc=None):
        stmt = ("UPDATE requests SET state=?, reply_doc=?, last_update_time=? "
                "WHERE request_id=?")
        try:
            if reply_doc is not None:
                reply_doc = json.dumps(reply_doc)

            def do_it(cursor):
                nw = datetime.datetime.now()
                cursor.execute(stmt, (state, reply_doc, nw, request_id))
                if cursor.rowcount != 1:
                    raise exceptions.PersistenceException(
                        "%d rows were updated when exactly 1 should have "
                        "been" % cursor.rowcount)
            self._execute(do_it)
        except Exception as ex:
            raise exceptions.PersistenceException(ex)

    @agent_utils.class_method_sync
    def clean_all_expired(self, cut_off_time):
        stmt = ("DELETE FROM requests WHERE request_id in (SELECT request_id "
                "FROM requests WHERE last_update_time < ?)")

        def do_it(cursor):
            cursor.execute(stmt, (cut_off_time,))
        self._execute(do_it)

    @agent_utils.class_method_sync
    def clean_all(self, request_id):
        stmt = ("DELETE FROM requests WHERE request_id <> ?")

        def do_it(cursor):
            cursor.execute(stmt, (request_id,))
        self._execute(do_it)

    @agent_utils.class_method_sync
    def add_user(self, agent_id, name, ssh_key, admin):
        test_owner = ("SELECT * FROM users where agent_id=?")
        test_exists = ("SELECT * FROM users where agent_id=? and "
                       "username=?")
        insert_new = ("INSERT INTO users(username, agent_id, owner, "
                      "administrator, ssh_public_key, added_time) "
                      "VALUES(?, ?, ?, ?, ?, ?)")
        update_existing = ("UPDATE users SET username=?, agent_id=?, owner=?, "
                           "administrator=?, ssh_public_key=?, added_time=?")

        def do_it(cursor):
            nw = datetime.datetime.now()
            if admin:
                administrator = 1
            else:
                administrator = 0
            cursor.execute(test_owner, (agent_id,))
            if cursor.rowcount != 0:
                owner = 1
            else:
                owner = 0
            cursor.execute(test_exists, (agent_id, name))
            if cursor.rowcount != 0:
                cursor.execute(
                    update_existing,
                    (name, agent_id, owner, administrator, ssh_key, nw))
            else:
                cursor.execute(
                    insert_new,
                    (name, agent_id, owner, administrator, ssh_key, nw))

        self._execute(do_it)

    @agent_utils.class_method_sync
    def get_owner(self, agent_id, name, ssh_key, admin):
        stmt = ("SELECT username, ssh_public_key FROM users where agent_id=? and owner=1")

        def do_it(cursor):
            cursor.execute(stmt, (agent_id,))
            if cursor.rowcount < 1:
                raise exceptions.PersistenceException(
                    "There is no owner in the database")
            if cursor.rowcount > 1:
                _g_logger.warning(
                    "The database has more than 1 user as the owner")
            row = cursor.fetchone()
            return (row[0], row[1])

        return self._execute(do_it)

    @agent_utils.class_method_sync
    def add_alert(self, alert_time, time_received,
                  alert_hash, level, rule, subject, message):
        insert_new = ("INSERT INTO alerts(alert_time, added_time, alert_hash, "
                      "level, rule, subject, message) "
                      "VALUES(?, ?, ?, ?, ?, ?, ?)")
        stmt = "SELECT alert_time from alerts"


        def do_it(cursor):
            cursor.execute(
                insert_new,
                (alert_time, time_received, alert_hash, level, rule,
                 subject, message))
            cursor.execute(stmt)
            row = cursor.fetchone()
            return row

        return self._execute(do_it)

    @agent_utils.class_method_sync
    def get_latest_alert_time(self):
        stmt = "SELECT max(alert_time) from alerts"

        def do_it(cursor):
            cursor.execute(stmt)
            row = cursor.fetchone()
            if row is None:
                return 0
            return row[0]

        return self._execute(do_it)


class DBCleaner(threading.Thread):

    def __init__(self, db, max_time, max_size, interval):
        super(DBCleaner, self).__init__()
        self._max_time = max_time
        self.max_size = max_size
        self._interval = interval
        self._done = threading.Event()
        self._cond = threading.Condition()
        self._db = db

    def run(self):
        while not self._done.isSet():
            self._cond.acquire()
            try:
                self._cond.wait(self._interval)
                cut_off_time = datetime.datetime.now() - datetime.timedelta(
                    microseconds=self._max_time)
                self._db.clean_all_expired(cut_off_time)
            except Exception as ex:
                _g_logger.exception("An exception occurred in the db sweeper "
                                    "thread " + str(ex))
            finally:
                self._cond.release()

    def done(self):
        self._cond.acquire()
        try:
            self._done.set()
            self._cond.notify()
        finally:
            self._cond.release()
