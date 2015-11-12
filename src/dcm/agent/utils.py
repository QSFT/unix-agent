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
import logging
import netifaces
import os
import platform
import pwd
import subprocess
import sys
import tempfile
import traceback
import urllib.error
import urllib.parse
import urllib.request

import dcm
import dcm.agent.exceptions as exceptions
import dcm.agent.logger as dcm_logger


_g_logger = logging.getLogger(__name__)

_g_map_platform_installer = {
    "ubuntu": ["/usr/bin/dpkg", "-i"],
    "debian": ["/usr/bin/dpkg", "-i"],
    "centos": ["/bin/rpm", "-Uvh"],
    "rhel": ["/bin/rpm", "-Uvh"]
}

_g_map_platform_remove_package = {
    "ubuntu": ["/usr/bin/dpkg", "--purge"],
    "debian": ["/usr/bin/dpkg", "--purge"],
    "centos": ["/bin/rpm", "-e"],
    "rhel": ["/bin/rpm", "-e"]
}

_g_extras_pkgs_name = "dcm-agent-extras"


class OperationalState(object):
    OK = "OK"
    EXCESS_RESOURCES = "EXCESS_RESOURCES"
    CONSTRAINED_RESOURCES = "CONSTRAINED_RESOURCES"
    TERMINATED = "TERMINATED"
    NOT_RESPONDING = "NOT_RESPONDING"
    AGENT_FAILURE = "AGENT_FAILURE"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"


# A decorator for abstract classes
def not_implemented_decorator(func):
    def call(self, *args, **kwargs):
        def raise_error(func):
            raise exceptions.AgentNotImplementedException(
                func_name=func.__name__)
        return raise_error(func)
    return call


def class_method_sync(func):
    def wrapper(self, *args, **kwargs):
        self.lock()
        try:
            return func(self, *args, **kwargs)
        finally:
            self.unlock()
    return wrapper


def verify_config_file(opts):
    must_haves = ["connection_type", "cloud_type", "platform_name",
                  "connection_agentmanager_url"]
    warn_haves = ["cloud_metadata_url"]

    for must in must_haves:
        try:
            getattr(opts, must)
        except:
            raise exceptions.AgentOptionValueNotSetException(
                must, msg="Please check your config file.")

    for warn in warn_haves:
        try:
            getattr(opts, warn)
        except:
            _g_logger.warn("Please check the config file.  The value %s is "
                           "missing and could be needed." % warn)


def setup_remote_pydev(host, port):
    try:
        import pydevd

        pydevd.settrace(host,
                        port=port,
                        stdoutToServer=True,
                        stderrToServer=True,
                        suspend=True)

        return True
    except Exception:
        return False


def run_command(conf, cmd_line, cwd=None, in_env=None):
    _, log_file = tempfile.mkstemp(dir=conf.storage_temppath)
    env = {b"DCM_USER": conf.system_user.encode('utf-8'),
           b"DCM_BASEDIR": conf.storage_base_dir.encode('utf-8'),
           b"DCM_TMP_DIR": conf.storage_temppath.encode('utf-8'),
           b"DCM_LOG_FILE": log_file.encode('utf-8'),
           b"DCM_PYTHON": sys.executable.encode('utf-8')}
    if conf.platform_name:
        env[b"DCM_AGENT_PLATFORM_NAME"] = conf.platform_name
    if conf.platform_version:
        env[b"DCM_AGENT_PLATFORM_VERSION"] = conf.platform_version
    if 'PATH' in os.environ:
        env[b'PATH'] = os.environ['PATH']
    if in_env is not None:
        env.update(in_env)
    if conf.jr is not None:
        rc = conf.jr.run_command(cmd_line, cwd=cwd, env=env)
    else:
        _g_logger.warn("Running without the job runner process")
        process = subprocess.Popen(cmd_line,
                                   shell=False,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=cwd,
                                   env=env)
        stdout, stderr = process.communicate()
        if stdout is not None:
            stdout = stdout.decode()
        else:
            stdout = ""
        if stderr is not None:
            stderr = stderr.decode()
        else:
            stderr = ""

        rc = (stdout, stderr, process.returncode)
    if log_file:
        # read everything logged and send it to the logger
        with open(log_file, "r") as fptr:
            for line in fptr.readlines():
                if line.strip():
                    dcm_logger.log_to_dcm_console_job_details(
                        job_name=str(cmd_line), details=line)
        os.remove(log_file)
    return rc


