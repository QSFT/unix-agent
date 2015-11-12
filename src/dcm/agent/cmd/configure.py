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
# this program simply creates the configuration file needed by the agent
# it is assumed that all of the directories have already been created with
# the proper permissions
from __future__ import print_function

import argparse
import configparser
import glob
import os
import shutil
import sys
import textwrap
import urllib.parse

import dcm.agent
import dcm.agent.cloudmetadata as cloudmetadata
import dcm.agent.config as config
import dcm.agent.utils as agent_utils


# below are the variables with no defaults that must be determined
cloud_choice = None
g_user_env_str = "DCM_USER"
g_basedir_env_str = "DCM_BASEDIR"


_g_bundled_cert_file = "/opt/dcm-agent/embedded/ssl/certs/cacert.pem"
_g_cert_warning = """
*****************************************************************************
                             WARNING
                             -------
The certificate file %s is bundled /opt/dcm-agent/embedded/ssl/certs/cacert.pem
with the agent and  must be maintained manually.  There is no daemon running
that will update the certificates in it or enforce revocation policies.
*****************************************************************************
""" % _g_bundled_cert_file


cloud_choices = [i for i in
                 dir(cloudmetadata.CLOUD_TYPES) if not i.startswith("__")]


def setup_command_line_parser():
    parser = argparse.ArgumentParser(
        description='DCM Agent Installer for linux.')

    parser.add_argument("--cloud", "-c", metavar="{Amazon, etc...}",
                        dest="cloud",
                        help="The cloud where this virtual machine will be "
                             "run.  Options: %s" % ", ".join(cloud_choices))

    parser.add_argument("--url", "-u", dest="url",
                        help="The location of the dcm web socket listener")

    parser.add_argument("--verbose", "-v", dest="verbose",
                        action='store_true',
                        default=False,
                        help="Increase the amount of output produced by the "
                             "script.")

    parser.add_argument("--initial", "-I", dest="initial",
                        action='store_true',
                        default=False,
                        help=argparse.SUPPRESS)

    parser.add_argument("--interactive", "-i", dest="interactive",
                        action='store_true',
                        default=False,
                        help="Run an interactive session where questions "
                             "will be asked and answered vi stdio.")

    parser.add_argument("--base-path", "-p",
                        dest="base_path",
                        help="The path to enstratius")

    parser.add_argument("--mount-point", "-m",
                        dest="mount_path",
                        help="The path to mount point")

    parser.add_argument("--on-boot", "-B",
                        dest="on_boot",
                        action='store_true',
                        default=False,
                        help="Setup the agent to start when the VM boots")

    parser.add_argument("--reload-conf", "-r",
                        dest="reload",
                        help="The previous config file that will be used "
                             "to populate defaults.")

    parser.add_argument("--rewrite-logging-plugin", "-R",
                        dest="rewrite_logging_plugin",
                        action="store_true",
                        default=False,
                        help="When reconfiguring the agent with -r option "
                             "You can additionally specifiy this option to"
                             "force the overwrite of plugin and logging configs.")

    parser.add_argument("--temp-path", "-t",
                        dest="temp_path",
                        help="The temp path")

    parser.add_argument("--user", "-U",
                        dest="user",
                        help="The system user that will run the agent.")

    parser.add_argument("--connection-type", "-C",
                        dest="con_type",
                        help="The type of connection that will be formed "
                             "with the agent manager.")

    parser.add_argument("--logfile", "-l", dest="logfile")

    parser.add_argument("--loglevel", "-L",
                        dest="loglevel",
                        default="INFO",
                        help="The level of logging for the agent.")

    parser.add_argument("--install-extras",
                        dest="install_extras",
                        action='store_true',
                        help='to install addition set of packages (puppet etc)'
                             ' now which are needed for certain actions. '
                             'If this is not set at boot time the packages '
                             'will still be downloaded and installed on '
                             'demand')

    parser.add_argument("--extra-package-location",
                        dest="extra_package_location",
                        default="https://linux-stable-agent.enstratius.com/",
                        help="The URL of the dcm-agent-extras package which "
                             "contains additional software dependencies "
                             "needed for some commands.")

    parser.add_argument("--package-name",
                        dest="package_name",
                        default=None,
                        help="Name of the extra package to be installed.")

    parser.add_argument("--chef-client", "-o", dest="chef-client",
                        action='store_true',
                        default=False,
                        help="This is just a placeholder for now.")

    parser.add_argument("--allow-unknown-certs", "-Z",
                        dest="allow_unknown_certs",
                        action='store_true',
                        default=False,
                        help="Disable cert validation.  In general this is a"
                             "bad idea but is very useful for testing.")

    parser.add_argument("--cacert-file", "-A", dest="cacert_file",
                        default=None)

    parser.add_argument("--intrusion-detection-ossec", "-d",
                        dest="intrusion_detection_ossec",
                        action='store_true',
                        default=False,
                        help="Flag to install and start ossec.  In addition the agent will process alerts.")

    return parser


