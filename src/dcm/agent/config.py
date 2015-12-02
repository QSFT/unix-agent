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
import configparser
import logging
import logging.config
import os
import tempfile
import yaml

import dcm
import dcm.agent.cloudmetadata as cloudmetadata
from dcm.agent.cloudmetadata import CLOUD_TYPES
import dcm.agent.connection.websocket as websocket
import dcm.agent.exceptions as exceptions
import dcm.agent.job_runner as job_runner
from dcm.agent.plugins.api.exceptions import AgentPluginConfigException
import dcm.agent.tests.utils.test_connection as test_connection  # TODO
import dcm.agent.utils as utils


_g_logger = logging.getLogger(__name__)
_g_conf_file_env = "DCM_AGENT_CONF"

print("Hellllooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooo There")
class PLATFORM_TYPES(object):
    PLATFORM_UBUNTU = "ubuntu"
    PLATFORM_RHEL = "rhel"
    PLATFORM_CENTOS = "centos"
    PLATFORM_DEBIAN = "debian"


def get_python_script_dir():
    # we allow it to pull out of the python package for tests and
    # installs that are done from something other than out packaging
    _ROOT = dcm.agent.get_root_location()
    return os.path.join(_ROOT, 'scripts')


def get_connection_object(conf):
    con_type = conf.connection_type
    if not con_type:
        raise exceptions.AgentOptionValueNotSetException("connection_type")

    # XXX should we stevedore load this or __import__ it or go with a
    # hard coded list?  for now hard coded list

    if con_type == "success_tester":
        source_file = conf.connection_source_file
        if not source_file:
            raise exceptions.AgentOptionValueNotSetException(
                "[connection]source_file",
                msg="Using the %s connection type." % con_type)
        fptr = open(source_file, "r")
        if not conf.connection_dest_file:
            raise exceptions.AgentOptionValueNotSetException(
                "[connection]dest_file",
                msg="Using the %s connection type." % con_type)

        outf = open(conf.connection_dest_file, "w")
        con = test_connection.TestConnection(fptr, outf)
    elif con_type == "ws":
        if not conf.connection_agentmanager_url:
            raise exceptions.AgentOptionValueNotSetException(
                "[connection]agentmanager_url")
        con = websocket.WebSocketConnection(
            conf.connection_agentmanager_url,
            backoff_amount=conf.connection_backoff,
            max_backoff=conf.connection_max_backoff,
            heartbeat=conf.connection_heartbeat_frequency,
            allow_unknown_certs=conf.connection_allow_unknown_certs,
            ca_certs=conf.connection_ca_cert)
    else:
        raise exceptions.AgentOptionValueException(
            "[connection]type", con_type, "ws,success_tester,dummy")
    return con


class ConfigOpt(object):

    def __init__(self, section, name, t, default=None,
                 options=None, minv=None, maxv=None, help_msg=None,
                 hidden=False):
        self.section = section
        self.name = name
        self.my_type = t
        self.options = options
        self.default = default
        self.minv = minv
        self.maxv = maxv
        self.help_msg = help_msg
        self.features = {}
        self.hidden = hidden

    def get_option_name(self):
        option_name = "%s_%s" % (self.section, self.name)
        return option_name

    def get_default(self):
        return self.default

    def get_help(self):
        return self.help_msg

    def get_value(self, parser, default=None, **kwargs):
        if default is None:
            default = self.default
        try:
            v = parser.get(self.section, self.name, fallback=default)
        except configparser.NoOptionError:
            v = default
        except configparser.NoSectionError:
            v = default
        if v is None:
            return v
        try:
            if self.my_type == list:
                v = v.split(",")
            elif self.my_type == bool:
                if type(v) == str:
                    v = (v.lower() == "true" or v.lower() == "yes")
                else:
                    v = bool(v)
            else:
                v = self.my_type(v)
        except ValueError:
            raise exceptions.AgentOptionTypeException(
                self.name, self.my_type, v)

        if self.options is not None:
            vx = v
            if type(v) == str:
                vx = vx.lower()
                if vx not in self.options:
                    raise exceptions.AgentOptionValueException(
                        self.name, self.options, v)

        if self.my_type == int or self.my_type == float:
            if self.minv is not None and v < self.minv:
                raise exceptions.AgentOptionRangeException(
                    self.name, self.minv, self.maxv)
            if self.maxv is not None and v > self.maxv:
                raise exceptions.AgentOptionValueException(
                    self.name, self.minv, self.maxv)

        return v


class FilenameOpt(ConfigOpt):

    def __init__(self, section, name, default=None, help_msg=None):
        super(FilenameOpt, self).__init__(section, name, str, default=default,
                                          help_msg=help_msg)

    def get_value(self, parser, relative_path=None, **kwarg):
        v = super(FilenameOpt, self).get_value(parser)
        if v is None:
            return None
        if not os.path.isabs(v):
            v = os.path.join(relative_path, v)
        return os.path.abspath(v)


