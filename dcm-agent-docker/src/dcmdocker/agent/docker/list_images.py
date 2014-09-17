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

import dcm.agent.docker.utils as docker_utils


class ListImages(docker_utils.DockerJob):

    protocol_arguments = {
        "name": ("", False, str, None),
        "quiet": ("", False, bool, False),
        "all": ("", False, bool, False),
        "viz": ("", False, bool, False)
    }

    def __init__(self, conf, job_id, items_map, name, arguments):
        super(ListImages, self).__init__(
            conf, job_id, items_map, name, arguments)

    def run(self):
        out = self.docker_conn.images(name=self.args.name,
                                      quiet=self.args.quiet,
                                      all=self.args.all,
                                      viz=self.args.viz)
        reply_doc = {
            "return_code": 0,
            "reply_type": "docker_image_array",
            "reply_object": out
        }
        return reply_doc


def load_plugin(conf, job_id, items_map, name, arguments):
    return ListImages(conf, job_id, items_map, name, arguments)