def _get_input(prompt):
    return input(prompt)


def select_cloud(default=cloudmetadata.CLOUD_TYPES.Amazon):
    """
    :param default:
    :return:
    """

    for i, cloud_name in enumerate(cloud_choices):
        col = "%2d) %-13s" % (i, cloud_name)
        print(col)

    cloud = None
    while cloud is None:
        input_str = _get_input("Select your cloud (%s): " % default)
        input_str = input_str.strip().lower()
        if not input_str:
            input_str = default.lower()
        if input_str in [i.lower() for i in cloud_choices]:
            return input_str
        try:
            ndx = int(input_str)
            cloud = cloud_choices[ndx]
        except:
            print("%s is not a valid choice." % input_str)
    return cloud


def guess_default_cloud(conf_d):
    (h, cloud_name) = conf_d["cloud"]["type"]
    if cloud_name != cloudmetadata.CLOUD_TYPES.UNKNOWN:
        return
    conf = config.AgentConfig([])
    name = cloudmetadata.guess_effective_cloud(conf)
    if name is None:
        raise Exception("Cloud %s is not a known type." % cloud_name)
    print("The detected cloud is " + name)
    conf_d["cloud"]["type"] = (h, name)


def normalize_cloud_name(conf_d):
    (h, cloud) = conf_d["cloud"]["type"]
    name = cloudmetadata.normalize_cloud_name(cloud)
    if name is None:
        raise Exception("Cloud %s is not a known type." % cloud)
    conf_d["cloud"]["type"] = (h, name)


def pick_meta_data(conf_d):
    (_, cloud) = conf_d["cloud"]["type"]
    if cloud == cloudmetadata.CLOUD_TYPES.Amazon:
        mu = "http://169.254.169.254/latest/meta-data/"
    elif cloud == cloudmetadata.CLOUD_TYPES.Eucalyptus:
        mu = "http://169.254.169.254/1.0/meta-data/"
    elif cloud == cloudmetadata.CLOUD_TYPES.OpenStack:
        mu = "http://169.254.169.254/openstack/2012-08-10/meta_data.json"
    elif cloud == cloudmetadata.CLOUD_TYPES.Google:
        mu = "http://metadata.google.internal/computeMetadata/v1"
    elif cloud == cloudmetadata.CLOUD_TYPES.DigitalOcean:
        mu = "http://169.254.169.254/metadata/v1"
    elif cloud == cloudmetadata.CLOUD_TYPES.CloudStack:
        mu = None
    elif cloud == cloudmetadata.CLOUD_TYPES.CloudStack3:
        mu = None
    else:
        return None

    (h, _) = conf_d["cloud"]["metadata_url"]
    conf_d["cloud"]["metadata_url"] = (h, mu)


def get_default_conf_dict():
    conf_dict = {}
    option_list = config.build_options_list()

    for c in option_list:
        if c.hidden:
            continue

        s_d = {}
        if c.section in conf_dict:
            s_d = conf_dict[c.section]
        else:
            conf_dict[c.section] = s_d

        s_d[c.name] = (c.get_help(), c.get_default())
    return conf_dict