class AgentConfig(object):
    """
    This is a serializable object that is threaded through to all classes.
    When/if multiprocessing is used it will be send to the worker threads.

    It is semi-read-only.  Any write operation must be done with thread
    primitives.  The exception is set handshake because that will be done
    before any thread is created.
    """

    def __init__(self, conf_files):
        self._cli_args = None
        self._remaining_argv = None
        self.instance_id = None
        self.jr = None
        self.state = "STARTING"
        self.features = {}

        self.agent_id = None
        self.customer_id = None

        self.server_id = None
        self.server_name = None
        self.storage_dbfile = None
        self.meta_data_object = None  # until we call set_metadata_object

        self.config_files = conf_files

        self.parse_config_files(build_options_list(), add_features="features")

        #  here is where we set which Meta object to use from cloudmetadata.py
        cloudmetadata.set_metadata_object(self)

        self._normalize_options()

        setup_logging(self.logging_configfile)

    def _normalize_options(self):
        if self.storage_dbfile is None:
            self.storage_dbfile = \
                os.path.join(self.storage_base_dir, "secure", "agentdb.sql")
        if self.storage_script_dir is None:
            self.storage_script_dir = \
                os.path.join(self.storage_base_dir, "bin")
        if self.storage_script_dir == "/PYTHON_LIBS_SCRIPTS":
            self.storage_script_dir = None

        if self.platform_name is None or self.platform_version is None:
            distro_name, distro_version = utils.identify_platform(self)
            self.platform_name = distro_name
            self.platform_version = distro_version

    def get_script_location(self, name):
        if self.storage_script_dir is not None:
            path = os.path.join(self.storage_script_dir, name)
            _g_logger.debug("Script location %s" % path)
            if not os.path.exists(path):
                raise AgentPluginConfigException(
                    "There is no proper configuration for %s" % name)
            return path

        script_dir = get_python_script_dir()
        _g_logger.debug("Script Dir %s" % script_dir)
        for platform in self.platform_script_locations:
            _g_logger.debug("Script platform %s" % platform)
            path = os.path.join(script_dir, platform, name)
            _g_logger.debug("Script location %s" % path)
            if os.path.exists(path):
                return path
        return None

    def is_upgrading(self):
        return False

    def start_job_runner(self):
        self.jr = job_runner.JobRunner(self)

    def stop_job_runner(self):
        if self.jr:
            self.jr.shutdown()
            self.jr = None

    def get_temp_file(self, filename, isdir=False):
        new_dir = tempfile.mkdtemp(dir=self.storage_temppath)
        if isdir:
            return new_dir
        return os.path.join(new_dir, filename)

    def parse_config_files(self, option_list, add_features=None):

        # set all the default values on the agent conf object
        for o in option_list:
            k = o.get_option_name()
            v = o.get_default()
            setattr(self, k, v)

        for config_file in self.config_files:

            relative_path = os.path.dirname(config_file)

            parser = configparser.ConfigParser()
            parser.read(config_file)

            if add_features is not None:
                try:
                    features = parser.items(add_features)
                    for k, v in features:
                        self.features[k] = v
                except configparser.NoSectionError:
                    pass

            for opt in option_list:
                try:
                    oname = opt.get_option_name()
                    v = opt.get_value(parser, relative_path=relative_path,
                                      default=getattr(self, oname))
                    setattr(self, oname, v)
                except configparser.NoSectionError:
                    raise exceptions.AgentOptionSectionNotFoundException(
                        opt.name)

    def get_secure_dir(self):
        token_dir = os.path.join(self.storage_base_dir, "secure")
        if not os.path.exists(token_dir):
            os.mkdir(token_dir, 0o700)
        # At some point we should validate that only this user can read this
        # file
        # utils.validate_file_permissions(
        #     token_dir, username=self.conf.system_user, permissions=0700)
        #
        return token_dir


