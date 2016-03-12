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
import json
import logging
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

import dcm.agent.exceptions as exceptions
import dcm.agent.utils as utils


_g_logger = logging.getLogger(__name__)
ENV_INJECTED_ID_KEY = "DCM_AGENT_INJECTED_ID"


class CLOUD_TYPES:
    Amazon = "Amazon"
    Azure = "Azure"
    CloudStack = "CloudStack"
    CloudStack3 = "CloudStack3"
    DigitalOcean = "DigitalOcean"
    Google = "Google"
    Joyent = "Joyent"
    _Konami = "Konami" # won't show in interactive session
    OpenStack = "OpenStack"
    VirtuStream = "VirtuStream"
    ScaleMatrix = "ScaleMatrix"
    VMware = "VMware"
    WindowsAzurePack = "WindowsAzurePack"
    Other = "Other"
    UNKNOWN = "UNKNOWN"


def normalize_cloud_name(cloud_name):
    for key in [i for i in dir(CLOUD_TYPES)
                if not i.startswith("__")]:
        name = getattr(CLOUD_TYPES, key)
        if name.lower() == cloud_name.lower():
            return name
    return None


class CloudMetaData(object):
    def __init__(self, conf):
        self.conf = conf

    def get_cloud_metadata(self, key):
        return None

    def get_instance_id(self):
        _g_logger.debug("Get instance ID called")
        return None

    def get_injected_id(self):
        # The injected ID should be retrieved as follows:
        # 1) if it is available from the cloud specific metadata use that
        # 2) if in the env use that
        # 3) if the secure file has it use that
        secure_dir = self.conf.get_secure_dir()
        id_file_path = os.path.join(secure_dir, "injected_id")

        env_key = None
        if ENV_INJECTED_ID_KEY in os.environ:
            env_key = os.environ[ENV_INJECTED_ID_KEY]
            with os.fdopen(os.open(id_file_path,
                           os.O_WRONLY | os.O_CREAT,
                           0o600), "wb") as fptr:
                fptr.write(env_key.encode())
        elif os.path.exists(id_file_path):
            with open(id_file_path, "r") as fptr:
                env_key = fptr.readline()

        if env_key and env_key.strip() != "":
            return env_key.strip()
        return None

    def get_startup_script(self):
        raise exceptions.AgentNotImplementedException("get_startup_script")

    def get_ipv4_addresses(self):
        return utils.get_ipv4_addresses()

    def get_handshake_ip_address(self):
        return self.get_ipv4_addresses()

    def is_effective_cloud(self):
        try:
            tst = self.get_instance_id()
            return tst is not None
        except:
            return False
        return True

    def get_cloud_type(self):
        raise exceptions.AgentNotImplementedException("get_cloud_type")


class UnknownMetaData(CloudMetaData):
    def __init__(self, conf):
        super(UnknownMetaData, self).__init__(conf)
        _g_logger.debug("Using Unknown")

    def is_effective_cloud(self):
        return True

    def get_cloud_type(self):
        return CLOUD_TYPES.UNKNOWN


class AWSMetaData(CloudMetaData):
    def __init__(self, conf, base_url=None):
        super(AWSMetaData, self).__init__(conf)
        _g_logger.debug("Using AWS")
        if base_url is not None:
            self.base_url = base_url
        else:
            self.base_url = "http://169.254.169.254/latest/meta-data"

    def get_cloud_metadata(self, key):
        _g_logger.debug("Get metadata %s" % key)
        url = self.base_url + "/" + key
        result = _get_metadata_server_url_data(url)
        _g_logger.debug("Metadata value of %s is %s" % (key, result))
        return result

    def get_startup_script(self):
        url = "http://169.254.169.254/latest/user-data"
        _g_logger.debug("Get user-data %s" % url)
        result = _get_metadata_server_url_data(url)
        _g_logger.debug("user-data: %s" % result)
        return result

    def get_instance_id(self):
        instance_id = self.get_cloud_metadata("instance-id")
        super(AWSMetaData, self).get_instance_id()
        _g_logger.debug("Instance ID is %s" % str(instance_id))
        return instance_id

    def get_injected_id(self):
        injected_id = self.get_cloud_metadata("es:dmcm-launch-id")
        _g_logger.debug("AWS injected ID is %s" % str(injected_id))
        if injected_id:
            return injected_id
        return super(AWSMetaData, self).get_injected_id()

    def get_ipv4_addresses(self):
        # do caching
        ip_list = []
        private_ip = self.get_cloud_metadata("local-ipv4")

        if private_ip:
            ip_list.append(private_ip)

        ip_list_from_base =\
            super(AWSMetaData, self).get_ipv4_addresses()
        for ip in ip_list_from_base:
            ip_list.append(ip)

        return ip_list

    def get_handshake_ip_address(self):
        return [self.get_cloud_metadata("local-ipv4")]

    def get_cloud_type(self):
        return CLOUD_TYPES.Amazon