def update_from_config_file(conf_file, conf_dict):
    # pull from the existing config file
    parser = configparser.ConfigParser()
    parser.read([conf_file])

    for s in parser.sections():
        if s in conf_dict:
            sd = conf_dict[s]
        else:
            sd = {}
            conf_dict[s] = sd

        items_list = parser.items(s)
        for (key, value) in items_list:
            help_str = None
            if key in conf_dict:
                (help_str, _) = sd[key]
            sd[key] = (help_str, value)


def write_conf_file(dest_filename, conf_dict):

    with open(dest_filename, "w") as fptr:
        for section_name in conf_dict:
            sd = conf_dict[section_name]
            fptr.write("[%s]%s" % (section_name, os.linesep))

            for item_name in sd:
                (help_str, value) = sd[item_name]
                if help_str:
                    help_lines = textwrap.wrap(help_str, 79)
                    for h in help_lines:
                        fptr.write("# %s%s" % (h, os.linesep))
                if value is None:
                    fptr.write("#%s=" % item_name)
                else:
                    if type(value) == list:
                        value = str(value)[1:-1]
                    fptr.write("%s=%s" % (item_name, str(value)))

                fptr.write(os.linesep)

            fptr.write(os.linesep)


def make_dirs(conf_d):
    (_, base_path) = conf_d["storage"]["base_dir"]

    dirs_to_make = [
        (base_path, 0o755),
        (os.path.join(base_path, "bin"), 0o750),
        (conf_d["storage"]["script_dir"][1], 0o750),
        (os.path.join(base_path, "etc"), 0o700),
        (os.path.join(base_path, "logs"), 0o700),
        (os.path.join(base_path, "home"), 0o750),
        (os.path.join(base_path, "secure"), 0o700),
        (conf_d["storage"]["temppath"][1], 0o1777),
    ]

    for (directory, mod) in dirs_to_make:
        try:
            os.mkdir(directory)
        except OSError as ex:
            if ex.errno != 17:
                raise
        os.chmod(directory, mod)

    print("...Done.")


def do_set_owner_and_perms(conf_d):
    (_, script_dir) = conf_d["storage"]["script_dir"]
    (_, base_path) = conf_d["storage"]["base_dir"]
    (_, user) = conf_d["system"]["user"]

    for f in os.listdir(script_dir):
        os.chmod(os.path.join(script_dir, f), 0o550)

    with open(os.path.join(script_dir, "variables.sh"), "w") as fptr:
        fptr.write("DCM_USER=%s" % user)
        fptr.write(os.linesep)
        fptr.write("DCM_BASEDIR=%s" % base_path)
        fptr.write(os.linesep)
        fptr.write(os.linesep)

    print("Changing ownership to %s:%s" % (user, user))
    os.system("chown -R %s:%s %s" % (user, user, base_path))


def merge_opts(conf_d, opts):

    map_opts_to_conf = {
        "cloud": ("cloud", "type"),
        "user": ("system", "user"),
        "url": ("connection", "agentmanager_url"),
        "base_path": ("storage", "base_dir"),
        "temp_path": ("storage", "temppath"),
        "con_type": ("connection", "type"),
        "mount_path": ("storage", "mountpoint"),
        "extra_package_location": ("extra", "location"),
        "package_name": ("extra", "package_name"),
        "allow_unknown_certs": ("connection", "allow_unknown_certs"),
        "cacert_file": ("connection", "ca_cert"),
        "intrusion_detection_ossec": ("intrusion_detection", "ossec")
    }
    for opts_name in map_opts_to_conf:
        (s, i) = map_opts_to_conf[opts_name]

        if s not in conf_d:
            conf_d[s] = {}
        sd = conf_d[s]
        v = getattr(opts, opts_name, None)
        h = None
        if i in sd:
            (h, _) = sd[i]
        if v is not None:
            sd[i] = (h, v)


def do_plugin_conf(conf_d):
    (_, base_dir) = conf_d["storage"]["base_dir"]
    (_, dest_plugin_path) = conf_d["plugin"]["configfile"]
    root_dir = dcm.agent.get_root_location()
    src_pluggin_path = os.path.join(root_dir, "etc", "plugin.conf")
    shutil.copy(src_pluggin_path, dest_plugin_path)


