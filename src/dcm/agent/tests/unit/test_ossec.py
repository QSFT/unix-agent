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
import unittest
import os
import time
import dcm.agent.tests.utils.general as test_utils

from dcm.agent.ossec import OssecAlertParser

TEST_STRING="""
<132>Oct 28 20:46:35 ip-172-31-11-194 ossec:
{"crit":5,"id":5503,"component":"ip-172-31-11-194->/var/log/auth.log","classification":" pam,syslog,authentication_failed,","description":"User login failed.","message":"Oct 28 20:46:33 ip-172-31-11-194 su[17588]: pam_unix(su:auth): authentication failure; logname=ubuntu uid=1000 euid=0 tty=/dev/pts/1 ruser=ubuntu rhost=  user=root"}
<132>Oct 28 20:46:37 ip-172-31-11-194 ossec:
{"crit":5,"id":2501,"component":"ip-172-31-11-194->/var/log/auth.log","classification":" syslog,access_control,authentication_failed,","description":"User authentication failure.","message":"Oct 28 20:46:35 ip-172-31-11-194 su[17588]: pam_authenticate: Authentication failure"}
<132>Oct 28 20:46:37 ip-172-31-11-194 ossec:
{"crit":5,"id":5301,"component":"ip-172-31-11-194->/var/log/auth.log","classification":" syslog, su,authentication_failed,","description":"User missed the password to change UID (user id).","message":"Oct 28 20:46:35 ip-172-31-11-194 su[17588]: FAILED su for root by ubuntu"}
<132>Oct 28 20:46:37 ip-172-31-11-194 ossec:
{"crit":9,"id":5302,"component":"ip-172-31-11-194->/var/log/auth.log","classification":" syslog, su,authentication_failed,","description":"User missed the password to change UID to root.","message":"Oct 28 20:46:35 ip-172-31-11-194 su[17588]: - /dev/pts/1 ubuntu:root","acct":"root"}
"""
class TestOssec(unittest.TestCase, OssecAlertParser):

    @classmethod
    def setUpClass(cls):
        test_utils.connect_to_debugger()

    def setUp(self):
        oap = OssecAlertParser(dir_to_watch='/tmp')
        oap.start()

    def test_change_when_file_created(self):
        os.system("touch /tmp/alert.log")

    def test_write_to_file(self):
        with open("/tmp/alert.log", 'a') as f:
            f.write(TEST_STRING)
        value = super(OssecAlertParser, self).process()
        print(value)
