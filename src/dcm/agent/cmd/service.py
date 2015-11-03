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
from __future__ import print_function

import argparse
import datetime
import clint
import json
import logging
import os
import psutil
import signal
import sys
import tarfile

import dcm.agent
import dcm.agent.cloudmetadata as cm
import dcm.agent.config as config
import dcm.agent.dispatcher as dispatcher
import dcm.agent.exceptions as exceptions
import dcm.agent.handshake as handshake
import dcm.agent.logger as logger
import dcm.agent.messaging as messaging
import dcm.agent.messaging.persistence as persistence
import dcm.agent.messaging.reply as reply
import dcm.agent.ossec as ossec
import dcm.agent.utils as utils
import dcm.agent.systemstats as systemstats

import dcm.agent.events.globals as events


class DCMAgent(object):

    def __init__(self, conf):
        self.shutting_down = False
        self.conn = None
        self.conf = conf
        self.disp = None
        self.intrusion_detection = None
        self.request_listener = None
        self.g_logger = logging.getLogger(__name__)
        self._db = persistence.SQLiteAgentDB(conf.storage_dbfile)
        self.db_cleaner = None
        self.handshaker = handshake.HandshakeManager(self.conf, self._db)
        events.global_pubsub.subscribe(
            events.DCMAgentTopics.CLEANUP, self.clean_db_handler)

    def clean_db_handler(self, request_id=None, *args, **kwargs):
        self._db.clean_all(request_id)
        logger.delete_logs()

    def kill_handler(self, signum, frame):
        self.shutdown_main_loop()

    def stack_trace_handler(self, signum, frame):
        utils.build_assertion_exception(self.g_logger, "signal stack")

    def shutdown_main_loop(self):
        self.shutting_down = True
        events.global_space.wakeup(cancel_all=True)

    def pre_threads(self):
        signal.signal(signal.SIGINT, self.kill_handler)
        signal.signal(signal.SIGTERM, self.kill_handler)
        signal.signal(signal.SIGUSR2, self.stack_trace_handler)

        if self.conf.pydev_host:
            utils.setup_remote_pydev(self.conf.pydev_host,
                                     self.conf.pydev_port)

        if 'PYDEVD_DEBUG_HOST' in os.environ:
            pydev = os.environ['PYDEVD_DEBUG_HOST']
            h, p = pydev.split(":")
            utils.setup_remote_pydev(h, int(p))

    def run_agent(self):
        try:
            self.db_cleaner = persistence.DBCleaner(
                self._db, self.conf.storage_db_timeout, 100000, 3600)
            self.db_cleaner.start()

            # def get a connection object
            self.conn = config.get_connection_object(self.conf)
            self.disp = dispatcher.Dispatcher(self.conf)
            self.request_listener = reply.RequestListener(
                self.conf, self.conn, self.disp, self._db)

            logger.set_dcm_connection(self.conf, self.conn)

            self.conn.connect(self.request_listener.incoming_parent_q_message,
                              self.handshaker)
            self.disp.start_workers(self.request_listener)

            if self.conf.intrusion_detection_ossec:
                self.intrusion_detection =\
                    ossec.AlertSender(self.conn, self._db)
                self.intrusion_detection.start()

            rc = self.agent_main_loop()
            return rc
        finally:
            self.cleanup_agent()

    def agent_main_loop(self):
        while not self.shutting_down:
            try:
                events.global_space.poll()
            except Exception as ex:
                utils.log_to_dcm(
                    logging.ERROR,
                    "An unexpected error occurred in the agent: %s"
                    % str(ex))
                self.g_logger.exception("A top level exception occurred")

    def cleanup_agent(self):
        systemstats.clean_up_all()
        if self.intrusion_detection:
            self.intrusion_detection.stop()
        if self.db_cleaner:
            self.g_logger.debug("Shutting down the db cleaner runner")
            self.db_cleaner.done()
            self.db_cleaner.join()
        self.g_logger.debug("Shutting down the job runner")
        self.conf.stop_job_runner()
        if self.request_listener:
            self.g_logger.debug("Stopping the reply listener")
            self.request_listener.shutdown()
        if self.disp:
            self.g_logger.debug("Stopping the dispatcher")
            self.disp.stop()
        if self.conn:
            self.g_logger.debug("Closing the connection")
            self.conn.close()

        self.g_logger.debug("Waiting for all threads and callbacks in the "
                            "event system.")
        events.global_space.reset()
        self.g_logger.debug("Service closed")