def do_logging_conf(conf_d, opts):
    (_, base_dir) = conf_d["storage"]["base_dir"]
    (_, dest_logging_path) = conf_d["logging"]["configfile"]
    root_dir = dcm.agent.get_root_location()
    src_logging_path = os.path.join(root_dir, "etc", "logging.yaml")
    shutil.copy(src_logging_path, dest_logging_path)

    if opts.logfile is None:
        log_file = os.path.join(base_dir, "logs", "agent.log")
    else:
        log_file = opts.logfile

    with open(src_logging_path, "r") as fptr:
        lines = fptr.readlines()

    with open(dest_logging_path, "w") as fptr:
        for line in lines:
            line = line.replace("@LOGFILE_PATH@", log_file)
            line = line.replace("@LOG_LEVEL@", opts.loglevel)
            line = line.replace("@DCM_USER@", conf_d["system"]["user"][1])
            fptr.write(line)


def copy_scripts(conf_d):
    (h, dest_dir) = conf_d["storage"]["script_dir"]
    src_script_dir = os.path.join(
        config.get_python_script_dir(), 'common-linux')
    for s in glob.glob("%s/*" % os.path.abspath(src_script_dir)):
        if os.path.isfile(s):
            d = os.path.basename(s)
            shutil.copy(s, os.path.join(dest_dir, d))


def update_relative_paths(conf_d):
    (_, base_dir) = conf_d["storage"]["base_dir"]

    def _val_update(section_name, item_name, default_val):
        h = ""
        try:
            (h, val) = conf_d[section_name][item_name]
        except:
            val = None
        if val is None:
            val = os.path.join(base_dir, default_val)
            conf_d[section_name][item_name] = (h, val)

    _val_update("logging", "configfile", "etc/logging.yaml")
    _val_update("plugin", "configfile", "etc/plugin.conf")
    _val_update("storage", "script_dir", "bin")


def get_url(default=None):
    if not default:
        default = "wss://dcm.enstratius.com/agentManager"
    print("Please enter the contact string of the agent manager (%s)"
          % default)
    url = sys.stdin.readline().strip()
    if not url:
        return default

    # validate
    try:
        up = urllib.parse.urlparse(url)
        if up.port is not None:
            int(up.port)
    except Exception:
        raise Exception("The agent manager contact %s is not a valid url"
                        % url)
    allowed_schemes = ["ws", "wss"]
    if up.scheme not in allowed_schemes:
        raise Exception("The url %s does not consist of an allowed scheme. "
                        "Only the follow schemes are allows %s"
                        % (url, str(allowed_schemes)))
    return url


def enable_start_agent(opts):
    ask = opts.interactive
    on_boot = opts.on_boot
    if on_boot:
        ask = False

    if ask:
        print("Would you like to start the agent on boot? (Y/n)")
        ans = sys.stdin.readline().strip()
        on_boot = ans == "" or ans.lower() == "y" or ans.lower() == "yes"
    if on_boot:
        if os.path.exists("/sbin/insserv"):
            os.system("/sbin/insserv dcm-agent")
        elif os.path.exists("/usr/sbin/update-rc.d"):
            os.system("update-rc.d dcm-agent defaults")
        elif os.path.exists("/sbin/chkconfig"):
            os.system("/sbin/chkconfig --add dcm-agent")
        # TODO other platforms


def guess_cacert_location():
    possible_locations = ["/etc/ssl/certs/ca-bundle.crt",
                          "/etc/ssl/certs/ca-certificates.crt",
                          _g_bundled_cert_file]
    for l in possible_locations:
        if os.path.exists(l):
            return l


def cert_check():
    print("Would you like to disable certificate checking? (not recommended) (y/N)")
    ans = sys.stdin.readline().strip()
    return ans == ans.lower() == "y" or ans.lower() == "yes"


def interactive_cert_path():
    default_path = guess_cacert_location()
    print("Please select a default path for certificate file (%s)" %
          default_path)
    ans = sys.stdin.readline().strip()
    if not ans:
        ans = default_path
    return ans