def run_script(conf, name, args):
    cmd = conf.get_script_location(name)
    args.insert(0, cmd)
    return run_command(conf, args)


def safe_delete(fname):
    try:
        os.remove(fname)
        return True
    except OSError as osEx:
        if osEx.errno == 2:
            return True
        return False


def make_id_string(prefix, uid):
    return "%s%03d" % (prefix, uid)


def mount(conf, device_id, file_system, mount_point):
    if device_id.startswith("es"):
        device_id = "mapper/" + device_id

    command = [conf.get_script_location("mount"),
               device_id, file_system, mount_point]
    (stdout, stderr, rc) = run_command(conf, command)
    if rc != 0:
        raise exceptions.AgentExecutableException(command, rc, stdout, stderr)
    return rc


def agent_format(conf, device_id, file_system, mount_point, encryption_key):
    enc_str = str(encryption_key is not None).lower()
    command = [conf.get_script_location("format"),
               device_id,
               file_system,
               mount_point,
               enc_str]
    (stdout, stderr, rc) = run_command(conf, command)
    if rc != 0:
        raise exceptions.AgentExecutableException(command, rc, stdout, stderr)
    return rc


def open_encrypted_device(conf, raw_device_id, encrypted_device_id, key_file):
    command = [conf.get_script_location("openEncryption"),
               raw_device_id,
               encrypted_device_id,
               key_file]
    (stdout, stderr, rc) = run_command(conf, command)
    if rc != 0:
        raise exceptions.AgentExecutableException(command, rc, stdout, stderr)
    return rc


def build_assertion_exception(logger, msg):
    details_out = " === Stack trace Begin === " + os.linesep
    for threadId, stack in list(sys._current_frames().items()):
        details_out = details_out + os.linesep + \
            "##### Thread %s #####" % threadId + os.linesep
        for filename, lineno, name, line in traceback.extract_stack(stack):
            details_out = details_out + os.linesep + \
                'File: "%s", line %d, in %s' % (filename, lineno, name)
        if line:
            details_out = details_out + os.linesep + line.strip()

    details_out = details_out + os.linesep + " === Stack trace End === "
    msg = msg + " | " + details_out
    logger.error(msg)
    return msg


def identify_platform(conf):
    distro_name = None
    distro_version = None

    os_release_path = "/etc/lsb-release"
    if os.path.exists(os_release_path):
        with open(os_release_path) as fptr:
            for line in fptr.readlines():
                key, value = line.split("=", 1)
                if key == "DISTRIB_ID":
                    distro_name = value.lower()
                elif key == "DISTRIB_RELEASE":
                    distro_version = value
        if distro_name and distro_version:
            return distro_name.strip(), distro_version.strip()

    lsb = "/usr/bin/lsb_release"
    if os.path.exists(lsb) and os.access(lsb, os.X_OK):
        (stdout, stderr, rc) = run_command(conf, [lsb, "-i"])
        if rc != 0 or not stdout:
            raise exceptions.AgentPlatformNotDetectedException()

        parts = stdout.split()
        if len(parts) != 3:
            raise exceptions.AgentPlatformNotDetectedException()

        cand = parts[2].strip()
        if cand == "Ubuntu":
            distro_name = "ubuntu"
        elif cand == "CentOS":
            distro_name = "centos"
        elif cand == "RedHatEnterpriseServer":
            distro_name = "rhel"
        elif cand == "Debian":
            distro_name = "debian"
        else:
            raise exceptions.AgentPlatformNotDetectedException()

        (stdout, stderr, rc) = run_command(conf, [lsb, "-r"])
        if rc != 0:
            raise exceptions.AgentPlatformNotDetectedException()
        parts = stdout.split()
        distro_version = parts[1].strip()

        return distro_name.strip(), distro_version.strip()

    if os.path.exists("/etc/redhat-release"):
        with open("/etc/redhat-release") as fptr:
            redhat_info = fptr.readline().split()
        if redhat_info[0] == "CentOS":
            if redhat_info[2] == "release":
                distro_version = redhat_info[3]
            else:
                distro_version = redhat_info[2]
            distro_name = "centos"
        elif redhat_info[0] == "Red":
            distro_version = redhat_info[6]
            distro_name = "rhel"
        else:
            raise exceptions.AgentPlatformNotDetectedException()
        return distro_name.strip(), distro_version.strip()

    if os.path.exists("/etc/debian_version"):
        with open("/etc/debian_version") as fptr:
            distro_version = fptr.read().strip()
        distro_name = "debian"
        return distro_name.strip(), distro_version.strip()

    raise exceptions.AgentPlatformNotDetectedException()