def console_log(cli_args, level, msg, **kwargs):
    vb_level = getattr(cli_args, "verbose", 0)
    if level > vb_level:
        return
    print(msg % kwargs, file=sys.stderr)


def _gather_info(conf):
    output_tar_path = "/tmp/agent_info.tar.gz"
    tar = tarfile.open(output_tar_path, "w:gz")

    if os.path.exists(conf.storage_base_dir):
        tar.add(conf.storage_base_dir)
    try:
        effective_cloud = cm.guess_effective_cloud(conf)
    except:
        effective_cloud = "Not able to determine cloud"

    platform = (conf.platform_name, conf.platform_version)

    try:
        startup_script = conf.meta_data_object.get_startup_script()
    except Exception as ex:
        startup_script = "Not able to retrieve startup script: " + str(ex)

    version = dcm.agent.g_version
    protocol_version = dcm.agent.g_protocol_version
    message = "Effective cloud is: " + effective_cloud + "\n"
    message += "Platform is %s %s" % (platform[0], platform[1]) + "\n"
    message += "Version: " + version + "\n"
    message += "Protocol version: " + str(protocol_version)

    if startup_script:
        with open("/tmp/startup_script.txt", "w") as ss:
            ss.write(startup_script)

    with open("/tmp/meta_info.txt", "w") as mi:
        mi.write(message)

    # gather processes
    with open("/tmp/process_info.txt", "w") as pi:
        for p in [x for x in psutil.process_iter()
                  if x.username() == conf.system_user]:
            try:
                pi.write(p.name() + " : " + str(p.pid) + os.linesep)
                pi.write("\tstarted at: " + str(p.create_time()) + os.linesep)
                pi.write("\t: " + str(p.cmdline()) + os.linesep)
                pi.write("\t" + str(p.get_cpu_times()) + os.linesep)
                pi.write("\t" + str(p.get_memory_info()) + os.linesep)
            except psutil.AccessDenied:
                # the process list may change
                pass
            except psutil.NoSuchProcess:
                pass

    files_to_collect = ["/tmp/boot.log",
                        "/tmp/error.log",
                        "/var/log/cloud-init-output.log",
                        "/var/log/cloud-init.log",
                        "/var/log/boot.log",
                        "/tmp/meta_info.txt",
                        "/tmp/startup_script.txt",
                        "/tmp/process_info.txt"]

    for f in files_to_collect:
        if os.path.isfile(f):
            tar.add(f)

    tar.close()

    print("""
**********************************************************************
To get all log and configuration file copy %s to
your local machine
**********************************************************************
""" % output_tar_path)
    return output_tar_path


def parse_command_line(argv):
    conf_parser = argparse.ArgumentParser(description="Start the agent")
    conf_parser.add_argument(
        "-c", "--conffile", help="Specify config file", metavar="FILE",
        default=None)
    conf_parser.add_argument("-v", "--verbose", action="count",
                             help="Display more output on the console.",
                             default=0)
    conf_parser.add_argument("-V", "--version", action="store_true",
                             help="Display just the version of this "
                                  "agent installation.",
                             dest="version",
                             default=False)
    conf_parser.add_argument("-r", "--report", action="store_true",
                             help="Get debug info on agent installation.",
                             dest="report",
                             default=False)
    return conf_parser.parse_known_args(args=argv)


def start_main_service(cli_args):
    agent = None
    try:
        config_files = config.get_config_files(conffile=cli_args.conffile)
        conf = config.AgentConfig(config_files)
        agent = DCMAgent(conf)
        agent.pre_threads()
        if cli_args.version:
            print("Version %s" % dcm.agent.g_version)
            return 0

        if cli_args.report:
            utils._g_logger.disabled = True
            cm._g_logger.disabled = True
            config._g_logger.disabled = True
            agent.g_logger.disabled = True
            _gather_info(conf)
            return 0

        utils.verify_config_file(conf)
        conf.start_job_runner()
        agent.run_agent()
    except exceptions.AgentOptionException as aoex:
        console_log(cli_args, 0, "The agent is not configured properly. "
                    "please check the config file.")
        console_log(cli_args, 0, str(aoex))
        if agent:
            agent.shutdown_main_loop()
        if getattr(cli_args, "verbose", 0) > 2:
            raise
    except Exception:
        _g_logger = logging.getLogger(__name__)
        console_log(
            cli_args,
            0, "Shutting down due to a top level exception")
        _g_logger.exception("An unknown exception bubbled to the top")
        if agent:
            agent.shutdown_main_loop()
        raise
    return 0


