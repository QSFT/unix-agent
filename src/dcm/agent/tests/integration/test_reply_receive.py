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
import base64
import getpass
import hashlib
import logging
import os
import pwd
import random
import shutil
import socket
import string
import sys
import tempfile
import threading
import time
import traceback
import unittest
import uuid

from mock import patch

import dcm.agent
import dcm.agent.cmd.configure as configure
import dcm.agent.cmd.service as service
import dcm.agent.config as config
import dcm.agent.dispatcher as dispatcher
import dcm.agent.logger as logger
import dcm.agent.messaging.persistence as persistence
import dcm.agent.messaging.reply as reply
import dcm.agent.messaging.request as request
import dcm.agent.tests.utils.general as test_utils
import dcm.agent.tests.utils.test_connection as test_conn
import dcm.agent.utils as utils

from dcm.agent.events.globals import global_space as dcm_events


class CloudT(object):

    def __init__(self, id, key, secret, endpoint, account, region):
        self.id = id
        self.key = key
        self.secret = secret
        self.endpoint = endpoint
        self.account = account
        self.region = region

    def __str__(self):
        return "cloud_%d" % self.id


# does not inherit from unittest because of the python generators for
# testing storage clouds
class TestProtocolCommands(unittest.TestCase):
    def new_message(self, reply):
        pass

    def message_done(self, reply):
        self._event.set()

    def incoming_message(self, incoming_doc):
        pass

    @classmethod
    def _setup_storage_clouds(cls):
        env_str = "DCM_AGENT_STORAGE_CREDS"

        cls.storage_clouds = []
        if env_str not in os.environ:
            return

        path = os.environ[env_str]
        if not os.path.exists(path):
            return
        try:
            with open(path, "r") as fptr:
                cloud_lines = fptr.readlines()
        except Exception as ex:
            logging.error("Failed to setup storage clouds, continuing all "
                          "tests that do not require a storage cloud", ex)
            return

        for cloud_line in cloud_lines:
            cloud_endpoint = None
            cloud_account = None
            cloud_region = None
            c_a = cloud_line.split(" ")
            cloud_id = int(c_a.pop(0).strip())
            cloud_key = c_a.pop(0).strip()
            cloud_secret = c_a.pop(0).strip()
            if c_a:
                cloud_region = c_a.pop(0).strip()
            if c_a:
                cloud_endpoint = c_a.pop(0).strip()
            if c_a:
                cloud_account = c_a.pop(0).strip()

            cloud = CloudT(cloud_id,
                           cloud_key,
                           cloud_secret,
                           cloud_endpoint,
                           cloud_account,
                           cloud_region)
            cls.storage_clouds.append(cloud)

    @classmethod
    def setUpClass(cls):
        test_utils.connect_to_debugger()
        cls.run_as_user = getpass.getuser()
        cls.test_base_path = tempfile.mkdtemp()
        conf_args = ["-c", "Amazon",
                     "-u", "http://doesntmatter.org/ws",
                     "-p", cls.test_base_path,
                     "-t", os.path.join(cls.test_base_path, "tmp"),
                     "-C", "success_tester",
                     "-U", cls.run_as_user,
                     "-l", "/tmp/agent_test_log.log"]
        if 'DCM_AWS_EXTRAS_BUCKET' in os.environ:
            extras_repo = ("http://" + os.environ['DCM_AWS_EXTRAS_BUCKET']
                           + ".s3.amazonaws.com")
            conf_args.append("--extra-package-location")
            conf_args.append(extras_repo)
        if 'DCM_INSTALL_EXTRAS' in os.environ:
            conf_args.append("--install-extras")
        rc = configure.main(conf_args)
        if rc != 0:
            raise Exception("We could not configure the test env")

    @classmethod
    def tearDownClass(cls):
        logger.clear_dcm_logging()

        shutil.rmtree(cls.test_base_path)

    def setUp(self):
        self.test_conf_path = \
            os.path.join(self.test_base_path, "etc", "agent.conf")
        self.conf_obj = config.AgentConfig([self.test_conf_path])
        self.svc = service.DCMAgent(self.conf_obj)

        self._event = threading.Event()

        utils.verify_config_file(self.conf_obj)
        # script_dir must be forced to None so that we get the built in dir
        self.svc.pre_threads()
        self.conf_obj.start_job_runner()

        self.disp = dispatcher.Dispatcher(self.conf_obj)

        self.req_conn = test_conn.RequestConnection()
        self.reply_conn = test_conn.ReplyConnection()

        self.db = persistence.SQLiteAgentDB(
            os.path.join(self.test_base_path, "etc", "agentdb.sql"))
        self.request_listener = reply.RequestListener(
            self.conf_obj, self.reply_conn, self.disp, self.db)
        observers = self.request_listener.get_reply_observers()
        observers.append(self)
        self.req_conn.set_request_listener(self.request_listener)

        self.agent_id = "theAgentID" + str(uuid.uuid4())
        self.customer_id = 50

        handshake_doc = {}
        handshake_doc["version"] = "1"
        handshake_doc["agentID"] = self.agent_id
        handshake_doc["cloudId"] = "Amazon"
        handshake_doc["customerId"] = self.customer_id
        handshake_doc["regionId"] = None
        handshake_doc["zoneId"] = "rack2"
        handshake_doc["serverId"] = "thisServer"
        handshake_doc["serverName"] = "dcm.testagent.com"
        handshake_doc["ephemeralFileSystem"] = "/tmp"
        handshake_doc["encryptedEphemeralFsKey"] = "DEADBEAF"

        self.svc.conn = self.reply_conn
        self.svc.disp = self.disp
        self.svc.request_listener = self.request_listener

        self.svc.handshaker.incoming_document({"handshake": handshake_doc,
                                               "return_code": 200})

        self.disp.start_workers(self.request_listener)

    def _run_main_loop(self):
        self.svc.agent_main_loop()

    def _rpc_wait_reply(self, doc):

        def reply_callback():
            pass

        reqRPC = request.RequestRPC(doc, self.req_conn, self.agent_id,
                                    reply_callback=reply_callback)

        self.reply_conn.set_request_side(reqRPC)
        reqRPC.send()

        # wait for message completion:
        while not self._event.isSet():
            dcm_events.poll()
        self._event.clear()

        reqRPC.cleanup()
        self.shutting_down = False

        return reqRPC

    def tearDown(self):
        self.request_listener.wait_for_all_nicely()
        self.svc.cleanup_agent()
        self.req_conn.close()
        test_utils.test_thread_shutdown()

    def test_heartbeat(self):
        doc = {
            "command": "heartbeat",
            "arguments": {}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["reply_type"], "string")
        self.assertEqual(r["payload"]["return_code"], 0)
        # TODO verify that this matches the output of the command

    def test_get_agent_data(self):
        doc = {
            "command": "get_agent_data",
            "arguments": {}
        }
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["reply_type"], "agent_data")
        self.assertEqual(r["payload"]["return_code"], 0)

    @test_utils.system_changing
    def test_add_user_remove_user(self):
        user_name = "dcm" + str(random.randint(10, 99))

        doc = {
            "command": "add_user",
            "arguments": {"customerId": self.customer_id,
                          "userId": user_name,
                          "firstName": "buzz",
                          "lastName": "troll",
                          "authentication": "public key data",
                          "administrator": False}}
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        pw_ent = pwd.getpwnam(user_name)

        self.assertEqual(pw_ent.pw_name, user_name)

        doc = {
            "command": "remove_user",
            "arguments": {"userId": user_name}}

        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        try:
            pwd.getpwnam(user_name)
            self.assertTrue(False, "should have raised an exception")
        except KeyError:
            pass

    def _build_underscore_dash_names(self, user_name):

        doc = {
            "command": "add_user",
            "arguments": {"customerId": self.customer_id,
                          "userId": user_name,
                          "firstName": "buzz",
                          "lastName": "troll",
                          "authentication": "public key data",
                          "administrator": False}}

        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        msg = 'this following name failed:  ' + user_name

        try:
            self.assertTrue(r["payload"]["return_code"] != 0, msg)

        finally:
            try:  # delete and clean up user
                pw_ent = pwd.getpwnam(user_name)
                if pw_ent is not None:
                    os.system('userdel -r %s' % user_name)
            except Exception as e:  # show exception
                print(e)

    def test_add_underscore_dash_username_fails(self):
        """
        :return: tests to show that names created
                 with -,_ at beginning or end of username fail
        """
        if "SYSTEM_CHANGING_TEST" not in os.environ:
            raise unittest.SkipTest('skipping')

        usernames = ['-bob', '_bob', 'bob_', 'bob-',
                     '-bob-', '_bob_', '_bob-', '-bob_']

        for user_name in usernames:
            self._build_underscore_dash_names(user_name)

    def _build_fake_names(self, sc):
        user_name = 'Bob' + sc

        doc = {
            "command": "add_user",
            "arguments": {"customerId": self.customer_id,
                          "userId": user_name,
                          "firstName": "buzz",
                          "lastName": "troll",
                          "authentication": "public key data",
                          "administrator": False}}

        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        msg = 'special char is ' + sc

        try:
            self.assertTrue(r["payload"]["return_code"] != 0, msg)
        finally:
            try:  # delete and clean up user
                pw_ent = pwd.getpwnam(user_name)
                if pw_ent is not None:
                    os.system('userdel -r %s' % user_name)
            except Exception as e:  # show exception
                print(e)

    def test_add_special_char_username_fails(self):
        """
        :return: tests to show that names created
                 with things in spec_chars fail
        """
        if "SYSTEM_CHANGING_TEST" not in os.environ:
            raise unittest.SkipTest('skipping')

        spec_chars = ['*', '&', '!', '?', '/', '\\', '.', '^', '$', '(', ')',
                      '{', '}', '[', ']']

        for sc in spec_chars:
            self._build_fake_names(sc)

    @test_utils.system_changing
    def test_add_admin_user_remove_user(self):
        user_name = "dcm" + str(random.randint(10, 99))

        doc = {
            "command": "add_user",
            "arguments": {"customerId": self.customer_id,
                          "userId": user_name,
                          "firstName": "buzz",
                          "lastName": "troll",
                          "authentication": "public key data",
                          "administrator": True}}
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        print(str(r))
        self.assertEqual(r["payload"]["return_code"], 0)

        pw_ent = pwd.getpwnam(user_name)

        # TODO figure out a safe way to verify that sudo was added

        self.assertEqual(pw_ent.pw_name, user_name)

        doc = {
            "command": "remove_user",
            "arguments": {"userId": user_name}}

        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        try:
            pwd.getpwnam(user_name)
            self.assertTrue(False, "should have raised an exception")
        except KeyError:
            pass

    @test_utils.skip_docker
    @test_utils.system_changing
    def test_initialize(self):
        cust = 10
        new_hostname = "testdcmagent"
        doc = {
            "command": "initialize",
            "arguments": {"cloudId": "3",
                          "customerId": cust,
                          "regionId": None,
                          "zoneId": None,
                          "serverId": self.agent_id,
                          "serverName": new_hostname,
                          "encryptedEphemeralFsKey": None}}
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        self.assertEqual(socket.gethostname(), new_hostname)

        customer_user = utils.make_id_string("c", cust)
        pw_ent = pwd.getpwnam(customer_user)
        self.assertEqual(pw_ent.pw_name, customer_user)

    def test_list_devices(self):
        doc = {
            "command": "list_devices",
            "arguments": {}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        # TODO verify that this matches the output of the command

    @test_utils.skip_docker
    @test_utils.system_changing
    def test_rename(self):
        orig_hostname = socket.gethostname()

        new_hostname = "buzztroll"
        doc = {
            "command": "rename",
            "arguments": {"serverName": new_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        self.assertEqual(socket.gethostname(), new_hostname)

        doc = {
            "command": "rename",
            "arguments": {"serverName": orig_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        self.assertEqual(socket.gethostname(), orig_hostname)

    @test_utils.skip_docker
    @test_utils.system_changing
    def test_rename_bad_hostname(self):
        orig_hostname = socket.gethostname()

        new_hostname = "@pp1#"
        doc = {
            "command": "rename",
            "arguments": {"serverName": new_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertTrue(r["payload"]["return_code"] == 0)
        self.assertEqual(socket.gethostname(), "pp1")

        doc = {
            "command": "rename",
            "arguments": {"serverName": orig_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        self.assertEqual(socket.gethostname(), orig_hostname)

    @test_utils.skip_docker
    @test_utils.system_changing
    def test_rename_long_hostname(self):
        orig_hostname = socket.gethostname()

        new_hostname = ''.join(random.choice(
            string.ascii_letters) for n in range(512))

        doc = {
            "command": "rename",
            "arguments": {"serverName": new_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        print(socket.gethostname())
        self.assertTrue(r["payload"]["return_code"] != 0)
        self.assertEqual(socket.gethostname(), orig_hostname)

    def _get_job_description(self, job_id):
        arguments = {
            "jobId": job_id
        }
        doc = {
            "command": "get_job_description",
            "arguments": arguments
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        self.assertEqual(r["payload"]["reply_type"], "job_description")

        jd = r["payload"]["reply_object"]

        time.sleep(0.1)

        return jd

    def test_unmount_something_not_mounted(self):
        arguments = {
            "deviceId": "/dev/notreal",
        }
        doc = {
            "command": "unmount_volume",
            "arguments": arguments
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 1)

    @test_utils.skip_docker
    @test_utils.system_changing
    def test_rename_bad_name(self):
        orig_hostname = socket.gethostname()

        new_hostname = "@#@#$"
        doc = {
            "command": "rename",
            "arguments": {"serverName": new_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertTrue(r["payload"]["return_code"] != 0)
        self.assertEqual(socket.gethostname(), orig_hostname)

        doc = {
            "command": "rename",
            "arguments": {"serverName": orig_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        self.assertEqual(socket.gethostname(), orig_hostname)

    @test_utils.skip_docker
    @test_utils.system_changing
    def test_initialize_rename_error(self):
        cust = 10
        orig_hostname = socket.gethostname()
        new_hostname = "....."
        doc = {
            "command": "initialize",
            "arguments": {"cloudId": "3",
                          "customerId": cust,
                          "regionId": None,
                          "zoneId": None,
                          "serverId": self.agent_id,
                          "serverName": new_hostname,
                          "encryptedEphemeralFsKey": None}}
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        self.assertTrue(r["payload"]["return_code"] != 0)
        self.assertEqual(socket.gethostname(), orig_hostname)

    @test_utils.system_changing
    def test_mount_variety(self):
        mount_point = os.path.join(tempfile.mkdtemp(), "mnt")

        if os.path.exists("/dev/sdb"):
            device_id = "sdb"
        elif os.path.exists("/dev/hdb"):
            device_id = "hdb"
        else:
            raise unittest.SkipTest("No second drive was found")

        mappings = utils.get_device_mappings(self.conf_obj)
        for dm in mappings:
            if dm['device_id'] == device_id:
                os.system("umount " + dm['mount_point'])

        print(device_id)
        mappings = utils.get_device_mappings(self.conf_obj)
        for dm in mappings:
            if dm['device_id'] == device_id:
                if dm['mount_point'] != mount_point:
                    raise unittest.SkipTest("The device is already mounted")

        doc = {
            "command": "mount_volume",
            "arguments": {"formatVolume": True,
                          "fileSystem": "ext3",
                          "raidLevel": "NONE",
                          "encryptedFsEncryptionKey": None,
                          "mountPoint": mount_point,
                          "devices": [device_id]}}
        print("trying to mount")
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        jd = r["payload"]["reply_object"]
        while jd["job_status"] in ["WAITING", "RUNNING"]:
            jd = self._get_job_description(jd["job_id"])
        self.assertEqual(jd["job_status"], "COMPLETE")
        print("done mount")

        found = False
        mappings = utils.get_device_mappings(self.conf_obj)
        for dm in mappings:
            if dm['device_id'] == device_id:
                found = True
                self.assertEqual(dm['mount_point'], mount_point)
        self.assertTrue(found)

        arguments = {
            "deviceId": device_id,
        }
        doc = {
            "command": "unmount_volume",
            "arguments": arguments
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        mount_point = os.path.join(tempfile.mkdtemp(), "mnt2")
        doc = {
            "command": "mount_volume",
            "arguments": {"formatVolume": True,
                          "fileSystem": "ext3",
                          "raidLevel": "NONE",
                          "encryptedFsEncryptionKey": None,
                          "mountPoint": mount_point,
                          "devices": [device_id]}}
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        jd = r["payload"]["reply_object"]
        while jd["job_status"] in ["WAITING", "RUNNING"]:
            jd = self._get_job_description(jd["job_id"])
        self.assertEqual(jd["job_status"], "COMPLETE")
        print("done format")

        arguments = {
            "deviceId": device_id,
        }
        doc = {
            "command": "unmount_volume",
            "arguments": arguments
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

    @test_utils.system_changing
    def test_mount_encryption(self):
        enc_str = "ENCRYPTED_FILE_ENV"

        if enc_str not in os.environ:
            raise unittest.SkipTest("set %s to try encryption tests" % enc_str)

        enc_key = os.environ["ENCRYPTED_FILE_ENV"]
        mount_point = os.path.join(tempfile.mkdtemp(), "mnt")
        device_id = "sdb"

        mappings = utils.get_device_mappings(self.conf_obj)
        for dm in mappings:
            if dm['device_id'] == device_id:
                if dm['mount_point'] != mount_point:
                    raise Exception("The device is already mounted")

        doc = {
            "command": "mount_volume",
            "arguments": {"formatVolume": True,
                          "fileSystem": "ext3",
                          "raidLevel": "NONE",
                          "encryptedFsEncryptionKey":
                          base64.b64encode(enc_key.encode()).decode(),
                          "mountPoint": mount_point,
                          "devices": [device_id]}}
        req_rpc = self._rpc_wait_reply(doc)
        r = req_rpc.get_reply()
        jd = r["payload"]["reply_object"]
        while jd["job_status"] in ["WAITING", "RUNNING"]:
            jd = self._get_job_description(jd["job_id"])
        self.assertEqual(jd["job_status"], "COMPLETE")

        arguments = {
            "deviceId": "es" + device_id,
            "encrypted": True
        }
        doc = {
            "command": "unmount_volume",
            "arguments": arguments
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

    def test_upgrade(self):
        try:
            print("starting upgrade")
            _, tmpfname = tempfile.mkstemp()
            _, exefname = tempfile.mkstemp()
            exe_data = """#!/bin/bash
                          echo $@ > %s
                       """ % tmpfname

            url = "file:///%s" % exefname
            newVersion = "10.100.newversion"
            with open(exefname, "w") as fptr:
                fptr.write(exe_data)

            doc = {
                "command": "upgrade",
                "arguments": {"url": url,
                              "newVersion": newVersion,
                              "args": ["arg1", "arg2"]}
            }
            print("sending upgrade")
            req_reply = self._rpc_wait_reply(doc)
            r = req_reply.get_reply()
            self.assertEqual(r["payload"]["return_code"], 0)

            print("verify upgrade")
            with open(tmpfname, "r") as fptr:
                line = fptr.readline()
            self.assertTrue(line)
            la = line.split()

            self.assertEqual(la[0], newVersion)
            self.assertEqual(la[1], dcm.agent.g_version)
        except Exception as ex:
            with open("/tmp/SUP", "w") as fptr:
                fptr.write("got here")
                fptr.write(os.linesep)
                try:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    traceback.print_tb(exc_traceback, file=fptr)
                except Exception as ex2:
                    fptr.write(str(ex2))
                    fptr.write(os.linesep)
                fptr.write(str(ex))
                fptr.write(os.linesep)
                fptr.write(str(ex))
                fptr.write(os.linesep)
                fptr.write(test_utils.build_assertion_exception("tester"))
            print(ex)
            print(test_utils.build_assertion_exception("tester"))
            self.assertTrue(False, str(ex))

    def test_run_script(self):
        _, tmpfname = tempfile.mkstemp()
        _, exefname = tempfile.mkstemp()
        args = ["arg1", "hello", "args3"]
        exe_data = """#!/bin/bash
                      echo $@ > %s
                   """ % tmpfname

        sha256 = hashlib.sha256()
        sha256.update(exe_data.encode())
        checksum = sha256.hexdigest()

        doc = {
            "command": "run_script",
            "arguments": {
                "b64script": base64.b64encode(exe_data.encode()).decode(),
                "arguments": args,
                "checksum": checksum
            }
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)

        with open(tmpfname, "r") as fptr:
            line = fptr.readline()
        self.assertTrue(line)
        la = line.split()

        self.assertEqual(la, args)

    @test_utils.system_changing
    def test_configure_server_with_chef(self):
        _, tmpfname = tempfile.mkstemp()
        fake_chef_script = """#!/bin/bash
        echo $@ > %s
        """ % tmpfname

        chef_script_path = os.path.join(
            self.test_base_path, "bin", "runConfigurationManagement-CHEF")

        with open(chef_script_path, "w") as fptr:
            fptr.write(fake_chef_script)
        os.chmod(chef_script_path, 0o755)

        runListIds = ["recipe[git]", "recipe[2]"]
        confClientName = "confname"

        arguments = {
            "configType": "CHEF",
            "runListIds": runListIds,
            "configClientName": confClientName
        }
        doc = {
            "command": "configure_server_17",
            "arguments": arguments
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        self.assertEqual(r["payload"]["reply_type"], "job_description")

        jd = r["payload"]["reply_object"]
        while jd["job_status"] in ["WAITING", "RUNNING"]:
            jd = self._get_job_description(jd["job_id"])
        self.assertEqual(jd["job_status"], "COMPLETE")

        with open(tmpfname, "r") as fptr:
            lines = fptr.readlines()
        self.assertTrue(len(lines) >= 1)

        line1_a = lines[0].split()
        self.assertEqual(line1_a[1], confClientName)

    @patch('dcm.agent.utils.extras_installed')
    @test_utils.system_changing
    def test_configure_server_with_puppet(self, extras_installed_cmd):
        extras_installed_cmd.return_value = True
        _, tmpfname = tempfile.mkstemp()
        fake_chef_script = """#!/bin/bash
        echo $@ > %s
        """ % tmpfname

        chef_script_path = os.path.join(
            self.test_base_path, "bin", "runConfigurationManagement-PUPPET")

        old_extra_path = self.conf_obj.extra_base_path
        try:
            self.conf_obj.extra_base_path = tempfile.mkdtemp()
            os.mkdir(os.path.join(self.conf_obj.extra_base_path, "puppetconf"))
            os.mkdir(os.path.join(self.conf_obj.extra_base_path, "bin"))
            with open(os.path.join(self.conf_obj.extra_base_path,
                                   "bin/puppet"), "w") as fptr:
                fptr.write("x")

            with open(os.path.join(self.conf_obj.extra_base_path,
                                   "puppetconf/puppet.conf.template"),
                      "w") as fptr:
                fptr.write("[agent]" + os.linesep)
                fptr.write("fake=stuff")

            with open(chef_script_path, "w") as fptr:
                fptr.write(fake_chef_script)
            os.chmod(chef_script_path, 0o755)

            confClientName = "confname"
            configCert = base64.b64encode(str(uuid.uuid4()).encode()).decode()
            configKey = base64.b64encode(str(uuid.uuid4()).encode()).decode()

            arguments = {
                "endpoint": "http://notreal.com",
                "configType": "PUPPET",
                "configClientName": confClientName,
                "configCert": configCert,
                "configKey": configKey
            }
            doc = {
                "command": "configure_server_17",
                "arguments": arguments
            }
            req_reply = self._rpc_wait_reply(doc)
            r = req_reply.get_reply()
            self.assertEqual(r["payload"]["return_code"], 0)
            self.assertEqual(r["payload"]["reply_type"], "job_description")

            jd = r["payload"]["reply_object"]
            while jd["job_status"] in ["WAITING", "RUNNING"]:
                jd = self._get_job_description(jd["job_id"])
            self.assertEqual(jd["job_status"], "COMPLETE")

            with open(tmpfname, "r") as fptr:
                lines = fptr.readlines()
            self.assertTrue(len(lines) >= 1)

            line1_a = lines[0].split()
            self.assertEqual(line1_a[3], confClientName)
        finally:
            self.conf_obj.extra_base_path = old_extra_path

    def test_bad_arguments(self):
        orig_hostname = socket.gethostname()

        new_hostname = "@pp1#"
        doc = {
            "command": "rename",
            "arguments": {"NotAName": new_hostname}
        }
        req_reply = self._rpc_wait_reply(doc)
        r = req_reply.get_reply()
        self.assertTrue(r["payload"]["return_code"] != 0)
        self.assertEqual(socket.gethostname(), orig_hostname)

    @test_utils.system_changing
    def test_remove_multiple_users(self):
        user_list = []
        for i in range(5):
            user_name = "dcm" + str(random.randint(10, 99))

            doc = {
                "command": "add_user",
                "arguments": {"customerId": self.customer_id,
                              "userId": user_name,
                              "firstName": "buzz",
                              "lastName": "troll",
                              "authentication": "public key data",
                              "administrator": False}}
            user_list.append(user_name)
            req_rpc = self._rpc_wait_reply(doc)
            r = req_rpc.get_reply()
            self.assertEqual(r["payload"]["return_code"], 0)

            pw_ent = pwd.getpwnam(user_name)
            self.assertEqual(pw_ent.pw_name, user_name)

        doctwo = {
            "command": "clean_image",
            "arguments": {"delUser": user_list}}

        req_rpc = self._rpc_wait_reply(doctwo)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        try:
            for name in user_list:  # delete and clean up user
                pw_ent = pwd.getpwnam(name)
                if pw_ent is not None:
                    os.system('userdel -r %s' % name)
        except KeyError:
            print("The name doesn't exist")

    @test_utils.system_changing
    def test_delete_private_keys(self):
        user_list = []
        for i in range(5):
            user_name = "dcm" + str(random.randint(10, 99))

            doc = {
                "command": "add_user",
                "arguments": {"customerId": self.customer_id,
                              "userId": user_name,
                              "firstName": "buzz",
                              "lastName": "troll",
                              "authentication": "public key data",
                              "administrator": False}}
            user_list.append(user_name)
            req_rpc = self._rpc_wait_reply(doc)
            r = req_rpc.get_reply()
            self.assertEqual(r["payload"]["return_code"], 0)

            pw_ent = pwd.getpwnam(user_name)
            self.assertEqual(pw_ent.pw_name, user_name)
            keyfile = '/home/%s/.ssh/key' % user_name
            with open(keyfile, "w") as kf:
                kf.write('-----BEGIN RSA PRIVATE KEY-----\n')
        doctwo = {
            "command": "clean_image",
            "arguments": {"delKeys": True}}

        req_rpc = self._rpc_wait_reply(doctwo)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        jd = r["payload"]["reply_object"]
        while jd["job_status"] in ["WAITING", "RUNNING"]:
            jd = self._get_job_description(jd["job_id"])
        self.assertEqual(jd["job_status"], "COMPLETE")

        for user in user_list:
            keyfile_path = '/home/%s/.ssh/key' % user
            self.assertEqual(os.path.isfile(keyfile_path), False)

        try:
            for name in user_list:  # delete and clean up user and homedir
                pw_ent = pwd.getpwnam(name)
                if pw_ent is not None:
                    os.system('userdel -r %s' % name)
                    os.system('rm -rf /home/%s' % name)
        except KeyError:
            print("The name doesn't exist")

    @test_utils.system_changing
    def test_general_cleanup(self):
        user_list = []
        for i in range(5):
            user_name = "dcm" + str(random.randint(10, 99))

            doc = {
                "command": "add_user",
                "arguments": {"customerId": self.customer_id,
                              "userId": user_name,
                              "firstName": "buzz",
                              "lastName": "troll",
                              "authentication": "public key data",
                              "administrator": False}}
            user_list.append(user_name)
            req_rpc = self._rpc_wait_reply(doc)
            r = req_rpc.get_reply()
            self.assertEqual(r["payload"]["return_code"], 0)

            pw_ent = pwd.getpwnam(user_name)
            self.assertEqual(pw_ent.pw_name, user_name)
            history_file = '/home/%s/.fake_history' % user_name
            with open(history_file, "w") as kf:
                kf.write('this is fake stuff')

            keep_file = '/home/%s/keepme.fake_history' % user_name
            with open(keep_file, "w") as fptr:
                fptr.write('this is fake stuff')

        doctwo = {
            "command": "clean_image",
            "arguments": {'delHistory': 'true'}}

        req_rpc = self._rpc_wait_reply(doctwo)
        r = req_rpc.get_reply()
        self.assertEqual(r["payload"]["return_code"], 0)
        jd = r["payload"]["reply_object"]
        while jd["job_status"] in ["WAITING", "RUNNING"]:
            jd = self._get_job_description(jd["job_id"])
        self.assertEqual(jd["job_status"], "COMPLETE")

        for user in user_list:
            history_path = '/home/%s/.fake_history' % user
            self.assertEqual(os.path.isfile(history_path), False)
            self.assertEqual(os.path.isfile(keep_file), True)

        log_dir = os.path.join(self.test_base_path, 'logs')
        self.assertEqual(os.listdir(log_dir), [])
        secure_dir = os.path.join(self.test_base_path, 'secure')
        self.assertEqual(os.path.isfile(
            os.path.join(secure_dir, 'agentdb.sql')), True)

        try:
            for name in user_list:  # delete and clean up user and homedir
                pw_ent = pwd.getpwnam(name)
                if pw_ent is not None:
                    os.system('userdel -r %s' % name)
                    os.system('rm -rf /home/%s' % name)
        except KeyError:
            print("The name doesn't exist")