class DigitalOceanMetaData(CloudMetaData):
    def __init__(self, conf, base_url=None):
        super(DigitalOceanMetaData, self).__init__(conf)
        _g_logger.debug("Using Digital Ocean")
        if base_url is not None:
            self.base_url = base_url
        else:
            self.base_url = "http://169.254.169.254/metadata/v1"

    def get_cloud_metadata(self, key):
        _g_logger.debug("Get metadata %s" % key)
        url = self.base_url + "/" + key
        result = _get_metadata_server_url_data(url)
        _g_logger.debug("Metadata value of %s is %s" % (key, result))
        return result

    def get_startup_script(self):
        url = self.base_url + "/" + "user-data"
        _g_logger.debug("Get user-data %s" % url)
        result = _get_metadata_server_url_data(url)
        _g_logger.debug("user-data: %s" % result)
        return result

    def get_instance_id(self):
        instance_id = self.get_cloud_metadata("id")
        super(DigitalOceanMetaData, self).get_instance_id()
        _g_logger.debug("Instance ID is %s" % str(instance_id))
        return instance_id

    def get_ipv4_addresses(self):
        # do caching
        ip_list = []
        private_ip = self.get_cloud_metadata(
            "interfaces/public/0/ipv4/address")

        if private_ip:
            ip_list.append(private_ip)

        ip_list_from_base =\
            super(DigitalOceanMetaData, self).get_ipv4_addresses()
        for ip in ip_list_from_base:
            ip_list.append(ip)

        return ip_list

    def get_handshake_ip_address(self):
        return [self.get_cloud_metadata("interfaces/public/0/ipv4/address")]

    def get_cloud_type(self):
        return CLOUD_TYPES.DigitalOcean


class CloudStackMetaData(CloudMetaData):
    def __init__(self, conf, base_url=None):
        super(CloudStackMetaData, self).__init__(conf)
        _g_logger.debug("Using CloudStack")
        self.conf = conf
        self.base_url = base_url

    def _set_metadata_url(self):
        if not self.base_url:
            dhcp_addr = get_dhcp_ip_address(self.conf)
            self.base_url = "http://" + dhcp_addr
        _g_logger.debug("The CloudStack metadata server is " + self.base_url)

    def get_cloud_metadata(self, key):
        _g_logger.debug("Get metadata %s" % key)
        self._set_metadata_url()
        url = self.base_url + "/" + key
        result = _get_metadata_server_url_data(url)
        _g_logger.debug("Metadata value of %s is %s" % (key, result))
        return result

    def get_instance_id(self):
        self._set_metadata_url()
        instance_id = self.get_cloud_metadata("latest/instance-id")
        super(CloudStackMetaData, self).get_instance_id()
        _g_logger.debug("Instance ID is %s" % str(instance_id))
        return instance_id

    # TODO implement injected ID

    def get_cloud_type(self):
        return CLOUD_TYPES.CloudStack


class JoyentMetaData(CloudMetaData):
    def __init__(self, conf):
        super(JoyentMetaData, self).__init__(conf)
        _g_logger.debug("Using Joyent")
        self.conf = conf
        self.cmd_location = None

    def _run_command(self, cmd, key):
        cmd_args = [self.conf.system_sudo, cmd, key]
        (stdout, stderr, rc) = utils.run_command(self.conf, cmd_args)
        _g_logger.debug("Joyent metadata %d %s %s" % (rc, stdout, stderr))
        if rc != 0:
            result = None
        else:
            result = stdout.strip()
        _g_logger.debug("Metadata value from cmd %s of %s is %s" %
                        (cmd, key, str(result)))
        return (rc, result)

    def get_cloud_metadata(self, key):
        _g_logger.debug("Get metadata %s" % key)

        if self.cmd_location is not None:
            (rc, result) = self._run_command(self.cmd_location, key)
        else:
            cmd_possible_locations = [
                "/usr/sbin/mdata-get", "/lib/smartdc/mdata-get"]
            for cmd in cmd_possible_locations:
                (rc, result) = self._run_command(cmd, key)
                if rc == 0:
                    self.cmd_location = cmd
                    break
        return result

    def get_instance_id(self):
        # XXX TODO check to instance id, this is injected
        instance_id = self.get_cloud_metadata("es:dmcm-launch-id")
        super(JoyentMetaData, self).get_instance_id()
        _g_logger.debug("Instance ID is %s" % str(instance_id))
        return instance_id

    def get_injected_id(self):
        injected_id = self.get_cloud_metadata("es:dmcm-launch-id")
        _g_logger.debug("Injected ID is %s" % str(injected_id))
        if injected_id:
            return injected_id
        return super(JoyentMetaData, self).get_injected_id()

    def get_startup_script(self):
        return self.get_cloud_metadata("user-script")

    def get_cloud_type(self):
        return CLOUD_TYPES.Joyent


