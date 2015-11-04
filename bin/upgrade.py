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
import argparse
import logging
import os
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import glob
import requests

_g_log_file = "/tmp/myuplog" + str(uuid.uuid4()).split("-")[0]
_g_logger = logging.getLogger()
_g_logger.setLevel(logging.DEBUG)
_g_fh = logging.FileHandler(_g_log_file)
_g_fh.setLevel(logging.DEBUG)
_g_ch = logging.StreamHandler(stream=sys.stdout)
_g_ch.setLevel(logging.DEBUG)
_g_logger.addHandler(_g_fh)
_g_logger.addHandler(_g_ch)


def create_daemon():
    pid = os.fork()
    if pid == 0:
        os.setsid()
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        pid = os.fork()
        if pid == 0:
            os.chdir('/')
        else:
            sys.exit(0)
    else:
        sys.exit(0)

    _g_logger.removeHandler(_g_ch)
    _g_logger.removeHandler(_g_fh)
    _g_ch.close()
    _g_fh.close()

    maxfd = 16
    for fd in range(0, maxfd):
        try:
            os.close(fd)
        except OSError:
            pass
    if hasattr(os, "devnull"):
        REDIRECT_TO = os.devnull
    else:
        REDIRECT_TO = "/dev/null"
    os.open(REDIRECT_TO, os.O_RDWR)
    os.open("/tmp/agent_upgrade.txt", os.O_CREAT | os.O_WRONLY)
    os.dup2(1, 2)

    fh = logging.FileHandler("/tmp/agent_upgrade.log")
    fh.setLevel(logging.DEBUG)
    _g_logger.addHandler(fh)



def backup_agent_files(base_dir):
    backup_conf_dir = tempfile.mkdtemp()
    a_conf = os.path.join(base_dir, "etc/agent.conf")
    token = os.path.join(base_dir, "secure/token")
    agentdb = os.path.join(base_dir, "secure/agentdb.sql")
    shutil.copy(a_conf, backup_conf_dir)
    shutil.copy(token, backup_conf_dir)
    shutil.copy(agentdb, backup_conf_dir)
    backup_message = "Backing up agent files to %s" % backup_conf_dir
    _g_logger.debug(backup_message)
    return backup_conf_dir


def get_installer(url):
    url += '/installer.sh'
    osf, fname = tempfile.mkstemp()
    os.close(osf)
    response = requests.get(url)
    html = response.content
    with open(fname, "wb") as fptr:
        fptr.write(html)
    os.chmod(fname, 0o755)
    _g_logger.debug("Downloading installer from %s to %s" % (url, fname))
    return fname


def run_installer(local_exe, pkg_base_url, new_version, backup_dir,
                  allow_unknown_certs, package_location):
    old_conf = os.path.join(backup_dir, "agent.conf")
    env = os.environ.copy()
    env["AGENT_BASE_URL"] = pkg_base_url
    env["AGENT_VERSION"] = new_version
    env["DCM_AGENT_REMOVE_EXISTING"] = "1"
    if package_location is not None:
        env['AGENT_LOCAL_PACKAGE'] = package_location

    if allow_unknown_certs:
        cmd = ['sudo', '-E', local_exe, '-Z', '-r', old_conf]
    else:
        cmd = ['sudo', '-E', local_exe, '-r', old_conf]
    process = subprocess.Popen(cmd,
                               shell=False,
                               env=env)
    rc = process.wait()
    _g_logger.debug("Ran the installer with rc %s" % rc)
    return rc


def _is_valid_version(version):
    if re.match("^\d\.\d{1,2}\.\d{1,2}$", version):
        return True
    return False