def get_status(cli_args):
    config_files = config.get_config_files(conffile=cli_args.conffile)
    conf = config.AgentConfig(config_files)

    db_obj = messaging.persistence.SQLiteAgentDB(conf.storage_dbfile)

    complete = db_obj.get_all_complete()
    replied = db_obj.get_all_reply()
    rejected = db_obj.get_all_rejected()
    acked = db_obj.get_all_ack()
    reply_nacked = db_obj.get_all_reply_nacked()
    status = "UNKNOWN"
    color_func = clint.textui.colored.yellow

    def _check_command(cmd):
        try:
            payload_doc = request_doc['payload']
            command = payload_doc['command']
            if command == cmd:
                return True
        except:
            pass
        return False

    for r in complete:
        request_doc = json.loads(r.request_doc)
        if _check_command("initialize"):
            status = "INITIALIZED"
            color_func = clint.textui.colored.green
    for r in acked:
        request_doc = json.loads(r.request_doc)
        if _check_command("initialize"):
            status = "INITIALIZING"
            color_func = clint.textui.colored.green
    for r in replied:
        request_doc = json.loads(r.request_doc)
        if _check_command("initialize"):
            status = "INITIALIZING"
            color_func = clint.textui.colored.green
    for r in reply_nacked:
        request_doc = json.loads(r.request_doc)
        if _check_command("initialize"):
            status = "UNKNOWN INITIALIZATION STATE"
            color_func = clint.textui.colored.red

    for r in rejected:
        request_doc = json.loads(r.request_doc)
        if _check_command("initialize"):
            status = "INITIALIZATION REJECTED"
            color_func = clint.textui.colored.red

    clint.textui.puts(color_func(status))
    complete = db_obj.get_all_complete()
    replied = db_obj.get_all_reply()
    rejected = db_obj.get_all_rejected()
    acked = db_obj.get_all_ack()
    reply_nacked = db_obj.get_all_reply_nacked()

    label_col_width = 30
    vals = [(complete, "Commands processed: "),
            (rejected, "Commands rejected: "),
            (acked, "Commands being processed: "),
            (replied, "Commands being replying to: "),
            (reply_nacked, "Replies rejected: ")]
    with clint.textui.indent(4):
        for v, k in vals:
            clint.textui.puts(
                clint.textui.columns([k, label_col_width], [str(len(v)), 5]))

    try:
        pid_file = os.path.join(conf.storage_base_dir, "dcm-agent.pid")
        if not os.path.exists(pid_file):
            run_status = "NOT RUNNING"
            run_reason = "PID file not found"
        else:
            with open(pid_file, "r") as fptr:
                pid = int(fptr.read().strip())
            p = psutil.Process(pid)
            clint.textui.puts(clint.textui.colored.green("RUNNING"))
            start_time_str = datetime.datetime.fromtimestamp(
                p.create_time()).strftime("%Y-%m-%d %H:%M:%S")
            with clint.textui.indent(4):
                clint.textui.puts(clint.textui.columns(
                    ["Started at:", label_col_width],
                    [start_time_str, 70 - label_col_width]))
                clint.textui.puts(clint.textui.columns(
                    ["User:", label_col_width],
                    [p.username(), 70 - label_col_width]))
                clint.textui.puts(clint.textui.columns(
                    ["Status:", label_col_width],
                    [p.status(), 70 - label_col_width]))
                clint.textui.puts(clint.textui.columns(
                    ["Pid:", label_col_width],
                    [str(pid), 70 - label_col_width]))

            return 0
    except psutil.NoSuchProcess:
        run_status = "NOT RUNNING"
        run_reason = "The PID %d was not found" % pid
    except Exception as ex:
        run_reason = str(ex)
        run_status = "UNKNOWN"

    clint.textui.puts(clint.textui.colored.red(run_status))
    clint.textui.puts(clint.textui.colored.red(run_reason))

    return 1


def main(args=sys.argv):
    cli_args, remaining_argv = parse_command_line(args)

    if remaining_argv and len(remaining_argv) > 1 and \
            remaining_argv[1].lower() == "status":
        # do status reporting
        return get_status(cli_args)
    else:
        # start main service
        return start_main_service(cli_args)

if __name__ == '__main__':
    rc = main()
    sys.exit(rc)