def extras_installed(conf):
    return os.path.exists("/opt/dcm-agent-extras")


def extras_remove(conf):
    distro = conf.platform_name
    cmd = _g_map_platform_remove_package[distro][:]
    cmd.append(_g_extras_pkgs_name)
    _g_logger.info("Removing extras with: %s" % cmd)
    (stdout, stderr, rc) = run_command(conf, cmd, in_env=os.environ)
    if rc == 0:
        return True
    return False


def package_suffix(distro_name):
    rpms = ['centos', 'rhel']
    debs = ['debian', 'ubuntu']

    if distro_name.lower() in rpms:
        return "rpm"
    if distro_name.lower() in debs:
        return "deb"
    return None


def http_get_to_file(url, filename):
    try:
        response = urllib.request.urlopen(url)
        with open(filename, "wb") as fptr:
            data = response.read(64*1024)
            while data:
                fptr.write(data)
                data = response.read(64*1024)
    except urllib.error.URLError:
        raise exceptions.AgentRuntimeException(
            "There was a problem connecting to the URL " + url)


def install_extras(conf, package=None):
    if extras_installed(conf):
        return False
    location = conf.extra_location
    pkg_suffix = package_suffix(conf.platform_name)
    # convert a distro version name that potentially a x.y.z... format to x.y
    pkg_version = '.'.join(conf.platform_version.split(".")[:2])

    arch = "i386"
    if platform.machine() == "x86_64":
        if pkg_suffix == "deb":
            arch = "amd64"
        else:
            arch = "x86_64"

    while location.endswith('/'):
        location = location[:-1]
    _g_logger.info("Installing extra packages from %s" % location)

    if not package:
        major_only_pkg_version = conf.platform_version.split(".")[0]
        version = dcm.agent.g_version.split('-')[0]
        package = '%s-%s-%s-%s-%s.%s' %\
                  (_g_extras_pkgs_name,
                   conf.platform_name, pkg_version,
                   arch, version, pkg_suffix)
        major_only_package = '%s-%s-%s-%s-%s.%s' %\
            (_g_extras_pkgs_name,
             conf.platform_name, major_only_pkg_version,
             arch, version, pkg_suffix)
        try_packages = ["%s/%s" % (location, package),
                        "%s/%s" % (location, major_only_package)]
        # add without version names for latest
        package = '%s-%s-%s-%s.%s' %\
                  (_g_extras_pkgs_name,
                   conf.platform_name, pkg_version,
                   arch, pkg_suffix)
        try_packages.append("%s/%s" % (location, package))
        major_only_package = '%s-%s-%s-%s.%s' %\
            (_g_extras_pkgs_name,
             conf.platform_name, major_only_pkg_version,
             arch, pkg_suffix)
        try_packages.append("%s/%s" % (location, major_only_package))
    else:
        try_packages = ["%s/%s" % (location, package)]

    _, pkg_file = tempfile.mkstemp()

    found = False
    _g_logger.debug("Downloading the extras package file")
    for pkg in try_packages:
        try:
            http_get_to_file(pkg, pkg_file)
            found = True
            break
        except BaseException:
            _g_logger.warn("Failed to download the extras package %s.  "
                           "Falling back to the major only version."
                           % try_packages[0])

    if not found:
        raise exceptions.AgentRuntimeException(
            "No extras package was found.  Tried " + str(try_packages))

    install_command = _g_map_platform_installer[conf.platform_name][:]
    install_command.insert(0, conf.system_sudo)
    install_command.append(pkg_file)
    _g_logger.debug("Running: %s" % install_command)
    (stdout, stderr, rc) = run_command(
        conf, install_command, in_env=os.environ)
    if rc != 0:
        raise exceptions.AgentExtrasNotInstalledException(stderr)
    _g_logger.debug(stdout)
    return True