class GCEMetaData(CloudMetaData):
    def __init__(self, conf, base_url=None):
        super(GCEMetaData, self).__init__(conf)
        _g_logger.debug("Using GCE")
        if base_url is not None:
            self.base_url = base_url
        else:
            self.base_url =\
                "http://metadata.google.internal/computeMetadata/v1"

    def get_cloud_metadata(self, key):
        _g_logger.debug("Get metadata %s" % key)
        url = self.base_url + "/" + key
        result = _get_metadata_server_url_data(
            url, headers=[("Metadata-Flavor", "Google")])
        _g_logger.debug("Metadata value of %s is %s" % (key, result))
        return result

    def get_startup_script(self):
        return self.get_cloud_metadata("instance/attributes/startup-script")

    def get_instance_id(self):
        gce_id = self.get_cloud_metadata(
            "instance/id")
        if gce_id is None:
            return None
        md_hostname = self.get_cloud_metadata(
            "instance/hostname")
        if md_hostname is None:
            _g_logger.warn("GCE hostname metadata value is None")
            return None
        server_name = md_hostname.split('.', 1)[0]
        super(GCEMetaData, self).get_instance_id()
        instance_id = server_name + "_" + gce_id
        _g_logger.debug("Instance ID is %s" % str(instance_id))
        return instance_id

    def get_injected_id(self):
        injected_id = self.get_cloud_metadata(
            "instance/attributes/es-dmcm-launch-id")
        _g_logger.debug("Instance ID is %s" % str(injected_id))
        if injected_id:
            return injected_id
        return super(GCEMetaData, self).get_injected_id()

    def get_handshake_ip_address(self):
        return utils.get_ipv4_addresses()

    def get_cloud_type(self):
        return CLOUD_TYPES.Google


class AzureMetaData(CloudMetaData):
    def __init__(self, conf, base_url=None):
        super(AzureMetaData, self).__init__(conf)
        _g_logger.debug("Using Azure")

    def get_instance_id(self):
        hostname = socket.gethostname()
        if not hostname:
            return None
        ha = hostname.split(".")
        return "%s:%s:%s" % (ha[0], ha[0], ha[0])

    def is_effective_cloud(self):
        return os.path.exists("/var/lib/waagent/ovf-env.xml")

    def get_cloud_type(self):
        return CLOUD_TYPES.Azure


class OpenStackMetaData(CloudMetaData):
    def __init__(self, conf, base_url=None):
        super(OpenStackMetaData, self).__init__(conf)
        _g_logger.debug("Using OpenStack")
        if base_url is not None:
            self.base_url = base_url
        else:
            self.base_url =\
                "http://169.254.169.254/openstack/2012-08-10/meta_data.json"

    def get_cloud_metadata(self, key):
        _g_logger.debug("Get OpenStack metadata %s" % key)

        try:
            json_data = _get_metadata_server_url_data(self.base_url)
            jdict = json.loads(json_data)
            return jdict[key]
        except:
            _g_logger.exception("Failed to get the OpenStack metadata")
            return None

    def get_startup_script(self):
        url = "http://169.254.169.254/openstack/2012-08-10/user_data"
        return _get_metadata_server_url_data(url)

    def get_instance_id(self):
        return self.get_cloud_metadata("uuid")

    # TODO implement injected ID

    def get_cloud_type(self):
        return CLOUD_TYPES.OpenStack


