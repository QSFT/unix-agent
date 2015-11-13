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
import os
import tempfile
import time
import threading
import unittest
import uuid

import dcm.agent.exceptions as exceptions
import dcm.agent.messaging.persistence as persistence
import dcm.agent.messaging.states as messaging_states


class TestPersistMemory(unittest.TestCase):

    def setUp(self):
        self.db = persistence.SQLiteAgentDB(":memory:")

    def test_complete_empty(self):
        res = self.db.get_all_complete()
        self.assertEqual(res, [])

    def test_rejected_empty(self):
        res = self.db.get_all_rejected()
        self.assertEqual(res, [])

    def test_nacked_empty(self):
        res = self.db.get_all_reply_nacked()
        self.assertEqual(res, [])

    def test_acked_empty(self):
        res = self.db.get_all_ack()
        self.assertEqual(res, [])

    def test_reply_empty(self):
        res = self.db.get_all_reply()
        self.assertEqual(res, [])

    def test_lookup_empty(self):
        res = self.db.lookup_req("NotTThere")
        self.assertIsNone(res)

    def test_update_not_there(self):
        passed = False
        try:
            self.db.update_record("Nope", "ASTATE")
        except exceptions.PersistenceException:
            passed = True
        self.assertTrue(passed, "An exception did not happen")

    def test_new_record_ack_search(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.ACKED
        self.db.new_record(request_id, request_doc, None, state, agent_id)
        res = self.db.get_all_ack()
        self.assertTrue(res)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].agent_id, agent_id)
        self.assertEqual(res[0].request_id, request_id)

    def test_new_record_reply_search(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.REPLY
        self.db.new_record(request_id, request_doc, None, state, agent_id)
        res = self.db.get_all_reply()
        self.assertTrue(res)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].agent_id, agent_id)
        self.assertEqual(res[0].request_id, request_id)

    def test_new_record_reply_nacked_search(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.REPLY_NACKED
        self.db.new_record(request_id, request_doc, None, state, agent_id)
        res = self.db.get_all_reply_nacked()
        self.assertTrue(res)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].agent_id, agent_id)
        self.assertEqual(res[0].request_id, request_id)

    def test_new_record_nacked_search(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.NACKED
        self.db.new_record(request_id, request_doc, None, state, agent_id)
        res = self.db.get_all_rejected()
        self.assertTrue(res)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].agent_id, agent_id)
        self.assertEqual(res[0].request_id, request_id)

    def test_new_record_lookup(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.REPLY_NACKED
        reply_doc = {"akey": "andstuff"}

        self.db.new_record(request_id, request_doc, reply_doc, state, agent_id)
        res = self.db.lookup_req(request_id)
        self.assertEqual(res.agent_id, agent_id)
        self.assertEqual(res.request_id, request_id)
        self.assertEqual(json.loads(res.reply_doc), reply_doc)

    def test_new_record_update_lookup(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.REPLY_NACKED
        reply_doc = {"akey": "andstuff"}

        self.db.new_record(request_id, request_doc, None, state, agent_id)

        state = messaging_states.ReplyStates.ACKED
        self.db.update_record(request_id, state, reply_doc=reply_doc)

        res = self.db.lookup_req(request_id)
        self.assertEqual(res.agent_id, agent_id)
        self.assertEqual(res.request_id, request_id)
        self.assertEqual(json.loads(res.reply_doc), reply_doc)
        self.assertEqual(res.state, state)

    def test_clear_all_lost(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.ACKED
        reply_doc = {"akey": "andstuff"}

        self.db.new_record(request_id, request_doc, reply_doc, state, agent_id)

        self.db.starting_agent()
        res = self.db.lookup_req(request_id)
        self.assertEqual(res.agent_id, agent_id)
        self.assertEqual(res.request_id, request_id)
        r = json.loads(res.reply_doc)
        self.assertEqual(r["return_code"], 1)
        self.assertEqual(res.state, messaging_states.ReplyStates.REPLY)

    def test_clear_empty(self):
        cut_off_time = datetime.datetime.now()
        self.db.clean_all_expired(cut_off_time)

    def test_clear_lost(self):
        request_id1 = str(uuid.uuid4())
        request_id2 = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id1}
        state = messaging_states.ReplyStates.ACKED
        reply_doc = {"request": "one"}

        self.db.new_record(
            request_id1, request_doc, reply_doc, state, agent_id)

        time.sleep(0.1)
        cut_off_time = datetime.datetime.now()

        reply_doc = {"request": "two"}
        request_doc = {"request_id": request_id2}
        self.db.new_record(
            request_id2, request_doc, reply_doc, state, agent_id)

        self.db.clean_all_expired(cut_off_time)

        res = self.db.lookup_req(request_id1)
        self.assertTrue(res is None)
        res = self.db.lookup_req(request_id2)
        self.assertTrue(res is not None)


class TestPersistDisk(unittest.TestCase):

    def setUp(self):
        _, self.db_file = tempfile.mkstemp("test_db")
        self.db = persistence.SQLiteAgentDB(self.db_file)

    def tearDown(self):
        os.remove(self.db_file)

    def test_record_sweeper(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.REPLY_NACKED
        self.db.new_record(request_id, request_doc, None, state, agent_id)

        request_id2 = str(uuid.uuid4())
        request_doc = {"request_id": request_id2}
        self.db.new_record(request_id2, request_doc, None, state, agent_id)

        cleaner = persistence.DBCleaner(self.db, 10, 10, 0.05)
        cleaner.start()

        time.sleep(0.5)
        cleaner.done()
        res = self.db.lookup_req(request_id)
        self.assertTrue(not res)
        res = self.db.lookup_req(request_id2)
        self.assertTrue(not res)

    def test_add_alert_db(self):
        alert_time1 = int(time.time() * 1000)
        time_received = int(time.time() * 1000)
        level = 1
        rule = 5000
        subject = "Test alert"
        message = "test message"
        alert_hash1 = "madeup1"
        alert_hash2 = "madeup2"
        alert_time2 = int(time.time() * 1000)

        x = self.db.add_alert(alert_time1, time_received,
                  alert_hash1, level, rule, subject, message)
        y = self.db.add_alert(alert_time2, time_received,
                  alert_hash2, level, rule, subject, message)

        latest_time = self.db.get_latest_alert_time()
        self.assertEqual(latest_time, alert_time2)



class TestPersistMultiThread(unittest.TestCase):

    def setUp(self):
        _, self.db_file = tempfile.mkstemp("test_db")
        self.db = persistence.SQLiteAgentDB(self.db_file)

    def tearDown(self):
        os.remove(self.db_file)

    def test_thread_lookup(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.REPLY_NACKED
        self.db.new_record(request_id, request_doc, None, state, agent_id)

        request_id2 = str(uuid.uuid4())
        request_doc = {"request_id": request_id2}
        self.db.new_record(request_id2, request_doc, None, state, agent_id)

        failed = []

        def _thread_lookup():
            try:
                res = self.db.lookup_req(request_id)
                print(res)
            except Exception as ex:
                print(str(ex))
                failed.append(True)

        t = threading.Thread(target=_thread_lookup)

        t.start()
        t.join()
        self.assertTrue(len(failed) == 0)

    def test_thread_update(self):
        request_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id}
        state = messaging_states.ReplyStates.REPLY_NACKED
        self.db.new_record(request_id, request_doc, None, state, agent_id)

        request_id2 = str(uuid.uuid4())
        request_doc = {"request_id": request_id2}
        self.db.new_record(request_id2, request_doc, None, state, agent_id)

        failed = []

        def _thread_lookup():
            try:
                res = self.db.update_record(
                    request_id, messaging_states.ReplyStates.REPLY)
                print(res)
            except Exception as ex:
                print(str(ex))
                failed.append(True)

        t = threading.Thread(target=_thread_lookup)

        t.start()
        t.join()
        self.assertTrue(len(failed) == 0)

    def test_agent_mismatch(self):
        request_id1 = str(uuid.uuid4())
        request_id2 = str(uuid.uuid4())
        agent_id1 = str(uuid.uuid4())
        request_doc = {"request_id": request_id1}
        state = messaging_states.ReplyStates.REPLY_NACKED
        reply_doc = {"akey": "andstuff"}
        self.db.new_record(
            request_id1, request_doc, reply_doc, state, agent_id1)
        request_doc["request_id"] = request_id2
        self.db.new_record(
            request_id2, request_doc, reply_doc, state, agent_id1)

        res = self.db.lookup_req(request_id1)
        self.assertTrue(res is not None)

        res = self.db.lookup_req(request_id2)
        self.assertTrue(res is not None)

        self.db.check_agent_id("differentid")

        res = self.db.lookup_req(request_id1)
        self.assertTrue(res is None)

        res = self.db.lookup_req(request_id2)
        self.assertTrue(res is None)

    def test_agent_id_cleanup_empty(self):
        self.db.check_agent_id("differentid")

    def test_agent_id_match(self):
        request_id1 = str(uuid.uuid4())
        request_id2 = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        request_doc = {"request_id": request_id1}
        state = messaging_states.ReplyStates.REPLY_NACKED
        reply_doc = {"akey": "andstuff"}
        self.db.new_record(
            request_id1, request_doc, reply_doc, state, agent_id)
        request_doc["request_id"] = request_id2
        self.db.new_record(
            request_id2, request_doc, reply_doc, state, agent_id)

        res = self.db.lookup_req(request_id1)
        self.assertTrue(res is not None)
        res = self.db.lookup_req(request_id2)
        self.assertTrue(res is not None)

        self.db.check_agent_id(agent_id)

        res = self.db.lookup_req(request_id1)
        self.assertTrue(res is not None)
        res = self.db.lookup_req(request_id2)
        self.assertTrue(res is not None)