def build_options_list():
    option_list = [
        ConfigOpt("pydev", "host", str, default=None, options=None,
                  help_msg="The hostname of the pydev debugger"),
        ConfigOpt("pydev", "port", int, default=None, options=None,
                  help_msg="The port where the pydev debugger is listening"),

        ConfigOpt("workers", "count", int, default=2, options=None,
                  help_msg="The number of worker threads that will be "
                           "processing incoming requests"),

        ConfigOpt("workers", "long_runner_threads", int, default=1,
                  options=None,
                  help_msg="The number of worker threads that will be "
                           "processing long running plugins (anything that "
                           "returns a job description)"),

        ConfigOpt("connection", "type", str, default="ws", options=None,
                  help_msg="The type of connection object to use.  Supported "
                           "types are ws and fallback"),
        FilenameOpt("connection", "source_file", default=None),
        FilenameOpt("connection", "dest_file", default=None),
        ConfigOpt("connection", "agentmanager_url", str, default=None,
                  help_msg="The url of the agent manager with which this "
                           "agent will communicate."),
        ConfigOpt("connection", "backoff", int, default=1000,
                  help_msg="The number of milliseconds to add to the wait "
                           "time before retrying a failed connection."),
        ConfigOpt("connection", "max_backoff", int, default=300000,
                  help_msg="The maximum number of milliseconds to wait before "
                           "retrying a failed connection."),
        ConfigOpt("connection", "heartbeat_frequency", int, default=30,
                  help_msg="The maximum number of milliseconds to wait before "
                           "retrying a failed connection."),
        ConfigOpt("connection", "allow_unknown_certs", bool, default=False,
                  help_msg="A flag to disable DCM certificate verification. "
                           "When disabled certificates will be ignored. This "
                           "is useful for testing but should otherwise be "
                           "set to False."),
        FilenameOpt("connection", "ca_cert", default=None,
                    help_msg="A path to the location of the CA certificate to"
                             "be used when authenticating with DCM."),

        FilenameOpt("logging", "configfile", default=None,
                    help_msg="The location of the log configuration file"),
        FilenameOpt("plugin", "configfile",
                    help_msg="The location of the plugin configuration file"),

        FilenameOpt("storage", "temppath", default="/tmp"),
        FilenameOpt("storage", "base_dir", default="/dcm"),
        FilenameOpt("storage", "mountpoint", default="/mnt/dcmdata"),
        FilenameOpt("storage", "dbfile", default=None),
        FilenameOpt("storage", "script_dir", default=None),

        ConfigOpt("storage", "db_timeout", int, default=60*60*4,
                  help_msg="The amount of time in seconds for a request id to "
                           "stay in the database."),
        ConfigOpt("storage", "default_filesystem", str, default="ext3"),

        ConfigOpt("system", "user", str, default="dcm"),
        ConfigOpt("system", "sudo", str, default="/usr/bin/sudo"),

        ConfigOpt("intrusion_detection", "ossec", bool, default=False),
        ConfigOpt("intrusion_detection", "max_process_time", float, default=5.0,
                  help_msg="This value specifics the amount of time that must "
                           "expire between processing the alerts file.  This "
                           "value is here to prevent too many frequent alerts "
                           "from overwhelming the agent."),
        ConfigOpt("intrusion_detection", "alert_threshold", float, default=5,
                  help_msg="The ossec alert level threshold to send to dcm."
                           " Any alert level below this threshold will be"
                           " logged locally but not forwarded back to DCM."),

        ConfigOpt("cloud", "type", str, default=CLOUD_TYPES.UNKNOWN,
                  help_msg="The type of cloud on which this agent is running"),
        ConfigOpt("cloud", "metadata_url", str,
                  default=None,
                  help_msg="The url of the metadata server.  Not applicable "
                           "to all clouds."),

        ConfigOpt("messaging", "retransmission_timeout", float,
                  default=5.0),
        ConfigOpt("messaging", "max_at_once", int, default=-1,
                  help_msg="The maximum number of commands that can be "
                           "outstanding at once.  -1 means infinity."),

        ConfigOpt("platform", "script_locations", list,
                  default="common-linux"),
        ConfigOpt("platform", "name", str, default=None,
                  help_msg="The platform/distribution on which this agent is"
                           "being installed.  Must be used with "
                           "[platform]version.",
                  options=["ubuntu", "debian", "rhel",
                           "centos", "fedora"]),
        ConfigOpt(
            "platform", "version", str, default=None,
            help_msg="The platform/distribution version on which this "
                     "agent is being installed.  Must be used with "
                     "[platform]name."),
        ConfigOpt("jobs", "retain_job_time", int, default=3600),
        ConfigOpt("test", "skip_handshake", bool, default=False,
                  help_msg="This value is for internal testing only.  "
                           "Do not change it.", hidden=True),

        ConfigOpt("extra", "location", str,
                  default='http://s3.amazonaws.com/es-pyagent/',
                  help_msg="Location of extra packages"),

        ConfigOpt("extra", "package_name", str, default=None,
                  help_msg="Name of extra package to be installed"),

        ConfigOpt("extra", "base_path", str, default="/opt/dcm-agent-extras",
                  help_msg="The location where the extras package will be "
                           "installed.  This should only change in conjunction"
                           " with the extras omnibus installer.")
    ]

    return option_list


def setup_logging(logging_configfile):
    top_logger = 'dcm.agent'

    if logging_configfile is None:
        loghandler = logging.StreamHandler()
        top_logger = logging.getLogger("")
        top_logger.setLevel(logging.DEBUG)
        top_logger.addHandler(loghandler)
        return

    if not os.path.exists(logging_configfile):
        raise exceptions.AgentOptionPathNotFoundException(
            "logging:configfile", logging_configfile)

    with open(logging_configfile, 'rt') as f:
        config = yaml.load(f.read())
        logging.config.dictConfig(config)


def get_config_files(conffile=None):
    candidates = ["/dcm/etc/agent.conf"]
    if _g_conf_file_env in os.environ:
        candidates.append(os.environ[_g_conf_file_env])
    if conffile:
        candidates.append(conffile)

    locations = []
    for f in candidates:
        f = os.path.abspath(f)
        if os.path.exists(f):
            if f not in locations:
                locations.append(f)

    return locations

