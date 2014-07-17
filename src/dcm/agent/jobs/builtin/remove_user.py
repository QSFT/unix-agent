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
import dcm.agent.jobs.direct_pass as direct_pass


class RemoveUser(direct_pass.DirectPass):

    protocol_arguments = {
        "userId":
        ("The unix account name of the user to remove",
         True, str)
    }

    def __init__(self, conf, job_id, items_map, name, arguments):
        super(RemoveUser, self).__init__(
            conf, job_id, items_map, name, arguments)
        self.ordered_param_list = [self.args.userId]


def load_plugin(conf, job_id, items_map, name, arguments):
    return RemoveUser(conf, job_id, items_map, name, arguments)