def _upgrading(version, current_version):
    """
    >>> _upgrading('0.9.2', '1.9.2')
    False
    >>> _upgrading('0.11.3', '0.11.2')
    True
    >>> _upgrading('0.10.2', '0.9.2')
    True
    >>> _upgrading('1.1.3', '1.1.4')
    False
    >>> _upgrading('1.1.1', '1.1.1')
    False
    >>> _upgrading('0.9.1000', '50.1.1')
    False
    >>> _upgrading('50.1.1', '0.9.1000')
    True
    """
    version_parts = version.split('.')
    c_version_parts = current_version.split('.')
    c_version_parts[2] = c_version_parts[2].split('-')[0]
    if c_version_parts == version_parts:
        return False
    for i in range(3):
        if int(version_parts[i]) > int(c_version_parts[i]):
            return True
        elif int(version_parts[i]) < int(c_version_parts[i]):
            return False


def read_old_conf(backup_dir):
    agent_conf = os.path.join(backup_dir, 'agent.conf')
    assert os.path.isfile(agent_conf)
    config = configparser.ConfigParser()
    config.read(agent_conf)
    return config


def stop_agent():
    p = subprocess.Popen(['sudo', '/etc/init.d/dcm-agent', 'status'],
                         shell=False,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (stdoutdata, stderrdata) = p.communicate()
    rc = p.wait()
    status_message = stdoutdata.decode()
    if "RUNNING" in status_message and "NOT RUNNING" not in status_message:
        _g_logger.debug('Stopping the current agent')
        p = subprocess.Popen(['sudo', '/etc/init.d/dcm-agent', 'stop'],
                             shell=False,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (stdoutdata, stderrdata) = p.communicate()
        rc = p.wait()
        if rc != 0:
            stop_agent_message = "The agent did not stop: stdout=%s, stderr=%s" % (stdoutdata, stderrdata)
            _g_logger.debug(stop_agent_message)


def _run_report(backup_dir, pre):
    _g_logger.debug('Running the agent report')
    p = subprocess.Popen(['sudo',
                          '/opt/dcm-agent/embedded/agentve/bin/dcm-agent',
                          '--report'],
                         shell=False,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (stdoutdata, stderrdata) = p.communicate()
    rc = p.wait()
    if rc != 0:
        agent_report_message =\
            "The agent report did not run correctly: stdout=%s, stderr=%s" % (stdoutdata, stderrdata)
        _g_logger.debug(agent_report_message)
        sys.exit(1)

    if pre:
        return_report = "/tmp/pre_agent_info.tar.gz"
    else:
        return_report = "/tmp/post_agent_info.tar.gz"
    try:
        report = "/tmp/agent_info.tar.gz"
        assert os.path.isfile(report)
        os.rename(report, return_report)
        shutil.copy(return_report, backup_dir)
        os.remove(return_report)
    except Exception as e:
        pre_report_message = "The report did not run correctly: %s" % e
        _g_logger.debug(pre_report_message)
    return os.path.join(backup_dir, return_report.split('/')[2])


def start_agent():
    _g_logger.debug('Starting the new agent')
    p = subprocess.Popen(['sudo', '/etc/init.d/dcm-agent', 'start'],
                         shell=False,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (stdoutdata, stderrdata) = p.communicate()
    rc = p.wait()
    if rc != 0:
        stop_agent_message = "The agent did not start: stdout=%s, stderr=%s" % (stdoutdata, stderrdata)
        _g_logger.debug(stop_agent_message)
        sys.exit(1)


def get_agent_version():
    p = subprocess.Popen(['sudo',
                          '/opt/dcm-agent/embedded/agentve/bin/dcm-agent',
                          '--version'],
                         shell=False,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (stdoutdata, stderrdata) = p.communicate()
    rc = p.wait()
    if rc != 0:
        agent_version_message =\
            "The agent did not return version: stdout=%s, stderr=%s" % (stdoutdata, stderrdata)
        _g_logger.debug(agent_version_message)
        sys.exit(1)
    return stdoutdata.split()[1].decode()


def restore_secure_dir(backup_dir, base_dir):
    try:
        shutil.copy(os.path.join(backup_dir, "token"), os.path.join(base_dir, "secure/token"))
        shutil.copy(os.path.join(backup_dir, "agentdb.sql"), os.path.join(base_dir, "secure/agentdb.sql"))
    except Exception as e:
        restore_dir_message = "The report secure directory did not run correctly: %s" % e
        _g_logger.debug(restore_dir_message)


def get_parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--version",
                        "-v",
                        dest="version",
                        required=True,
                        help="The software version to be upgraded to.")

    parser.add_argument("--daemon",
                        "-d",
                        dest="daemon",
                        default=False,
                        action="store_true",
                        help="Run the upgrade program as a daemon.  This is useful for the agent but should not be used from the command line.")

    parser.add_argument("--base_dir",
                        "-b",
                        dest="base_dir",
                        default="/dcm",
                        help="Base directory where agent is installed if different from /dcm.")

    parser.add_argument("--package_url",
                        "-u",
                        dest="package_url",
                        default="https://linux-stable-agent.enstratius.com",
                        help="This value will set AGENT_BASE_URL")

    parser.add_argument("--package_location",
                        "-p",
                        dest="package_location",
                        default=None,
                        help="This value will set AGENT_LOCAL_PACKAGE")

    parser.add_argument("--allow_unknown_certs", "-Z",
                        dest="allow_unknown_certs",
                        action='store_true',
                        default=False,
                        help="Disable cert validation.  In general this is a"
                             "bad idea but is very useful for testing.")

    return parser.parse_args()


def main():
    parsed_args = get_parse_args()
    version = parsed_args.version
    base_dir = parsed_args.base_dir
    package_url = parsed_args.package_url
    allow_unknown_certs = parsed_args.allow_unknown_certs
    backup_dir = backup_agent_files(base_dir)
    pre_report = _run_report(backup_dir, pre=True)
    current_version = get_agent_version()

    if not _is_valid_version(version):
        valid_version_message = "Supplied version %s is not in a valid format." % version
        _g_logger.debug(valid_version_message)
        sys.exit(1)

    if not _upgrading(version, current_version):
        upgrade_message = "Current version %s is more recent than upgrade version %s.  You must supply a more recent version to upgrade" % (current_version, version)
        _g_logger.debug(upgrade_message)
        sys.exit(1)

    _g_logger.debug("Current version: %s | Upgrade to %s"
                    % (current_version, version))

    installer_exe = get_installer(package_url)
    if not os.path.isfile(installer_exe):
        _g_logger.debug("There was a problem downloading the installer.  Exiting program now.")
        exit(1)

    if parsed_args.daemon:
        _g_logger.debug("Running this program as a background daemon.")
        create_daemon()

    conf = read_old_conf(backup_dir)
    if not allow_unknown_certs:
        try:
            allow_unknown_certs = conf.getboolean(
                "connection", "allow_unknown_certs")
        except configparser.NoOptionError:
            pass
    stop_agent()
    run_installer(installer_exe, package_url, version, backup_dir,
                  allow_unknown_certs, parsed_args.package_location)
    restore_secure_dir(backup_dir, base_dir)
    dcm_user_info = pwd.getpwnam('dcm')
    _g_logger.debug("DCM user is %s" % dcm_user_info[0])
    if os.path.isdir(os.path.join(base_dir, 'secure')):
        _g_logger.debug("Secure directory detected")
        for name in glob.glob(os.path.join(base_dir, 'secure/*')):
            _g_logger.debug("CHOWN %s to %s" % (name, dcm_user_info[0]))
            os.chown(name, dcm_user_info[2], dcm_user_info[3])
    start_agent()
    post_report = _run_report(backup_dir, pre=False)

    logs_location = ("""
    There are logs associated with this upgrade if you wish to view them.
    They are located at:
        1. %s
        2. %s
        3. %s
    """ % (pre_report, post_report,
           os.path.join(backup_dir, os.path.basename(_g_log_file))))
    shutil.copy(_g_log_file, backup_dir)
    os.remove(_g_log_file)
    os.remove(os.path.join(backup_dir, "token"))
    os.remove(os.path.join(backup_dir, "agentdb.sql"))
    _g_logger.debug(logs_location)

if __name__ == "__main__":
    main()