class KonamiMetaData(CloudMetaData):
    def __init__(self, conf):
        super(KonamiMetaData, self).__init__(conf)
        _g_logger.debug("Using Konami")

    def get_cloud_metadata(self, key):
        env_str = "DCM_KONAMI_%s" % key
        try:
            return os.environ[env_str]
        except:
            return None

    def get_instance_id(self):
        return self.get_cloud_metadata("INSTANCE_ID")

    def get_injected_id(self):
        injected_id = self.get_cloud_metadata("INJECTED_ID")
        if injected_id:
            return injected_id
        return super(KonamiMetaData, self).get_injected_id()

    def get_handshake_ip_address(self):
        private = self.get_cloud_metadata("PRIVATE_IP")
        public = self.get_cloud_metadata("PUBLIC_IP")
        return [private, public]

    def get_cloud_type(self):
        return CLOUD_TYPES._Konami


def set_metadata_object(conf):
    cloud_name = normalize_cloud_name(conf.cloud_type)

    if cloud_name == CLOUD_TYPES.Amazon:
        meta_data_obj = AWSMetaData(conf, base_url=conf.cloud_metadata_url)
    elif cloud_name == CLOUD_TYPES.Joyent:
        meta_data_obj = JoyentMetaData(conf)
    elif cloud_name == CLOUD_TYPES.Google:
        meta_data_obj = GCEMetaData(conf, base_url=conf.cloud_metadata_url)
    elif cloud_name == CLOUD_TYPES.Azure:
        meta_data_obj = AzureMetaData(conf)
    elif cloud_name == CLOUD_TYPES.WindowsAzurePack:
        meta_data_obj = UnknownMetaData(conf)
    elif cloud_name == CLOUD_TYPES.OpenStack:
        meta_data_obj = OpenStackMetaData(conf,
                                          base_url=conf.cloud_metadata_url)
    elif cloud_name == CLOUD_TYPES.CloudStack or \
            cloud_name == CLOUD_TYPES.CloudStack3:
        meta_data_obj = CloudStackMetaData(
            conf, base_url=conf.cloud_metadata_url)
    elif cloud_name == CLOUD_TYPES.DigitalOcean:
        meta_data_obj = DigitalOceanMetaData(
            conf, base_url=conf.cloud_metadata_url)
    elif cloud_name == CLOUD_TYPES._Konami:
        meta_data_obj = KonamiMetaData(conf)
    elif cloud_name == CLOUD_TYPES.Other:
        meta_data_obj = UnknownMetaData(conf)
    else:
        meta_data_obj = CloudMetaData(conf)

    _g_logger.debug("Metadata comes from " + str(meta_data_obj))

    conf.meta_data_object = meta_data_obj


def guess_effective_cloud(conf):
    # it is important to clouds that clone AWS behavior but also have their
    # own behavior before AWS (eg: OpenStack).  Some clouds cannot be
    # guessed (eg: Azure)
    ordered_list_of_clouds = [
        JoyentMetaData(conf),
        OpenStackMetaData(conf),
        CloudStackMetaData(conf),
        AWSMetaData(conf),
        GCEMetaData(conf),
        DigitalOceanMetaData(conf),
        AzureMetaData(conf),
        UnknownMetaData(conf)
    ]
    for md in ordered_list_of_clouds:
        if md.is_effective_cloud():
            _g_logger.info("Using cloud " + md.get_cloud_type())
            return md.get_cloud_type()
    return CLOUD_TYPES.UNKNOWN


def get_dhcp_ip_address(conf):
    (stdout, stderr, rc) = utils.run_script(conf, "getDhcpAddress", [])
    if rc != 0:
        raise exceptions.AgentExecutableException(
            "getDhcpAddress", rc, stdout, stderr)

    dhcp_address = stdout.strip()
    return dhcp_address


def _get_metadata_server_url_data(url, timeout=10, headers=None):
    if not url:
        _g_logger.debug("URL is  %s" % url)
        return None

    _g_logger.debug("Attempting to get metadata at %s" % url)
    u_req = urllib.request.Request(url)
    u_req.add_header("Content-Type", "application/x-www-form-urlencoded")
    u_req.add_header("Connection", "Keep-Alive")
    u_req.add_header("Cache-Control", "no-cache")
    if headers:
        for (h, v) in headers:
            u_req.add_header(h, v)

    try:
        response = urllib.request.urlopen(u_req, timeout=timeout)
    except urllib.error.URLError as ex:
        _g_logger.debug("URL error message is %s" % ex.reason)
        return None
    if response.code != 200:
        _g_logger.debug("URL response code is %s" % str(response.code))
        return None
    data = response.read().decode()
    return data
