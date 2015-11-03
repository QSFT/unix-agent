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
import os
import subprocess
from setuptools import setup, find_packages
import sys


def get_git_version():
    try:
        basedir = os.path.dirname(os.path.expanduser(sys.argv[0]))
        if not basedir.strip():
            basedir = None
        p = subprocess.Popen("git describe --abbrev=0 --tags",
                             cwd=basedir,
                             shell=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (stdoutdata, stderrdata) = p.communicate()
        rc = p.wait()
        if rc != 0:
            semversion = "unknown"
        else:
            semversion = stdoutdata.decode().strip()

        p = subprocess.Popen("git rev-parse HEAD",
                             cwd=basedir,
                             shell=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (stdoutdata, stderrdata) = p.communicate()
        rc = p.wait()
        if rc != 0:
            return ""
        version = "-" + stdoutdata.decode().strip()

        p = subprocess.Popen("git diff",
                             cwd=basedir,
                             shell=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (stdoutdata, stderrdata) = p.communicate()
        rc = p.wait()
        if rc == 0 and stdoutdata:
            version = version + "-diff"
        return semversion + version
    except Exception:
        return ""


setup(name='dcm-agent',
      version=get_git_version(),
      description="Agent for DCM run VMs",
      author="Dell Software Group",
      author_email="support@enstratius.com",
      url="http://www.enstratius.com/",
      packages=find_packages(),
      entry_points={
          'console_scripts': [
              "dcm-agent=dcm.agent.cmd.service:main",
              "dcm-agent-scrubber=dcm.agent.cmd.scrubber:main",
              "dcm-agent-configure=dcm.agent.cmd.configure:main",
              "dcm-agent-gen-docs=dcm.agent.cmd.gen_docs:main",
              "dcm-agent-add-plugins=dcm.agent.cmd.add_plugin:main"
          ],
      },
      include_package_data=True,
      install_requires=["pyyaml == 3.10",
                        "ws4py == 0.3.4",
                        "psutil == 2.2.1",
                        "netifaces == 0.10.4",
                        "clint == 0.4.1",
                        "watchdog == 0.8.3"],

      package_data={"dcm.agent": ["dcm/agent/scripts/*",
                                  "dcm/agent/etc/*"],
                    "dcm.agent.tests": ["dcm/agent/tests/etc/*"]},

      classifiers=[
          "Development Status :: 4 - Beta",
          "Environment :: Console",
          "Intended Audience :: System Administrators",
          "License :: OSI Approved :: Apache Software License",
          "Operating System :: POSIX :: Linux",
          "Programming Language :: Python",
          "Topic :: System :: Clustering",
          "Topic :: System :: Distributed Computing",
          "Programming Language :: Python :: 3 :: Only"
      ]
      )
