#  ========= CONFIDENTIAL =========
#
#  Copyright (C) 2010-2014 Dell, Inc. - ALL RIGHTS RESERVED
#
#  ======================================================================
#   NOTICE: All information contained herein is, and remains the property
#   of Dell, Inc. The intellectual and technical concepts contained herein
#   are proprietary to Dell, Inc. and may be covered by U.S. and Foreign
#   Patents, patents in process, and are protected by trade secret or
#   copyright law. Dissemination of this information or reproduction of
#   this material is strictly forbidden unless prior written permission
#   is obtained from Dell, Inc.
#  ======================================================================

import os
from dcm.agent import exceptions
import dcm.agent.utils as utils
import dcm.agent.jobs.direct_pass as direct_pass


class AddUser(direct_pass.DirectPass):

    protocol_arguments = {
        "userId": ("The new unix account name to be created", True, str),
        "firstName": ("The user's first name", True, str),
        "lastName": ("The user's last name", True, str),
        "authentication": ("The user's ssh public key", True, str),
        "administrator": ("A string that is either 'true' or 'false' "
                          "which indicates if the new user should have"
                          "ssh access", True, str)
    }

    def __init__(self, conf, job_id, items_map, name, arguments):
        super(AddUser, self).__init__(
            conf, job_id, items_map, name, arguments)

        try:
            self.ordered_param_list = [arguments["userId"],
                                       arguments["userId"],
                                       arguments["firstName"],
                                       arguments["lastName"],
                                       arguments["administrator"],
                                       arguments["password"]]
            self.ssh_public_key = arguments["authentication"]
        except KeyError as ke:
            raise exceptions.AgentPluginConfigException(
                "The plugin %s requires the option %s" % (name, ke.message))

        if not arguments['password']:
            self.arguments["password"] = utils.generate_password()

    def run(self):
        key_file = os.path.join(
            self.conf.storage_temppath, self.arguments["userId"] + ".pub")

        try:
            if self.ssh_public_key:
                with open(key_file, "w") as f:
                    f.write(self.ssh_public_key)
            return super(AddUser, self).run()
        finally:
            if os.path.exists(key_file):
                os.remove(key_file)


def load_plugin(conf, job_id, items_map, name, arguments):
    return AddUser(conf, job_id, items_map, name, arguments)