def do_interactive(opts, conf_d):
    if not opts.interactive:
        return
    (h, cloud_type) = conf_d["cloud"]["type"]
    cloud_type = select_cloud(default=cloud_type)
    conf_d["cloud"]["type"] = (h, cloud_type)
    (h, url) = conf_d["connection"]["agentmanager_url"]
    url = get_url(default=url)
    conf_d["connection"]["agentmanager_url"] = (h, url)
    check_certs = cert_check()
    conf_d["connection"]["allow_unknown_certs"] = (h, check_certs)

    (h, cert_path) = conf_d["connection"]["ca_cert"]
    if not check_certs and cert_path is None:
        cert_path = interactive_cert_path()
        conf_d["connection"]["ca_cert"] = (h, cert_path)


def validate_cacerts(conf_d):
    (h, val) = conf_d["connection"]["allow_unknown_certs"]
    if val:
       return

    (h, val) = conf_d["connection"]["ca_cert"]
    if  val is None:
        val = guess_cacert_location()
        if val is None:
            raise Exception("If the unknown certificates are not allowed you must specify a cert file with the --cacert-file option.")
        conf_d["connection"]["ca_cert"] = (h, val)
    if val == _g_bundled_cert_file:
        print(_g_cert_warning)


def gather_values(opts):
    # get the default values based on the defaults set in the config object
    conf_d = get_default_conf_dict()
    # if we are reloading from a file override the defaults with what is in
    # that file
    if opts.reload:
        update_from_config_file(opts.reload, conf_d)
    # override any values passed in via options
    merge_opts(conf_d, opts)
    # set defaults for relative paths
    update_relative_paths(conf_d)

    return conf_d


def cleanup_previous_install(conf_d):
    # delete old DB if it exists
    (_, db_file) = conf_d['storage']['dbfile']
    if db_file and os.path.exists(db_file):
        os.remove(db_file)


def main(argv=sys.argv[1:]):
    parser = setup_command_line_parser()
    opts = parser.parse_args(args=argv)

    opts.loglevel = opts.loglevel.upper()
    if opts.loglevel not in ["ERROR", "WARN", "INFO", "DEBUG"]:
        print("WARNING: %s is an invalid log level.  Using INFO"
              % opts.loglevel)
        opts.loglevel = "INFO"

    conf_d = gather_values(opts)
    if not opts.initial:
        guess_default_cloud(conf_d)
    do_interactive(opts, conf_d)
    normalize_cloud_name(conf_d)
    pick_meta_data(conf_d)
    validate_cacerts(conf_d)

    # before writing anything make sure that all the needed values are
    # set
    if not opts.initial:
        if not conf_d["system"]["user"]:
            raise Exception("You must set the user name that will run "
                            "this service.")
        if not conf_d["storage"]["base_dir"]:
            raise Exception("You must set the base dir for this service "
                            "installation.")

    try:
        make_dirs(conf_d)
        (_, base_dir) = conf_d["storage"]["base_dir"]
        if not opts.reload:
            copy_scripts(conf_d)
            do_plugin_conf(conf_d)
            do_logging_conf(conf_d, opts)
        else:
            if not os.path.isfile(os.path.join(base_dir, "etc", "plugin.conf")) or opts.rewrite_logging_plugin:
                do_plugin_conf(conf_d)
            if not os.path.isfile(os.path.join(base_dir, "etc", "logging.yaml")) or opts.rewrite_logging_plugin:
                do_logging_conf(conf_d, opts)
        cleanup_previous_install(conf_d)
        conf_file_name = os.path.join(base_dir, "etc", "agent.conf")
        write_conf_file(conf_file_name, conf_d)
        do_set_owner_and_perms(conf_d)
        if not opts.initial:
            enable_start_agent(opts)

        if opts.install_extras:
            conf = config.AgentConfig([conf_file_name])
            if opts.package_name:
                agent_utils.install_extras(conf, package=opts.package_name)
            else:
                agent_utils.install_extras(conf)

    except Exception as ex:
        print(str(ex), file=sys.stderr)
        if opts.verbose:
            raise
        return 1
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
