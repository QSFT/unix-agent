import collections
import os
import unittest
from nose.plugins import skip
import uuid

import dcmdocker.utils as docker_utils
import dcmdocker.import_image as import_image
import dcmdocker.delete_image as delete_image
import dcmdocker.list_containers as list_containers
import dcmdocker.create_container as create_container
import dcmdocker.start_container as start_container
import dcmdocker.stop_container as stop_container
import dcmdocker.top_container as top_container
import dcmdocker.restart_container as restart_container
import dcmdocker.delete_container as delete_container
import dcmdocker.get_container_details as get_container_details

class TestDockerContainer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        FakeConf = collections.namedtuple(
            "FakeConf", ["docker_base_url", "docker_version", "docker_timeout"])
        cls.conf = FakeConf('http+unix://var/run/docker.sock', "1.12", 60)

        if 'DCM_DOCKER_IMAGE_LOCATION' not in os.environ:
            raise skip.SkipTest('skipping')

        image_location = os.environ['DCM_DOCKER_IMAGE_LOCATION']
        repo = "agenttest" + str(uuid.uuid4()).split("-")[0]
        arguments = {
            "src": image_location,
            "repository": repo,
            "tag": "1.0"
        }
        plugin = import_image.ImportImage(
            cls.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        cls.image_id = reply_obj['status']

    @classmethod
    def tearDownClass(cls):
        arguments = {"name": cls.image_id}
        plugin = delete_image.DeleteImages(
            cls.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']

    def setUp(self):
        """
        :return: a list of the files in src/dcm/agent/jobs/builtin
        """
        pass

    def tearDown(self):
        pass

    def test_container_list(self):
        arguments = {}
        plugin = list_containers.DockerListContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

    def test_create_delete_container(self):
        arguments = {
            "image": self.image_id,
            "command": "/bin/sleep 60"}
        plugin = create_container.DockerCreateContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        container_id = reply_obj['Id']

        arguments = {
            "container": container_id
        }
        plugin = delete_container.DeleteContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

    def test_create_inspect_list_list_all_delete_container(self):
        arguments = {
            "image": self.image_id,
            "command": "/bin/sleep 60"}
        plugin = create_container.DockerCreateContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        container_id = reply_obj['Id']

        arguments = {
            "container": container_id
        }
        plugin = get_container_details.GetContainerDetails(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        self.assertEqual(reply_obj['Image'], self.image_id)
        self.assertFalse(reply_obj['State']['Running'])

        arguments = {}
        plugin = list_containers.DockerListContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']

        found_cont = None
        for cont in reply_obj:
            if cont['Id'] == container_id:
                found_cont = cont
        self.assertIsNone(found_cont)

        arguments = {'all': True}
        plugin = list_containers.DockerListContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']

        found_cont = None
        for cont in reply_obj:
            if cont['Id'] == container_id:
                found_cont = cont
        self.assertIsNotNone(found_cont)

        arguments = {
            "container": container_id
        }
        plugin = delete_container.DeleteContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

    def test_create_start_top_stop_delete_container(self):
        arguments = {
            "image": self.image_id,
            "command": "/bin/sleep 60"}
        plugin = create_container.DockerCreateContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        container_id = reply_obj['Id']

        print "Container ID " + container_id
        arguments = {
            "container": container_id
        }
        plugin = start_container.StartContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

        plugin = top_container.TopContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        print "top"
        print reply

        plugin = stop_container.StopContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        arguments = {
            "container": container_id
        }
        plugin = delete_container.DeleteContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

    def test_create_start_list_inspect_stop_delete_container(self):
        arguments = {
            "image": self.image_id,
            "command": "/bin/sleep 60"}
        plugin = create_container.DockerCreateContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        container_id = reply_obj['Id']

        arguments = {
            "container": container_id
        }
        plugin = start_container.StartContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

        arguments = {
            "container": container_id
        }
        plugin = get_container_details.GetContainerDetails(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        self.assertEqual(reply_obj['Image'], self.image_id)
        self.assertTrue(reply_obj['State']['Running'])

        arguments = {}
        plugin = list_containers.DockerListContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']

        found_cont = None
        for cont in reply_obj:
            if cont['Id'] == container_id:
                found_cont = cont
        self.assertIsNotNone(found_cont)

        arguments = {
            "container": container_id
        }
        plugin = stop_container.StopContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        arguments = {
            "container": container_id
        }
        plugin = delete_container.DeleteContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

    def test_create_start_delete_container(self):
        arguments = {
            "image": self.image_id,
            "command": "/bin/sleep 60"}
        plugin = create_container.DockerCreateContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        reply_obj = reply['reply_object']
        container_id = reply_obj['Id']

        arguments = {
            "container": container_id
        }
        plugin = start_container.StartContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

        arguments = {
            "container": container_id,
            "force": True
        }
        plugin = delete_container.DeleteContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

    def test_create_start_restart_delete_container(self):
        arguments = {
            "image": self.image_id,
            "command": "/bin/sleep 60"}
        plugin = create_container.DockerCreateContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

        reply_obj = reply['reply_object']
        container_id = reply_obj['Id']
        arguments = {
            "container": container_id
        }
        plugin = start_container.StartContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

        plugin = restart_container.RestartContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

        plugin = stop_container.StopContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()
        arguments = {
            "container": container_id
        }
        plugin = delete_container.DeleteContainer(
            self.conf, "400", {}, "test", arguments)
        reply = plugin.run()