def _get_ipvX_addresses(family):
    ip_list = []
    for iface in netifaces.interfaces():
        try:
            new_addrs = [i['addr']
                         for i in netifaces.ifaddresses(iface)[family]]
            ip_list.extend(new_addrs)
        except KeyError:
            # when there is a key error it means we have nothing to add
            pass
    return ip_list


def get_ipv4_addresses():
    return _get_ipvX_addresses(netifaces.AF_INET)


def get_ipv6_addresses():
    return _get_ipvX_addresses(netifaces.AF_INET6)


def validate_file_permissions(file_path, username=None, permissions=None):
    stat_info = os.stat(file_path)
    if permissions is not None:
        if (stat_info.st_mode & 0o777) != permissions:
            raise exceptions.AgentFilePermissionsException(
                "The path %s does not have the proper permissions" % file_path)

    if username is not None:
        if pwd.getpwuid(stat_info.st_uid).pw_name != username:
            raise exceptions.AgentFilePermissionsException(
                "The path %s is not owned by %s" % (file_path, username))


def get_wire_logger():
    return logging.getLogger("DCM_AGENT_WIRE")


class DeviceTypes(object):
    ROOT = "ROOT"
    EPHEMERAL = "EPHEMERAL"
    CUSTOM = "CUSTOM"


def get_device_mappings(conf):
    command = [conf.get_script_location("listDevices")]

    (stdout, stderr, rc) = run_command(conf, command)
    if rc != 0:
        raise exceptions.AgentExecutableException(command, rc, stdout, stderr)

    try:
        device_mapping_list = []
        lines = stdout.split(os.linesep)
        for line in lines:
            parts = line.split()
            if len(parts) != 5:
                continue

            elements = parts[0].split("/")
            device_id = elements[len(elements) - 1]
            file_system = parts[1]
            mount_point = parts[2]
            try:
                size = int(parts[3])
                used = int(parts[4])
            except ValueError:
                continue
            if parts[0].startswith("/dev/mapper"):
                encrypted = True
            else:
                encrypted = False

            if mount_point == "/":
                device_type = DeviceTypes.ROOT
            elif mount_point == conf.storage_mountpoint:
                device_type = DeviceTypes.EPHEMERAL
            else:
                device_type = DeviceTypes.CUSTOM

            device_mapping = {
                "device_id": device_id,
                "encrypted": encrypted,
                "file_system": file_system,
                "mount_point": mount_point,
                "size":  size,
                "used": used,
                "device_type": device_type
            }
            device_mapping_list.append(device_mapping)
    except Exception as ex:
        _g_logger.exception(str(ex))
        _g_logger.error("listDevice stdout: " + stdout)
        _g_logger.error("listDevice stderr: " + stderr)
        raise

    return device_mapping_list

def ossec_running():

    return False

def start_ossec():
    os.system("/opt/dcm-agent-extras/ossec/bin/ossec-control start")
    return True
